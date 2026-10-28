import json,tempfile,unittest
from pathlib import Path
from test_union_profile_contracts import ROOT,event
from union_user_profiles import record_profile
class PromotionPersistence(unittest.TestCase):
 def test_missing_sdk_app_preserves_previous_author_proof(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as root:
   e,s,d=event(raw='M',group='G',union=None,mid='OLD');d['author']['user_openid']='P';record_profile(e,s,root)
   e,s,d=event(raw='M',group='G',union='UNION-A',mid='UPGRADE');record_profile(e,s,root)
   e,s,d=event(raw='M',group='G',union=None,app='',mid='SPARSE');record_profile(e,s,root)
   self.assertEqual(json.loads((Path(root)/'workbench_profiles_v1.json').read_text())['sources'][s.key].get('previous_identity',{}).get('value'),'P')
 def test_new_author_user_counterevidence_is_not_erased_by_union(self):
  for union in [None,'UNION-A']:
   with self.subTest(union=union),tempfile.TemporaryDirectory(dir=ROOT) as root:
    e,s,d=event(raw='M',group='G',union=None,mid='OLD');d['author']['user_openid']='P1';record_profile(e,s,root)
    e,s,d=event(raw='M',group='G',union='UNION-A',mid='UPGRADE');record_profile(e,s,root)
    e,s,d=event(raw='M',group='G',union=union,mid='CONTRADICT');d['author']['user_openid']='P2';record_profile(e,s,root)
    row=json.loads((Path(root)/'workbench_profiles_v1.json').read_text())['sources'][s.key]
    self.assertTrue(row.get('identity_conflict',False))
    self.assertTrue(any(p['identity'].get('value')=='P2' for p in row.get('identity_conflicts',[])))
 def test_sparse_event_preserves_previous_author_proof(self):
  with tempfile.TemporaryDirectory(dir=ROOT) as root:
   e,s,d=event(raw='M',group='G',union=None,mid='OLD');d['author']['user_openid']='P';record_profile(e,s,root)
   e,s,d=event(raw='M',group='G',union='UNION-A',mid='UPGRADE');record_profile(e,s,root)
   f=Path(root)/'workbench_profiles_v1.json';self.assertEqual(json.loads(f.read_text())['sources'][s.key]['previous_identity']['value'],'P')
   e,s,d=event(raw='M',group='G',union=None,mid='SPARSE');record_profile(e,s,root)
   self.assertEqual(json.loads(f.read_text())['sources'][s.key].get('previous_identity',{}).get('value'),'P')
if __name__=='__main__':unittest.main(verbosity=2)
