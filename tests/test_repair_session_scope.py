"""Final request isolation. All records and identities here are fictional."""
import tempfile
from types import SimpleNamespace
import unittest
from repair_pipeline_support import load_pipeline


class ScopeEvent:
    def __init__(self, sender='a', group='', instance='bot-one', platform='qq_official'):
        self.sender=sender; self.group=group; self.instance=instance; self.platform=platform
        self.extra={}; self.session_id=group or sender; self.message_str='new question'
        self.message_obj=SimpleNamespace(message_id='fixture-msg',self_id='fixture-self',message=[])
    @property
    def unified_msg_origin(self): return f'{self.instance}:{"GroupMessage" if self.group else "FriendMessage"}:{self.session_id}'
    def get_sender_id(self): return self.sender
    def get_group_id(self): return self.group
    def get_platform_id(self): return self.instance
    def get_platform_name(self): return self.platform
    def is_private_chat(self): return not self.group
    def get_extra(self,key,default=None): return self.extra.get(key,default)
    def set_extra(self,key,value): self.extra[key]=value
    def is_stopped(self): return False


class SessionScopeRegression(unittest.IsolatedAsyncioTestCase):
    async def test_existing_explicit_denial_survives_new_conversation_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp,names=())
            scope=obj._scope(ScopeEvent('a'))
            table={'a':{'reply':False,'proactive':True}}
            ns['_load']=lambda *a:table
            self.assertFalse(obj._perm(scope.key,'reply'))
            self.assertFalse(obj._perm(scope.key,'proactive'))
            table[scope.key]={'reply':True}
            self.assertTrue(obj._perm(scope.key,'reply'))

    async def test_switching_groups_does_not_reset_search_cooldown(self):
        import time
        from types import SimpleNamespace
        from unittest.mock import patch
        from test_repair_permissions import load_methods,Event
        obj,ns=load_methods();obj.search_cd={};obj.tool_react_at={}
        first=Event();first.private=False;first.get_group_id=lambda:'g1'
        second=Event();second.private=False;second.get_group_id=lambda:'g2'
        for event in (first,second):obj.tool_react_at[obj._scope(event).key]=time.time()
        async def search(*args,**kw):return [{'title':'fixture-result','snippet':'fixture'}]
        ns['time']=time
        with patch.dict(__import__('sys').modules,websearch=SimpleNamespace(web_search=search)):
            self.assertIn('fixture-result',await obj.web_search(first,'fixture'))
            self.assertNotIn('fixture-result',await obj.web_search(second,'fixture'))

    async def test_private_learned_material_cannot_reappear_through_shared_meme_store(self):
        import ast, os
        from pathlib import Path
        from test_repair_permissions import load_methods,Event,PLUGIN
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_methods()
            tree=ast.parse((PLUGIN/'main.py').read_text(encoding='utf-8'))
            fn=next(n for n in tree.body if getattr(n,'name','')=='_read_memes')
            from state_store import write_text
            ns.update(DATA=tmp,write_text=write_text,_read_notes=lambda key:[],_archive_read=lambda key,**kwargs:[])
            exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'<real meme reader>','exec'),ns)
            await obj.learn_meme(Event('friend'), 'fixture', 'private-secret meaning')
            result=await obj.recall(Event('friend',False),'fixture private-secret')
            self.assertNotIn('private-secret',result)

    async def test_final_group_request_excludes_framework_legacy_and_private_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin,ns=load_pipeline(tmp)
            ns['_read_notes']=lambda uid:['PRIVATE-NOTE-SENTINEL']
            ( __import__('pathlib').Path(tmp)/'persona.md').write_text('fixture persona',encoding='utf-8')
            req=SimpleNamespace(prompt='new question',system_prompt='',contexts=[{'role':'user','content':'OTHER-SENDER-SENTINEL'}],func_tool=None)
            await plugin.inject(ScopeEvent(group='g1'),req)
            final=str(req.contexts)+req.prompt+req.system_prompt
            self.assertNotIn('OTHER-SENDER-SENTINEL',final)
            self.assertNotIn('PRIVATE-NOTE-SENTINEL',final)

    async def test_keys_separate_people_groups_private_and_instances(self):
        from session_scope import bind_scope
        events=[ScopeEvent('a','g1'),ScopeEvent('b','g1'),ScopeEvent('a','g2'),ScopeEvent('a'),ScopeEvent('a','g1','bot-two')]
        scopes=[bind_scope(e) for e in events]
        self.assertEqual(len({s.key for s in scopes}),5)
        self.assertEqual(scopes[0].group_key,scopes[1].group_key)
        self.assertNotEqual(scopes[0].group_key,scopes[2].group_key)
        self.assertEqual(scopes[0].memory_key,scopes[3].memory_key)
        self.assertEqual(events[0].session_id,scopes[0].key)
        self.assertEqual(bind_scope(events[0]),scopes[0])
        self.assertEqual(scopes[0].target.address,'g1')
        self.assertEqual(scopes[0].source()['sender'],'a')


if __name__=='__main__': unittest.main()
