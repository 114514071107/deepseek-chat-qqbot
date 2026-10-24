"""Regression for the C04 correction falling between recent and excerpts."""
import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from repair_pipeline_support import load_pipeline
from test_repair_session_scope import ScopeEvent
from context_window import build_window


class RealContextRegression(unittest.IsolatedAsyncioTestCase):
    def rows(self, scope):
        rows = []
        for n in range(6):
            lead = ('约定：图书馆三楼，明天14点。' if n == 0 else
                    '更正：前面的会议时间改为明天16点30分，地点仍是图书馆三楼。' if n == 3 else '沿用前面的约定。')
            rows.append(dict(id=f'u{n}', role='user', text=lead + '无须回答的虚构物品清单。' * 155,
                             ts=n*2, source=dict(scope.source(), message_id=f'C{n+1:02}')))
            rows.append(dict(id=f'a{n}', role='assistant', text='收到，保留这条合成资料。', ts=n*2+1,
                             source=scope.source(), delivery={'status':'accepted'}))
        # Further material arrives before the final query; C04 is still in
        # the recent twelve, but too old to fit their raw-text budget.
        for n in range(2):
            rows.append(dict(id=f'tail{n}', role='user', text='补充合成材料。' * 450,
                             ts=20+n, source=dict(scope.source(), message_id=f'tail{n}')))
        return rows

    async def test_c04_correction_reaches_final_model_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj, _ = load_pipeline(tmp)
            Path(tmp, 'persona.md').write_text('fixture', encoding='utf-8')
            event = ScopeEvent(); scope = obj._scope(event)
            obj.h[scope.key] = self.rows(scope)
            before = copy.deepcopy(obj.h[scope.key])
            req = SimpleNamespace(prompt='最终时间？', contexts=[], system_prompt='', func_tool=None)
            await obj.inject(event, req)
            payload = json.dumps(req.contexts, ensure_ascii=False)
            self.assertIn('明天16点30分', payload)
            self.assertIn('C04', payload)
            self.assertEqual(obj.h[scope.key], before)
            self.assertLessEqual(sum(len(m['content']) for m in req.contexts), 10000)

    async def test_corrections_survive_boundary_rolling_and_repeated_compaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj, _ = load_pipeline(tmp); scope = obj._scope(ScopeEvent())
            rows = self.rows(scope); previous = None
            for n in range(8):
                window = build_window(rows, [], scope, 4000, previous)
                self.assertIn('明天16点30分', str(window['messages']))
                self.assertLessEqual(window['context_chars'], 4000)
                previous = window['summary']
                rows = rows[1:] + [dict(id=f'new{n}', role='user', text='材料' * 800,
                                       source=dict(scope.source(), message_id=f'next{n}'))]
            self.assertNotIn('明天16点30分', str(build_window([], [], scope, 4000, previous)['messages']))

    async def test_latest_revocation_prioritized_with_explicit_budget_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj, _ = load_pipeline(tmp); scope = obj._scope(ScopeEvent())
            rows = self.rows(scope)
            for n in range(8):
                rows.append(dict(id=f'correction{n}', role='user', text=f'更正：会议改为第{n}天。' + '说明' * 250,
                                 ts=100+n, source=dict(scope.source(), message_id=f'fix{n}')))
            rows.append(dict(id='cancel', role='user', text='取消：上述会议作废，不再按任何旧时间出发。',
                             ts=200, source=dict(scope.source(), message_id='cancel')))
            window = build_window(rows, [], scope, 1000)
            self.assertIn('上述会议作废', str(window['messages']))
            self.assertIn('更正', str(window['messages']))
            self.assertGreater(window['summary']['corrections_omitted'], 0)
            self.assertIn('不能仅凭旧约定确定现行值', str(window['messages']))
            self.assertLessEqual(window['context_chars'], 1000)

    async def test_long_correction_tail_old_summary_and_scope_cannot_reintroduce_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj, _ = load_pipeline(tmp); scope = obj._scope(ScopeEvent())
            rows=self.rows(scope)
            rows.insert(0, dict(id='late-cue', role='user', text='填充' * 400 + '更正：取消旧地点，改为实验室。',
                               source=dict(scope.source(),message_id='late-cue')))
            first=build_window(rows,[],scope,4000)
            self.assertIn('改为实验室',str(first['messages']))
            previous=first['summary']
            # An old selection algorithm is regenerated, not perpetuated.
            old=dict(previous,version=1,entries=[dict(id='ghost',role='user',text='OLD-SUMMARY-ONLY',sender='a')])
            self.assertNotIn('OLD-SUMMARY-ONLY',str(build_window(rows,[],scope,4000,old)['messages']))
            window=build_window(rows[1:],['late-cue'],scope,4000,previous)
            self.assertNotIn('改为实验室',str(window['messages']))
            foreign=[dict(row,source=dict(row['source'],group='foreign',private=False)) for row in rows]
            self.assertNotIn('改为实验室',str(build_window(foreign,[],scope,4000,previous)['messages']))

    async def test_newest_correction_wins_excerpt_priority_when_neither_raw_row_fits(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp);scope=obj._scope(ScopeEvent())
            rows=[dict(id=str(n),role='user',text=text+'填充'*600,ts=n,
                       source=dict(scope.source(),message_id=str(n))) for n,text in enumerate(
                           ('更正：旧时间为周一。','更正：周一已作废，最终改为周三。'))]
            window=build_window(rows,[],scope,1000)
            self.assertIn('最终改为周三',str(window['messages']))
            self.assertLessEqual(window['context_chars'],1000)


if __name__ == '__main__': unittest.main()
