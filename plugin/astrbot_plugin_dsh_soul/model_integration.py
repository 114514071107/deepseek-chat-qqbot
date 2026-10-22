"""AstrBot 4.29.1 reset boundary; no on-disk framework patch."""
import functools
import inspect
import copy
from resource_budget import BudgetProvider


class BudgetContext:
    """Preserve Provider class checks while binding pre-hook caption calls."""
    def __init__(self, context, plugin, event):
        self.context=context; self.plugin=plugin; self.event=event; self.providers={}

    def __getattr__(self, name): return getattr(self.context, name)

    def wrap(self, provider):
        if provider is None or not callable(getattr(provider,'text_chat',None)): return provider
        if id(provider) in self.providers: return self.providers[id(provider)]
        result=copy.copy(provider)
        result.provider_config=dict(provider.provider_config)
        result._dsh_base_provider=provider
        async def text_chat(**kw):
            bound=BudgetProvider(provider,self.plugin.resources,self.plugin._budget(self.event),'foreground',len(kw.get('image_urls') or []))
            return await bound.text_chat(**kw)
        async def stream(**kw):
            bound=BudgetProvider(provider,self.plugin.resources,self.plugin._budget(self.event),'foreground',len(kw.get('image_urls') or []))
            async for value in bound.text_chat_stream(**kw): yield value
        result.text_chat=text_chat;result.text_chat_stream=stream
        self.providers[id(provider)]=result
        return result

    def get_provider_by_id(self, *args, **kwargs):
        return self.wrap(self.context.get_provider_by_id(*args, **kwargs))

    async def get_using_provider_async(self, *args, **kwargs):
        return self.wrap(await self.context.get_using_provider_async(*args, **kwargs))


def install_model_adapters():
    from astrbot.core import astr_main_agent
    from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal
    build=astr_main_agent.build_main_agent
    if not getattr(build,'_dsh_budget_adapter',False):
        build_signature=inspect.signature(build)
        @functools.wraps(build)
        async def build_agent(*args, **kwargs):
            bound=build_signature.bind(*args, **kwargs)
            event=bound.arguments['event'];plugin=event.get_extra('_dsh_reply_owner')
            if plugin is not None:
                bound.arguments['plugin_context']=BudgetContext(bound.arguments['plugin_context'],plugin,event)
            return await build(*bound.args, **bound.kwargs)
        build_agent._dsh_budget_adapter=True
        astr_main_agent.build_main_agent=build_agent
        internal.build_main_agent=build_agent
    from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
    original = ToolLoopAgentRunner.reset
    if getattr(original, '_dsh_budget_adapter', False): return
    signature = inspect.signature(original)
    @functools.wraps(original)
    async def reset(self, *args, **kwargs):
        bound = signature.bind(self, *args, **kwargs)
        values = bound.arguments
        event = getattr(getattr(values.get('run_context'), 'context', None), 'event', None)
        plugin = event.get_extra('_dsh_reply_owner') if event is not None else None
        if plugin is not None:
            budget = plugin._budget(event)
            expected = event.get_extra('_dsh_expected_images', 0)
            provider=values['provider']
            values['provider'] = BudgetProvider(getattr(provider,'_dsh_base_provider',provider), plugin.resources, budget, 'foreground', expected)
            values['fallback_providers'] = [BudgetProvider(getattr(p,'_dsh_base_provider',p), plugin.resources, budget, 'foreground', expected)
                                           for p in values.get('fallback_providers') or []]
            compress = values.get('llm_compress_provider')
            if compress: values['llm_compress_provider'] = BudgetProvider(getattr(compress,'_dsh_base_provider',compress), plugin.resources, budget, 'background')
            values['streaming'] = False
            values['request_max_retries'] = 1
        return await original(*bound.args, **bound.kwargs)
    reset._dsh_budget_adapter = True
    ToolLoopAgentRunner.reset = reset
