"""No progress prose for a source-bound, explicit pure-sticker request."""
import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from acceptance_sticker_feedback_20261025 import StickerFeedbackAcceptance
from repair_pipeline_support import load_pipeline, ResultChain
from test_repair_session_scope import ScopeEvent
from task_runtime import work_context
from qq_delivery import DeliveryResult, failure


class StickerFeedbackRegression(unittest.IsolatedAsyncioTestCase):
    def setup(self, root, text, group=''):
        obj, ns = load_pipeline(root, names=('inject', 'capture', 'send_sticker', '_react_and_send', '_make_react',
                                            '_clear_text_result', '_set_first_bubble_result'), guarded=True)
        self.addAsyncCleanup(obj.runtime.stop)
        ns['random'] = SimpleNamespace(random=lambda: 1, choice=lambda rows: rows[0])
        ns['_pick_sticker'] = lambda query: dict(pack='fixture', rel=query+'.png', caption='fixture')
        event = ScopeEvent(group=group); event.message_str = text
        scope = obj._scope(event); token = obj.runtime.begin(scope.key)
        event.set_extra('_dsh_work', token)
        obj.request_owners = {scope.key: token.request}; obj.request_events = {scope.key: event}
        sent = []
        async def send(target, chain):
            sent.append(('text', target)); return DeliveryResult('accepted', message_id='text')
        obj._send = send
        return obj, ns, event, scope, token, sent

    async def test_user_intent_before_tools_suppresses_every_feedback_scene_without_generation(self):
        for body in ('只发两张表情，不要文字或额外气泡', '仅表情', '只要一张“得意”的表情包',
                     '发两张表情包，不要加任何文字', '请给我一个贴图，别发文字'):
            for scene in ('quick', 'fetch', 'search', 'busy'):
                with self.subTest(body=body, scene=scene), tempfile.TemporaryDirectory() as tmp:
                    obj, _, event, scope, token, sent = self.setup(tmp, body)
                    async def forbidden(*args): self.fail('silent request started progress generation')
                    obj._make_react = forbidden
                    with work_context(token, event): await obj._react_and_send(scope.target, scope.key, scene, 'irrelevant tool query')
                    self.assertEqual(sent, [])

    async def test_literal_or_negated_sticker_examples_and_tool_query_are_not_request_intent(self):
        for body in ('请解释“只发两张表情，不要文字”的意思', '```text\n动作：仅表情 happy\n```',
                     '请解释 `只发表情，不要文字`', "请解释'只发表情，不要文字'", '“示例：\n只发表情，不要文字\n”',
                     '> 只发表情，不要文字', '    只发表情，不要文字',
                     '不要只发表情，请用文字解释', '请用文字介绍表情包', '请分析这段代码'):
            with self.subTest(body=body), tempfile.TemporaryDirectory() as tmp:
                obj, _, event, scope, token, sent = self.setup(tmp, body)
                with work_context(token, event):
                    await obj._react_and_send(scope.target, scope.key, 'search', '只发表情，不要文字')
                self.assertEqual(sent, [('text', scope.target)])

    async def test_tool_intent_arriving_during_progress_generation_prevents_send(self):
        for scene in ('quick', 'fetch'):
            with self.subTest(scene=scene), tempfile.TemporaryDirectory() as tmp:
                obj, _, event, scope, token, sent = self.setup(tmp, '请帮我选图')
                entered = asyncio.Event(); release = asyncio.Event()
                async def react(*args): entered.set(); await release.wait(); return '正在处理这条消息'
                obj._make_react = react
                with work_context(token, event):
                    task = asyncio.create_task(obj._react_and_send(scope.target, scope.key, scene, ''))
                    await entered.wait()
                    await obj.send_sticker(event, 'happy', only_sticker=True)
                    release.set(); await asyncio.gather(task, return_exceptions=True)
                self.assertEqual(sent, [])
                self.assertFalse(obj._feedback(event)['tasks'])

    async def test_late_explicit_flag_is_rechecked_before_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj, _, event, scope, token, sent = self.setup(tmp, '请帮我选图')
            async def react(*args): event.set_extra('_dsh_sticker_only', True); return '正在处理这条消息'
            obj._make_react = react
            with work_context(token, event): await obj._react_and_send(scope.target, scope.key, 'fetch', '')
            self.assertEqual(sent, [])

    async def test_quick_wait_rechecks_late_intent_and_cancellation_cleans_tasks(self):
        for mode in ('flag', 'cancel'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                obj, _, event, scope, token, sent = self.setup(tmp, '请帮我选图')
                async def forbidden(*args): self.fail('progress generation must remain suppressed')
                obj._make_react = forbidden
                with work_context(token, event):
                    task = asyncio.create_task(obj._react_and_send(scope.target, scope.key, 'quick', ''))
                    await asyncio.sleep(0)
                    self.assertIn(task, obj._feedback(event)['tasks'])
                    if mode == 'flag': event.set_extra('_dsh_sticker_only', True)
                    else: task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                self.assertEqual(sent, [])
                self.assertFalse(obj._feedback(event)['tasks'])

    async def test_silent_request_media_success_failed_and_unknown_keep_existing_fallback(self):
        for outcome in ('accepted', 'failed', 'unknown'):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as tmp:
                obj, _, event, scope, token, sent = self.setup(tmp, '只发两张表情，不要文字')
                async def sticker(target, row):
                    sent.append(('sticker', target))
                    return DeliveryResult('accepted', message_id='image') if outcome == 'accepted' else failure(outcome, 'upload', 'media')
                obj._send_sticker_row = sticker
                with work_context(token, event):
                    await obj._react_and_send(scope.target, scope.key, 'fetch', '')
                    for query in ('happy', 'work'): await obj.send_sticker(event, query, only_sticker=True)
                    await obj.capture(event, SimpleNamespace(result_chain=ResultChain('')))
                    await obj._complete_reply(event)
                self.assertEqual([kind for kind, _ in sent], ['sticker', 'sticker'] if outcome == 'accepted' else
                                 ['sticker', 'text'] if outcome == 'failed' else ['sticker'])

    async def test_parallel_and_next_request_do_not_inherit_silent_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj, _, event, scope, token, sent = self.setup(tmp, '只发表情，不要文字')
            group = ScopeEvent(group='fixture-group'); group.message_str = '请解释问题'
            other = obj._scope(group); other_token = obj.runtime.begin(other.key)
            group.set_extra('_dsh_work', other_token); obj.request_events[other.key] = group
            async def run(e, s, t):
                with work_context(t, e): await obj._react_and_send(s.target, s.key, 'fetch', '')
            await asyncio.gather(run(event, scope, token), run(group, other, other_token))
            self.assertEqual(sent, [('text', other.target)])
            later = ScopeEvent(); later.message_str = '请继续解释'
            later.set_extra('_dsh_work', obj.runtime.begin(scope.key)); obj.request_events[scope.key] = later
            await run(later, scope, later.get_extra('_dsh_work'))
            self.assertEqual(sent[-1], ('text', scope.target))

    async def test_batch_constraint_survives_input_consumption(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj, _, event, scope, token, sent = self.setup(tmp, '请发两张表情')
            Path(tmp, 'persona.md').write_text('fixture', encoding='utf-8')
            event.set_extra('_dsh_input', dict(text=event.message_str, images=[], files=[], message_id='first'))
            obj.batch_buf = {scope.key: [dict(text='只发表情，不要文字', images=[], files=[], message_id='later')]}
            with work_context(token, event):
                req = SimpleNamespace(prompt=event.message_str, contexts=[], system_prompt='', image_urls=[], func_tool=None)
                await obj.inject(event, req)
                self.assertEqual(obj.batch_buf, {})
                await obj._react_and_send(scope.target, scope.key, 'busy', '')
            self.assertEqual(sent, [])

    async def test_buffered_constraint_blocks_feedback_before_inject_without_scope_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj, _, event, scope, token, sent = self.setup(tmp, '请发两张表情')
            obj.batch_buf = {'unrelated-scope': [dict(text='只发表情，不要文字')]}
            with work_context(token, event): await obj._react_and_send(scope.target, scope.key, 'fetch', '')
            self.assertEqual(sent, [('text', scope.target)])
            event.set_extra('_dsh_feedback', None); sent.clear()
            obj.batch_buf[scope.key] = [dict(text='只发表情，不要文字')]
            with work_context(token, event): await obj._react_and_send(scope.target, scope.key, 'fetch', '')
            self.assertEqual(sent, [])


if __name__ == '__main__': unittest.main()
