import asyncio
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from repair_pipeline_support import load_pipeline
from session_scope import Target, bind_scope
from test_repair_session_scope import ScopeEvent


class RoutingRegression(unittest.IsolatedAsyncioTestCase):
    async def test_actual_file_upload_and_send_keep_same_instance_and_original_private_target(self):
        from pathlib import Path
        from test_repair_permissions import load_methods,Event
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'fixture.md';file.write_text('fixture')
            obj,ns=load_methods();event=Event('owner');event.message_obj=SimpleNamespace(message_id='trigger',self_id='self')
            ns['_safe_local_path']=lambda *a,**kw:(str(file),None)
            calls=[]
            from qq_delivery import QQDelivery
            ns.update(File=lambda **kw:SimpleNamespace(**kw),MessageChain=lambda **kw:SimpleNamespace(**kw))
            platform=SimpleNamespace(meta=lambda:SimpleNamespace(id='fictional-bot',name='qq_official'))
            context=SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[platform]))
            async def api(platform,endpoint,payload):
                calls.append((endpoint,payload,platform.meta().id))
                if endpoint.endswith('/files'):
                    event.private=False  # subsequent chat/route state must not redirect this request
                    return 200,{'file_info':'fixture-media'}
                return 200,{'id':'accepted-file'}
            async def parse(chain):return '',None,None,None,None,chain.chain[0].file,chain.chain[0].name
            delivery=QQDelivery(context,request=api,parse=parse)
            obj._send=delivery.send
            obj._record_assistant_turn=lambda *a:None
            result=await obj.send_local_file(event,str(file))
            self.assertIn('QQ',result)
            self.assertEqual([row[0] for row in calls],['/v2/users/owner/files','/v2/users/owner/messages'])
            self.assertEqual({row[2] for row in calls},{'fictional-bot'})
            self.assertEqual(calls[1][1]['msg_id'],'trigger')
            self.assertEqual(calls[1][1]['media']['file_info'],'fixture-media')

    async def test_credential_lookup_requires_exact_platform_instance(self):
        import ast,os,time,json
        from pathlib import Path
        source=Path(__file__).resolve().parents[1]/'plugin/astrbot_plugin_dsh_soul/main.py'
        tree=ast.parse(source.read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if getattr(n,'name','')=='_qq_token')
        ns=dict(_QQ_TOKEN_CACHE={},time=time,os=os,DATA='unused',json=json,_load=lambda *a:{'platform':[
            {'id':'bot-a','type':'qq_official','appid':'fixture-a','secret':'fixture-secret-a'},
            {'id':'bot-b','type':'qq_official','appid':'fixture-b','secret':'fixture-secret-b'}]})
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'<actual credential selector>','exec'),ns)
        selected=[]
        def reply(request,**kw):
            selected.append(json.loads(request.data)['appId'])
            return SimpleNamespace(read=lambda:b'{"access_token":"fixture-token","expires_in":600}')
        with patch('urllib.request.urlopen',reply):
            ns['_qq_token']('bot-b')
            with self.assertRaises(RuntimeError):ns['_qq_token']('absent')
        self.assertEqual(selected,['fixture-b'])

    async def test_completion_uses_original_group_after_same_sender_moves_to_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            from repair_pipeline_support import ResultChain
            from qq_delivery import DeliveryResult
            obj,ns=load_pipeline(tmp,names=('capture','_clear_text_result','_set_first_bubble_result'),guarded=True)
            first=ScopeEvent('a','g1'); scope=obj._scope(first)
            await obj.capture(first,SimpleNamespace(result_chain=ResultChain('first\n\nlater')))
            obj._scope(ScopeEvent('a'))
            calls=[]
            async def send(target,*args):calls.append(target);return DeliveryResult('accepted',message_id='fixture')
            obj._send=send;obj._drip_interval=lambda:(0,0)
            ns['random']=SimpleNamespace(random=lambda:1,uniform=lambda *a:0)
            await obj._complete_reply(first)
            self.assertEqual(calls,[scope.target,scope.target])

    async def test_target_endpoints_and_absent_destination(self):
        for kind,address,base in [('private','user-id','users'),('group','group-id','groups')]:
            target=Target('qq_official','bot-one','self',kind,address,'trigger')
            self.assertEqual(target.endpoint('files'),f'/v2/{base}/{address}/files')
            self.assertEqual(target.endpoint('messages'),f'/v2/{base}/{address}/messages')
        with self.assertRaises(ValueError): Target('qq_official','bot','','private','').endpoint('messages')
        with self.assertRaises(ValueError): Target('aiocqhttp','bot','','group','g').endpoint('files')

    async def test_missing_or_wrong_instance_never_falls_back_to_another_bot(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp,names=('_send',))
            obj.context=SimpleNamespace(send_message=AsyncMock(),platform_manager=SimpleNamespace(platform_insts=[]))
            from qq_delivery import QQDelivery
            obj.delivery=QQDelivery(obj.context)
            with self.assertRaises(ValueError): await obj._send('last route',object())
            result=await obj._send(Target('qq_official','absent','','private','u'),object())
            self.assertEqual((result.status,result.category),('failed','route'))
            obj.context.send_message.assert_not_awaited()


if __name__=='__main__': unittest.main()
