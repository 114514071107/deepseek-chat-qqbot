"""Real installed proxy/manager/executor run only in a fresh temporary root."""
import asyncio
import functools
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class ProxyIntegration(unittest.TestCase):
    def test_full_tool_set_proxy_survives_inject_and_both_permission_layers(self):
        with tempfile.TemporaryDirectory(prefix='dsh-framework-test-') as tmp:
            env=os.environ.copy()
            env.update(ASTRBOT_ROOT=tmp,TEMP=tmp,TMP=tmp,PYTHONIOENCODING='utf-8')
            result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--framework-case'],
                cwd=tmp,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',timeout=45)
            self.assertEqual(result.returncode,0,result.stdout[-6500:])
            self.assertIn('proxy pipeline OK',result.stdout)


async def framework_case():
    # AstrBot core import initializes config/logging/SQLite/scheduler. The parent
    # has isolated ASTRBOT_ROOT, cwd and TEMP before this interpreter starts.
    from astrbot.core.agent.tool import FunctionTool
    from astrbot.core.provider import func_tool_manager as framework
    from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
    from repair_pipeline_support import load_pipeline
    from test_repair_permissions import load_methods,Event
    from tool_permissions import install_executor_guard,trusted_plugin_tool

    plugin,ns=load_methods(guarded=True)
    from task_runtime import Runtime
    plugin.runtime=Runtime(lambda *args:True)
    root=Path(os.environ['ASTRBOT_ROOT'])
    (root/'persona.md').write_text('fixture persona',encoding='utf-8')
    pipeline,_=load_pipeline(root,names=('inject',),guarded=True)
    plugin.__dict__.update(pipeline.__dict__)
    # Bind the actual inject method to the same instance that owns tool handlers.
    type(plugin).inject=type(pipeline).inject
    ns.update(time=time,_gallery_db_rows=lambda tag,limit:[dict(pack='shared',rel='test.png',tag='happy',caption='fixture')])
    plugin.search_cd={}; plugin.tool_react_at={}
    event=Event()
    event.is_admin=lambda:False
    plugin.tool_react_at[plugin._scope(event).key]=time.time()
    allowed=('get_current_time','web_search','list_stickers')
    manager=object.__new__(framework.FunctionToolManager)
    manager.func_list=[FunctionTool(name=name,description='fixture',parameters={'type':'object','properties':{}},
        handler=functools.partial(getattr(type(plugin),name),plugin)) for name in (*allowed,'run_command','peek_user_data')]
    request=SimpleNamespace(prompt='fixture input',system_prompt='',func_tool=manager.get_full_tool_set())
    assert all(type(t) is framework._PermissionGuardedTool for t in request.func_tool.tools)
    await plugin.inject(event,request)
    assert request.func_tool.names()==list(allowed), f'allowed schemas lost: {request.func_tool.names()}'
    assert event.extra.get('_dsh_tool_used',0)==0
    for tool in request.func_tool.tools:
        assert type(tool) is framework._PermissionGuardedTool and tool.handler is None
        assert trusted_plugin_tool(tool,plugin)
    assert not trusted_plugin_tool(SimpleNamespace(name='get_current_time',handler=None,_wrapped=manager.func_list[0]),plugin)
    mismatch=framework._PermissionGuardedTool(manager.func_list[0],manager); mismatch.name='web_search'
    assert not trusted_plugin_tool(mismatch,plugin)
    cycle=framework._PermissionGuardedTool(manager.func_list[0],manager); cycle._wrapped=cycle
    assert not trusted_plugin_tool(cycle,plugin)
    class FakeProxy(framework._PermissionGuardedTool):
        async def call(self,*args,**kwargs): raise AssertionError('untrusted subclass executed')
    assert not trusted_plugin_tool(FakeProxy(manager.func_list[0],manager),plugin)

    class Preferences:
        permissions={}
        async def global_get(self,key,default): return {'_default':self.permissions}
    prefs=Preferences()
    context=SimpleNamespace(context=SimpleNamespace(event=event),tool_call_timeout=2)
    install_executor_guard(plugin,FunctionToolExecutor)
    async def search(query,**kwargs):
        return [dict(title='offline search',snippet='fixture result',url='https://fixture.invalid/')]
    def text(results): return '\n'.join(item.text for result in results for item in result.content)
    with patch.object(framework,'sp',prefs),patch.dict(sys.modules,websearch=SimpleNamespace(web_search=search)):
        for name,kwargs,want in [('get_current_time',{},'星期'),('web_search',{'query':'fixture'},'offline search'),
                                 ('list_stickers',{},'shared/test.png')]:
            result=[r async for r in FunctionToolExecutor.execute(request.func_tool.get_tool(name),context,**kwargs)]
            assert want in text(result), (name,text(result))
        assert event.extra['_dsh_tool_used']==3, event.extra
        prefs.permissions={'get_current_time':'admin'}
        result=[r async for r in FunctionToolExecutor.execute(request.func_tool.get_tool('get_current_time'),context)]
        assert 'requires admin' in text(result),text(result)
        assert event.extra['_dsh_tool_used']==3  # framework rejection must not bypass its policy
        prefs.permissions={}
        for tool in manager.get_full_tool_set().tools:
            if tool.name in ('run_command','peek_user_data'):
                result=[r async for r in FunctionToolExecutor.execute(tool,context)]
                assert '权限拒绝' in text(result)
        assert event.extra['_dsh_tool_used']==3
    # The same isolated real framework also supplies the response/Plain classes,
    # proving capture's final chain retains code through actual SDK containers.
    from astrbot.core.provider.entities import LLMResponse
    from astrbot.core.message.message_event_result import MessageChain
    from astrbot.core.message.components import Plain
    import ast
    for i,code in enumerate(('def say():\n    if True:\n        print("动作：表情 得意")\n\n    return "中文。"',
                             'def say():\r\n\treturn 1')):
        capture_root=root/('capture-'+str(i)); capture_root.mkdir()
        producer,globals_=load_pipeline(capture_root)
        globals_['Plain']=Plain
        text='```python\n'+code+'\n```'
        response=LLMResponse(role='assistant',result_chain=MessageChain(chain=[Plain(text)]))
        await producer.capture(event,response)
        assert response.result_chain.get_plain_text()==text
        ast.parse(code)
    # Actual framework event, registration, lock and workspace paths, all under
    # the parent's temporary ASTRBOT_ROOT. No production DB is opened.
    from astrbot.api.event import filter as real_filter
    from astrbot.core.star.star_handler import star_handlers_registry
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
    from astrbot.core.platform.platform_metadata import PlatformMetadata
    from astrbot.core.platform.message_type import MessageType
    from astrbot.core.provider.entities import ProviderRequest
    from astrbot.core.utils.session_lock import SessionLockManager
    from astrbot.core.workspace import default_workspace_root
    from session_scope import bind_scope
    matrix_root=root/'scope-matrix';matrix_root.mkdir()
    (matrix_root/'persona.md').write_text('fixture',encoding='utf-8')
    scoped,scope_ns=load_pipeline(matrix_root,guarded=True)
    scoped.runtime=Runtime(lambda *args:True)
    # Keep the real registration decorator on the actual source function.
    tree=ast.parse((Path(__file__).resolve().parents[1]/'plugin/astrbot_plugin_dsh_soul/main.py').read_text(encoding='utf-8'))
    definition=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DshSoul')
    fn=next(n for n in definition.body if getattr(n,'name','')=='inject')
    scope_ns.update(filter=real_filter,__name__='repair_scope_registration')
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'<real registered inject>','exec'),scope_ns)
    type(scoped).inject=scope_ns['inject']
    metadata=star_handlers_registry.get_handler_by_full_name('repair_scope_registration_inject')
    assert metadata.handler is type(scoped).inject and metadata.handler._dsh_managed
    events=[]
    for index,(sender,group,instance) in enumerate([('a','g1','b1'),('b','g1','b1'),('a','g2','b1'),('a','','b1'),('a','g1','b2')]):
        msg=AstrBotMessage();msg.type=MessageType.GROUP_MESSAGE if group else MessageType.FRIEND_MESSAGE
        msg.self_id='fixture-bot';msg.message_id='fixture-'+str(index);msg.group_id=group
        msg.sender=MessageMember(sender,'fixture');msg.message=[Plain('new question')];msg.message_str='new question';msg.raw_message={}
        current=AstrMessageEvent('new question',msg,PlatformMetadata('qq_official','fixture',instance),group or sender)
        scope=scoped._scope(current);scoped.h[scope.key]=[{'role':'user','text':'ONLY-SCOPE-'+str(index),
            'source':dict(scope.source(),message_id='previous-'+str(index))}]
        events.append(current)
    scope_ns['_read_notes']=lambda key:['PRIVATE-MEMORY-SENTINEL'] if key.startswith('p2_') else ['GROUP-MEMORY-SENTINEL']
    for index,current in enumerate(events):
        req=ProviderRequest(prompt='new question',contexts=[{'role':'user','content':'LEGACY-GROUP-SENTINEL'}])
        await metadata.handler(scoped,current,req)
        messages=[{'role':'system','content':req.system_prompt},*req.contexts,await req.assemble_context()]
        wire=__import__('json').dumps(messages,ensure_ascii=False)
        assert 'LEGACY-GROUP-SENTINEL' not in wire
        assert ('PRIVATE-MEMORY-SENTINEL' in wire)==(index==3)
        assert 'ONLY-SCOPE-'+str(index) in wire
        allowed={0,1} if index in (0,1) else {index}
        assert all(('ONLY-SCOPE-'+str(other) in wire)==(other in allowed) for other in range(5))
        assert ('GROUP-MEMORY-SENTINEL' in wire)==(index!=3)
    assert len({default_workspace_root(e.unified_msg_origin) for e in events})==4
    locks=SessionLockManager()
    async with locks.acquire_lock(events[0].unified_msg_origin):
        async def other_sender():
            async with locks.acquire_lock(events[1].unified_msg_origin): return True
        task=asyncio.create_task(other_sender())
        await asyncio.sleep(.02)
        assert not task.done(), 'same-group sender bypassed shared session lock'
    assert await asyncio.wait_for(task,.2)
    # The framework's passive first bubble also awaits outside plugin _send.
    # Disabling reply must cancel the borrowed event task before event.send.
    from astrbot.core.pipeline.respond.stage import RespondStage
    from astrbot.core.message.message_event_result import MessageEventResult
    from state_store import StateController,read_json
    for operation,body in [('switch',{'key':'enabled','value':False}),('user',{'key':'reply','value':False}),('legacy-user',{'key':'reply','value':False})]:
        response_root=root/('respond-'+operation);response_root.mkdir()
        (response_root/'persona.md').write_text('fixture',encoding='utf-8')
        responder,env=load_pipeline(response_root,names=('inject','_allowed'),guarded=True)
        responder.sil={}
        env['_conf']=lambda key:read_json(response_root/'dsh_soul_conf.json',{}).get(key,True)
        env['_load']=read_json
        responder.runtime=Runtime(responder._allowed)
        current=events[3]
        current._extras.pop('_dsh_work',None)
        responder._scope(current)
        stage=RespondStage();stage.enable_seg=True;stage.only_llm_result=False;stage.platform_settings={}
        ready=asyncio.Event();release=asyncio.Event();sent=[]
        async def interval(comp):ready.set();await release.wait();return 0
        async def send(chain):sent.append(chain)
        stage._calc_comp_interval=interval;current.send=send
        current.set_result(MessageEventResult(chain=[Plain('fixture')]))
        async def pipeline():
            await responder.inject(current,ProviderRequest(prompt='fixture'))
            await stage.process(current)
        task=asyncio.create_task(pipeline());await asyncio.wait_for(ready.wait(),1)
        state=StateController(responder,response_root,clear_framework=lambda key:asyncio.sleep(0))
        if operation=='user':body['uid']=bind_scope(current).key
        if operation=='legacy-user':body['uid']=bind_scope(current).sender
        await state.apply('user' if operation=='legacy-user' else operation,body);release.set()
        await asyncio.gather(task,return_exceptions=True)
        assert task.cancelled() and not sent,(operation,sent)
        await responder.runtime.stop()
    await scoped.runtime.stop();await plugin.runtime.stop()
    print('proxy pipeline OK')


if __name__=='__main__':
    if '--framework-case' in sys.argv: asyncio.run(framework_case())
    else: unittest.main()
