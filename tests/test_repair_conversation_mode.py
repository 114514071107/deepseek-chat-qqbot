"""Conversation ownership is independent of actor authorization/quota."""
import tempfile,unittest,json,sys
from pathlib import Path
from repair_pipeline_support import load_pipeline
from test_repair_session_scope import ScopeEvent
from session_scope import bind_scope,Scope
from context_window import build_window
class ConversationMode(unittest.TestCase):
 def test_group_context_shares_speakers_but_not_other_group_or_private(self):
  a=bind_scope(ScopeEvent('a','G1'));b=bind_scope(ScopeEvent('b','G1'));other=bind_scope(ScopeEvent('a','G2'));private=bind_scope(ScopeEvent('a'))
  self.assertNotEqual(a.key,b.key);self.assertEqual(a.conversation_key,b.conversation_key)
  self.assertNotEqual(a.memory_key,b.memory_key);self.assertNotEqual(a.conversation_key,private.conversation_key)
  rows=[dict(id=str(i),role='user',text=tag,source=s.source()) for i,(s,tag) in enumerate([(a,'G1-A'),(b,'G1-B'),(other,'G2-SECRET'),(private,'PRIVATE-SECRET')])]
  w=build_window(rows,[],a);text=json.dumps(w,ensure_ascii=False)
  self.assertIn('G1-A',text);self.assertIn('G1-B',text);self.assertNotIn('G2-SECRET',text);self.assertNotIn('PRIVATE-SECRET',text)
  self.assertIn('说话者=b',text);self.assertEqual(w['summary']['scope'],a.conversation_key)
 def test_framework_session_is_group_while_event_target_and_sender_stay_bound(self):
  ea,eb=ScopeEvent('a','G'),ScopeEvent('b','G');a,b=bind_scope(ea),bind_scope(eb)
  self.assertEqual(ea.session_id,eb.session_id);self.assertNotEqual(a.key,b.key);self.assertEqual(a.target.address,'G');self.assertEqual(b.sender,'b')
 def test_profiles_only_one_group_and_private_no_union_or_member_profiles(self):
  from user_profiles import record_profile
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as tmp:
   for sender,group in [('a','G'),('b','G'),('a','')]:
    e=ScopeEvent(sender,group);s=bind_scope(e);e.message_obj.raw_message=SimpleNamespace(raw_data={'id':s.message_id,'author':{('member_openid' if group else 'user_openid'):sender,'union_openid':''},**({'group_openid':group} if group else {})})
    record_profile(e,s,tmp)
   store=json.loads((Path(tmp)/'conversation_profiles_v1.json').read_text());self.assertEqual(len(store['sources']),2)
   group=next(v for v in store['sources'].values() if v['kind']=='group');self.assertNotIn('sender',group);self.assertNotIn('identity',group)

 def test_group_delete_resolves_all_actors_and_keeps_other_conversations(self):
  import asyncio
  from state_store import StateController,write_json,read_json
  async def run():
   with tempfile.TemporaryDirectory() as tmp:
    obj,ns=load_pipeline(tmp,names=());obj.th={};obj.t_path=str(Path(tmp)/'thoughts_v2.json')
    a=obj._scope(ScopeEvent('a','G'));b=obj._scope(ScopeEvent('b','G'));p=obj._scope(ScopeEvent('a'))
    obj.groups[a.group_key]=[{'role':'user','text':'DELETE-ME','id':'del','source':a.source()}];write_json(obj.group_path,obj.groups)
    obj.h={a.key:[{'role':'user','text':'a'}],b.key:[{'role':'user','text':'b'}],p.key:[{'role':'user','text':'PRIVATE-KEEP'}]};write_json(obj.h_path,obj.h)
    mem=Path(tmp)/'memories';mem.mkdir();(mem/(a.conversation_key+'.md')).write_text('GROUP-DELETE');(mem/(p.key+'.md')).write_text('PRIVATE-KEEP')
    state=StateController(obj,tmp,lambda k:asyncio.sleep(0));result=await state.delete(a.conversation_key,['rolling','memory'])
    self.assertTrue(result['ok'],result);self.assertEqual(obj.h[p.key][0]['text'],'PRIVATE-KEEP');self.assertEqual(obj.h[a.key],[]);self.assertEqual(obj.h[b.key],[])
    self.assertEqual(obj._dialogue_rows(a.key),[]);self.assertEqual(obj.groups.get(a.group_key,[]),[]);self.assertFalse((mem/(a.conversation_key+'.md')).exists());self.assertTrue((mem/(p.key+'.md')).exists());await obj.runtime.stop();await obj.resources.close()
  asyncio.run(run())

 def test_group_partial_memory_failure_is_not_success_and_invalid_layers_rejected(self):
  import asyncio
  from state_store import StateController
  from unittest.mock import AsyncMock
  async def run():
   with tempfile.TemporaryDirectory() as tmp:
    obj,ns=load_pipeline(tmp,names=());obj.th={};a=obj._scope(ScopeEvent('a','G'));state=StateController(obj,tmp,lambda k:asyncio.sleep(0))
    state._delete_layer=AsyncMock(return_value={'status':'partial','retained':'failed memory'})
    result=await state.delete(a.group_key,['memory']);self.assertFalse(result['ok']);self.assertEqual(result['layers']['memory']['status'],'partial')
    with self.assertRaises(ValueError):await state.delete(a.group_key,['not-a-layer'])
    await obj.runtime.stop();await obj.resources.close()
  asyncio.run(run())

 def test_member_arriving_while_delete_waits_for_state_lock_is_revoked(self):
  import asyncio
  from state_store import StateController
  async def run():
   with tempfile.TemporaryDirectory() as tmp:
    obj,ns=load_pipeline(tmp,names=());obj.th={};a=obj._scope(ScopeEvent('a','G'));state=StateController(obj,tmp,lambda k:asyncio.sleep(0))
    await state.lock.acquire();deletion=asyncio.create_task(state.delete(a.group_key,['memory']));await asyncio.sleep(0)
    b=obj._scope(ScopeEvent('b','G'));started=asyncio.Event();release=asyncio.Event();writes=[]
    async def stale():started.set();await release.wait();writes.append(True)
    work=obj.runtime.spawn(stale(),key=b.key);await started.wait();state.lock.release();await deletion;release.set();await asyncio.gather(work,return_exceptions=True)
    self.assertEqual(writes,[]);self.assertTrue(work.cancelled());await obj.runtime.stop();await obj.resources.close()
  asyncio.run(run())

