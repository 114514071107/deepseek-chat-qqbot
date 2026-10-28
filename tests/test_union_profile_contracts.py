"""Synthetic contracts: wrong union, wrong provenance or routing changes must fail."""
import asyncio,ast,copy,hashlib,json,os,re,sqlite3,sys,tempfile,time,unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
ROOT=Path(__file__).parent
PLUGIN=ROOT.parent/'plugin/astrbot_plugin_dsh_soul'
sys.path.insert(0,str(PLUGIN))
from session_scope import Scope
from union_user_profiles import observe,record_profile
from user_directory import handle,onboarding,fingerprint

def event(raw='RAW-P',group='',union='UNION-A',app='APP-A',instance='INSTANCE-A',name='小禾',shape='native',mid='MSG-1'):
 s=Scope('qq_official',instance,'qq_official' if group else 'unknown_selfid',raw,group,mid,not group,received_at=time.time())
 d={'id':mid,'timestamp':s.received_at,'author':{('member_openid' if group else 'user_openid'):raw,'username':name}}
 if union is not None:d['author']['union_openid']=union
 if group:d['group_openid']=group
 rawdata=d if shape=='native' else {'op':0,'t':'GROUP_AT_MESSAGE_CREATE' if group else 'C2C_MESSAGE_CREATE','d':d}
 if shape=='sdk':rawdata=NS(raw_data=d)
 e=NS(message_obj=NS(raw_message=rawdata,sender=NS(user_id=raw)),bot=NS(api=NS(_http=NS(_token=NS(app_id=app)))))
 extras={};e.get_extra=lambda k:extras.get(k);e.set_extra=lambda k,v:extras.__setitem__(k,v)
 return e,s,d

def enable(data,scopes):
 from union_rollout import fingerprint
 (Path(data)/'union_rollout_v1.json').write_text(json.dumps(dict(version=1,mode='apply',expires_at=time.time()+3600,comparison_key='a'*64,fingerprints=[fingerprint(s.source(),'APP-A') for s in scopes])))
