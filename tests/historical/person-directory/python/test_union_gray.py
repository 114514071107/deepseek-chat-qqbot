import json,tempfile,time,unittest
from pathlib import Path
from test_union_profile_contracts import ROOT,event,enable
from user_profiles import record_profile
from user_directory import handle
from union_rollout import FILE,OBSERVATIONS, fingerprint
class Canary(unittest.TestCase):
 def test_leaving_apply_does_not_corrupt_saved_union_on_normal_events(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as root:
   e,s,d=event();enable(root,[s]);record_profile(e,s,root)
   p=Path(root)/FILE;v=json.loads(p.read_text());v['mode']='observe';p.write_text(json.dumps(v))
   e,s,d=event(mid='AFTER-ROLLBACK');record_profile(e,s,root)
   row=json.loads((Path(root)/'workbench_profiles_v1.json').read_text())['sources'][s.key]
   self.assertFalse(row.get('identity_conflict',False))
   self.assertEqual(row['identity']['namespace'],'qq_union_openid')
 def test_absent_policy_preserves_original_identity_and_no_diagnostics(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as root:
   e,s,d=event();record_profile(e,s,root)
   row=json.loads((Path(root)/'workbench_profiles_v1.json').read_text())['sources'][s.key]
   self.assertEqual(row['identity']['namespace'],'qq_user_openid')
   self.assertFalse((Path(root)/OBSERVATIONS).exists())
 def test_observe_only_is_bounded_and_never_stores_plaintext_union(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as root:
   e,s,d=event();enable(root,[s]);p=Path(root)/FILE;v=json.loads(p.read_text());v['mode']='observe';p.write_text(json.dumps(v))
   record_profile(e,s,root)
   row=json.loads((Path(root)/'workbench_profiles_v1.json').read_text())['sources'][s.key]
   self.assertEqual(row['identity']['namespace'],'qq_user_openid')
   text=(Path(root)/OBSERVATIONS).read_text();self.assertNotIn('UNION-A',text);self.assertTrue(json.loads(text)['rows'][0]['union_valid'])
   self.assertIn('5 分钟有效',handle(e,s,root,'关联身份'))
   self.assertEqual(len(json.loads((Path(root)/'user_directory_v1.json').read_text())['pending']),1)
 def test_only_apply_cohort_changes_identity_and_retires_binding(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as root:
   e,s,d=event();enable(root,[s]);record_profile(e,s,root)
   row=json.loads((Path(root)/'workbench_profiles_v1.json').read_text())['sources'][s.key];self.assertEqual(row['identity']['namespace'],'qq_union_openid')
   self.assertIn('已停用',handle(e,s,root,'关联身份'))
   e2,s2,d2=event(raw='OUTSIDE');record_profile(e2,s2,root)
   self.assertNotIn('已停用',handle(e2,s2,root,'关联身份'))
   rows=json.loads((Path(root)/'workbench_profiles_v1.json').read_text())['sources'];self.assertEqual(rows[s2.key]['identity']['namespace'],'qq_user_openid')
 def test_expired_or_wrong_source_policy_does_not_apply(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as root:
   e,s,d=event();enable(root,[s]);p=Path(root)/FILE;v=json.loads(p.read_text());v['expires_at']=time.time()-1;p.write_text(json.dumps(v));record_profile(e,s,root)
   self.assertEqual(json.loads((Path(root)/'workbench_profiles_v1.json').read_text())['sources'][s.key]['identity']['namespace'],'qq_user_openid')
if __name__=='__main__':unittest.main(verbosity=2)
