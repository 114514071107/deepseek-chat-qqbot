"""Actual AstrBot request/image/provider assembly in a disposable subprocess."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class FrameworkInputRegression(unittest.TestCase):
    def test_gate_batch_final_openai_blocks_and_model_budget(self):
        with tempfile.TemporaryDirectory(prefix='dsh-w4-framework-') as tmp:
            env=os.environ.copy();env.update(ASTRBOT_ROOT=tmp,TEMP=tmp,TMP=tmp,PYTHONIOENCODING='utf-8')
            result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--framework'],
                cwd=tmp,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',timeout=55)
            self.assertEqual(result.returncode,0,result.stdout[-8500:])


async def framework_case():
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch
    import base64
    import re
    import json
    from repair_pipeline_support import load_pipeline
    from test_repair_batch_input import PNG
    from test_repair_p2_acceptance import real_event
    from state_store import read_json, write_json
    from task_runtime import work_context
    from resource_budget import BudgetProvider, Resources, ImageUnavailable, BudgetExceeded, image_count
    from model_integration import install_model_adapters
    from astrbot.core.message.components import Plain, Image
    from astrbot.core.provider.entities import ProviderRequest, LLMResponse
    from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
    from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
    from astrbot.core.utils.image_input import prepare_request_images
    from astrbot.core.star.session_llm_manager import SessionServiceManager
    from astrbot.core.star.session_plugin_manager import SessionPluginManager
    install_model_adapters(); wrapper=ToolLoopAgentRunner.reset
    install_model_adapters(); assert wrapper is ToolLoopAgentRunner.reset
    root=Path(os.environ['ASTRBOT_ROOT']); (root/'persona.md').write_text('fixture',encoding='utf-8')
    paths=[]
    for n in range(3):
        from PIL import Image as PillowImage
        path=root/f'fixed-{n}.png';PillowImage.new('RGB',(2,2),(n*80,30,100)).save(path);paths.append(path)
    obj,ns=load_pipeline(root,names=('gate','inject','_save_inbox_images','_save_inbox_files','_entry_feature'),guarded=True)
    obj.resources=Resources({'model_calls':2})
    ns.update(Plain=Plain,Image=Image,File=type('UnusedFile',(),{}),_save=write_json,_load=read_json,
        _conf=lambda key: key=='enabled',POINTS_FILE=str(root/'points.json'),_conf_val=lambda key,default:default,
        MASTER_SWITCH_RE=re.compile('^never$'),REMIND_CMD_RE=re.compile('^never$'),STATUS_RE=re.compile('^never$'),
        BATCH_STREAK_GAP=8,BATCH_DONE_MINLEN=8,BATCH_END_PUNCT='。!?',MAX_ITEMS=8,
        normalize_image=__import__('batch_input').normalize_image,read_local_image=__import__('batch_input').read_local_image,
        random=SimpleNamespace(random=lambda:1),BATCH_WAIT=0)
    obj.names={};obj.sil={};obj.n_path=str(root/'names.json');obj._match_sleep_cmd=lambda *a:None
    obj.batch_buf={};obj.batch_skipwait={};obj.last_msg_at={}
    obj.context=SimpleNamespace(get_config=lambda **kw:{'agent_runner':{'runner_type':'local'}})
    # A later image starts downloading before inject consumes the batch. Its
    # presence must already be reserved, even when the image finishes later.
    first=real_event(group='slow-group');first.message_obj.message_id='slow-first'
    later_event=real_event(group='slow-group');later_event.message_str=''
    later_event.message_obj.message_id='slow-later';later_event.message_obj.message=[Image.fromFileSystem(str(paths[0]))]
    actual_images=obj._save_inbox_images;started=asyncio.Event();release=asyncio.Event()
    async def delayed_images(uid,event):
        if event is later_event:started.set();await release.wait()
        return await actual_images(uid,event)
    obj._save_inbox_images=delayed_images
    with patch.object(SessionServiceManager,'is_session_enabled',AsyncMock(return_value=True)),patch.object(SessionPluginManager,'is_plugin_enabled_for_session',AsyncMock(return_value=True)):
        await obj.gate(first)
        arrival=asyncio.create_task(obj.gate(later_event));await started.wait()
        request=ProviderRequest(prompt='question')
        injecting=asyncio.create_task(obj.inject(first,request));await asyncio.sleep(.03)
        waited=not injecting.done();release.set();await asyncio.gather(arrival,injecting)
        assert waited and request.image_urls,'late image download was invisible to batch consumer'
    obj._save_inbox_images=actual_images
    physical=[]
    provider=object.__new__(ProviderOpenAIOfficial)
    provider.provider_config={'id':'offline','modalities':['text','image'],'model':'fixture','custom_extra_body':{'max_tokens':99999}}
    provider.model_name='fixture';provider.get_model=lambda:'fixture';provider.api_keys=['fixture-key'];provider.client=SimpleNamespace(api_key='',base_url=SimpleNamespace(host='offline.invalid'))
    async def query(payload,tools,**kw):
        physical.append((payload,kw))
        return LLMResponse(role='assistant',completion_text='offline')
    provider._query=query
    for text,images,later,group in [('look',[],[0],'g1'),('',[0],[],'g2'),('mix',[0],[1,2],'g3')]:
        event=real_event(group=group);event.message_str=text
        event.message_obj.message=[Plain(text)]+[Image.fromFileSystem(str(paths[n])) for n in images]
        event.message_obj.message_id='first-'+group
        with patch.object(SessionServiceManager,'is_session_enabled',AsyncMock(return_value=True)),patch.object(SessionPluginManager,'is_plugin_enabled_for_session',AsyncMock(return_value=True)):
            await obj.gate(event)
            for n in later:
                extra=real_event(group=group);extra.message_str='';extra.message_obj.message=[Image.fromFileSystem(str(paths[n]))]
                extra.message_obj.message_id='extra-'+group+str(n)
                await obj.gate(extra);assert extra.is_stopped()
            req=ProviderRequest(prompt=text)
            await obj.inject(event,req)
            await prepare_request_images(req,event,max_size=1536,prepared={},output_dir=root/'prepared')
            assert len(req.image_urls)==len(images)+len(later),(group,req)
            runner=ToolLoopAgentRunner()
            await runner.reset(provider=provider,request=req,run_context=SimpleNamespace(context=SimpleNamespace(event=event)),
                tool_executor=None,agent_hooks=None)
            contexts=runner._sanitize_contexts_for_provider(runner.run_context.messages)
            assert image_count(contexts)==len(images)+len(later)
            await runner.provider.text_chat(contexts=contexts)
            payload=physical[-1][0]
            assert image_count(payload['messages'])==len(images)+len(later)
            for message in payload['messages']:
                if isinstance(message['content'],list):
                    for part in message['content']:
                        if part.get('type')=='image_url':
                            assert part['image_url']['url'].startswith('data:image/')
                            assert base64.b64decode(part['image_url']['url'].split(',',1)[1]).startswith(b'\x89PNG')
            assert 'OTHER-GROUP' not in json.dumps(payload)
            assert physical[-1][1]['request_max_retries']==1
            assert physical[-1][0].get('max_tokens')==1024,'output cap missing from physical API payload'
            # A third invocation on this same real request never reaches _query.
            await runner.provider.text_chat(contexts=contexts)
            try:await runner.provider.text_chat(contexts=contexts)
            except BudgetExceeded:pass
            else:raise AssertionError('unbounded model continuation')
            before=len(physical)
            provider.provider_config['modalities']=['text']
            try:await runner.provider.text_chat(contexts=contexts)
            except (ImageUnavailable,BudgetExceeded):pass
            else:raise AssertionError('removed capability reached upstream')
            assert len(physical)==before
            provider.provider_config['modalities']=['text','image']
    # Captioning happens before OnLLMRequest in 4.29.1. Its provider must retain
    # the real Provider class while sharing this event's finite budget.
    from model_integration import BudgetContext
    from astrbot.core.astr_main_agent import _request_img_caption
    caption_event=real_event(group='caption-scope');scope=obj._scope(caption_event)
    caption_event.set_extra('_dsh_work',obj.runtime.begin(scope.key))
    proxy=BudgetContext(SimpleNamespace(get_provider_by_id=lambda identity:provider),obj,caption_event)
    assert isinstance(proxy.get_provider_by_id('fixture'),ProviderOpenAIOfficial)
    for _ in range(2):
        assert await _request_img_caption('fixture',{},[str(paths[0])],proxy)=='offline'
    try:await _request_img_caption('fixture',{},[str(paths[0])],proxy)
    except BudgetExceeded:pass
    else:raise AssertionError('pre-hook captioning bypassed event model budget')
    # The real OpenAI compatibility handler must not strip images and retry.
    async def reject(payload,tools,**kw):
        physical.append((payload,kw));raise RuntimeError('The model is not a VLM')
    provider._query=reject
    bounded=BudgetProvider(provider,obj.resources,obj.resources.budget('compat-fixture'),'foreground',1)
    before=len(physical)
    try:await bounded.text_chat(prompt='fixture',image_urls=['data:image/png;base64,'+base64.b64encode(PNG).decode()])
    except RuntimeError:pass
    else:raise AssertionError('image rejection silently became text')
    assert len(physical)==before+1
    stream_payload=[]
    async def query_stream(payload,tools,**kw):
        stream_payload.append(payload.copy())
        yield LLMResponse(role='assistant',completion_text='x'*50000,is_chunk=True)
    provider._query_stream=query_stream
    stream_provider=BudgetProvider(provider,obj.resources,obj.resources.budget('stream-fixture'),'foreground')
    try:[chunk async for chunk in stream_provider.text_chat_stream(prompt='fixture',max_tokens=7)]
    except BudgetExceeded:pass
    else:raise AssertionError('one oversized stream chunk bypassed output budget')
    assert stream_payload[0].get('max_tokens')==7,'physical stream omitted output limit'
    await obj.runtime.stop();await obj.resources.close()
    print('workorder4 framework OK')


if __name__=='__main__':
    if '--framework' in sys.argv:asyncio.run(framework_case())
    else:unittest.main()
