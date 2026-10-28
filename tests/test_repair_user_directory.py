"""Self-service proof stays local, bounded and separate from chat/auth state."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
from repair_pipeline_support import load_pipeline
from test_repair_session_scope import ScopeEvent
from session_scope import bind_scope
from user_directory import handle, onboarding


class UserDirectoryRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def event(self, sender='private-a', group='', app='fixture-app', name=''):
        e = ScopeEvent(sender, group)
        e.bot = SimpleNamespace(api=SimpleNamespace(_http=SimpleNamespace(_token=SimpleNamespace(app_id=app))))
        # Installed official adapter: C2C and group use different placeholders.
        e.message_obj.self_id = 'qq_official' if group else 'unknown_selfid'
        s = bind_scope(e)
        raw = {'id':s.message_id, 'timestamp':s.received_at,
               'author':{('member_openid' if group else 'user_openid'):sender}}
        if name: raw['author']['username'] = name
        if group: raw['group_openid'] = group
        e.message_obj.raw_message = SimpleNamespace(raw_data=raw)
        return e, s

    def call(self, event, text, now=100):
        return handle(*event, self.root, text, now=now)

    def state(self):
        return json.loads((self.root/'user_directory_v1.json').read_text(encoding='utf-8'))

    def token(self, reply):
        return re.search(r'关联身份 ([A-Z2-7]{16})', reply)[1]

    def test_name_is_self_selected_not_qq_nickname_and_normal_chat_never_joins(self):
        a, b = self.event(), self.event('member-a', 'group-a')
        self.assertIsNone(self.call(a, '我叫小禾，帮我记住'))
        self.call(a, '设置称呼 小禾'); self.call(b, '设置称呼 小禾')
        rows = list(self.state()['sources'].values())
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({r['person'] for r in rows}), 2)
        self.assertEqual(rows[0]['nickname']['kind'], 'self_selected')
        self.assertIn('1', self.call(a, '设置称呼 1号'))
        self.assertIn('称呼', self.call(a, '设置称呼 ' + '长'*33))

    def test_group_claim_cannot_merge_until_original_private_confirms_and_replay_fails(self):
        a, g, stranger = self.event(), self.event('member-a','group-a'), self.event('private-b')
        self.call(a, '设置称呼 小禾')
        code = self.token(self.call(a, '关联身份'))
        response = self.call(g, '关联身份 '+code)
        challenge = re.search(r'确认关联 ([A-Z2-7]{16})', response)[1]
        self.assertEqual(len({r['person'] for r in self.state()['sources'].values()}), 2)
        self.assertIn('私聊', self.call(g, '确认关联 '+challenge))
        self.assertIn('无效', self.call(stranger, '确认关联 '+challenge))
        self.assertIn('已关联', self.call(a, '确认关联 '+challenge))
        rows = list(self.state()['sources'].values())
        self.assertEqual(len({r['person'] for r in rows if r['source']['sender']!='private-b'}), 1)
        self.assertNotIn(code, json.dumps(self.state()))
        self.assertNotIn(challenge, json.dumps(self.state()))
        self.assertIn('无效', self.call(a, '确认关联 '+challenge))

    def test_expired_cross_app_and_different_group_claims_do_not_bind(self):
        a = self.event(); code = self.token(self.call(a, '关联身份'))
        self.assertIn('无效', self.call(self.event('m','g',app='other-app'), '关联身份 '+code))
        self.assertIn('过期', self.call(self.event('m','g'), '关联身份 '+code, now=401))
        self.assertGreaterEqual(len({r['person'] for r in self.state()['sources'].values()}), 1)
        self.assertIn('私聊', self.call(self.event('m','g'), '关联身份'))

    def test_cross_instance_and_unproven_bot_are_isolated(self):
        a = self.event(); code = self.token(self.call(a, '关联身份'))
        e, s = self.event('m','g')
        self.assertIn('无效', self.call((e,replace(s,instance='another-instance')), '关联身份 '+code))
        self.assertIn('无效', self.call((e,replace(s,bot='unproven-bot')), '关联身份 '+code))
        self.assertIn('无效', self.call((e,replace(s,bot='qq_official_adapter_placeholder')), '关联身份 '+code))

    def test_first_name_survives_new_event_and_concurrent_claim_never_merges_without_private_confirmation(self):
        from concurrent.futures import ThreadPoolExecutor
        a=self.event();self.assertIn('已将',self.call(a,'设置称呼 小禾'))
        # Fresh adapter event and fresh handle/store read, as after restart.
        self.assertEqual(next(iter(self.state()['sources'].values()))['nickname']['value'],'小禾')
        code=self.token(self.call(self.event(),'关联身份'))
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies=list(pool.map(lambda pair:self.call(pair,'关联身份 '+code),[self.event('m1','g'),self.event('m2','g')]))
        self.assertLessEqual(sum('确认关联' in reply for reply in replies),1)
        self.assertEqual(len({r['person'] for r in self.state()['sources'].values()}),len(self.state()['sources']))

    def test_competing_claim_invalidates_challenge_and_requires_restart(self):
        a = self.event(); code = self.token(self.call(a, '关联身份'))
        response = self.call(self.event('m1','g'), '关联身份 '+code)
        challenge = re.search(r'确认关联 ([A-Z2-7]{16})',response)[1]
        self.call(self.event('m2','g'), '关联身份 '+code)
        self.assertIn('无效', self.call(a,'确认关联 '+challenge))
        self.assertEqual(len({r['person'] for r in self.state()['sources'].values()}),3)

    def test_untrusted_event_cannot_write_and_onboarding_is_once_per_source(self):
        a = self.event()
        a[0].message_obj.raw_message.raw_data['author']['user_openid']='wrong'
        self.assertIn('核验', self.call(a,'设置称呼 偷改'))
        self.assertFalse((self.root/'user_directory_v1.json').exists())
        a = self.event()
        self.assertIn('设置称呼', onboarding(*a,self.root,now=100))
        self.assertIsNone(onboarding(*a,self.root,now=101))
        self.assertIsNone(onboarding(*self.event('named',name='平台名'),self.root,now=102))

    def test_denied_sources_remain_denied_and_file_lock_never_overwrites(self):
        from user_directory import fingerprint, decisions
        a, g = self.event(), self.event('m','g')
        code = self.token(self.call(a,'关联身份'))
        challenge = re.search(r'确认关联 ([A-Z2-7]{16})',self.call(g,'关联身份 '+code))[1]
        denied = [decisions(a[1].source(),'fixture-app')[0], decisions(g[1].source(),'fixture-app')[0]]
        (self.root/'console_people_v1.json').write_text(json.dumps({'version':2,'groups':[],'denied':[denied]}))
        self.assertIn('解除',self.call(a,'确认关联 '+challenge))
        before=(self.root/'user_directory_v1.json').read_bytes()
        lock=self.root/'user_directory_v1.json.lock'; lock.write_text('fixture')
        self.assertIn('稍后',self.call(a,'设置称呼 覆盖'))
        self.assertEqual((self.root/'user_directory_v1.json').read_bytes(),before)

    def test_conflicting_platform_identity_cannot_report_successful_self_pairing(self):
        from user_profiles import record_profile
        a, g = self.event(), self.event('m','g')
        g[0].message_obj.raw_message.raw_data['author']['user_openid']='different-private-user'
        record_profile(*a,self.root); record_profile(*g,self.root)
        code=self.token(self.call(a,'关联身份'))
        challenge=re.search(r'确认关联 ([A-Z2-7]{16})',self.call(g,'关联身份 '+code))[1]
        self.assertIn('冲突',self.call(a,'确认关联 '+challenge))
        self.assertEqual(len({r['person'] for r in self.state()['sources'].values()}),2)

    def test_pairing_issuance_is_bounded_and_expired_codes_do_not_return(self):
        a=self.event();codes=[]
        for _ in range(5):codes.append(self.token(self.call(a,'关联身份')))
        self.assertIn('频繁',self.call(a,'关联身份'))
        self.assertEqual(len(self.state()['pending']),1)
        self.assertIn('过期',self.call(self.event('m','g'),'关联身份 '+codes[0]))
        self.assertIn('关联身份',self.call(a,'关联身份',now=701))


class DirectoryGateRegression(unittest.IsolatedAsyncioTestCase):
    async def test_local_pairing_stops_before_points_model_and_plugin_history_and_respects_disable(self):
        with tempfile.TemporaryDirectory() as root:
            obj, ns = load_pipeline(root, names=('gate',))
            self.addAsyncCleanup(obj.runtime.stop); self.addAsyncCleanup(obj.resources.close)
            ns['MASTER_SWITCH_RE'] = re.compile(r'^NEVER$')
            ns['Image'] = type('Image', (), {}); ns['File'] = type('File', (), {})
            ns['_conf'] = lambda key:key == 'enabled'
            obj.names = {}; obj.n_path = str(Path(root)/'names.json'); obj.sil = {}
            obj._perm = lambda *args:True; obj._owner = lambda *args:False
            event = ScopeEvent('private-a'); scope = bind_scope(event)
            event.message_obj.raw_message = SimpleNamespace(raw_data={'id':scope.message_id,'timestamp':scope.received_at,'author':{'user_openid':scope.sender}})
            event.bot = SimpleNamespace(api=SimpleNamespace(_http=SimpleNamespace(_token=SimpleNamespace(app_id='fixture-app'))))
            event.message_str = '关联身份'; stopped=[]; sent=[]
            event.stop_event = lambda:stopped.append(True)
            async def send(target, chain):
                self.assertEqual(target.kind,'private');self.assertEqual(target.address,'private-a')
                sent.append(chain.chain[0].text)
            obj._send = send
            def forbidden(*args,**kw):self.fail('identity command escaped into history/points/model')
            obj._record_user_turn = forbidden; ns['_points_charge'] = forbidden
            await obj.gate(event)
            self.assertEqual(len(stopped),1);self.assertEqual(len(sent),1)
            self.assertRegex(sent[0],r'关联身份 [A-Z2-7]{16}')
            self.assertFalse((Path(root)/'history.json').exists())
            self.assertFalse(event.get_extra('_dsh_admitted'))
            before=(Path(root)/'user_directory_v1.json').read_bytes()
            ns['_conf'] = lambda key:False;event.message_str='设置称呼 不应修改'
            await obj.gate(event)
            self.assertEqual((Path(root)/'user_directory_v1.json').read_bytes(),before)
            self.assertEqual(len(sent),1)


if __name__ == '__main__': unittest.main()