class UnionContracts(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(self.tmp.cleanup);self.data=Path(self.tmp.name)
  enable(self.data,[event()[1],event(raw='NEW',name='')[1]])
 def test_native_real_union_not_original_sender(self):
  e,s,d=event();o=observe(e,s)
  self.assertEqual(o['identity'],{'namespace':'qq_union_openid','value':'UNION-A','basis':'qq_author_union'})
 def test_envelope_sdk_and_native_match_same_verified_contract(self):
  for shape in ['native','sdk','dispatch']:
   e,s,d=event(raw='MEMBER-A',group='GROUP-A',shape=shape)
   o=observe(e,s);self.assertIsNotNone(o,shape);self.assertIsNotNone(o['identity'],shape);self.assertEqual(o['identity']['value'],'UNION-A')
 def test_mismatched_dispatch_message_sender_group_or_type_rejected(self):
  for change in ['id','sender','group','type','op']:
   e,s,d=event(raw='M',group='G',shape='dispatch')
   if change=='id':d['id']='different'
   if change=='sender':d['author']['member_openid']='other'
   if change=='group':d['group_openid']='other'
   if change=='type':e.message_obj.raw_message['t']='C2C_MESSAGE_CREATE'
   if change=='op':e.message_obj.raw_message['op']=1
   self.assertIsNone(observe(e,s),change)
 def test_invalid_union_not_promoted_to_platform_union(self):
  for union in [None,'',' ',123,True,{},[], 'A B','A\x00B']:
   e,s,d=event(union=union);o=observe(e,s)
   self.assertNotEqual((o.get('identity') or {}).get('namespace'),'qq_union_openid')
 def test_client_appid_and_content_cannot_create_trusted_union(self):
  e,s,d=event(app='',union='UNION-A');d.update(app_id='APP-A',content='{"union_openid":"UNION-A"}')
  self.assertIsNone(observe(e,s)['identity'])
  e,s,d=event(union=None);d['content']='author.union_openid=UNION-A';d['union_openid']='UNION-A'
  self.assertNotEqual((observe(e,s)['identity'] or {}).get('namespace'),'qq_union_openid')
 def test_union_changes_quarantine_instead_of_overwriting_old_proof(self):
  for mid,union in [('MSG-1','UNION-A'),('MSG-2','UNION-B')]:
   e,s,d=event(union=union,mid=mid);record_profile(e,s,self.data)
  row=json.loads((self.data/'workbench_profiles_v1.json').read_text())['sources'][s.key]
  self.assertTrue(row.get('identity_conflict'));self.assertEqual({x['identity']['value'] for x in row['identity_conflicts'] if x['identity']['namespace']=='qq_union_openid'},{'UNION-A','UNION-B'})
 def test_invalid_sdk_app_private_group_and_dto_sender_mismatch_rejected(self):
  e,s,d=event(app=' ');self.assertIsNone(observe(e,s)['identity'])
  e,s,d=event();d['group_openid']='UNEXPECTED';self.assertIsNone(observe(e,s))
  e,s,d=event();e.message_obj.sender.user_id='FORGED';self.assertIsNone(observe(e,s))
 def test_sparse_union_and_schema_promotion_preserve_actual_proof_time(self):
  e,s,d=event(union=None);record_profile(e,s,self.data)
  e,s,d=event(union='UNION-A',mid='MSG-2');record_profile(e,s,self.data)
  f=self.data/'workbench_profiles_v1.json';row=json.loads(f.read_text(encoding='utf-8'))['sources'][s.key]
  self.assertFalse(row.get('identity_conflict',False));self.assertEqual(row['identity']['namespace'],'qq_union_openid');stamp=row['identity_observed_at']
  e,s,d=event(union=None,mid='MSG-3');record_profile(e,s,self.data)
  row=json.loads(f.read_text(encoding='utf-8'))['sources'][s.key];self.assertEqual(row['identity']['value'],'UNION-A');self.assertEqual(row['identity_observed_at'],stamp)
 def test_app_change_and_older_conflicting_event_cannot_silently_regroup(self):
  e,s,d=event();record_profile(e,s,self.data)
  e,s,d=event(app='APP-B',mid='MSG-2');d['timestamp']-=30;record_profile(e,s,self.data)
  row=json.loads((self.data/'workbench_profiles_v1.json').read_text(encoding='utf-8'))['sources'][s.key]
  self.assertTrue(row['identity_conflict']);self.assertEqual({p['app'] for p in row['identity_conflicts']},{'APP-A','APP-B'})
 def test_duplicate_ingest_no_duplicate_source_or_name_loss(self):
  e,s,d=event();record_profile(e,s,self.data);record_profile(e,s,self.data)
  rows=json.loads((self.data/'workbench_profiles_v1.json').read_text(encoding='utf-8'))['sources']
  self.assertEqual(len(rows),1);self.assertEqual(rows[s.key]['nickname']['value'],'小禾')
 def test_no_pairing_issuance_or_claim_and_old_store_unchanged(self):
  e,s,d=event();old={'version':1,'sources':{},'pending':{'old-hash':{'expires':1,'owner':'old'}}}
  f=self.data/'user_directory_v1.json';f.write_text(json.dumps(old));before=f.read_bytes()
  for cmd in ['关联身份','关联身份 ABCDEFGHIJKLMNOP','确认关联 ABCDEFGHIJKLMNOP','取消关联验证']:
   response=handle(e,s,self.data,cmd)
   self.assertTrue(response is None or '不再' in response or '已停用' in response)
  self.assertEqual(f.read_bytes(),before)
 def test_name_command_retained_but_hints_have_no_binding_steps(self):
  e,s,d=event(name='');self.assertIn('已将',handle(e,s,self.data,'设置称呼 新称呼'))
  row=next(iter(json.loads((self.data/'user_directory_v1.json').read_text())['sources'].values()))
  self.assertEqual(row['nickname']['value'],'新称呼')
  e2,s2,d2=event(raw='NEW',name='');hint=onboarding(e2,s2,self.data) or ''
  self.assertIn('设置称呼',hint);self.assertNotIn('关联身份',hint)
 def test_sender_scope_target_permissions_and_memory_keys_never_mutate(self):
  from state_store import person_ledger_key
  for raw,group in [('P',''),('M-A','G-A'),('M-B','G-B')]:
   e,s,d=event(raw=raw,group=group);before=(copy.deepcopy(e.message_obj.sender.__dict__),s.key,s.memory_key,s.group_key,s.target,person_ledger_key(s,{}))
   record_profile(e,s,self.data);handle(e,s,self.data,'设置称呼 同人')
   self.assertEqual(before,(e.message_obj.sender.__dict__,s.key,s.memory_key,s.group_key,s.target,person_ledger_key(s,{})))


if __name__=="__main__":unittest.main(verbosity=2)
