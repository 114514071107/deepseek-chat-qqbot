"""QQ requests terminate at a fake HTTP/media boundary; never connect to QQ."""
import asyncio
import importlib
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'plugin/astrbot_plugin_dsh_soul'))
from session_scope import Target


class QQDeliveryRegression(unittest.IsolatedAsyncioTestCase):
    def sender(self, responses=None, now=1000):
        try:
            module=importlib.import_module('qq_delivery')
        except ModuleNotFoundError:
            self.fail('F06 lacks a QQ sender with explicit receipts')
        calls=[]
        replies=list(responses or [(200, {'id':'accepted-message'})]*10)
        async def request(platform, endpoint, payload):
            calls.append((platform,endpoint,dict(payload)))
            item=replies.pop(0)
            if isinstance(item, BaseException): raise item
            return item
        platform=SimpleNamespace(meta=lambda:SimpleNamespace(id='bot',name='qq_official'),client=SimpleNamespace(appid='self'))
        context=SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[platform]))
        async def parse(chain): return chain
        obj=module.QQDelivery(context, request=request, parse=parse, clock=lambda:now)
        return obj,calls

    def target(self, kind='group', **kw):
        return Target('qq_official','bot','self',kind,'destination','trigger',received_at=1000,**kw)

    async def test_first_react_bubbles_and_media_share_trigger_and_increment_sequence(self):
        sender,calls=self.sender([(200,{'id':'r1'}),(200,{'file_info':'media'}),(200,{'id':'r2'})])
        target=self.target()
        first=await sender.send(target,('hello',None,None,None,None,None,None))
        second=await sender.send(target,('', 'fixture-base64',None,None,None,None,None))
        self.assertEqual([first.status,second.status],['accepted','accepted'])
        self.assertEqual([c[1] for c in calls],['/v2/groups/destination/messages','/v2/groups/destination/files','/v2/groups/destination/messages'])
        self.assertEqual(calls[0][2],{'msg_type':0,'content':'hello','msg_id':'trigger','msg_seq':1})
        self.assertEqual(calls[1][2]['srv_send_msg'],False)
        self.assertEqual(calls[2][2],{'msg_type':7,'media':{'file_info':'media'},'msg_id':'trigger','msg_seq':2})

    async def test_limits_expiry_and_event_credential_never_become_proactive(self):
        for kind,limit in [('private',4),('group',5)]:
            sender,calls=self.sender(); target=self.target(kind)
            results=[await sender.send(target,('hello',None,None,None,None,None,None)) for _ in range(limit+1)]
            self.assertEqual(len(calls),limit)
            self.assertEqual(results[-1].category,'exhausted')
        sender,calls=self.sender(now=1301)
        result=await sender.send(self.target(),('hello',None,None,None,None,None,None))
        self.assertEqual((result.status,result.category,len(calls)),('skipped','expired',0))
        sender,calls=self.sender()
        target=Target('qq_official','bot','self','private','destination',event_id='evt',received_at=1000)
        await sender.send(target,('hello',None,None,None,None,None,None))
        self.assertEqual(calls[0][2]['event_id'],'evt'); self.assertNotIn('msg_id',calls[0][2])

    async def test_duplicate_sequence_permission_and_upload_success_message_failure(self):
        for code,category in [(40054005,'duplicate'),(40034105,'permission'),(40034100,'rate_limit'),(40034005,'expired'),(40034024,'route')]:
            sender,calls=self.sender([(200,{'file_info':'media'}),(400,{'code':code,'message':'secret identity/token'})])
            result=await sender.send(self.target(),('', 'base64',None,None,None,None,None))
            self.assertEqual((result.status,result.stage,result.category),('failed','message',category))
            self.assertNotIn('secret',result.error); self.assertEqual(len(calls),2)
            again=await sender.send(self.target(),('no retry',None,None,None,None,None,None))
            self.assertEqual(again.status,'skipped');self.assertEqual(len(calls),2)

    async def test_timeout_empty_http_success_missing_platform_and_proactive_are_distinct(self):
        for response in [TimeoutError(),(200,{}),(503,{'code':50055001})]:
            sender,calls=self.sender([response])
            result=await sender.send(self.target(),('hello',None,None,None,None,None,None))
            self.assertEqual(result.status,'unknown');self.assertEqual(len(calls),1)
            await sender.send(self.target(),('again',None,None,None,None,None,None))
            self.assertEqual(len(calls),1)
        sender,calls=self.sender();sender.context.platform_manager.platform_insts=[]
        result=await sender.send(self.target(),('hello',None,None,None,None,None,None))
        self.assertEqual((result.status,result.category,len(calls)),('failed','route',0))
        sender,calls=self.sender()
        await sender.send(self.target(),('hello',None,None,None,None,None,None),mode='proactive')
        self.assertNotIn('msg_id',calls[0][2]);self.assertNotIn('event_id',calls[0][2])

    async def test_expiry_during_upload_and_media_failure_fallback_use_finite_budget(self):
        sender,calls=self.sender([(200,{'file_info':'uploaded'})])
        real=sender.request
        async def upload(*args):
            value=await real(*args);sender.clock=lambda:1301;return value
        sender.request=upload
        result=await sender.send(self.target(),('', 'base64',None,None,None,None,None))
        self.assertEqual((result.status,result.category,len(calls)),('skipped','expired',1))
        sender,calls=self.sender([(200,{'file_info':'uploaded'}),(400,{'code':40034004}),(200,{'id':'text'})])
        voice=await sender.send(self.target(),('', 'base64',None,None,None,None,None))
        text=await sender.send(self.target(),('fallback',None,None,None,None,None,None))
        self.assertEqual((voice.status,text.status,text.seq),('failed','accepted',2))
        self.assertEqual(len(calls),3)

    async def test_upload_permission_cannot_be_misclassified_as_media_and_text_retried(self):
        sender,calls=self.sender([(403,{'code':40034105})])
        result=await sender.send(self.target(),('', 'base64',None,None,None,None,None))
        self.assertEqual((result.status,result.stage,result.category),('failed','upload','permission'))

    async def test_cancel_in_flight_message_preserves_unknown_result_and_closes_credential(self):
        sender,calls=self.sender();entered=asyncio.Event()
        async def request(*args):calls.append(args);entered.set();await asyncio.Event().wait()
        sender.request=request
        task=asyncio.create_task(sender.send(self.target(),('hello',None,None,None,None,None,None)))
        await entered.wait();task.cancel()
        try:await task
        except asyncio.CancelledError as error:
            self.assertEqual(getattr(getattr(error,'delivery_result',None),'status',None),'unknown')
        result=await sender.send(self.target(),('again',None,None,None,None,None,None))
        self.assertEqual(result.status,'skipped');self.assertEqual(len(calls),1)

    async def test_duplicate_message_with_different_event_id_keeps_one_sequence_ledger(self):
        sender,calls=self.sender()
        await sender.send(self.target(event_id='delivery-a'),('one',None,None,None,None,None,None))
        await sender.send(self.target(event_id='delivery-b'),('two',None,None,None,None,None,None))
        self.assertEqual([row[2]['msg_seq'] for row in calls],[1,2])


if __name__=='__main__': unittest.main()
