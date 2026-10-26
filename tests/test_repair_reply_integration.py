"""Real AstrBot classes are imported only in a disposable isolated interpreter."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class ReplyFrameworkRegression(unittest.TestCase):
    def test_real_respond_empty_chain_history_runner_and_scheduler_completion(self):
        with tempfile.TemporaryDirectory(prefix='dsh-reply-framework-') as tmp:
            env=os.environ.copy();env.update(ASTRBOT_ROOT=tmp,TEMP=tmp,TMP=tmp,PYTHONIOENCODING='utf-8')
            run=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--framework'],cwd=tmp,
                env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',timeout=55)
            self.assertEqual(run.returncode,0,run.stdout[-8000:])
            self.assertIn('reply framework OK',run.stdout)


async def framework_case():
    import base64
    from repair_pipeline_support import load_pipeline
    from task_runtime import Runtime
    from qq_delivery import QQDelivery, request_once
    from reply_integration import install_reply_adapters
    from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import QQOfficialMessageEvent
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
    from astrbot.core.platform.message_type import MessageType
    from astrbot.core.platform.platform_metadata import PlatformMetadata
    from astrbot.core.provider.entities import LLMResponse, ProviderRequest
    from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
    from astrbot.api.message_components import Plain, Image, Record, Reply
    from astrbot.core.pipeline.respond.stage import RespondStage
    from astrbot.core.pipeline.scheduler import PipelineScheduler
    from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import InternalAgentSubStage
    from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
    from astrbot.core.agent.runners.base import AgentState
    from astrbot.core.agent.response import AgentStats
    from astrbot.core.astr_agent_hooks import MainAgentHooks
    from astrbot.core.star.session_llm_manager import SessionServiceManager
    from astrbot.core.star.session_plugin_manager import SessionPluginManager
    from astrbot.core.star.star_handler import EventType, star_handlers_registry
    from astrbot.core.star.star import star_map
    from unittest.mock import AsyncMock
    from state_store import read_json,write_json
    install_reply_adapters();first_wrapper=RespondStage.process
    install_reply_adapters();assert RespondStage.process is first_wrapper
    root=Path(os.environ['ASTRBOT_ROOT'])
    pack=root/'sticker_packs'/'fixture';pack.mkdir(parents=True)
    (pack/'image.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='))
    (root/'sticker_packs/shared_gallery_v1.json').write_text(json.dumps({'version':1,'files':{'fixture/image.png':{
        'basis':'owner-explicit-share','source':'synthetic fixture','sha256':__import__('hashlib').sha256((pack/'image.png').read_bytes()).hexdigest()}}}),encoding='utf-8')
    for scenario in ('text','sticker','first-failed','partial-failed','unknown','empty','tool-failed','cancelled','intermediate','no-yield-sticker','ordinary-image','mixed-image','direct-image'):
        directory=root/scenario;directory.mkdir()
        obj,ns=load_pipeline(directory,names=('capture','_clear_text_result','_set_first_bubble_result','_send','_send_sticker_row'),guarded=True)
        ns.update(Plain=Plain,Image=Image,Record=Record,MessageChain=MessageChain,PACKS=str(root/'sticker_packs'),
                  random=SimpleNamespace(random=lambda:1,uniform=lambda *a:0),_load=read_json,_save=write_json)
        obj._drip_interval=lambda:(0,0)
        ns['_pick_sticker']=lambda q:dict(pack='fixture',rel='image.png',tag='happy',caption='fixture')
        msg=AstrBotMessage();msg.type=MessageType.GROUP_MESSAGE;msg.self_id='self';msg.message_id='trigger-'+scenario
        msg.group_id='fixture-group';msg.sender=MessageMember('friend','fixture');msg.message=[Plain('question')]
        msg.message_str='question';msg.raw_message={}
        event=QQOfficialMessageEvent('question',msg,PlatformMetadata('qq_official','fixture','bot'),'fixture-group',SimpleNamespace())
        scope=obj._scope(event);token=obj.runtime.begin(scope.key);event.set_extra('_dsh_work',token)
        obj.request_owners={scope.key:token.request};obj.run_active[scope.key]=1
        obj.request_events={scope.key:event}
        calls=[];saved=[]
        async def api(platform,endpoint,payload):
            calls.append((endpoint,payload))
            if endpoint.endswith('/files'): return 200,{'file_info':'upload-ok'}
            count=sum(p.endswith('/messages') for p,_ in calls)
            if scenario=='first-failed' or scenario=='partial-failed' and count==2:return 400,{'code':40034105}
            if scenario=='unknown':raise TimeoutError('fixture')
            return 200,{'id':'receipt-'+str(count)}
        async def history(umo,cid,**kw):saved.append(kw['history'])
        obj.context=SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[SimpleNamespace(meta=lambda:SimpleNamespace(id='bot',name='qq_official'))]),
            conversation_manager=SimpleNamespace(update_conversation=history))
        obj.delivery=QQDelivery(obj.context,request=api,retain_media=obj._retain_sent_media,audit=obj._record_delivery_result)
        req=ProviderRequest(prompt='question');req.conversation=SimpleNamespace(cid='fixture')
        async def hook(current,response):await obj.capture(current,response)
        handler=SimpleNamespace(handler=hook,handler_module_path='reply_fixture',handler_name='capture')
        content='动作：表情 得意' if scenario in ('sticker','no-yield-sticker') else '' if scenario=='empty' else 'first\n\nsecond'
        response=LLMResponse(role='assistant');response.completion_text=content
        if scenario in ('ordinary-image','mixed-image'):
            response.result_chain=MessageChain(chain=([Plain('caption')] if scenario=='mixed-image' else [])+[Image.fromFileSystem(str(pack/'image.png'))])
        if scenario=='direct-image':response.completion_text=''
        if scenario=='text':
            response.result_chain=MessageChain(chain=[Reply(id='REFIDX_original'),Plain(content)])
        runner=ToolLoopAgentRunner();runner.agent_hooks=MainAgentHooks();runner._state=AgentState.RUNNING;runner.stats=AgentStats()
        runner.run_context=SimpleNamespace(context=SimpleNamespace(event=event),messages=[])
        runner._resolve_unconsumed_follow_ups=lambda:None
        class Capture:
            async def process(self,event):
                if scenario=='tool-failed':raise RuntimeError('fixture tool failure')
                if scenario=='cancelled':raise asyncio.CancelledError()
                if scenario=='intermediate':
                    await event.send(MessageChain(chain=[Plain('visible tool preface')]))
                if scenario=='direct-image':
                    await event.send(MessageChain(chain=[Image.fromFileSystem(str(pack/'image.png'))]))
                await runner._complete_with_assistant_response(response)
                # The real runner has already appended the entire generated
                # assistant; the save adapter must disregard these messages.
                event.set_result(MessageEventResult(chain=response.result_chain.chain if response.result_chain else []))
        stage=object.__new__(InternalAgentSubStage)
        class Save:
            async def process(self,event):await stage._save_to_history(event,req,response,runner.run_context.messages,None)
        scheduler=object.__new__(PipelineScheduler);scheduler.stages=[Capture(),object.__new__(RespondStage),Save()]
        if scenario=='no-yield-sticker':scheduler.stages=[Capture(),Save()]
        with patch.object(SessionServiceManager,'is_session_enabled',AsyncMock(return_value=True)), \
             patch.object(SessionPluginManager,'is_plugin_enabled_for_session',AsyncMock(return_value=True)), \
             patch.dict(star_map,reply_fixture=SimpleNamespace(name='fixture')), \
             patch.object(star_handlers_registry,'get_handlers_by_event_type',side_effect=lambda kind,**kw:[handler] if kind==EventType.OnLLMResponseEvent else []):
            try:await scheduler.execute(event)
            except (RuntimeError,asyncio.CancelledError):
                assert scenario in ('tool-failed','cancelled')
        accepted=obj.h.get(scope.key,[])
        expected=[] if scenario in ('first-failed','unknown','empty','tool-failed','cancelled') else ['first'] if scenario=='partial-failed' else ['[表情] fixture'] if scenario in ('sticker','no-yield-sticker') else ['visible tool preface','first','second'] if scenario=='intermediate' else ['first','second']
        if scenario in ('ordinary-image','mixed-image','direct-image'):
            expected=['caption'] if scenario=='mixed-image' else ['[媒体]']
        assert [h['text'] for h in accepted]==expected,(scenario,accepted)
        assert scope.key not in obj.run_active and scope.key not in obj.pending_sticker,scenario
        if saved: assert [h['content'] for h in saved[-1]]==expected,(scenario,saved)
        if scenario in ('ordinary-image','mixed-image','direct-image'):
            row=accepted[0];ref=row.get('images',[None])[0]
            assert ref and ref.startswith('media/sent/'+scope.key+'/'),(scenario,row)
            assert (directory/ref).read_bytes()==(pack/'image.png').read_bytes()
            archive=__import__('json').loads((directory/'archive.jsonl').read_text(encoding='utf-8').splitlines()[0])
            for entry in (archive,obj.groups[scope.group_key][0],read_json(obj.h_path,{})[scope.key][0]):
                assert entry['id']==row['id'] and entry['images']==row['images']
            receipt=read_json(directory/'delivery_receipts_v2.json',{})[scope.key][0]
            assert row['request_id']==token.request==receipt['request_id']
            assert row['delivery']['attempt_id']==receipt['attempt_id']
        if scenario in ('first-failed','unknown'):assert len(calls)==1
        if scenario=='sticker':
            assert len(calls)==2 and calls[-1][1]['msg_id']=='trigger-sticker'
            assert accepted[0]['sticker']=='sticker_packs/fixture/image.png'
        if scenario=='text':
            assert [payload['msg_seq'] for _,payload in calls]==[1,2]
            assert 'message_reference' not in calls[0][1], 'QQ v2 native references are documented unsupported'
            assert 'message_reference' not in calls[1][1]
        await obj.runtime.stop()

    # Exercise the real low-level transport with an authenticated-session double.
    # The SDK request function is intentionally unavailable: retries cannot hide.
    requests=[]
    class Response:
        status=200
        async def json(self,**kw):return {'id':'once'}
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
    class Session:
        def request(self,**kw):requests.append(kw);return Response()
    http=SimpleNamespace(check_session=AsyncMock(),is_sandbox=False,_session=Session(),_headers={'Authorization':'fixture-only'})
    result=await request_once(SimpleNamespace(client=SimpleNamespace(api=SimpleNamespace(_http=http))),'/v2/groups/fixture/messages',{'msg_type':0,'content':'fixture'})
    assert result==(200,{'id':'once'}) and len(requests)==1
    assert requests[0]['allow_redirects'] is False
    # A framework permission change during authentication must still prevent
    # the actual POST, even though the plugin's own switches remain enabled.
    from task_runtime import work_context
    runtime=Runtime(lambda *a:True);token=runtime.begin('fixture-policy')
    denied=False
    async def authenticate():
        nonlocal denied
        denied=True
    async def policy(current):
        if denied:raise asyncio.CancelledError('fixture framework disabled')
    http.check_session=authenticate
    requests.clear()
    with work_context(token,event),patch('session_scope.check_framework_policy',policy):
        try:await request_once(SimpleNamespace(client=SimpleNamespace(api=SimpleNamespace(_http=http))),'/v2/groups/fixture/messages',{'content':'must not send'})
        except asyncio.CancelledError:pass
        else:raise AssertionError('framework permission was ignored after authentication')
    assert not requests
    print('reply framework OK')


if __name__=='__main__':
    if '--framework' in sys.argv:asyncio.run(framework_case())
    else:unittest.main()
