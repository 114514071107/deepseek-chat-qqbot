"""Acceptance regression for QQ P02/G02: one requested image queued twice.

Uses actual pipeline methods with synthetic data and an in-memory sender.
Run separately: python -B -m unittest discover -s tests -p acceptance_real_qq_20261025_duplicate.py -v
"""
import tempfile
import unittest
from types import SimpleNamespace
from repair_pipeline_support import load_pipeline, ResultChain
from test_repair_session_scope import ScopeEvent
from task_runtime import work_context
from qq_delivery import DeliveryResult


class SingleStickerAcceptance(unittest.IsolatedAsyncioTestCase):
    async def send_plan(self, action):
        with tempfile.TemporaryDirectory() as tmp:
            obj, ns = load_pipeline(tmp, names=('capture', 'send_sticker', '_clear_text_result', '_set_first_bubble_result'))
            self.addAsyncCleanup(obj.runtime.stop)
            ns['random'] = SimpleNamespace(random=lambda: 1)
            ns['_pick_sticker'] = lambda query: dict(pack='fixture', rel=query+'.png', caption='fixture')
            sent = []

            async def send(target, row):
                sent.append(row['rel'])
                return DeliveryResult('accepted', message_id=str(len(sent)))

            obj._send_sticker_row = send
            event = ScopeEvent()
            event.message_str = '只发一张表情包，不要文字或额外气泡'
            scope = obj._scope(event)
            token = obj.runtime.begin(scope.key)
            event.set_extra('_dsh_work', token)
            with work_context(token, event):
                await obj.send_sticker(event, 'happy', only_sticker=True)
                await obj.capture(event, SimpleNamespace(result_chain=ResultChain('动作：仅表情 '+action if action else '')))
                await obj._complete_reply(event)
            return sent

    async def test_control_tool_only_sends_one(self):
        self.assertEqual(len(await self.send_plan(None)), 1)

    async def test_matching_tool_and_action_do_not_duplicate_one_requested_image(self):
        self.assertEqual(len(await self.send_plan('happy')), 1,
                         'one requested image was queued from both tool and action')

    async def test_different_tool_and_action_choices_still_represent_one_requested_image(self):
        self.assertEqual(len(await self.send_plan('work')), 1,
                         'deduplicating identical image files alone does not reconcile the two channels')


if __name__ == '__main__':
    unittest.main()
