"""Work order 2 acceptance failures, using actual plugin and framework paths."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from repair_pipeline_support import load_pipeline
from session_scope import bind_scope
from state_store import StateController, LAYERS, read_json, write_json
from task_runtime import Runtime
from test_repair_session_scope import ScopeEvent


class AcceptanceRegression(unittest.IsolatedAsyncioTestCase):
    async def test_all_layers_deleted_then_inject_cannot_recover_ephemeral_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'persona.md').write_text('fixture',encoding='utf-8')
            obj,ns=load_pipeline(root,guarded=True);event=ScopeEvent();scope=obj._scope(event)
            obj.runtime=Runtime(lambda *a:True);obj.th={};obj.t_path=str(root/'thoughts_v2.json')
            ns.update(_load=read_json,_save=write_json,_jf=lambda key,name:str(root/(name+'_'+key+'.json')))
            markers=('UNSENT-PRIVATE-CONTENT','RECENT-PRIVATE-REPLY','OLD-MEDIA-CAPTION')
            obj.interrupted_note[scope.key]=markers[0]
            obj.last_react[scope.key]={'text':markers[1],'ts':time.time()}
            obj.last_sticker[scope.key]={'tag':'fixture','caption':markers[2],'ts':time.time()}
            state=StateController(obj,root,clear_framework=lambda key:asyncio.sleep(0))
            result=await state.delete(scope.key,list(LAYERS),backup_files=[],confirm_shared_backups=True)
            self.assertTrue(result['ok'],result)
            req=SimpleNamespace(prompt='new question',contexts=[],system_prompt='')
            await obj.inject(ScopeEvent(),req)
            wire=json.dumps(vars(req),ensure_ascii=False)
            for marker in markers:self.assertNotIn(marker,wire)
            await obj.runtime.stop()

    async def test_archive_only_delete_preserves_rolling_context_and_other_person(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp,names=());scope=obj._scope(ScopeEvent());other=obj._scope(ScopeEvent('b'))
            obj.runtime=Runtime(lambda *a:True)
            obj.interrupted_note={scope.key:'rolling context',other.key:'other context'}
            state=StateController(obj,tmp,clear_framework=lambda key:asyncio.sleep(0))
            self.assertTrue((await state.delete(scope.key,['archive']))['ok'])
            self.assertEqual(obj.interrupted_note,{scope.key:'rolling context',other.key:'other context'})
            await obj.runtime.stop()

    async def test_startup_greet_records_the_frozen_owner_scope_after_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'persona.md').write_text('fixture',encoding='utf-8')
            obj,ns=load_pipeline(root,names=('_startup_greet','_record_assistant_turn'),guarded=True)
            scope=obj._scope(ScopeEvent('owner'));obj.runtime=Runtime(lambda *a:True)
            obj.g_path=str(root/'greet.json');sent=[]
            async def sleep(seconds):pass
            async def model(*a,**kw):return SimpleNamespace(completion_text='上线啦。')
            async def send(target,chain,**kw):
                from qq_delivery import DeliveryResult
                assert kw=={'mode':'proactive'}
                sent.append((target,chain));return DeliveryResult('accepted',message_id='greet')
            obj._chat=model;obj._send=send
            ns.update(asyncio=SimpleNamespace(sleep=sleep),_load=read_json,_save=write_json,MessageChain=lambda **kw:kw)
            await obj._startup_greet(scope.key,scope.target)
            self.assertEqual(sent[0][0],scope.target)
            self.assertEqual(obj.h[scope.key][0]['text'],'上线啦')
            self.assertEqual(obj.h[scope.key][0]['source']['sender'],'owner')
            self.assertGreater(read_json(obj.g_path,{})['last'],0)
            await obj.runtime.stop()


class FrameworkAcceptance(unittest.TestCase):
    def isolated(self,case):
        with tempfile.TemporaryDirectory(prefix='dsh-p2-framework-') as tmp:
            env=os.environ.copy();env.update(ASTRBOT_ROOT=tmp,TEMP=tmp,TMP=tmp,PYTHONIOENCODING='utf-8')
            result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),case],cwd=tmp,env=env,
                                  stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',timeout=45)
            self.assertEqual(result.returncode,0,result.stdout[-6500:])

    def test_framework_hook_swallowing_cancellation_cannot_resume_pipeline(self):self.isolated('--cancel-case')
    def test_rekey_preserves_live_framework_session_policies(self):self.isolated('--policy-case')
    def test_dashboard_new_scope_denials_apply_and_unsupported_profile_route_fails(self):self.isolated('--dashboard-case')
    def test_constructor_protects_dashboard_routes_before_first_message(self):self.isolated('--startup-routes-case')


def real_event(sender='a',group='g1',instance='fixture-instance'):
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
    from astrbot.core.platform.platform_metadata import PlatformMetadata
    from astrbot.core.platform.message_type import MessageType
    from astrbot.core.message.components import Plain
    msg=AstrBotMessage();msg.type=MessageType.GROUP_MESSAGE if group else MessageType.FRIEND_MESSAGE
    msg.self_id='fixture-bot';msg.message_id='fixture-msg';msg.group_id=group
    msg.sender=MessageMember(sender,'fixture');msg.message=[Plain('question')];msg.raw_message={}
    return AstrMessageEvent('question',msg,PlatformMetadata('qq_official','fixture',instance),group or sender)


async def cancel_case():
    from astrbot.core.pipeline.context_utils import call_event_hook
    from astrbot.core.pipeline.scheduler import PipelineScheduler
    from astrbot.core.star.star_handler import star_handlers_registry,EventType
    from astrbot.core.star.star import star_map
    from astrbot.core.provider.entities import ProviderRequest
    from astrbot.core.message.message_event_result import MessageEventResult
    from astrbot.core.message.components import Plain
    cases=[('inject',EventType.OnLLMRequestEvent,False),('capture',EventType.OnLLMResponseEvent,False),
           ('post_send',EventType.OnAfterMessageSentEvent,False),('inject',EventType.OnLLMRequestEvent,True)]
    for index,(name,kind,waiting) in enumerate(cases):
        root=Path(os.environ['ASTRBOT_ROOT'])/str(index);root.mkdir();(root/'persona.md').write_text('fixture')
        obj,ns=load_pipeline(root,names=('inject','capture','post_send'),guarded=True);obj.runtime=Runtime(lambda *a:True)
        event=real_event();scope=obj._scope(event)
        event.set_extra('_dsh_work',obj.runtime.begin(scope.key))
        entered=asyncio.Event()
        if waiting:
            obj.batch_wait[scope.key]=True;obj.last_msg_at={scope.key:time.time()};obj.batch_skipwait={}
            async def wait(seconds):entered.set();await asyncio.Event().wait()
            ns.update(BATCH_WAIT=60,BATCH_MAX_WAIT=60,REST_IDLE=float('inf'),asyncio=SimpleNamespace(sleep=wait))
        else:obj.runtime.invalidate(scope.key)
        event.set_result(MessageEventResult(chain=[Plain('must not send')]))
        args=[ProviderRequest(prompt='question')] if name=='inject' else [SimpleNamespace()] if name=='capture' else []
        async def callback(event):await getattr(obj,name)(event,*args)
        handler=SimpleNamespace(handler=callback,handler_module_path='fixture_p2',handler_name=name)
        effects=[]
        class Hooks:
            async def process(self,event):await call_event_hook(event,kind)
        class Following:
            async def process(self,event):effects.extend(['model dispatch','passive send'])
        scheduler=object.__new__(PipelineScheduler);scheduler.stages=[Hooks(),Following()]
        with patch.dict(star_map,fixture_p2=SimpleNamespace(name='fixture')), \
             patch.object(star_handlers_registry,'get_handlers_by_event_type',return_value=[handler]):
            if waiting:
                task=asyncio.create_task(scheduler._process_stages(event));await asyncio.wait_for(entered.wait(),1)
                obj.runtime.invalidate(scope.key);await task
            else:await scheduler._process_stages(event)
        assert event.is_stopped() and not effects,(name,effects)
        assert not event.get_result().chain,(name,event.get_result())
        await obj.runtime.stop()
    # Policy backends can await too. Termination must own the event before that
    # first await, rather than noticing it only once policy loading completes.
    root=Path(os.environ['ASTRBOT_ROOT'])/'policy-wait';root.mkdir()
    obj,_=load_pipeline(root,guarded=True);obj.runtime=Runtime(lambda *a:True)
    event=real_event();entered=asyncio.Event()
    async def slow_policy(event):entered.set();await asyncio.Event().wait()
    with patch('session_scope.check_framework_policy',slow_policy):
        task=asyncio.create_task(obj.inject(event,ProviderRequest(prompt='fixture')))
        await asyncio.wait_for(entered.wait(),1);await obj.runtime.stop()
        assert task.done(),'termination returned while policy-wait event was still running'
        await asyncio.gather(task,return_exceptions=True)
        assert task.cancelled() and event.is_stopped()


async def policy_case():
    from astrbot.core.star.session_llm_manager import SessionServiceManager as Services
    from astrbot.core.star.session_plugin_manager import SessionPluginManager as Plugins
    from astrbot.core.star.context import Context
    from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
    from astrbot.core import sp
    first=real_event();second=real_event('b');private=real_event(group='')
    original=first.unified_msg_origin;private_original=private.unified_msg_origin
    await sp.put_async(scope='umo',scope_id=original,key='session_service_config',value={'llm_enabled':False,'tts_enabled':False,'session_enabled':False})
    await sp.put_async(scope='umo',scope_id=original,key='session_plugin_config',value={original:{'disabled_plugins':['fixture-plugin']}})
    for event in (first,second,private):bind_scope(event)
    assert first.unified_msg_origin==second.unified_msg_origin  # entire group owns one session
    assert not await Services.should_process_llm_request(first),'rekey reopened disabled LLM'
    assert not await Services.should_process_tts_request(first),'rekey reopened disabled TTS'
    assert not await Services.is_session_enabled(first.unified_msg_origin),'rekey reopened stopped session'
    assert not await Plugins.is_plugin_enabled_for_session(first.unified_msg_origin,'fixture-plugin')
    assert await Services.should_process_llm_request(private),'group policy leaked into private'
    assert await Services.is_llm_enabled_for_session('unrelated:FriendMessage:fixture')
    # Live changes and setters remain attached to the original policy identity.
    await Services.set_llm_status_for_session(original,True)
    assert await Services.should_process_llm_request(first)
    assert await Services.is_llm_enabled_for_session(original)
    mgr=object.__new__(AstrBotConfigManager)
    mgr.confs={'default':{'provider_settings':{'enable':True}},'limited':{'provider_settings':{'enable':False}}}
    mgr.abconf_data={'limited':{'name':'fixture','path':'fixture.json'}}
    mgr.ucr=SimpleNamespace(get_conf_id_for_umop=lambda umo:'limited' if umo==original else None)
    ctx=object.__new__(Context);ctx.astrbot_config_mgr=mgr;ctx._config=mgr.confs['default']
    assert ctx.get_config(first.unified_msg_origin)['provider_settings']['enable'] is False,'rekey lost source config profile'
    assert ctx.get_config(private.unified_msg_origin)['provider_settings']['enable'] is True
    assert first.get_extra('_dsh_original_umo')==original
    assert private.get_extra('_dsh_original_umo')==private_original
    # Both the live filter and direct plugin-policy lookup preserve the anchor.
    from astrbot.core.star.star import star_map
    handler=SimpleNamespace(handler_module_path='fixture_policy',handler_name='fixture')
    with patch.dict(star_map,fixture_policy=SimpleNamespace(name='fixture-plugin',reserved=False)):
        assert await Plugins.filter_handlers_by_session(first,[handler])==[]
    # unique_session may give the original group event a composite session ID.
    unique=real_event('c');unique.session_id='g1_c';unique_original=unique.unified_msg_origin
    await sp.put_async(scope='umo',scope_id=unique_original,key='session_service_config',value={'llm_enabled':False})
    bind_scope(unique)
    assert unique.get_extra('_dsh_original_umo')==unique_original
    assert not await Services.should_process_llm_request(unique)
    # Two actors can have different original unique-session policies, while
    # sharing a group history. The last event must never choose A's policy.
    restricted=real_event('restricted','policy-group');restricted.session_id='policy-group_restricted'
    allowed=real_event('allowed','policy-group');allowed.session_id='policy-group_allowed'
    restricted_origin=restricted.unified_msg_origin
    await sp.put_async(scope='umo',scope_id=restricted_origin,key='session_service_config',value={'llm_enabled':False})
    bind_scope(restricted);bind_scope(allowed)
    assert restricted.unified_msg_origin==allowed.unified_msg_origin
    assert not await Services.should_process_llm_request(restricted),'same-group later actor reopened earlier actor policy'
    assert await Services.should_process_llm_request(allowed)
    from task_runtime import work_context
    mgr.ucr.get_conf_id_for_umop=lambda umo:'limited' if umo==restricted_origin else None
    with work_context(None,restricted):assert ctx.get_config(restricted.unified_msg_origin)['provider_settings']['enable'] is False
    with work_context(None,allowed):assert ctx.get_config(allowed.unified_msg_origin)['provider_settings']['enable'] is True
    await sp.put_async(scope='umo',scope_id=restricted_origin,key='session_plugin_config',value={restricted_origin:{'disabled_plugins':['fixture-plugin']}})
    with patch.dict(star_map,fixture_policy=SimpleNamespace(name='fixture-plugin',reserved=False)):
        assert await Plugins.filter_handlers_by_session(restricted,[handler])==[]
        assert await Plugins.filter_handlers_by_session(allowed,[handler])==[handler]
    # Admission stages run before the plugin gate: one group rate limit must
    # still apply before admitted members share the group's session lock.
    from astrbot.core.pipeline.rate_limit_check.stage import RateLimitStage
    rate=RateLimitStage()
    await rate.initialize(SimpleNamespace(astrbot_config={'platform_settings':{'rate_limit':{'count':1,'time':60,'strategy':'discard'}}}))
    admitted=real_event('x','rate-fixture');limited=real_event('y','rate-fixture')
    await rate.process(admitted);bind_scope(admitted)
    await rate.process(limited)
    assert not admitted.is_stopped() and limited.is_stopped()


async def dashboard_case():
    from astrbot.core.star.session_llm_manager import SessionServiceManager as Services
    from astrbot.core.star.session_plugin_manager import SessionPluginManager as Plugins
    from astrbot.dashboard.services.session_management_service import SessionManagementService
    from astrbot.dashboard.services.config_service import ConfigRoutingService
    from astrbot.core.umop_config_router import UmopConfigRouter
    from astrbot.core import sp
    event=real_event();original=event.unified_msg_origin;bind_scope(event);umo=event.unified_msg_origin
    service=object.__new__(SessionManagementService)
    await service.update_session_rule({'umo':umo,'rule_key':'session_service_config','rule_value':{'llm_enabled':False,'tts_enabled':False}})
    assert not await Services.should_process_llm_request(event),'Dashboard saved false but LLM stayed enabled'
    assert not await Services.should_process_tts_request(event)
    await service.update_session_rule({'umo':umo,'rule_key':'session_plugin_config','rule_value':{'disabled_plugins':['fixture-plugin']}})
    assert not await Plugins.is_plugin_enabled_for_session(umo,'fixture-plugin')
    await service.batch_update_service({'umos':[umo],'llm_enabled':True,'session_enabled':False})
    assert not await Services.is_session_enabled(umo)
    root=Path(os.environ['ASTRBOT_ROOT'])/'dashboard';root.mkdir()
    obj,ns=load_pipeline(root,guarded=True);obj.runtime=Runtime(lambda *a:True)
    try:await obj.inject(event,SimpleNamespace(prompt='question',system_prompt='',contexts=[]))
    except asyncio.CancelledError:pass
    assert event.is_stopped(),'new scope stopped session bypassed managed entry'
    # Parent restrictions remain a ceiling even when a child explicitly allows.
    await Services.set_llm_status_for_session(original,False)
    await Services.set_llm_status_for_session(umo,True)
    assert not await Services.should_process_llm_request(event)
    # A config profile is still attached to the actual group/private admission
    # pipeline. Reject internal-only profile bindings before acknowledging them.
    router=UmopConfigRouter(sp);routing=ConfigRoutingService(SimpleNamespace(umop_config_router=router))
    unseen='fixture-instance:GroupMessage:c2_'+'1'*64
    for operation in (lambda:routing.set_route(umo=umo,config_id='fixture'),
                      lambda:routing.replace_route_mapping(routing={umo:'fixture'}),
                      lambda:routing.set_route(unseen,'fixture'),
                      lambda:routing.replace_route_mapping({'fixture-instance:GroupMessage:c2_*':'fixture'})):
        try:await operation()
        except ValueError as error:assert '原始会话' in str(error),str(error)
        else:raise AssertionError('internal-only profile binding must fail explicitly')
        assert router.umop_to_conf_id=={}
    await routing.set_route(original,'fixture');assert router.umop_to_conf_id=={original:'fixture'}
    # Helper reload must not drop policies for already-bound live events or
    # stack wrapper layers on framework classes that outlive the plugin.
    import importlib,session_scope
    before=Services.is_llm_enabled_for_session
    importlib.reload(session_scope)
    session_scope.bind_scope(real_event('b'))
    assert Services.is_llm_enabled_for_session is before
    assert not await Services.should_process_llm_request(event)
    await obj.runtime.stop()


async def startup_routes_case():
    # Exercise the actual constructor, not a manual call to the adapter or
    # bind_scope. Import/instantiate AstrBot only in the parent's temporary root.
    import ast
    import importlib
    import session_scope
    from astrbot.core.star.base import Star
    from astrbot.core.star.context import Context
    from astrbot.core.umop_config_router import UmopConfigRouter
    from astrbot.dashboard.services.config_service import ConfigRoutingService
    from astrbot.core import sp
    from repair_pipeline_support import PLUGIN
    from task_runtime import managed
    from tool_permissions import install_executor_guard
    root=Path(os.environ['ASTRBOT_ROOT'])/'startup';root.mkdir()
    tree=ast.parse((PLUGIN/'main.py').read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DshSoul')
    cls.decorator_list=[]
    cls.body=[n for n in cls.body if getattr(n,'name','') in ('__init__','_allowed','_clear_framework_history','terminate','_record_delivery_result','_retain_sent_media','_thread')]
    imports=[n for n in tree.body if isinstance(n,ast.ImportFrom) and n.module in ('session_scope','reply_integration','qq_delivery','resource_budget','model_integration')]
    ns=dict(__name__='repair_startup_fixture',Star=Star,Context=Context,Runtime=Runtime,managed=managed,background_work=__import__('task_runtime').background_work,
            StateController=StateController,DATA=str(root),os=os,_load=read_json,
            _jf=lambda uid,name:str(root/(name+'_'+uid+'.json')),
            install_executor_guard=install_executor_guard,
            _ensure_collect_pack=lambda:None)  # gallery setup is unrelated to routing
    exec(compile(ast.fix_missing_locations(ast.Module(body=imports+[cls],type_ignores=[])),'<actual plugin constructor>','exec'),ns)
    router=UmopConfigRouter(sp)
    service=ConfigRoutingService(SimpleNamespace(umop_config_router=router))
    baseline={'fixture-instance:GroupMessage:original-group':'base'}
    await service.replace_route_mapping(dict(baseline))
    failures=[];previous_wrapper=None
    for phase in ('first load','repeated construction','helper reload'):
        if phase=='helper reload':importlib.reload(session_scope)
        plugin=ns['DshSoul'](SimpleNamespace())
        assert not session_scope._policy_origins,'fixture must never bind a message'
        wrapper=ConfigRoutingService.set_route
        if previous_wrapper is not None:assert wrapper is previous_wrapper,'adapters stacked on reload'
        previous_wrapper=wrapper
        internal=('fixture-instance:GroupMessage:c2_'+'a'*64,
                  'fixture-instance:FriendMessage:p2_'+'b'*64,
                  'fixture-instance:GroupMessage:c2_*',
                  'fixture-instance:FriendMessage:p2_*')
        for umo in internal:
            for mode in ('single','bulk'):
                try:
                    if mode=='single':await service.upsert_route_from_dashboard_payload({'umo':umo,'conf_id':'limited'})
                    else:await service.replace_routes_from_dashboard_payload({'routing':{**baseline,umo:'limited'}})
                except ValueError as error:assert '原始会话' in str(error),str(error)
                else:failures.append((phase,mode,umo.split(':',2)[-1][:3]))
                if router.umop_to_conf_id!=baseline:
                    failures.append((phase,mode,'routing changed'))
                    await router.update_routing_data(dict(baseline))
                assert await sp.global_get('umop_config_routing',{})==baseline,'rejected route reached persistence'
        # Actual original-session/platform writes still work before any message.
        await service.upsert_route_from_dashboard_payload({'umo':'fixture-instance::','conf_id':'platform'})
        assert router.umop_to_conf_id['fixture-instance::']=='platform'
        await service.replace_routes_from_dashboard_payload({'routing':dict(baseline)})
        await plugin.terminate()
    assert not failures,('routes accepted before first message',failures)


if __name__=='__main__':
    if '--cancel-case' in sys.argv:asyncio.run(cancel_case())
    elif '--policy-case' in sys.argv:asyncio.run(policy_case())
    elif '--dashboard-case' in sys.argv:asyncio.run(dashboard_case())
    elif '--startup-routes-case' in sys.argv:asyncio.run(startup_routes_case())
    else:unittest.main()
