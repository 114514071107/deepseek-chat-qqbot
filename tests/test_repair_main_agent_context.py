"""Exercise the real main-agent builder in a disposable framework process."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class MainAgentContextRegression(unittest.TestCase):
    def isolated(self, case):
        with tempfile.TemporaryDirectory(prefix='dsh-main-agent-') as tmp:
            env = os.environ.copy()
            env.update(ASTRBOT_ROOT=tmp, TEMP=tmp, TMP=tmp, PYTHONIOENCODING='utf-8')
            result = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), case],
                cwd=tmp, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout[-8500:])
            self.assertIn('main-agent context OK', result.stdout)

    def test_text_main_builder_validates_context_and_completes_reply(self): self.isolated('--text')

    def test_pre_hook_caption_and_main_model_share_one_finite_budget(self): self.isolated('--caption')

    def test_concurrent_main_builders_keep_context_and_budgets_request_local(self): self.isolated('--concurrent')


async def framework_case(case):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch
    from repair_pipeline_support import load_pipeline
    from test_repair_p2_acceptance import real_event
    from test_repair_batch_input import PNG
    from resource_budget import Resources, BudgetExceeded, BudgetProvider
    from model_integration import install_model_adapters
    from reply_integration import install_reply_adapters
    from tool_permissions import install_executor_guard
    from task_runtime import work_context
    from qq_delivery import QQDelivery
    from astrbot.core import astr_main_agent
    from astrbot.core.astr_agent_context import AstrAgentContext
    from astrbot.core.star.context import Context
    from astrbot.core.agent.tool import ToolSet
    from astrbot.core.provider.entities import LLMResponse
    from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
    from astrbot.core.message.components import Plain, Image
    from astrbot.core.message.message_event_result import MessageChain
    from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import InternalAgentSubStage
    from astrbot.core.star.session_llm_manager import SessionServiceManager
    from astrbot.core.star.session_plugin_manager import SessionPluginManager
    from astrbot.core.star.star_handler import star_handlers_registry, EventType
    from astrbot.core.star.star import star_map
    from astrbot.core.skills.skill_manager import SkillManager

    root = Path(os.environ['ASTRBOT_ROOT'])
    obj, ns = load_pipeline(root, names=('capture', '_clear_text_result', '_set_first_bubble_result', '_send'), guarded=True)
    obj.resources = Resources({'model_calls': 2})
    ns.update(Plain=Plain, MessageChain=MessageChain, random=SimpleNamespace(random=lambda: 1, uniform=lambda *a: 0))
    obj._drip_interval = lambda: (0, 0)
    physical = []; posts = []; saved = []; config_origins = []
    caption = case == '--caption'

    def provider(identity, modalities):
        result = object.__new__(ProviderOpenAIOfficial)
        result.provider_config = dict(id=identity, modalities=modalities, model='fixture', max_context_tokens=128000)
        result.model_name = 'fixture'; result.get_model = lambda: 'fixture'; result.api_keys = ['fixture-key']
        result.client = SimpleNamespace(api_key='', base_url=SimpleNamespace(host='offline.invalid'))
        async def query(payload, tools, **kw):
            physical.append((identity, payload, kw))
            return LLMResponse(role='assistant', completion_text='fixed image description' if identity == 'caption' else 'offline answer')
        result._query = query
        return result
    main = provider('main', ['text'] if caption else ['text', 'image'])
    image_provider = provider('caption', ['text', 'image'])
    config = {'provider_settings': {'default_image_caption_provider_id': 'caption' if caption else '',
        'web_search': False}, 'timezone': 'Asia/Shanghai'}
    conversation = SimpleNamespace(cid='fixture-cid', history='[]', persona_id=None, token_usage=0)
    async def get_conversation(*args): return conversation
    async def save_conversation(umo, cid, **kwargs): saved.append((umo, kwargs['history']))
    conv_manager = SimpleNamespace(get_curr_conversation_id=AsyncMock(return_value='fixture-cid'),
        get_conversation=get_conversation, update_conversation=save_conversation)
    tools = SimpleNamespace(get_full_tool_set=lambda: ToolSet())
    manager = SimpleNamespace(inst_map={'main': main, 'caption': image_provider}, llm_tools=tools,
        get_using_provider_async=AsyncMock(return_value=main))
    def get_conf(umo): config_origins.append(umo); return config
    # A real Context constructor with replacement services, never real config,
    # SQLite, provider creation, platform clients or plugin registration.
    context = Context(event_queue=asyncio.Queue(), config=config, db=None,
        provider_manager=manager,
        platform_manager=SimpleNamespace(platform_insts=[SimpleNamespace(meta=lambda: SimpleNamespace(id='fixture-instance', name='qq_official'))]),
        conversation_manager=conv_manager, message_history_manager=None,
        persona_manager=SimpleNamespace(resolve_selected_persona=AsyncMock(return_value=(None, None, None, False))),
        astrbot_config_mgr=SimpleNamespace(get_conf=get_conf), knowledge_base_manager=SimpleNamespace(), cron_manager=None)
    obj.context = context
    async def parse(chain): return chain.get_plain_text(), None, None, None, None, None, None
    async def post(platform, endpoint, payload):
        posts.append((endpoint, payload)); return 200, {'id': 'accepted-'+str(len(posts))}
    obj.delivery = QQDelivery(context, parse=parse, request=post, audit=obj._record_delivery_result)
    install_executor_guard(obj); install_reply_adapters(); install_model_adapters()
    installed = astr_main_agent.build_main_agent
    install_model_adapters()
    assert astr_main_agent.build_main_agent is installed
    assert InternalAgentSubStage.__module__  # imports the consumer of the patched builder
    from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal
    assert internal.build_main_agent is installed
    async def capture(event, response): await obj.capture(event, response)
    handler = SimpleNamespace(handler=capture, handler_module_path='builder_fixture', handler_name='capture')
    image = root/'fixed.png'; image.write_bytes(PNG)

    def event_for(group):
        event = real_event(group=group)
        event.platform_meta.support_proactive_message = False
        if caption: event.message_obj.message.append(Image.fromFileSystem(str(image)))
        scope = obj._scope(event); token = obj.runtime.begin(scope.key)
        event.set_extra('_dsh_work', token)
        obj.request_owners = getattr(obj, 'request_owners', {}); obj.request_owners[scope.key] = token.request
        obj.request_events = getattr(obj, 'request_events', {}); obj.request_events[scope.key] = event
        obj.run_active[scope.key] = 1
        return event, scope, token
    settings = astr_main_agent.MainAgentBuildConfig(tool_call_timeout=1, add_cron_tools=False,
        computer_use_runtime='none', timezone='Asia/Shanghai', provider_settings=config['provider_settings'])
    with patch.object(SessionServiceManager, 'is_session_enabled', AsyncMock(return_value=True)), \
         patch.object(SessionPluginManager, 'is_plugin_enabled_for_session', AsyncMock(return_value=True)), \
         patch.object(SkillManager, 'list_skills', return_value=[]), \
         patch('astrbot.core.tools.knowledge_base_tools.sp.session_get', AsyncMock(return_value={})), \
         patch.dict(star_map, builder_fixture=SimpleNamespace(name='fixture')), \
         patch.object(star_handlers_registry, 'get_handlers_by_event_type', side_effect=lambda kind, **kw: [handler] if kind == EventType.OnLLMResponseEvent else []):
        async def build(event):
            # No replacement for build_main_agent, AstrAgentContext or reset.
            return await astr_main_agent.build_main_agent(event=event, plugin_context=context, config=settings)
        first, scope, token = event_for('first-group')
        if case == '--concurrent':
            second, other_scope, other_token = event_for('second-group')
            a, b = await asyncio.gather(build(first), build(second))
            for built, event, identity in [(a, first, token.request), (b, second, other_token.request)]:
                bound = built.agent_runner.run_context.context.context
                assert isinstance(bound, Context) and type(bound) is type(context)
                assert bound is not context and bound.conversation_manager is conv_manager
                assert isinstance(built.agent_runner.run_context.context, AstrAgentContext)
                assert built.agent_runner.run_context.context.event is event
                assert built.agent_runner.provider.budget.identity == identity
                assert bound.get_provider_by_id('main') is not main
            assert a.agent_runner.run_context.context.context is not b.agent_runner.run_context.context.context
            with work_context(token, first):
                await a.agent_runner.provider.text_chat(prompt='first')
                await a.agent_runner.provider.text_chat(prompt='first')
                try: await a.agent_runner.provider.text_chat(prompt='over limit')
                except BudgetExceeded: pass
                else: raise AssertionError('request gained another model quota')
            with work_context(other_token, second): await b.agent_runner.provider.text_chat(prompt='second')
            assert obj._budget(first).calls == 2 and obj._budget(second).calls == 1
        else:
            with work_context(token, first):
                built = await build(first)
                runner = built.agent_runner
                assert isinstance(runner.run_context.context.context, Context)
                assert runner.run_context.context.event is first
                assert isinstance(runner.provider, BudgetProvider)
                assert runner.provider.budget is obj._budget(first)
                if caption:
                    assert [p[0] for p in physical] == ['caption']
                    assert 'fixed image description' in str(built.provider_request.extra_user_content_parts)
                    assert obj._budget(first).calls == 1
                else: assert physical == []
                responses = [response async for response in runner.step()]
                assert responses and runner.final_llm_resp.completion_text == 'offline answer'
                # Real capture, completion, accepted history and framework save.
                assert first.get_extra('_dsh_reply_plan') is not None
                stage = object.__new__(InternalAgentSubStage)
                await stage._save_to_history(first, built.provider_request, runner.final_llm_resp, runner.run_context.messages, None)
                assert [row['text'] for row in obj.h[scope.key]] == ['offline answer']
                assert obj.h[scope.key][0]['delivery']['status'] == 'accepted'
                assert saved[-1][1][-1]['content'] == 'offline answer'
                assert len(posts) == 1 and posts[0][1]['msg_id'] == 'fixture-msg'
                assert scope.key not in obj.run_active
                # Context adaptation must retain the actual tool executor guard.
                denied = [value async for value in runner.tool_executor.execute(
                    SimpleNamespace(name='astrbot_execute_shell'), runner.run_context)]
                assert len(denied) == 1 and denied[0].isError
                if not caption: await runner.provider.text_chat(prompt='remaining quota')
                before = len(physical)
                try: await runner.provider.text_chat(prompt='over budget')
                except BudgetExceeded: pass
                else: raise AssertionError('main model bypassed shared caption/request quota')
                assert len(physical) == before
                assert all(p[2]['request_max_retries'] == 1 for p in physical)
        assert context.get_provider_by_id('main') is main
        assert await context.get_using_provider_async(umo=first.unified_msg_origin) is main
        assert 'get_provider_by_id' not in context.__dict__
        assert all(not origin.startswith(('c2_', 'p2_')) for origin in config_origins)
    await obj.runtime.stop(); await obj.resources.close()
    print('main-agent context OK', case)


if __name__ == '__main__':
    case = next((arg for arg in sys.argv if arg in ('--text', '--caption', '--concurrent')), None)
    if case: asyncio.run(framework_case(case))
    else: unittest.main()
