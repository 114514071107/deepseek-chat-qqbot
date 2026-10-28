"""QQ tool policy. Trust event metadata, never model arguments or prompt text."""
from dataclasses import dataclass
import functools
import inspect
import sys

DENIED = '（权限拒绝：此身份或场景不允许使用该工具）'
DISABLED = frozenset(('peek_user_data', 'run_command', 'ask_kimi', 'download_file', 'zip_files', 'unzip_file', 'read_word', 'write_word',
                      'set_alarm','list_alarms','cancel_alarm'))
OWNER_PRIVATE = frozenset(('read_local_file', 'write_local_file', 'list_files', 'search_in_files',
                           'read_word', 'write_word', 'send_local_file', 'retag_sticker', 'delete_sticker'))
ORDINARY = frozenset(('recall', 'learn_meme', 'record_thought', 'record_note', 'delete_note',
                     'get_current_time', 'web_search', 'fetch_url', 'send_sticker', 'list_stickers',
                     'set_alarm', 'list_alarms', 'cancel_alarm'))
KNOWN = DISABLED | OWNER_PRIVATE | ORDINARY


@dataclass(frozen=True)
class Caller:
    platform: str
    instance: str
    sender: str
    private: bool
    group: str


def caller(event):
    try:
        identity = Caller(event.get_platform_name(), event.get_platform_id(), event.get_sender_id(),
                          event.is_private_chat() is True, event.get_group_id())
        if identity.platform not in ('qq_official', 'aiocqhttp') or not identity.instance or not identity.sender:
            return None
        if identity.private and identity.group:
            return None
        if not identity.private and not identity.group:
            return None
        return identity
    except Exception:
        return None


def authorize(event, name, master, user_perm, *, owner_instance='', consume=True):
    if name in ('set_alarm','list_alarms','cancel_alarm'):
        return '（权限拒绝：闹钟暂不可用，可靠投递及 F09 政策待完成；未创建新任务，既有数据保留且暂停投递）'
    who = caller(event)
    if not who or name not in KNOWN or name in DISABLED:
        return DENIED
    if event.is_stopped():
        return DENIED
    owner = bool(owner_instance and who.instance == owner_instance and who.sender == master)
    if name in OWNER_PRIVATE and not (owner and who.private):
        return DENIED
    # Legacy archive/memory has no trustworthy group provenance; F01 supplies it.
    if name in ('set_alarm', 'list_alarms', 'cancel_alarm') and not user_perm(who.sender, 'alarm'):
        return DENIED
    if name in OWNER_PRIVATE - {'retag_sticker', 'delete_sticker'} and not user_perm(who.sender, 'files'):
        return DENIED
    if event.get_extra('_dsh_admitted') is not True:
        return DENIED
    limit = event.get_extra('_dsh_tool_limit')
    used = event.get_extra('_dsh_tool_used', 0)
    if type(limit) is not int or limit < 1 or type(used) is not int or used >= limit:
        return '（权限拒绝：本次事件工具调用额度已用尽或未初始化）'
    if consume:
        event.set_extra('_dsh_tool_used', used + 1)
    return None


def tool_guard(name):
    def decorate(fn):
        @functools.wraps(fn)
        async def guarded(self, event, *args, **kwargs):
            denial = self._authorize_tool(event, name)
            if denial:
                return denial
            from resource_budget import BudgetExceeded, payload_size
            try:
                budget = self._budget(event)
                budget.tool(); budget.input(payload_size(args)+payload_size(kwargs))
                result = await self.resources.run('foreground', lambda: fn(self, event, *args, **kwargs),
                    budget, stage='tool', timeout=self.resources.config['tool_timeout'])
                return budget.tool_result(result) if isinstance(result, str) else result
            except BudgetExceeded as exc:
                return '（资源限制：' + str(exc) + '）'
        guarded._dsh_tool_name = name
        return guarded
    return decorate


def trusted_plugin_tool(tool, plugin):
    """A matching tool name alone must not authorize a built-in, MCP or handoff."""
    name = getattr(tool, 'name', '')
    # get_full_tool_set() keeps handler=None on this exact framework proxy so
    # execution must still go through its per-tool permission check. Inspect
    # the wrapped handler for identity only; never replace the original proxy.
    manager_module = sys.modules.get('astrbot.core.provider.func_tool_manager')
    proxy_type = getattr(manager_module, '_PermissionGuardedTool', None)
    seen = set()
    while proxy_type is not None and type(tool) is proxy_type:
        if id(tool) in seen or tool.handler is not None:
            return False
        seen.add(id(tool))
        tool = tool._wrapped
        if getattr(tool, 'name', None) != name:
            return False
    fn = getattr(tool, 'handler', None)
    bound_to = getattr(fn, '__self__', None)
    if isinstance(fn, functools.partial):
        bound_to = fn.args[0] if fn.args else None
        fn = fn.func
    if inspect.ismethod(fn):
        fn = fn.__func__
    expected = getattr(type(plugin), name, None)
    return bound_to is plugin and fn is expected and getattr(fn, '_dsh_tool_name', None) == name


def install_executor_guard(plugin, executor_cls=None):
    """Versioned AstrBot 4.29.1 integration; never edits site-packages.

    on_using_llm_tool exceptions are swallowed and do not stop execution in that
    version. Guard execute itself, before local/MCP/handoff/background dispatch.
    Remain installed until process exit, so disabling the plugin cannot reopen
    host access. Reload only updates the policy owner, never stacks wrappers.
    """
    if executor_cls is None:
        from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
        executor_cls = FunctionToolExecutor
    if not hasattr(executor_cls, '_dsh_original_execute'):
        executor_cls._dsh_original_execute = executor_cls.execute

        async def guarded_execute(cls, tool, run_context, **tool_args):
            from mcp.types import CallToolResult, TextContent
            current = cls._dsh_policy_plugin
            event = getattr(getattr(run_context, 'context', None), 'event', None)
            if not trusted_plugin_tool(tool, current):
                yield CallToolResult(content=[TextContent(type='text', text=DENIED)], isError=True)
                return
            denial = current._authorize_tool(event, tool.name, consume=False)
            if denial:
                yield CallToolResult(content=[TextContent(type='text', text=denial)], isError=True)
                return
            async for result in cls._dsh_original_execute(tool, run_context, **tool_args):
                yield result

        executor_cls.execute = classmethod(guarded_execute)
    executor_cls._dsh_policy_plugin = plugin
