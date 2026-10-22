"""Accepted media is retained by request, using real delivery/history methods."""
import asyncio
import base64
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from repair_pipeline_support import load_pipeline,ResultChain
from test_repair_session_scope import ScopeEvent
from qq_delivery import QQDelivery,DeliveryResult
from task_runtime import work_context
from state_store import read_json,write_json

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


class MediaHistoryRegression(unittest.IsolatedAsyncioTestCase):
    def plugin(self,root):
        obj,ns=load_pipeline(root,guarded=True)
        ns.update(_load=read_json,_save=write_json,random=SimpleNamespace(random=lambda:1))
        return obj,ns

    async def test_accepted_image_in_pure_and_mixed_replies_has_identical_scoped_history_references(self):
        for text in ('','caption'):
            with self.subTest(text=text),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'data';root.mkdir()
                obj,ns=load_pipeline(root,guarded=True)
                ns.update(_load=read_json,_save=write_json,random=SimpleNamespace(random=lambda:1))
                event=ScopeEvent(group='group');response=SimpleNamespace(result_chain=ResultChain(text))
                image=SimpleNamespace(type='Image',file=str(Path(tmp)/'transient.png'))
                Path(image.file).write_bytes(PNG)
                response.result_chain.chain.insert(0,image)
                await obj.capture(event,response)
                scope=event.get_extra('_dsh_scope');calls=[]
                async def api(platform,endpoint,payload):
                    calls.append((endpoint,payload))
                    return (200,{'file_info':'uploaded'}) if endpoint.endswith('/files') else (200,{'id':'accepted-image'})
                async def parse(chain):return text,base64.b64encode(PNG).decode(),image.file,None,None,None,None
                context=SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[SimpleNamespace(meta=lambda:SimpleNamespace(id='bot-one',name='qq_official'))]))
                kwargs={}
                # The pre-fix sender has no retention callback; still reach its
                # real accepted/history path to reproduce the missing field.
                if hasattr(obj,'_retain_sent_media'):kwargs['retain_media']=obj._retain_sent_media
                obj.delivery=QQDelivery(context,request=api,parse=parse,audit=obj._record_delivery_result,**kwargs)
                async def send(target,chain):return await obj.delivery.send(target,chain)
                obj._send=send
                await obj._complete_reply(event)
                row=obj.h[scope.key][0]
                self.assertTrue(row.get('images'),'accepted ordinary image lacks a history reference')
                rel=row['images'][0]
                self.assertTrue(rel.startswith('media/sent/'+scope.key+'/'))
                self.assertEqual((root/rel).read_bytes(),PNG)
                self.assertEqual(row['delivery']['message_id'],'accepted-image')
                self.assertEqual(row['request_id'],event.get_extra('_dsh_work').request)
                self.assertEqual(row['plan_id'],event.get_extra('_dsh_reply_plan').id)
                self.assertEqual(row['delivery']['attempt_id'],event.get_extra('_dsh_reply_plan').results[0].attempt_id)
                archived=json.loads((root/'archive.jsonl').read_text(encoding='utf-8').splitlines()[0])
                disk=read_json(obj.h_path,{})[scope.key][0];group=read_json(obj.group_path,{})[scope.group_key][0]
                for entry in (archived,disk,group):
                    self.assertEqual(entry['id'],row['id']);self.assertEqual(entry['images'],[rel])
                audit=read_json(root/'delivery_receipts_v2.json',{})[scope.key][0]
                self.assertEqual(audit['request_id'],row['request_id'])
                self.assertEqual(audit['attempt_id'],row['delivery']['attempt_id'])
                self.assertNotIn(base64.b64encode(PNG).decode(),json.dumps(audit))
                self.assertEqual(read_json(root/'media_v2.json',{})[scope.key],[rel])
                self.assertEqual(len(calls),2)

    async def test_failed_unknown_and_media_fallback_never_record_unsent_image(self):
        for outcome in ('failed','unknown','fallback'):
            with self.subTest(outcome=outcome),tempfile.TemporaryDirectory() as tmp:
                obj,ns=self.plugin(tmp)
                event=ScopeEvent(group='group');response=SimpleNamespace(result_chain=ResultChain('caption'))
                image=SimpleNamespace(type='Image',file='https://example.invalid/fixture.png')
                response.result_chain.chain.insert(0,image);await obj.capture(event,response)
                async def parse(chain):
                    has_image=any(getattr(c,'type',None)=='Image' for c in chain.chain)
                    return 'caption',base64.b64encode(PNG).decode() if has_image else None,None,None,None,None,None
                calls=[]
                async def api(platform,endpoint,payload):
                    calls.append(endpoint)
                    if endpoint.endswith('/files'):return 200,{'file_info':'uploaded'}
                    if payload.get('msg_type')==7:
                        if outcome=='unknown':raise TimeoutError('fixture')
                        return 400,{'code':40034004 if outcome=='fallback' else 40034105}
                    return 200,{'id':'accepted-text'}
                context=SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[SimpleNamespace(meta=lambda:SimpleNamespace(id='bot-one',name='qq_official'))]))
                obj.delivery=QQDelivery(context,parse=parse,request=api,retain_media=obj._retain_sent_media)
                async def send(target,chain):return await obj.delivery.send(target,chain)
                obj._send=send
                await obj._complete_reply(event)
                self.assertFalse((Path(tmp)/'media/sent').exists())
                rows=obj.h.get(event.get_extra('_dsh_scope').key,[])
                self.assertEqual(len(rows),int(outcome=='fallback'))
                self.assertTrue(all('images' not in row for row in rows))
                self.assertEqual(len(calls),3 if outcome=='fallback' else 2)

    async def test_audio_and_file_references_are_owned_by_concurrent_scene_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'data';root.mkdir();obj,ns=self.plugin(root)
            blob=b'RIFF'+b'\x00'*4+b'WAVE'+b'fixture'
            wav=Path(tmp)/'audio.wav';wav.write_bytes(blob)
            file=Path(tmp)/'fixture.md';file.write_bytes(b'fixture attachment')
            events=[ScopeEvent(),ScopeEvent(group='group')]
            scopes=[obj._scope(event) for event in events]
            tokens=[obj.runtime.begin(scope.key) for scope in scopes]
            async def parse(chain):
                c=chain.chain[0]
                return '',None,None,c.file if c.type=='Record' else None,None,c.file_ if c.type=='File' else None,'fixture.md' if c.type=='File' else None
            async def api(platform,endpoint,payload):
                await asyncio.sleep(0)
                return (200,{'file_info':'uploaded'}) if endpoint.endswith('/files') else (200,{'id':endpoint})
            context=SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[SimpleNamespace(meta=lambda:SimpleNamespace(id='bot-one',name='qq_official'))]))
            sender=QQDelivery(context,parse=parse,request=api,retain_media=obj._retain_sent_media,audit=obj._record_delivery_result)
            async def one(i):
                component=SimpleNamespace(type='Record',file=str(wav)) if i==0 else SimpleNamespace(type='File',file_=str(file))
                with work_context(tokens[i],events[i]):
                    result=await sender.send(scopes[i].target,SimpleNamespace(chain=[component]))
                    obj._record_assistant_turn(scopes[i].key,'[媒体]',result)
                    return result
            results=await asyncio.gather(one(0),one(1))
            for i,field,data in ((0,'voice',blob),(1,'files',b'fixture attachment')):
                row=obj.h[scopes[i].key][0];rel=row[field] if field=='voice' else row[field][0]
                self.assertIn('/'+scopes[i].key+'/',rel)
                self.assertEqual((root/rel).read_bytes(),data)
                self.assertEqual(row['request_id'],tokens[i].request)
                self.assertEqual(row['delivery']['attempt_id'],results[i].attempt_id)
            self.assertEqual(json.loads((root/'archive.jsonl').read_text(encoding='utf-8').splitlines()[0])['id'],obj.h[scopes[0].key][0]['id'])

    async def test_retention_failure_and_other_owner_path_do_not_change_receipt_or_expose_reference(self):
        for problem in ('disk','other-owner'):
            with self.subTest(problem=problem),tempfile.TemporaryDirectory() as tmp:
                obj,ns=self.plugin(tmp);event=ScopeEvent();scope=obj._scope(event);token=obj.runtime.begin(scope.key)
                original=Path(tmp)/'media/inbox/private.png';original.parent.mkdir(parents=True);original.write_bytes(PNG)
                write_json(Path(tmp)/'media_v2.json',{'another-owner':['media/inbox/private.png']})
                if problem=='disk':
                    original=Path(tmp).parent/'transient-fixture.png'
                    def fail(*a):raise OSError('fixture')
                    obj._write_media=fail
                async def parse(chain):return '',base64.b64encode(PNG).decode(),str(original),None,None,None,None
                calls=[]
                async def api(platform,endpoint,payload):
                    calls.append(endpoint)
                    return (200,{'file_info':'uploaded'}) if endpoint.endswith('/files') else (200,{'id':'accepted'})
                context=SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[SimpleNamespace(meta=lambda:SimpleNamespace(id='bot-one',name='qq_official'))]))
                sender=QQDelivery(context,parse=parse,request=api,retain_media=obj._retain_sent_media)
                with work_context(token,event):
                    result=await sender.send(scope.target,SimpleNamespace(chain=[SimpleNamespace(type='Image',file=str(original))]))
                    row=obj._record_assistant_turn(scope.key,'[媒体]',result)
                self.assertEqual(result.status,'accepted');self.assertEqual(result.persistence['media'],'failed')
                self.assertEqual(result.media,{});self.assertNotIn('images',row)
                self.assertNotIn(str(original),json.dumps(row));self.assertEqual(len(calls),2)
                self.assertFalse((Path(tmp)/'media/sent').exists())

    async def test_new_media_layer_deletion_removes_only_requested_scope_snapshots(self):
        from state_store import StateController
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=self.plugin(tmp);first=obj._scope(ScopeEvent());second=obj._scope(ScopeEvent(group='other'))
            for scope in (first,second):
                obj._write_media(scope.key,'media/sent/'+scope.key+'/fixture.png',PNG)
            state=StateController(obj,tmp,clear_framework=lambda key:asyncio.sleep(0))
            result=await state.delete(first.key,['media'])
            self.assertTrue(result['ok'],result)
            self.assertFalse((Path(tmp)/('media/sent/'+first.key+'/fixture.png')).exists())
            self.assertTrue((Path(tmp)/('media/sent/'+second.key+'/fixture.png')).exists())

    async def test_mutating_registered_source_during_send_cannot_change_accepted_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=self.plugin(tmp);event=ScopeEvent();scope=obj._scope(event);token=obj.runtime.begin(scope.key)
            original=Path(tmp)/'media/inbox/original.png'
            obj._write_media(scope.key,'media/inbox/original.png',PNG)
            async def parse(chain):return '',base64.b64encode(PNG).decode(),str(original),None,None,None,None
            async def api(platform,endpoint,payload):
                if endpoint.endswith('/files'):return 200,{'file_info':'uploaded'}
                original.write_bytes(b'new unrelated bytes')
                return 200,{'id':'accepted'}
            context=SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[SimpleNamespace(meta=lambda:SimpleNamespace(id='bot-one',name='qq_official'))]))
            sender=QQDelivery(context,parse=parse,request=api,retain_media=obj._retain_sent_media)
            with work_context(token,event):
                result=await sender.send(scope.target,SimpleNamespace(chain=[SimpleNamespace(type='Image',file=str(original))]))
                row=obj._record_assistant_turn(scope.key,'[媒体]',result)
            self.assertEqual((Path(tmp)/row['images'][0]).read_bytes(),PNG)
            self.assertNotEqual(row['images'][0],'media/inbox/original.png')

    async def test_background_work_without_trigger_still_has_matching_nonempty_receipt_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=self.plugin(tmp);scope=obj._scope(ScopeEvent());token=obj.runtime.token(scope.key)
            result=DeliveryResult('accepted',message_id='background')
            with work_context(token):row=obj._record_assistant_turn(scope.key,'background',result)
            ledger=read_json(Path(tmp)/'delivery_receipts_v2.json',{})[scope.key][0]
            self.assertTrue(row['request_id']);self.assertEqual(row['request_id'],ledger['request_id'])

    async def test_revocation_after_known_acceptance_keeps_receipt_and_prevents_media_history_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=self.plugin(tmp);event=ScopeEvent();scope=obj._scope(event);token=obj.runtime.begin(scope.key)
            async def parse(chain):return '',base64.b64encode(PNG).decode(),None,None,None,None,None
            async def api(platform,endpoint,payload):
                if endpoint.endswith('/files'):return 200,{'file_info':'uploaded'}
                obj.runtime.invalidate(scope.key)
                return 200,{'id':'known-accepted'}
            context=SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[SimpleNamespace(meta=lambda:SimpleNamespace(id='bot-one',name='qq_official'))]))
            sender=QQDelivery(context,parse=parse,request=api,retain_media=obj._retain_sent_media)
            with work_context(token,event):
                try:await sender.send(scope.target,SimpleNamespace(chain=[]))
                except asyncio.CancelledError as error:
                    receipt=getattr(error,'delivery_result',None)
                    self.assertIsNotNone(receipt)
                    self.assertEqual(receipt.status,'accepted')
                    self.assertEqual(receipt.message_id,'known-accepted')
                    self.assertEqual(receipt.persistence['media'],'cancelled')
                else:self.fail('revoked media write did not cancel')
            self.assertFalse((Path(tmp)/'media/sent').exists());self.assertEqual(obj.h,{})

    async def test_history_without_explicit_request_id_inherits_runtime_identity_and_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp)
            scope=obj._scope(ScopeEvent());token=obj.runtime.begin(scope.key)
            result=DeliveryResult('accepted',message_id='preface')
            with work_context(token):row=obj._record_assistant_turn(scope.key,'preface',result)
            self.assertEqual(row['request_id'],token.request)
            self.assertEqual(row['delivery']['attempt_id'],result.attempt_id)


if __name__=='__main__':unittest.main()
