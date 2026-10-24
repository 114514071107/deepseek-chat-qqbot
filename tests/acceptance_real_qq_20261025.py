"""Independent acceptance: synthetic data and actual pipeline methods, no QQ/model.

Run separately from the delivered test_repair_*.py suite:
  python -B -m unittest discover -s tests -p acceptance_real_qq_20261025.py -v
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from repair_pipeline_support import load_pipeline, ResultChain
from test_repair_session_scope import ScopeEvent
from task_runtime import work_context
from qq_delivery import DeliveryResult


class IndependentAcceptance(unittest.IsolatedAsyncioTestCase):
    async def sticker_plan(self, preamble):
        with tempfile.TemporaryDirectory() as tmp:
            obj, ns = load_pipeline(tmp)
            self.addAsyncCleanup(obj.runtime.stop)
            ns['random'] = SimpleNamespace(random=lambda: 1)
            ns['_pick_sticker'] = lambda query: dict(pack='fixture', rel='happy.png', caption='fixture')
            sent = []

            async def sticker(*args):
                sent.append('sticker')
                return DeliveryResult('accepted', message_id='fixture-image')

            async def text(target, chain):
                sent.append('text')
                return DeliveryResult('accepted', message_id='fixture-text')

            obj._send_sticker_row = sticker
            obj._send = text
            event = ScopeEvent()
            scope = obj._scope(event)
            token = obj.runtime.begin(scope.key)
            event.set_extra('_dsh_work', token)
            with work_context(token, event):
                await obj.capture(event, SimpleNamespace(result_chain=ResultChain(preamble + '\n动作：仅表情 得意')))
                await obj._complete_reply(event)
            self.assertTrue(event.get_extra('_dsh_sticker_only'), 'explicit protocol line must be recognized')
            return sent

    async def compacted_request(self, trailing_note):
        with tempfile.TemporaryDirectory() as tmp:
            obj, _ = load_pipeline(tmp)
            self.addAsyncCleanup(obj.runtime.stop)
            event = ScopeEvent()
            scope = obj._scope(event)

            def row(identity, text, timestamp):
                return dict(id=identity, role='user', text=text, ts=timestamp,
                            source=dict(scope.source(), message_id=identity))

            rows = [row('old', '约定：会议在周一。', 1),
                    row('correction', '更正：会议改为周三。' + '附件内容供归档参考。' * 160 + trailing_note, 2)]
            rows += [row(f'tail{n}', '合成附件数据' * 300, n + 3) for n in range(12)]
            self.assertLessEqual(max(len(item['text']) for item in rows), 2000)
            obj.h[scope.key] = rows
            Path(tmp, 'persona.md').write_text('fixture', encoding='utf-8')
            request = SimpleNamespace(prompt='最终会议时间？', contexts=[], system_prompt='', func_tool=None)
            await obj.inject(event, request)
            self.assertLessEqual(sum(len(message['content']) for message in request.contexts), 10000)
            return json.dumps(request.contexts, ensure_ascii=False)

    async def test_control_unquoted_sticker_preamble(self):
        self.assertEqual(await self.sticker_plan('给你一个得意的表情'), ['sticker'])

    async def test_explicit_sticker_only_with_ordinary_quoted_word(self):
        self.assertEqual(await self.sticker_plan('给你一个“得意”的表情'), ['sticker'],
                         'ordinary quoted word must not disable explicit sticker-only intent')

    async def test_control_correction_without_late_incidental_cue(self):
        payload = await self.compacted_request('另注：这份清单仅供查阅。')
        self.assertIn('周三', payload)

    async def test_correction_not_lost_to_late_incidental_cue(self):
        payload = await self.compacted_request('另注：这份清单不是待办任务。')
        self.assertTrue('周三' in payload or '不能仅凭旧约定确定现行值' in payload,
                        'old Monday remains but corrected Wednesday and correction-gap warning are both absent')


if __name__ == '__main__':
    unittest.main()
