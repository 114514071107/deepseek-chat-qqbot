"""Actual capture/completion methods; all content, senders and files are fixtures."""
import tempfile
from types import SimpleNamespace
import unittest
import asyncio
import json
from pathlib import Path
from repair_pipeline_support import load_pipeline, ResultChain
from test_repair_session_scope import ScopeEvent
from qq_delivery import DeliveryResult, failure
from task_runtime import work_context


class ReplyCompletionRegression(unittest.IsolatedAsyncioTestCase):
    def setup_reply(self,tmp,text,voice=False):
        obj,ns=load_pipeline(tmp,names=('capture','_clear_text_result','_set_first_bubble_result','_voice_reply'),guarded=True)
        ns['random']=SimpleNamespace(random=lambda:1,uniform=lambda *a:0)
        ns['_load']=lambda *a:{}
        obj._perm=lambda *a:True
        obj._drip_interval=lambda:(0,0)
        event=ScopeEvent(); scope=obj._scope(event)
        obj.run_active[scope.key]=1
        return obj,ns,event,SimpleNamespace(result_chain=ResultChain(text))

    async def test_capture_never_commits_generated_text_before_platform_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp)
            event=ScopeEvent();scope=obj._scope(event)
            await obj.capture(event,SimpleNamespace(result_chain=ResultChain('first\n\nsecond')))
            self.assertEqual(obj.h.get(scope.key,[]),[],'generated content was recorded as sent')

    async def test_pure_sticker_has_a_current_turn_completion_instead_of_callback_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp)
            ns['_pick_sticker']=lambda q:dict(pack='fixture',rel='happy.png',tag='happy',caption='fixture')
            event=ScopeEvent();scope=obj._scope(event)
            await obj.capture(event,SimpleNamespace(result_chain=ResultChain('动作：表情 得意')))
            self.assertIsNotNone(event.get_extra('_dsh_reply_plan'),'empty-chain reply has no completion owner')

    async def test_partial_failure_only_commits_accepted_bubble_in_all_histories(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns,event,resp=self.setup_reply(tmp,'first\n\nsecond')
            sent=[]
            async def send(target,chain):
                sent.append(chain.chain[0].text)
                return DeliveryResult('accepted',message_id='one',seq=1) if len(sent)==1 else failure('failed','message','permission')
            obj._send=send
            await obj.capture(event,resp);key=event.get_extra('_dsh_scope').key
            obj.run_active[key]=1
            await obj._complete_reply(event)
            self.assertEqual(sent,['first','second'])
            self.assertEqual([h['text'] for h in obj.h[key]],['first'])
            self.assertEqual([h['text'] for h in map(json.loads,(Path(tmp)/'archive.jsonl').read_text().splitlines())],['first'])
            self.assertEqual(json.loads((Path(tmp)/'history.json').read_text())[key][0]['delivery']['message_id'],'one')
            self.assertNotIn(key,obj.run_active);self.assertTrue(event.get_extra('_dsh_reply_plan').finished)
            await obj._complete_reply(event);self.assertEqual(len(sent),2)

    async def test_first_failure_and_unknown_do_not_save_or_retry(self):
        for result in (failure('failed','message','permission'),failure('unknown','message','network')):
            with self.subTest(status=result.status),tempfile.TemporaryDirectory() as tmp:
                obj,ns,event,resp=self.setup_reply(tmp,'first\n\nsecond')
                sent=[]
                async def send(*a):sent.append(a);return result
                obj._send=send
                await obj.capture(event,resp);await obj._complete_reply(event)
                self.assertEqual(len(sent),1);self.assertEqual(obj.h,{})
                self.assertFalse((Path(tmp)/'archive.jsonl').exists())

    async def test_voice_success_then_next_turn_and_synthesis_or_media_failures_fallback(self):
        for scenario in ('success','absent','synthesis','upload','message','unknown','permission'):
            with self.subTest(scenario=scenario),tempfile.TemporaryDirectory() as tmp:
                obj,ns,event,resp=self.setup_reply(tmp,'原来的完整文字\n动作：语音')
                sent=[]
                async def synth(*a):
                    if scenario in ('absent','synthesis'):raise ConnectionError('fixture')
                    return 'media/voice/fixture.wav'
                obj._synthesize_voice=synth
                async def send(target,chain):
                    kind='text' if hasattr(chain.chain[0],'text') else 'voice';sent.append(kind)
                    if kind=='voice' and scenario in ('upload','message'):return failure('failed',scenario,'media')
                    if kind=='voice' and scenario in ('unknown','permission'):return failure(scenario if scenario=='unknown' else 'failed','message','network' if scenario=='unknown' else 'permission')
                    return DeliveryResult('accepted',message_id='accepted-'+kind+'-'+str(len(sent)))
                obj._send=send
                await obj.capture(event,resp);await obj._complete_reply(event)
                key=event.get_extra('_dsh_scope').key
                expected=['voice'] if scenario in ('success','unknown','permission') else ['text'] if scenario in ('absent','synthesis') else ['voice','text']
                self.assertEqual(sent,expected);self.assertNotIn(key,obj.run_active)
                hist=obj.h.get(key,[])
                self.assertEqual(len(hist),0 if scenario in ('unknown','permission') else 1)
                if hist:
                    self.assertEqual(hist[0]['text'],'原来的完整文字')
                    self.assertEqual('voice' in hist[0],scenario=='success')
                    archive=json.loads((Path(tmp)/'archive.jsonl').read_text(encoding='utf-8').splitlines()[0])
                    self.assertEqual(archive['id'],hist[0]['id']);self.assertEqual(archive.get('voice'),hist[0].get('voice'))
                next_event=ScopeEvent();next_event.message_obj.message_id='next'
                await obj.capture(next_event,SimpleNamespace(result_chain=ResultChain('下一轮')))
                await obj._complete_reply(next_event)
                self.assertEqual(obj.h[key][-1]['text'],'下一轮')

    async def test_pure_sticker_is_consumed_once_and_never_leaks_to_next_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns,event,resp=self.setup_reply(tmp,'动作：表情 得意')
            ns['_pick_sticker']=lambda q:dict(pack='fixture',rel='happy.png',tag='happy',caption='happy')
            sends=[]
            async def sticker(target,row):sends.append((target,row));return DeliveryResult('accepted',message_id='image')
            obj._send_sticker_row=sticker
            await obj.capture(event,resp);self.assertEqual(resp.result_chain.chain,[])
            await obj._complete_reply(event)
            key=event.get_extra('_dsh_scope').key
            self.assertEqual(len(sends),1);self.assertNotIn(key,obj.pending_sticker)
            self.assertEqual(obj.h[key][0]['sticker'],'sticker_packs/fixture/happy.png')
            next_event=ScopeEvent();next_event.message_obj.message_id='next'
            await obj.capture(next_event,SimpleNamespace(result_chain=ResultChain('')))
            await obj._complete_reply(next_event);self.assertEqual(len(sends),1)

    async def test_old_completion_cancel_and_two_scenes_cannot_clear_or_attach_new_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns,event,resp=self.setup_reply(tmp,'first\n\nsecond')
            started=asyncio.Event();sent=[]
            async def send(target,chain):
                sent.append(target)
                if len(sent)==2: started.set();await asyncio.Event().wait()
                return DeliveryResult('accepted',message_id='first')
            obj._send=send
            await obj.capture(event,resp)
            old=asyncio.create_task(obj._complete_reply(event));await started.wait()
            new_event=ScopeEvent();new_event.message_obj.message_id='new'
            await obj.capture(new_event,SimpleNamespace(result_chain=ResultChain('new')))
            key=event.get_extra('_dsh_scope').key;obj.run_active[key]=999
            await asyncio.gather(old,return_exceptions=True)
            self.assertEqual(obj.run_active[key],999)
            other_event=ScopeEvent(group='another-group')
            await obj.capture(other_event,SimpleNamespace(result_chain=ResultChain('group')))
            await obj._complete_reply(other_event)
            self.assertEqual(obj.h[key][0]['text'],'first')
            group=other_event.get_extra('_dsh_scope')
            self.assertEqual(obj.h[group.key][0]['source']['group'],'another-group')
            self.assertNotEqual(group.key,key)
            obj._finish_reply(new_event);self.assertNotIn(key,obj.run_active)

    async def test_history_failure_does_not_turn_platform_acceptance_into_send_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns,event,resp=self.setup_reply(tmp,'accepted')
            receipt=DeliveryResult('accepted',message_id='one')
            async def send(*a):return receipt
            obj._send=send
            await obj.capture(event,resp)
            ns['_archive_append']=lambda *a:(_ for _ in ()).throw(OSError('fixture write failure'))
            await obj._complete_reply(event)
            self.assertEqual(receipt.status,'accepted');self.assertEqual(receipt.persistence['archive'],'failed')
            self.assertEqual(receipt.persistence['rolling'],'saved')
            self.assertEqual(len(obj.h[event.get_extra('_dsh_scope').key]),1)

    async def test_voice_disabled_while_synthesizing_cannot_send_voice_or_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns,event,resp=self.setup_reply(tmp,'text\n动作：语音')
            enabled=True;entered=asyncio.Event();release=asyncio.Event();sends=[]
            obj.runtime.allowed=lambda key,feature:enabled or feature!='voice'
            async def synth(*a):entered.set();await release.wait();return 'media/voice/fixture.wav'
            obj._synthesize_voice=synth
            async def send(*a):sends.append(a);return DeliveryResult('accepted',message_id='bad')
            obj._send=send
            await obj.capture(event,resp)
            task=asyncio.create_task(obj._complete_reply(event));await entered.wait()
            enabled=False;release.set()
            await asyncio.gather(task,return_exceptions=True)
            self.assertEqual(sends,[])

    async def test_nontext_response_and_preserved_components_are_consumed_in_current_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns,event,resp=self.setup_reply(tmp,'')
            component=SimpleNamespace(type='Image',file='fixture.png');resp.result_chain.chain=[component]
            sent=[]
            async def send(target,chain):sent.extend(chain.chain);return DeliveryResult('accepted',message_id='media')
            obj._send=send
            await obj.capture(event,resp);await obj._complete_reply(event)
            self.assertEqual(sent,[component])

    async def test_late_old_hook_cannot_retake_cleanup_ownership_from_new_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns,old,resp=self.setup_reply(tmp,'old')
            await obj.capture(old,resp)
            new=ScopeEvent();new.message_obj.message_id='new'
            await obj.capture(new,SimpleNamespace(result_chain=ResultChain('new')))
            key=new.get_extra('_dsh_scope').key;obj.run_active[key]=999
            try:await obj.capture(old,resp)
            except asyncio.CancelledError:pass
            obj._finish_reply(old)
            self.assertEqual(obj.run_active.get(key),999)
            self.assertEqual(obj.request_owners[key],new.get_extra('_dsh_work').request)

    async def test_console_send_is_explicit_proactive_and_propagates_failure_or_unknown(self):
        from state_store import StateController
        from session_scope import Scope
        for status in ('accepted','failed','unknown','skipped'):
            with self.subTest(status=status),tempfile.TemporaryDirectory() as tmp:
                obj,ns=load_pipeline(tmp,names=('_admin_send',),guarded=True)
                scope=Scope('qq_official','bot','self','user','group','old-trigger',False,received_at=1)
                obj.scopes[scope.key]=scope.source();calls=[]
                async def send(target,chain,**kw):
                    calls.append((target,kw));return DeliveryResult(status,message_id='receipt' if status=='accepted' else '')
                obj._send=send
                state=StateController(obj,tmp,clear_framework=lambda key:asyncio.sleep(0))
                result=await state.apply('send',{'target_key':scope.key,'kind':'group','instance':'bot','text':'fixture'})
                self.assertEqual(calls[0][1],{'mode':'proactive'})
                self.assertEqual(result['ok'],status=='accepted');self.assertEqual(result['delivery']['status'],status)
                self.assertEqual(len(obj.h.get(scope.key,[])),int(status=='accepted'))

    async def test_buffered_event_with_shared_token_cannot_finish_main_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp,names=('capture','post_send','_clear_text_result','_set_first_bubble_result'),guarded=True)
            first=ScopeEvent();await obj.capture(first,SimpleNamespace(result_chain=ResultChain('first')))
            key=first.get_extra('_dsh_scope').key
            obj.batch_wait[key]=123;obj.run_active[key]=999;obj.pending_sticker[key]=['owned-by-first']
            buffered=ScopeEvent();buffered.message_obj.message_id='second'
            await obj.post_send(buffered)  # a second managed callback shares batch token, like gate
            self.assertEqual(buffered.get_extra('_dsh_work').request,first.get_extra('_dsh_work').request)
            obj._finish_reply(buffered)
            self.assertEqual(obj.batch_wait.get(key),123)
            self.assertEqual(obj.run_active.get(key),999)
            self.assertEqual(obj.pending_sticker.get(key),['owned-by-first'])

    async def test_mixed_media_failure_falls_back_to_text_once_but_unknown_does_not(self):
        for status in ('failed','unknown'):
            with self.subTest(status=status),tempfile.TemporaryDirectory() as tmp:
                obj,ns,event,resp=self.setup_reply(tmp,'original text')
                media=SimpleNamespace(type='Image',file='fixture.png');resp.result_chain.chain.insert(0,media)
                sent=[]
                async def send(target,chain):
                    sent.append(chain)
                    return failure(status,'message','media') if len(sent)==1 else DeliveryResult('accepted',message_id='text')
                obj._send=send
                await obj.capture(event,resp);await obj._complete_reply(event)
                self.assertEqual(len(sent),2 if status=='failed' else 1)
                hist=obj.h.get(event.get_extra('_dsh_scope').key,[])
                self.assertEqual([h['text'] for h in hist],['original text'] if status=='failed' else [])

    async def test_unknown_receipt_is_durable_outside_dialogue_and_archive_delete_is_scoped(self):
        from qq_delivery import QQDelivery
        from state_store import read_json,write_json,StateController
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns,event,resp=self.setup_reply(tmp,'unsent-generated-secret')
            self.assertTrue(callable(getattr(obj,'_record_delivery_result',None)),'delivery outcomes lack durable metadata')
            ns.update(_load=read_json,_save=write_json)
            async def api(*a):raise TimeoutError('fixture-token must never persist')
            async def parse(chain):return chain.chain[0].text,None,None,None,None,None,None
            context=SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[SimpleNamespace(meta=lambda:SimpleNamespace(id='bot-one',name='qq_official'))]))
            obj.delivery=QQDelivery(context,request=api,parse=parse,audit=obj._record_delivery_result)
            async def send(target,chain):return await obj.delivery.send(target,chain)
            obj._send=send
            await obj.capture(event,resp);await obj._complete_reply(event)
            key=event.get_extra('_dsh_scope').key
            path=Path(tmp)/'delivery_receipts_v2.json';audit=read_json(path,{})
            self.assertEqual(audit[key][0]['status'],'unknown');self.assertEqual(obj.h,{})
            self.assertNotIn('unsent-generated-secret',path.read_text(encoding='utf-8'))
            self.assertNotIn('fixture-token',path.read_text(encoding='utf-8'))
            audit['other']=[{'status':'unknown'}];write_json(path,audit)
            state=StateController(obj,tmp,clear_framework=lambda key:asyncio.sleep(0))
            result=await state.delete(key,['archive'])
            self.assertTrue(result['ok']);self.assertEqual(read_json(path,{})[key],[])
            self.assertEqual(read_json(path,{})['other'],[{'status':'unknown'}])

    async def test_same_sender_simultaneous_private_and_group_voice_media_remain_request_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns,private,resp=self.setup_reply(tmp,'private text\n动作：语音')
            group=ScopeEvent(group='group');group.message_obj.message_id='group-trigger'
            await obj.capture(private,resp)
            await obj.capture(group,SimpleNamespace(result_chain=ResultChain('group text\n动作：语音')))
            scopes=[private.get_extra('_dsh_scope'),group.get_extra('_dsh_scope')]
            async def synth(uid,text):return 'media/voice/'+uid+'.wav'
            entered=[];release=asyncio.Event()
            async def send(target,chain):
                entered.append((target,chain.chain[0].file))
                if len(entered)==2:release.set()
                await release.wait()
                return DeliveryResult('accepted',message_id=target.kind)
            obj._synthesize_voice=synth;obj._send=send
            await asyncio.gather(obj._complete_reply(private),obj._complete_reply(group))
            for scope,text in zip(scopes,['private text','group text']):
                row=obj.h[scope.key][0]
                self.assertEqual(row['text'],text)
                self.assertEqual(row['voice'],'media/voice/'+scope.key+'.wav')
                self.assertEqual(row['delivery']['message_id'],scope.target.kind)
                self.assertEqual(row['source']['group'],scope.group)
            archived=[json.loads(line) for line in (Path(tmp)/'archive.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual({row['id'] for row in archived},{obj.h[s.key][0]['id'] for s in scopes})

    async def test_framework_save_failure_is_separate_from_api_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns,event,resp=self.setup_reply(tmp,'accepted')
            receipt=DeliveryResult('accepted',message_id='accepted')
            async def send(*a):return receipt
            obj._send=send
            await obj.capture(event,resp);await obj._complete_reply(event)
            async def fail(*a,**kw):raise OSError('fixture storage error')
            obj.context=SimpleNamespace(conversation_manager=SimpleNamespace(update_conversation=fail))
            await obj._persist_framework_reply(event,SimpleNamespace(conversation=SimpleNamespace(cid='fixture')))
            self.assertEqual(receipt.status,'accepted');self.assertEqual(receipt.persistence['framework'],'failed')
            self.assertEqual(event.get_extra('_dsh_framework_persistence'),'failed')


if __name__=='__main__':unittest.main()
