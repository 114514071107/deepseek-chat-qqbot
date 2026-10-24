"""Independent acceptance for current prose versus retained-prefix ordering."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from repair_pipeline_support import load_pipeline, ResultChain
from test_repair_session_scope import ScopeEvent
from task_runtime import work_context
from qq_delivery import DeliveryResult


class CurrentCountOrderAcceptance(unittest.IsolatedAsyncioTestCase):
    async def run_pipeline(self, text, *, supplement=None):
        with tempfile.TemporaryDirectory() as tmp:
            obj, ns = load_pipeline(tmp, names=('inject', 'capture', 'send_sticker',
                '_clear_text_result', '_set_first_bubble_result'), guarded=True)
            self.addAsyncCleanup(obj.runtime.stop)
            Path(tmp, 'persona.md').write_text('fixture', encoding='utf-8')
            ns['_pick_sticker'] = lambda q: dict(pack='fixture', rel=q+'.png', caption='fixture')
            ns['random'] = SimpleNamespace(random=lambda: 1)
            event = ScopeEvent()
            event.message_str = text
            scope = obj._scope(event)
            token = obj.runtime.begin(scope.key)
            event.set_extra('_dsh_work', token)
            # gate retains exactly this bounded prefix for the incoming item.
            event.set_extra('_dsh_input', dict(text=text[:2000], images=[], files=[], message_id='first'))
            obj.batch_buf = {}
            if supplement is not None:
                obj.batch_buf = {scope.key: [dict(text=supplement, images=[], files=[], message_id='later')]}
            obj.request_owners = {scope.key: token.request}
            obj.request_events = {scope.key: event}
            sent = []
            async def media(target, row):
                sent.append(row['rel'])
                return DeliveryResult('accepted', message_id=str(len(sent)))
            obj._send_sticker_row = media
            with work_context(token, event):
                req = SimpleNamespace(prompt=text, contexts=[], system_prompt='', image_urls=[], func_tool=None)
                await obj.inject(event, req)
                for n in range(5):
                    await obj.send_sticker(event, 'choice'+str(n), only_sticker=True)
                budget = obj._sticker_budget(event)
                limit, queued = budget['limit'], len(obj.pending_sticker.get(scope.key, []))
                await obj.capture(event, SimpleNamespace(result_chain=ResultChain('')))
                planned = len(event.get_extra('_dsh_reply_plan').stickers)
                await obj._complete_reply(event)
            return limit, queued, planned, len(sent)

    async def test_short_final_total_remains_authoritative(self):
        observed = await self.run_pipeline('只发表情，原方案共三张。更正：只发两张表情，共两张。')
        self.assertEqual(observed, (2, 2, 2, 2))

    async def test_retained_prefix_cannot_override_later_current_total(self):
        text = '只发表情，原方案共三张。' + '合成材料甲乙丙。'*300 + '更正：只发两张表情，共两张。'
        self.assertGreater(len(text), 2000)
        observed = await self.run_pipeline(text)
        self.assertEqual(observed, (2, 2, 2, 2), 'limit, queue, plan, and actual sends must follow the final current total')

    async def test_later_batch_supplement_can_override_current_total(self):
        observed = await self.run_pipeline('只发两张表情，共两张。', supplement='更正：只发一张表情，共一张。')
        self.assertEqual(observed, (1, 1, 1, 1))


if __name__ == '__main__':
    unittest.main()
