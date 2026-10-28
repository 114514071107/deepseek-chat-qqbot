"""Exercise actual async helpers with revocation during await, rather than only the token API."""
import asyncio
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from repair_pipeline_support import load_pipeline
from session_scope import bind_scope
from state_store import StateController, read_json, write_json
from task_runtime import Runtime
from test_repair_session_scope import ScopeEvent


class PipelineInterleavings(unittest.IsolatedAsyncioTestCase):
    async def test_owner_qq_switch_uses_same_revocation_and_can_reenable(self):
        import re
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp,patch.dict(__import__('os').environ,DSH_OWNER_PLATFORM_ID='bot-one'):
            names=('gate','_entry_feature','_allowed','_send','_record_gate_turn')
            obj,ns=load_pipeline(tmp,names=names,guarded=True)
            owner=obj._scope(ScopeEvent('owner'));friend=obj._scope(ScopeEvent('friend'))
            obj.runtime=Runtime(obj._allowed);obj.sil={}
            obj.state=StateController(obj,tmp,clear_framework=lambda key:asyncio.sleep(0))
            ns.update(_load=read_json,_save=write_json,MASTER_SWITCH_RE=re.compile(r'^总开关 (开|关)$'),
                      MessageChain=lambda **kw:kw)
            ns['_conf']=lambda key:read_json(Path(tmp)/'dsh_soul_conf.json',{}).get(key,True)
            sent=[]
            from qq_delivery import QQDelivery
            async def send(*args):sent.append(args);return 200,{'id':'fixture'}
            obj.context=SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[SimpleNamespace(meta=lambda:SimpleNamespace(id='bot-one',name='qq_official'))]),send_message=send)
            async def parse(chain): return chain['chain'][0].text,None,None,None,None,None,None
            obj.delivery=QQDelivery(obj.context,request=send,parse=parse)
            async def waiting():await asyncio.Event().wait()
            old=obj.runtime.spawn(waiting(),key=friend.key)
            for message in ('总开关 关','总开关 开'):
                event=ScopeEvent('owner');event.message_str=message;event.message_obj.message_id='synthetic-'+message;event.stop_event=lambda:None
                await obj.gate(event)
            await asyncio.gather(old,return_exceptions=True)
            self.assertTrue(old.cancelled());self.assertEqual(len(sent),2)
            self.assertTrue(read_json(Path(tmp)/'dsh_soul_conf.json',{})['enabled'])
            await obj.runtime.stop()

    async def test_disabling_reminder_during_model_wait_keeps_global_desire_loop_alive(self):
        with tempfile.TemporaryDirectory() as tmp:
            names=('_desire_loop','_check_reminders','_send_reminder','_chat','_spawn','_allowed')
            obj,ns=load_pipeline(tmp,names=names,guarded=True);scope=obj._scope(ScopeEvent('owner'))
            obj.sil={};obj.rm_path=str(Path(tmp)/'reminders.json');obj._owner_target=lambda:scope
            ns['_conf']=lambda key:read_json(Path(tmp)/'dsh_soul_conf.json',{}).get(key,True)
            obj.runtime=Runtime(obj._allowed);ticks=[];started=asyncio.Event();release=asyncio.Event()
            async def tick(): ticks.append(True)
            async def model(**kw):started.set();await release.wait();return SimpleNamespace(completion_text='fixture')
            async def short_sleep(seconds): await asyncio.sleep(0.005)
            obj._desire_tick=tick;obj.context=SimpleNamespace(get_using_provider=lambda:SimpleNamespace(text_chat=model))
            ns.update(REMINDER_SCENES={'fixture':'fixture'},_in_window=lambda *a:True,_usage_add=lambda *a:None)
            ns['asyncio']=SimpleNamespace(sleep=short_sleep,wait_for=asyncio.wait_for,current_task=asyncio.current_task)
            loop=obj._spawn(obj._desire_loop());await asyncio.wait_for(started.wait(),1)
            state=StateController(obj,tmp,clear_framework=lambda key:asyncio.sleep(0))
            await state.apply('switch',{'key':'reminders','value':False});release.set();before=len(ticks)
            await asyncio.sleep(0.03)
            self.assertFalse(loop.done());self.assertGreater(len(ticks),before)
            await obj.runtime.stop()

    async def test_cancelled_admin_send_does_not_disable_management_channel(self):
        from admin_bridge import serve_inbox
        with tempfile.TemporaryDirectory() as tmp:
            runtime=Runtime(lambda *a:True);calls=[]
            async def apply(op,body):
                calls.append(op)
                if op=='send': raise asyncio.CancelledError('fixture scope revoked')
                return {'ok':True}
            task=runtime.spawn(serve_inbox(tmp,runtime,apply))
            await asyncio.sleep(0)
            import time
            for index,operation in enumerate(('send','switch')):
                name=('%032x'%index)+'.json'
                write_json(Path(tmp)/'admin_v2/requests'/name,{'instance':runtime.id,'deadline':time.time()+2,'operation':operation,'body':{}})
                response=Path(tmp)/'admin_v2/responses'/name
                for _ in range(50):
                    if response.exists():break
                    await asyncio.sleep(0.01)
                self.assertEqual(read_json(response,{})['ok'],index==1)
            self.assertEqual(calls,['send','switch']);self.assertFalse(task.done());await runtime.stop()

    async def test_real_summary_wait_is_cancelled_by_delete_without_restoring_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp,names=('_refresh_summary','_chat','_spawn'),guarded=True)
            scope=obj._scope(ScopeEvent()); obj.h[scope.key]=[dict(role='user',text='fixture')]
            obj.th={};obj.t_path=str(Path(tmp)/'thoughts_v2.json')
            obj.runtime=Runtime(lambda *a:True); started=asyncio.Event()
            actual_thread=obj._thread
            async def blocked_summary(fn,*args,**kw):
                started.set(); await asyncio.Event().wait()
                return await actual_thread(fn,*args,**kw)
            obj._thread=blocked_summary
            ns['_save']=write_json; ns['_load']=read_json; ns['_jf']=lambda key,name:str(Path(tmp)/(name+'_'+key+'.json'))
            task=obj._spawn(obj._refresh_summary(scope.key),key=scope.key)
            await started.wait()
            state=StateController(obj,tmp,clear_framework=lambda key:asyncio.sleep(0))
            result=await state.delete(scope.key,['summary'])
            self.assertTrue(result['ok']);self.assertTrue(task.cancelled())
            self.assertFalse(list(Path(tmp).glob('session_*.json')))
            await obj.runtime.stop()

    async def test_real_download_completion_after_stop_cannot_write_voice_or_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp,names=('_voice_reply','_thread','_spawn'),guarded=True)
            scope=obj._scope(ScopeEvent()); obj.runtime=Runtime(lambda *a:True)
            started=threading.Event(); release=threading.Event(); writes=[]; sends=[]
            def read(): started.set(); release.wait(2); return b'fake wave'
            obj._write_media=lambda *a:writes.append(a)
            async def send(*a): sends.append(a)
            obj._send=send; ns['json']=json
            with patch('urllib.request.urlopen',return_value=SimpleNamespace(read=read)):
                obj._spawn(obj._voice_reply(scope.target,scope.key,'fixture'),key=scope.key)
                await asyncio.to_thread(started.wait,2)
                await obj.runtime.stop();release.set();await asyncio.sleep(0.03)
            self.assertEqual(writes,[]);self.assertEqual(sends,[])

    async def test_real_kimi_cancellation_kills_and_reaps_only_fake_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp,names=('_run_kimi','_spawn'),guarded=True)
            scope=obj._scope(ScopeEvent());obj.runtime=Runtime(lambda *a:True)
            started=asyncio.Event(); killed=[]; reaped=[]
            async def communicate(): started.set(); await asyncio.Event().wait()
            async def wait(): reaped.append(True)
            proc=SimpleNamespace(returncode=None,communicate=communicate,kill=lambda:killed.append(True),wait=wait)
            async def create(*args,**kw): return proc
            ns.update(KIMI_CLI='never-run-fixture',KIMI_MODEL='fixture')
            with patch('asyncio.create_subprocess_exec',create):
                obj._spawn(obj._run_kimi('fixture',tmp,target=scope.target),key=scope.key)
                await started.wait();await obj.runtime.stop()
            self.assertEqual(killed,[True]);self.assertEqual(reaped,[True])

    async def test_new_scope_waits_for_delete_and_other_scope_can_continue(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp,names=()); a=obj._scope(ScopeEvent('a'));b=obj._scope(ScopeEvent('b'))
            obj.runtime=Runtime(lambda *a:True);obj.th={};obj.t_path=str(Path(tmp)/'thoughts_v2.json')
            entered=asyncio.Event(); release=asyncio.Event(); finished=[]
            async def clear(key): entered.set();await release.wait()
            state=StateController(obj,tmp,clear_framework=clear)
            deleting=asyncio.create_task(state.delete(a.key,['rolling']))
            await entered.wait()
            async def next_turn(key): await obj.runtime.ready(key);finished.append(key)
            waiting=asyncio.create_task(next_turn(a.key));await next_turn(b.key);await asyncio.sleep(0)
            self.assertEqual(finished,[b.key]);release.set();await deleting;await waiting
            self.assertEqual(finished,[b.key,a.key]);await obj.runtime.stop()

    async def test_state_changes_points_and_chat_do_not_restore_old_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp,names=('_save_thought',));scope=obj._scope(ScopeEvent())
            obj.runtime=Runtime(lambda *a:True);obj.th={};obj._th=lambda key:obj.th.setdefault(key,[])
            obj.names={};obj.blocked=set();obj.sil={};obj.t_path=str(Path(tmp)/'thoughts_v2.json')
            state=StateController(obj,tmp,clear_framework=lambda key:asyncio.sleep(0))
            self.assertTrue((await state.apply('points',dict(uid=scope.key,mode='set',value=10)))['ok'])
            self.assertTrue((await state.apply('name',dict(uid=scope.key,name='fixture name')))['ok'])
            self.assertEqual(obj.names[scope.key],'fixture name')
            await state.apply('user',dict(uid=scope.key,key='voice',value=False))
            await state.apply('points',dict(uid=scope.key,mode='add',value=2))
            self.assertEqual(read_json(Path(tmp)/'points_all.json',{})[scope.memory_key]['balance'],12)
            self.assertFalse(read_json(Path(tmp)/'friends_all.json',{})[scope.key]['voice'])
            await obj.runtime.stop()


if __name__=='__main__':unittest.main()
