"""Real history/scope methods, synthetic targets and receipts only."""
import asyncio
import tempfile
import unittest
from dataclasses import replace
from repair_pipeline_support import load_pipeline
from test_repair_session_scope import ScopeEvent
from task_runtime import work_context
from qq_delivery import DeliveryResult
from qq_delivery import QQDelivery
from types import SimpleNamespace
from state_store import read_json,write_json
from pathlib import Path


class OutboundOwnershipRegression(unittest.IsolatedAsyncioTestCase):
    async def test_empty_original_request_is_authoritative_when_repeating_receipt_under_later_context(self):
        with tempfile.TemporaryDirectory() as root:
            obj,ns=load_pipeline(root,names=('_send',));ns.update(_load=read_json,_save=write_json)
            scope=obj._scope(ScopeEvent())
            class Sender:
                async def send(_self,*args,**kw):return DeliveryResult('accepted',message_id='proactive')
            obj.delivery=Sender()
            with work_context(obj.runtime.token(scope.key,request='')):
                result=await obj._send(scope.target,object(),mode='proactive')
                obj._record_delivery_result(scope.target,result)
                row=obj._record_assistant_turn(scope.key,'proactive',result)
            with work_context(obj.runtime.begin(scope.key)):
                obj._record_delivery_result(scope.target,result)
            ledger=read_json(Path(root)/'delivery_receipts_v2.json',{})[scope.key]
            self.assertEqual(len(ledger),1);self.assertEqual(ledger[0]['request_id'],result.attempt_id)
            self.assertEqual(row['request_id'],result.attempt_id)

    async def test_delayed_callback_without_current_context_cannot_resurrect_revoked_history(self):
        with tempfile.TemporaryDirectory() as root:
            obj,_=load_pipeline(root,names=('_send',));scope=obj._scope(ScopeEvent());token=obj.runtime.begin(scope.key)
            class Sender:
                async def send(_self,*args,**kwargs):return DeliveryResult('accepted',message_id='late')
            obj.delivery=Sender()
            with work_context(token):result=await obj._send(scope.target,object())
            obj.runtime.invalidate(scope.key);obj.h.pop(scope.key,None)
            with self.assertRaises(asyncio.CancelledError):obj._record_assistant_turn(scope.key,'late',result)
            self.assertNotIn(scope.key,obj.h)

    async def test_parallel_groups_private_targets_media_and_late_callbacks_keep_frozen_relations(self):
        with tempfile.TemporaryDirectory() as root:
            obj,ns=load_pipeline(root,names=('_send',))
            ns.update(_load=read_json,_save=write_json)
            scopes=[obj._scope(ScopeEvent('person-A','group-A')),obj._scope(ScopeEvent('person-B')),
                    obj._scope(ScopeEvent('person-C','group-B')),obj._scope(ScopeEvent('person-D'))]
            tokens=[replace(obj.runtime.begin(s.key),source=s) for s in scopes]
            entered=[asyncio.Event() for _ in scopes];release=asyncio.Event();calls=[]
            async def request(platform,endpoint,payload):
                index=next(i for i,s in enumerate(scopes) if endpoint.endswith('/'+s.target.address+'/messages'))
                calls.append((index,payload));entered[index].set();await release.wait()
                return 200,{'id':'platform-out-'+str(index)}
            async def parse(chain):return chain.text,None,None,None,None,None,None
            platform=SimpleNamespace(meta=lambda:SimpleNamespace(id='bot-one',name='qq_official'))
            obj.delivery=QQDelivery(SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[platform])),request=request,parse=parse,audit=obj._record_delivery_result)
            async def send(i):
                with work_context(tokens[i]):return await obj._send(scopes[i].target,SimpleNamespace(text='PART-'+str(i)))
            tasks=[asyncio.create_task(send(i)) for i in range(4)]
            await asyncio.gather(*(e.wait() for e in entered))
            for s in scopes:obj.scopes[s.key]=replace(s,message_id='later-unrelated-inbound').source()
            release.set();results=await asyncio.gather(*tasks)
            for i,result in enumerate(results):
                # Delayed callback runs without a current event/token; it must use receipt provenance.
                row=obj._record_assistant_turn(scopes[i].key,'PART-'+str(i),result,media={'files':['files/synthetic.txt']})
                self.assertEqual(row['role'],'assistant');self.assertEqual(row['request_id'],tokens[i].request)
                self.assertEqual(row['source'],scopes[i].source());self.assertEqual(row['provenance']['target']['address'],scopes[i].target.address)
                self.assertEqual(row['files'],['files/synthetic.txt'])
                self.assertEqual(len(obj.h[scopes[i].key]),1)
            self.assertEqual(len(calls),4)
            stored=read_json(Path(root)/'history.json',{})
            self.assertEqual({r[0]['request_id'] for r in stored.values()},{t.request for t in tokens})
            receipts=read_json(Path(root)/'delivery_receipts_v2.json',{})
            self.assertEqual(sum(map(len,receipts.values())),4)
            self.assertTrue(all(row['persistence'].get('rolling')=='saved' for rows in receipts.values() for row in rows))

    async def test_proactive_unknown_failed_and_accepted_have_distinct_durable_outcomes(self):
        with tempfile.TemporaryDirectory() as root:
            obj,ns=load_pipeline(root,names=('_send',));ns.update(_load=read_json,_save=write_json)
            scopes=[obj._scope(ScopeEvent('p-'+str(i))) for i in range(3)]
            responses=[(200,{'id':'accepted'}),TimeoutError(),(403,{'code':'40034105'})]
            async def request(platform,endpoint,payload):
                self.assertNotIn('msg_id',payload)
                response=responses.pop(0)
                if isinstance(response,Exception):raise response
                return response
            async def parse(chain):return 'proactive',None,None,None,None,None,None
            obj.delivery=QQDelivery(SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[SimpleNamespace(meta=lambda:SimpleNamespace(id='bot-one',name='qq_official'))])),request=request,parse=parse,audit=obj._record_delivery_result)
            for s,status in zip(scopes,['accepted','unknown','failed']):
                with work_context(replace(obj.runtime.token(s.key,request=''),source=s)):
                    result=await obj._send(s.target,object(),mode='proactive')
                    row=obj._record_assistant_turn(s.key,'proactive',result)
                self.assertEqual(result.status,status);self.assertEqual(result.provenance['request_id'],'')
                self.assertEqual(result.provenance['source']['message_id'],'')
                self.assertEqual(row is not None,status=='accepted')
            ledger=read_json(Path(root)/'delivery_receipts_v2.json',{})
            self.assertEqual(sorted(row['status'] for rows in ledger.values() for row in rows),['accepted','failed','unknown'])

    async def test_a_new_attempt_with_same_platform_message_is_not_inserted_twice(self):
        with tempfile.TemporaryDirectory() as root:
            obj,_=load_pipeline(root,names=());scope=obj._scope(ScopeEvent())
            first=obj._record_assistant_turn(scope.key,'image',DeliveryResult('accepted',message_id='platform-id'),media={'images':['media/synthetic.png']})
            second=obj._record_assistant_turn(scope.key,'image',DeliveryResult('accepted',message_id='platform-id'))
            self.assertEqual(first['id'],second['id']);self.assertEqual(len(obj.h[scope.key]),1)

    async def test_accepted_callback_uses_sent_scope_not_mutable_latest_message(self):
        with tempfile.TemporaryDirectory() as root:
            obj,_=load_pipeline(root,names=('_send',))
            scope=obj._scope(ScopeEvent('person','group-A'))
            token=obj.runtime.begin(scope.key)
            result=DeliveryResult('accepted',message_id='out')
            class Sender:
                async def send(_self,target,chain,**kw):return result
            obj.delivery=Sender()
            with work_context(token):
                delivered=await obj._send(scope.target,object())
                obj.scopes[scope.key]=replace(scope,message_id='later-inbound').source()
                entry=obj._record_assistant_turn(scope.key,'answer',delivered)
            self.assertEqual(entry['source']['message_id'],'fixture-msg')
            self.assertEqual(entry['request_id'],token.request)
            self.assertEqual(entry['role'],'assistant')

    async def test_duplicate_receipt_does_not_append_duplicate_messages_or_archive_rows(self):
        with tempfile.TemporaryDirectory() as root:
            obj,_=load_pipeline(root,names=())
            scope=obj._scope(ScopeEvent())
            receipt=DeliveryResult('accepted',message_id='out')
            first=obj._record_assistant_turn(scope.key,'answer',receipt,request_id='explicit-request')
            again=obj._record_assistant_turn(scope.key,'answer',receipt,request_id='explicit-request')
            self.assertEqual(first['id'],again['id'])
            self.assertEqual(len(obj.h[scope.key]),1)
            self.assertEqual(len(__import__('pathlib').Path(root,'archive.jsonl').read_text().splitlines()),1)

    async def test_platform_self_echo_is_rejected_before_creating_scope(self):
        with tempfile.TemporaryDirectory() as root:
            obj,_=load_pipeline(root,names=())
            event=ScopeEvent('fixture-self','group-A')
            with self.assertRaises((ValueError,asyncio.CancelledError)):obj._scope(event)
            self.assertEqual(obj.scopes,{})

    async def test_explicit_task_request_is_not_replaced_by_empty_background_token(self):
        with tempfile.TemporaryDirectory() as root:
            obj,_=load_pipeline(root,names=())
            scope=obj._scope(ScopeEvent())
            with work_context(obj.runtime.token(scope.key,request='')):
                entry=obj._record_assistant_turn(scope.key,'answer',DeliveryResult('accepted'),request_id='original-task-request')
            self.assertEqual(entry['request_id'],'original-task-request')


if __name__=='__main__':unittest.main()
