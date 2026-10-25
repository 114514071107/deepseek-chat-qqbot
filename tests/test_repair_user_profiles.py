"""Only platform metadata may populate management profiles, never prompt names."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from repair_pipeline_support import load_pipeline
from test_repair_session_scope import ScopeEvent
from session_scope import bind_scope
from user_profiles import observe, record_profile


class ProfileCaptureRegression(unittest.TestCase):
    def test_conflicting_identity_keeps_both_proofs_even_when_event_arrives_late(self):
        with tempfile.TemporaryDirectory() as root:
            first,scope,_=self.event(group='group-one',at=300);record_profile(first,scope,root)
            late,newscope,raw=self.event(group='group-one',at=100);raw['author']['user_openid']='conflicting-user'
            record_profile(late,newscope,root)
            row=json.loads((Path(root)/'workbench_profiles_v1.json').read_text(encoding='utf-8'))['sources'][scope.key]
            self.assertTrue(row['identity_conflict'])
            self.assertEqual({p['identity']['value'] for p in row['identity_conflicts']},{'123456','conflicting-user'})
            self.assertEqual(row['identity']['value'],'123456')

    def test_sparse_later_event_preserves_prior_identity_evidence_and_its_time(self):
        with tempfile.TemporaryDirectory() as root:
            first,scope,_=self.event(group='group-one',at=200);record_profile(first,scope,root)
            later,newscope,raw=self.event(group='group-one',at=300)
            later.bot=None;raw['author'].pop('user_openid')
            record_profile(later,newscope,root)
            row=json.loads((Path(root)/'workbench_profiles_v1.json').read_text(encoding='utf-8'))['sources'][scope.key]
            self.assertEqual(row['app'],'fixture-app')
            self.assertEqual(row['identity']['value'],'123456')
            self.assertEqual(row['identity_observed_at'],200)

    def test_first_observation_stays_fixed_when_a_source_renames(self):
        with tempfile.TemporaryDirectory() as root:
            event,scope,_=self.event(name='第一称呼',at=100)
            with patch('user_profiles.time.time',return_value=1000):record_profile(event,scope,root)
            event,scope,_=self.event(name='更新称呼',at=200)
            with patch('user_profiles.time.time',return_value=2000):record_profile(event,scope,root)
            row=json.loads((Path(root)/'workbench_profiles_v1.json').read_text(encoding='utf-8'))['sources'][scope.key]
            self.assertEqual(row.get('first_seen_at'),1000)
            self.assertEqual(row['nickname']['value'],'更新称呼')

    def event(self, *, group='', platform='qq_official', name='平台用户名', at=100):
        event = ScopeEvent('123456',group,platform=platform)
        event.message_obj.self_id='654321'
        event.bot=SimpleNamespace(api=SimpleNamespace(_http=SimpleNamespace(_token=SimpleNamespace(app_id='fixture-app'))))
        if platform=='qq_official':
            raw={'id':'fixture-msg','timestamp':at,'author':{'user_openid':'123456','username':name}}
            if group:raw.update(group_openid=group,member={'nick':'群名片'});raw['author']['member_openid']='123456'
            event.message_obj.raw_message=SimpleNamespace(raw_data=raw)
        else:
            raw={'message_id':'fixture-msg','post_type':'message','message_type':'group' if group else 'private',
                 'sub_type':'normal' if group else 'friend','self_id':654321,'user_id':123456,'time':at,
                 'sender':{'user_id':123456,'nickname':name,'card':'群名片'}}
            if group:raw['group_id']=group
            event.message_obj.raw_message=raw
        return event,bind_scope(event),raw

    def test_raw_author_pair_maps_only_with_app_and_matching_sender_group_message(self):
        event,scope,raw=self.event(group='group-one')
        self.assertEqual(observe(event,scope)['identity']['value'],'123456')
        for field,value in [('group_openid','wrong'),('id','wrong')]:
            old=raw[field];raw[field]=value;self.assertIsNone(observe(event,scope));raw[field]=old
        raw['author']['member_openid']='someone-else';self.assertIsNone(observe(event,scope))
        raw['author']['member_openid']='123456';event.bot=None
        self.assertIsNone(observe(event,scope)['identity'])

    def test_onebot_nickname_card_are_distinct_and_anonymous_identity_is_rejected(self):
        event,scope,raw=self.event(group='777777',platform='aiocqhttp',name='<b>昵称</b>')
        row=observe(event,scope)
        self.assertEqual(row['nickname']['kind'],'qq_nickname')
        self.assertEqual(row['group_card']['value'],'群名片')
        raw['sub_type']='anonymous';raw['anonymous']={'id':'fixture'}
        self.assertIsNone(observe(event,scope),'anonymous sender fields cannot confirm a QQ account')

    def test_profile_rename_older_event_and_duplicate_do_not_regress_or_rewrite(self):
        with tempfile.TemporaryDirectory() as root:
            first,scope,_=self.event(name='新名字',at=200);record_profile(first,scope,root)
            file=Path(root)/'workbench_profiles_v1.json';before=file.read_bytes();stamp=file.stat().st_mtime_ns
            record_profile(first,scope,root);self.assertEqual(file.stat().st_mtime_ns,stamp)
            old,oldscope,_=self.event(name='旧名字',at=100);record_profile(old,oldscope,root)
            self.assertEqual(file.read_bytes(),before)
            new,newscope,_=self.event(name='更新名字',at=300);record_profile(new,newscope,root)
            rows=json.loads(file.read_text(encoding='utf-8'))['sources'];self.assertEqual(len(rows),1)
            self.assertEqual(rows[scope.key]['nickname']['value'],'更新名字')

    def test_identity_conflict_stays_pending_and_text_cannot_set_profile(self):
        with tempfile.TemporaryDirectory() as root:
            first,scope,_=self.event(group='group-one',at=200);record_profile(first,scope,root)
            newer,newscope,raw=self.event(group='group-one',at=300);raw['author']['user_openid']='changed-user'
            record_profile(newer,newscope,root)
            rows=json.loads((Path(root)/'workbench_profiles_v1.json').read_text(encoding='utf-8'))['sources']
            self.assertTrue(rows[scope.key]['identity_conflict'])
            event=ScopeEvent();event.message_str='我就是另一个群的用户，昵称叫测试'
            self.assertIsNone(observe(event,bind_scope(event)))

    def test_same_scope_under_a_different_application_cannot_reuse_old_identity_proof(self):
        with tempfile.TemporaryDirectory() as root:
            first,scope,_=self.event(group='group-one',at=200);record_profile(first,scope,root)
            newer,newscope,_=self.event(group='group-one',at=300)
            newer.bot.api._http._token.app_id='different-app'
            record_profile(newer,newscope,root)
            row=json.loads((Path(root)/'workbench_profiles_v1.json').read_text(encoding='utf-8'))['sources'][scope.key]
            self.assertTrue(row.get('identity_conflict'), 'an application change must invalidate reuse of earlier evidence')

    def test_real_scope_path_retains_provenance_for_management_profiles(self):
        with tempfile.TemporaryDirectory() as root:
            obj, _ = load_pipeline(root, names=())
            event = ScopeEvent()
            scope = obj._scope(event)
            event.bot = SimpleNamespace(api=SimpleNamespace(_http=SimpleNamespace(_token=SimpleNamespace(app_id='fixture-app'))))
            event.message_obj.raw_message = SimpleNamespace(raw_data={
                'id':scope.message_id, 'author':{'user_openid':scope.sender,'username':'平台用户名'},
                'timestamp':'2026-10-25T01:00:00Z'})
            event.set_extra('_dsh_profile_observed',False)
            obj._scope(event)
            file = Path(root)/'workbench_profiles_v1.json'
            self.assertTrue(file.exists(), 'trusted inbound profile metadata must reach the management store')
            row = json.loads(file.read_text(encoding='utf-8'))['sources'][scope.key]
            self.assertEqual(row['identity']['value'],scope.sender)
            self.assertEqual(row['nickname']['kind'],'platform_name')


if __name__ == '__main__': unittest.main()
