"""Tool selection and protocol fallback are alternative routes for one reply."""
import tempfile
from types import SimpleNamespace
import unittest

from acceptance_real_qq_20261025_duplicate import SingleStickerAcceptance
from repair_pipeline_support import load_pipeline, ResultChain
from test_repair_session_scope import ScopeEvent
from task_runtime import work_context
from qq_delivery import DeliveryResult, failure


class StickerSelectionRegression(unittest.IsolatedAsyncioTestCase):
    async def reply(self, queries, body, *, only=True, outcome='accepted', missing=(), group='', user_text='只发一张表情'):
        with tempfile.TemporaryDirectory() as tmp:
            obj, ns = load_pipeline(tmp, names=('capture', 'send_sticker', '_clear_text_result', '_set_first_bubble_result'))
            self.addAsyncCleanup(obj.runtime.stop)
            ns['random'] = SimpleNamespace(random=lambda: 1)
            picked = []
            def pick(query):
                picked.append(query)
                return None if query in missing else dict(pack='fixture', rel=query+'.png', caption='fixture')
            ns['_pick_sticker'] = pick
            sent = []
            async def sticker(target, row):
                sent.append(('sticker', row['rel'], target))
                return DeliveryResult('accepted', message_id=f'image{len(sent)}') if outcome == 'accepted' else failure(outcome, 'upload', 'media')
            async def text(target, chain):
                sent.append(('text', ''.join(c.text for c in chain.chain if hasattr(c, 'text')), target))
                return DeliveryResult('accepted', message_id=f'text{len(sent)}')
            obj._send_sticker_row = sticker; obj._send = text
            event = ScopeEvent(group=group); event.message_str = user_text
            scope = obj._scope(event); token = obj.runtime.begin(scope.key)
            event.set_extra('_dsh_work', token)
            obj.request_owners = {scope.key: token.request}; obj.request_events = {scope.key: event}
            with work_context(token, event):
                for query in queries: await obj.send_sticker(event, query, only_sticker=only)
                await obj.capture(event, SimpleNamespace(result_chain=ResultChain(body)))
                plan = event.get_extra('_dsh_reply_plan')
                planned = [row['rel'] for row in plan.stickers]
                await obj._complete_reply(event)
                await obj._complete_reply(event)  # repeated completion must not resend
            self.assertNotIn(scope.key, obj.pending_sticker)
            self.assertTrue(all(target == scope.target for _, _, target in sent))
            return planned, [(kind, content) for kind, content, _ in sent], picked

    async def test_protocol_only_and_failed_tool_lookup_still_select_one(self):
        for queries in ([], ['missing']):
            for body in ('动作：仅表情 happy', '给你一个“得意”的表情\n动作：仅表情 happy'):
                with self.subTest(queries=queries, body=body):
                    planned, sent, _ = await self.reply(queries, body, missing=('missing',))
                    self.assertEqual(planned, ['happy.png'])
                    self.assertEqual(sent, [('sticker', 'happy.png')])

    async def test_tool_wins_same_or_different_action_with_or_without_preamble(self):
        for action in ('happy', 'work'):
            for preamble in ('', '给你一个“得意”的表情\n'):
                for group in ('', 'fixture-group'):
                    with self.subTest(action=action, preamble=preamble, group=group):
                        planned, sent, picked = await self.reply(['happy'], preamble+'动作：仅表情 '+action, group=group)
                        self.assertEqual(planned, ['happy.png'])
                        self.assertEqual(sent, [('sticker', 'happy.png')])
                        self.assertEqual(picked, ['happy'])

    async def test_explicit_multiple_tool_choices_are_preserved_without_extra_action_image(self):
        for queries in (['happy', 'work'], ['happy', 'happy']):
            for body in ('', '动作：仅表情 extra', '给你两张\n动作：仅表情 extra'):
                with self.subTest(queries=queries, body=body):
                    planned, sent, picked = await self.reply(queries, body, user_text='明确发两张表情，可以重复')
                    expected = [query+'.png' for query in queries]
                    self.assertEqual(planned, expected)
                    self.assertEqual(sent, [('sticker', image) for image in expected])
                    self.assertEqual(picked, queries)

    async def test_mixed_text_and_sticker_also_reconciles_both_routes(self):
        planned, sent, picked = await self.reply(['happy'], '正文\n动作：表情 work', only=False)
        self.assertEqual(planned, ['happy.png'])
        self.assertEqual(sent, [('text', '正文'), ('sticker', 'happy.png')])
        self.assertEqual(picked, ['happy'])

    async def test_reconciled_single_image_preserves_safe_failure_and_unknown_behavior(self):
        for outcome in ('failed', 'unknown'):
            with self.subTest(outcome=outcome):
                planned, sent, _ = await self.reply(['happy'], '动作：仅表情 work', outcome=outcome)
                self.assertEqual(planned, ['happy.png'])
                self.assertEqual([kind for kind, _ in sent], ['sticker', 'text'] if outcome == 'failed' else ['sticker'])


if __name__ == '__main__': unittest.main()
