import copy
import tempfile
import unittest
from repair_pipeline_support import load_pipeline
from test_repair_session_scope import ScopeEvent
from context_window import build_window


class CorrectionFragments(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        obj, _ = load_pipeline(self.tmp.name)
        self.scope = obj._scope(ScopeEvent())

    def row(self, identity, text):
        return dict(id=identity, role='user', text=text, ts=1,
                    source=dict(self.scope.source(), message_id=identity))

    def tails(self):
        return [self.row(f'tail{n}', '附件数据。' * 400) for n in range(12)]

    def test_disjoint_corrections_are_exact_quotes_with_one_source(self):
        text = ('更正：会议改为周三。' + '附件供参考。' * 150 +
                '取消：旧地点作废，改为东门。' + '清单供参考。' * 150 + '另注：清单不是待办。')
        rows = [self.row('change', text)] + self.tails()
        before = copy.deepcopy(rows)
        window = build_window(rows, [], self.scope, 4000)
        payload = str(window['messages'])
        self.assertIn('会议改为周三', payload)
        self.assertIn('改为东门', payload)
        self.assertEqual(window['summary']['corrections_omitted'], 0)
        for entry in window['summary']['entries']:
            original = next(row for row in rows if row['id'] == entry['id'])
            for quote in [entry['text']] + entry.get('fragments', []):
                self.assertIn(quote, original['text'])
        self.assertEqual(rows, before)
        self.assertLessEqual(window['context_chars'], 4000)
        rolled = build_window(rows[1:], [], self.scope, 4000, window['summary'])
        self.assertIn('会议改为周三', str(rolled['messages']))
        self.assertIn('改为东门', str(rolled['messages']))
        self.assertEqual(rolled['summary']['corrections_omitted'], 0)

    def test_partial_single_record_warns_and_survives_rolling(self):
        # Every sentence is a separate correction fragment; selecting one is
        # not evidence that the whole source record has been retained.
        text = ''.join(f'更正：第{n}项改为新值{n}。' for n in range(100))
        rows = [self.row('many', text)] + self.tails()
        window = build_window(rows, [], self.scope, 1000)
        self.assertGreater(window['summary']['corrections_omitted'], 0)
        self.assertIn('不能仅凭旧约定确定现行值', str(window['messages']))
        rolled = build_window(rows[1:], [], self.scope, 1000, window['summary'])
        self.assertGreater(rolled['summary']['corrections_omitted'], 0)
        self.assertIn('不能仅凭旧约定确定现行值', str(rolled['messages']))
        self.assertLessEqual(rolled['context_chars'], 1000)
        recovered = build_window(rows, [], self.scope, 10000, rolled['summary'])
        self.assertEqual(recovered['summary']['corrections_omitted'], 0)
        self.assertNotIn('不能仅凭旧约定确定现行值', str(recovered['messages']))
        cleared = build_window([], [], self.scope, 1000, rolled['summary'])
        self.assertEqual(cleared['summary']['corrections_omitted'], 0)

    def test_v2_excerpt_is_rebuilt_from_available_source(self):
        rows = [self.row('change', '更正：改为周三。' + '归档材料。' * 250 + '清单不是任务。')] + self.tails()
        old = dict(version=2, scope=self.scope.key, retained_ids=['tail11'],
                   entries=[dict(id='ghost', role='user', sender='a', text='STALE V2 QUOTE')])
        window = build_window(rows, [], self.scope, 4000, old)
        self.assertIn('改为周三', str(window['messages']))
        self.assertNotIn('STALE V2 QUOTE', str(window['messages']))
        self.assertGreater(window['summary']['corrections_omitted'], 0)
        # With identical retained raw input the old excerpt can be fully
        # regenerated; don't claim a legacy gap when coverage is verifiable.
        from context_window import fingerprint
        old['source_version'] = fingerprint(rows)
        rebuilt = build_window(rows, [], self.scope, 4000, old)
        self.assertEqual(rebuilt['summary']['corrections_omitted'], 0)

    def test_correction_header_and_next_sentence_keep_the_new_value(self):
        for change in ('更正：\n会议在周三。', '更正：不是周一。现在周三。'):
            with self.subTest(change=change):
                rows = [self.row('change', change + '附件供参考。' * 180)] + self.tails()
                window = build_window(rows, [], self.scope, 4000)
                self.assertIn('周三', str(window['messages']))
                self.assertEqual(window['summary']['corrections_omitted'], 0)


if __name__ == '__main__': unittest.main()