class ActualModelConversation(unittest.IsolatedAsyncioTestCase):
 async def test_actual_inject_and_group_extraction_never_read_or_create_member_memory(self):
  import ast
  from types import SimpleNamespace
  from state_store import read_json,write_json,write_text
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);obj,ns=load_pipeline(tmp,names=('inject','_extract_notes','recall','_th'))
   obj.scopes_path=str(root/'scopes_v2.json')
   ns['_jf']=lambda uid,name:str(root/(name+'_'+uid+'.json'))
   del obj._th
   obj.th={}
   self.addAsyncCleanup(obj.runtime.stop);self.addAsyncCleanup(obj.resources.close)
   ns.update(_load=read_json,_save=write_json,write_text=write_text)
   tree=ast.parse((Path(__file__).resolve().parents[1]/'plugin/astrbot_plugin_dsh_soul/main.py').read_text(encoding='utf-8'))
   fns=[n for n in tree.body if getattr(n,'name','') in ('_notes_path','_read_notes','_read_memes','_append_note','_remove_note')]
   exec(compile(ast.Module(body=fns,type_ignores=[]),'<actual notes>','exec'),ns)
   a=obj._scope(ScopeEvent('a','G1'));b=obj._scope(ScopeEvent('b','G1'));other=obj._scope(ScopeEvent('a','G2'));private=obj._scope(ScopeEvent('a'))
   (root/'memories').mkdir();(root/'persona.md').write_text('synthetic persona')
   for scope,tag in [(a,'GROUP1-NOTES'),(other,'GROUP2-NOTES'),(private,'OLD-MIXED-PRIVATE')]: (root/'memories'/(scope.conversation_key+'.md')).write_text(tag)
   (root/'memories'/(b.memory_key+'.md')).write_text('RETIRED-MEMBER-SECRET')
   # Use the actual stopped-instance cleanup contract, then create new private-only notes.
   sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
   from conversation_cleanup import plan,apply_plan
   with tempfile.TemporaryDirectory() as backup:
    apply_plan(root,backup,plan(root))
    ns['_append_note'](private.key,'PRIVATE-NOTES')
    self.assertFalse((root/'memories'/(b.memory_key+'.md')).exists())
    self.assertEqual(plan(root)['actions'],[])
   (root/'memes').mkdir()
   for scope,tag in [(a,'GROUP1'),(other,'GROUP2'),(private,'PRIVATE')]:
    (root/'memes'/(scope.conversation_key+'.md')).write_text(tag+'-LEARNED')
    obj.th[scope.conversation_key]=[dict(src='chat',t=__import__('time').time(),text=tag+'-THOUGHT')]
   obj.groups[a.group_key]=[dict(id='a-old',role='user',text='G1-A-SPEECH',source=dict(a.source(),message_id='old-a')),dict(id='b-old',role='user',text='G1-B-SPEECH',source=dict(b.source(),message_id='old-b'))]
   obj.groups[other.group_key]=[dict(id='g2',role='user',text='GROUP2-SECRET',source=dict(other.source(),message_id='old-c'))]
   req=SimpleNamespace(prompt='new',contexts=[],system_prompt='',func_tool=None)
   await obj.inject(ScopeEvent('a','G1'),req);actual=str(req.contexts)+req.system_prompt
   for tag in ['G1-A-SPEECH','G1-B-SPEECH','GROUP1-NOTES','GROUP1-LEARNED','GROUP1-THOUGHT']:self.assertIn(tag,actual)
   for tag in ['GROUP2-SECRET','GROUP2-NOTES','PRIVATE-NOTES','RETIRED-MEMBER-SECRET','GROUP2-LEARNED','PRIVATE-LEARNED','GROUP2-THOUGHT','PRIVATE-THOUGHT']:self.assertNotIn(tag,actual)
   recalled=await obj.recall(ScopeEvent('b','G1'),'NOTES')
   self.assertIn('GROUP1-NOTES',recalled);self.assertNotIn('GROUP2-NOTES',recalled);self.assertNotIn('PRIVATE-NOTES',recalled)
   async def chat(*args,**kw):
    self.assertIn('不建立',kw['system_prompt']);self.assertNotIn('PRIVATE-NOTES',kw['prompt']);return SimpleNamespace(completion_text='增：群共同约定')
   obj._chat=chat;await obj._extract_notes(b.key)
   self.assertIn('群共同约定',(root/'memories'/(a.group_key+'.md')).read_text())
   self.assertFalse((root/'memories'/(b.key+'.md')).exists());self.assertFalse((root/'memories'/(b.memory_key+'.md')).exists())
   self.assertEqual(plan(root)['actions'],[])  # later group extraction never resurrects retired member storage
   req=SimpleNamespace(prompt='new',contexts=[],system_prompt='',func_tool=None);await obj.inject(ScopeEvent('a'),req)
   actual=str(req.contexts)+req.system_prompt;self.assertIn('PRIVATE-NOTES',actual);self.assertNotIn('GROUP1-NOTES',actual);self.assertNotIn('G1-B-SPEECH',actual)
   for tag in ['PRIVATE-LEARNED','PRIVATE-THOUGHT']:self.assertIn(tag,actual)
   for tag in ['GROUP1-LEARNED','GROUP1-THOUGHT','GROUP2-LEARNED','GROUP2-THOUGHT']:self.assertNotIn(tag,actual)
   self.assertEqual(read_json(root/('session_'+a.group_key+'.json'),{})['context']['scope'],a.group_key)
   self.assertEqual(read_json(root/('session_'+private.key+'.json'),{})['context']['scope'],private.key)

class NewStorage(unittest.TestCase):
 def test_new_private_note_with_same_bare_group_sender_can_be_written_without_binding(self):
  from conversation_storage import prepare_new_memory,memory_available
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);a=Scope('qq_official','inst','bot','same','group','m',False);p=Scope('qq_official','inst','bot','same','','p',True)
   (root/'scopes_v2.json').write_text(json.dumps({a.key:a.source(),p.key:p.source()}))
   self.assertTrue(prepare_new_memory(root,p.key));self.assertTrue(memory_available(root,p.key));(root/'memories').mkdir();(root/'memories'/(p.key+'.md')).write_text('NEW-PRIVATE')
   self.assertTrue(memory_available(root,p.key))
