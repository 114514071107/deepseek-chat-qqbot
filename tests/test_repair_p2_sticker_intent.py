import tempfile
from types import SimpleNamespace
import unittest
from repair_pipeline_support import load_pipeline, ResultChain
from test_repair_session_scope import ScopeEvent
from task_runtime import work_context
from qq_delivery import DeliveryResult, failure


class QuotedStickerIntent(unittest.IsolatedAsyncioTestCase):
    async def test_quoted_preamble_protocol_and_tool_cover_delivery_outcomes(self):
        for intent in ('protocol', 'tool'):
            for quote in ('“得意”', '"得意"', '「得意」'):
                for outcome in ('accepted', 'failed', 'unknown'):
                    with self.subTest(intent=intent, quote=quote, outcome=outcome), tempfile.TemporaryDirectory() as tmp:
                        obj, ns = load_pipeline(tmp, names=('capture', 'send_sticker', '_clear_text_result', '_set_first_bubble_result'))
                        self.addAsyncCleanup(obj.runtime.stop)
                        ns['random'] = SimpleNamespace(random=lambda: 1)
                        ns['_pick_sticker'] = lambda query: dict(pack='fixture', rel='happy.png', caption='fixture')
                        sent = []
                        async def sticker(*args):
                            sent.append('sticker')
                            return DeliveryResult('accepted', message_id='image') if outcome == 'accepted' else failure(outcome, 'upload', 'media')
                        async def text(target, chain):
                            sent.append('text')
                            return DeliveryResult('accepted', message_id='fallback')
                        obj._send_sticker_row = sticker; obj._send = text
                        event = ScopeEvent(); scope = obj._scope(event)
                        token = obj.runtime.begin(scope.key); event.set_extra('_dsh_work', token)
                        with work_context(token, event):
                            if intent == 'tool': await obj.send_sticker(event, '得意', only_sticker=True)
                            body = f'给你一个{quote}的表情' + ('\n动作：仅表情 得意' if intent == 'protocol' else '')
                            await obj.capture(event, SimpleNamespace(result_chain=ResultChain(body)))
                            self.assertTrue(event.get_extra('_dsh_reply_plan').sticker_only)
                            await obj._complete_reply(event)
                        self.assertEqual(sent, ['sticker', 'text'] if outcome == 'failed' else ['sticker'])

    async def test_literal_actions_are_not_erased_even_with_tool_intent(self):
        for literal in ('```text\n动作：仅表情 得意\n```', '    动作：仅表情 得意',
                        '\t动作：仅表情 得意', '> 动作：仅表情 得意',
                        '“动作：仅表情 得意”', '"动作：仅表情 得意"',
                        '“原文：\n动作：仅表情 得意\n”'):
            with self.subTest(literal=literal), tempfile.TemporaryDirectory() as tmp:
                obj, ns = load_pipeline(tmp)
                self.addAsyncCleanup(obj.runtime.stop)
                looked_up = []; ns['_pick_sticker'] = lambda query: looked_up.append(query)
                event = ScopeEvent(); event.set_extra('_dsh_sticker_only', True)
                await obj.capture(event, SimpleNamespace(result_chain=ResultChain(literal)))
                plan = event.get_extra('_dsh_reply_plan')
                self.assertEqual(plan.bubbles, [literal])
                self.assertFalse(plan.sticker_only)
                self.assertEqual(looked_up, [])


if __name__ == '__main__': unittest.main()
