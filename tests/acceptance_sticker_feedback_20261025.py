"""QS25 G02: pure-sticker requests must not receive progress text."""
import tempfile
import unittest
from types import SimpleNamespace
from repair_pipeline_support import load_pipeline, ResultChain
from test_repair_session_scope import ScopeEvent
from task_runtime import work_context
from qq_delivery import DeliveryResult


class StickerFeedbackAcceptance(unittest.IsolatedAsyncioTestCase):
    async def run_reply(self, pure, early_intent=False):
        with tempfile.TemporaryDirectory() as tmp:
            obj, ns = load_pipeline(tmp, names=('capture', 'send_sticker', '_react_and_send', '_make_react', '_clear_text_result', '_set_first_bubble_result'))
            self.addAsyncCleanup(obj.runtime.stop)
            ns['random'] = SimpleNamespace(random=lambda: 1, choice=lambda rows: rows[0])
            ns['_pick_sticker'] = lambda query: dict(pack='fixture', rel=query+'.png', caption='fixture')
            event = ScopeEvent(group='fixture-group')
            event.message_str = '只发两张表情，不要文字或额外气泡' if pure else '请回答这个问题'
            scope = obj._scope(event)
            token = obj.runtime.begin(scope.key)
            event.set_extra('_dsh_work', token)
            obj.request_owners = {scope.key: token.request}
            obj.request_events = {scope.key: event}
            sent = []

            async def text(target, chain):
                sent.append('text')
                return DeliveryResult('accepted', message_id=str(len(sent)))

            async def sticker(target, row):
                sent.append('sticker')
                return DeliveryResult('accepted', message_id=str(len(sent)))

            obj._send = text
            obj._send_sticker_row = sticker
            with work_context(token, event):
                if pure and early_intent:
                    await obj.send_sticker(event, 'happy', only_sticker=True)
                    await obj.send_sticker(event, 'work', only_sticker=True)
                await obj._react_and_send(scope.target, scope.key, 'quick', event.message_str)
                if pure and not early_intent:
                    await obj.send_sticker(event, 'happy', only_sticker=True)
                    await obj.send_sticker(event, 'work', only_sticker=True)
                await obj.capture(event, SimpleNamespace(result_chain=ResultChain('' if pure else '最终回答')))
                await obj._complete_reply(event)
            return sent

    async def test_control_normal_request_keeps_progress_feedback(self):
        self.assertEqual(await self.run_reply(False), ['text', 'text'])

    async def test_already_known_sticker_only_intent_suppresses_feedback_text(self):
        self.assertEqual(await self.run_reply(True, early_intent=True), ['sticker', 'sticker'])

    async def test_explicit_sticker_only_request_does_not_get_feedback_before_tool_intent(self):
        self.assertEqual(await self.run_reply(True), ['sticker', 'sticker'])


if __name__ == '__main__':
    unittest.main()
