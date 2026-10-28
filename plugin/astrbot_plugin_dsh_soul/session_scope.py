"""Versioned, source-bound conversation identities and immutable destinations."""
from dataclasses import asdict, dataclass
import hashlib
import json
import functools
import inspect
import sys
import asyncio
import re
import time
from types import SimpleNamespace


_policy_origins={}


def policy_origin(umo):
    """Only trusted events register aliases; history/workspace keys never change."""
    from task_runtime import current_event
    event=current_event()
    if event is not None and event.unified_msg_origin==umo:
        origin=event.get_extra('_dsh_original_umo')
        if origin:return origin
    return _policy_origins.get(str(umo),umo) if umo is not None else None


def _wrap_event_policy(cls,name):
    original=getattr(cls,name)
    if getattr(original,'_dsh_event_policy',False):return
    @functools.wraps(original)
    async def run(event,*args,**kwargs):
        from task_runtime import work_context,current_token
        with work_context(current_token(),event):
            return await original(event,*args,**kwargs)
    run._dsh_event_policy=True
    setattr(cls,name,staticmethod(run))


def _wrap_policy_method(cls,name):
    original=getattr(cls,name)
    if getattr(original,'_dsh_policy_origin',False): return
    @functools.wraps(original)
    async def run(session_id,*args,**kwargs):
        origin=policy_origin(session_id)
        inherited=await original(origin,*args,**kwargs)
        return inherited and (origin==session_id or await original(session_id,*args,**kwargs))
    run._dsh_policy_origin=True
    setattr(cls,name,staticmethod(run))


def _guard_profile_routes(cls,name,single):
    original=getattr(cls,name)
    if getattr(original,'_dsh_policy_origin',False): return
    signature=inspect.signature(original)
    @functools.wraps(original)
    async def run(self,*args,**kwargs):
        value=signature.bind(self,*args,**kwargs).arguments['umo' if single else 'routing']
        for pattern in ([value] if single else value):
            session=str(pattern).split(':',2)[-1]
            reserved=(re.fullmatch(r'[cpg]2_[0-9a-f]{64}',session)
                      or (session.startswith(('c2_','p2_','g2_')) and any(c in session for c in '*?[')))
            if reserved or any(self.ucr._is_umo_match(pattern,alias) and not self.ucr._is_umo_match(pattern,origin)
                   for alias,origin in _policy_origins.items()):
                raise ValueError('内部会话仅隔离历史；配置文件请绑定原始会话或平台，未修改配置')
        return await original(self,*args,**kwargs)
    run._dsh_policy_origin=True
    setattr(cls,name,run)


def install_policy_adapters():
    """AstrBot 4.29.1 integration in memory, never edits framework/config files.

    AstrBot uses UMO for both private history and session policy. Keep its live
    restrictions at the pre-rekey identity AND the new key, without copying
    preferences (which would go stale after a WebUI change). Profiles remain
    attached to the original admission pipeline; reject misleading new routes.
    Install during plugin construction, before the first message or loaded hook.
    """
    from astrbot.core.star.session_llm_manager import SessionServiceManager
    from astrbot.core.star.session_plugin_manager import SessionPluginManager
    from astrbot.core.star.context import Context
    from astrbot.dashboard.services.config_service import ConfigRoutingService
    global _policy_origins
    # Helpers may be reimported on reload while framework wrappers remain alive.
    stored=getattr(Context,'_dsh_policy_origins',_policy_origins)
    stored.update(_policy_origins);_policy_origins=stored;Context._dsh_policy_origins=stored
    for name in ('is_llm_enabled_for_session','is_tts_enabled_for_session','is_session_enabled'):
        _wrap_policy_method(SessionServiceManager,name)
    for name in ('should_process_llm_request','should_process_tts_request'):
        _wrap_event_policy(SessionServiceManager,name)
    _wrap_policy_method(SessionPluginManager,'is_plugin_enabled_for_session')
    original=SessionPluginManager.filter_handlers_by_session
    if not getattr(original,'_dsh_policy_origin',False):
        @functools.wraps(original)
        async def filter_handlers(event,handlers):
            # This version's filter reads only unified_msg_origin from event.
            source=SimpleNamespace(unified_msg_origin=policy_origin(event.unified_msg_origin))
            inherited=await original(source,handlers)
            return await original(event,inherited)
        filter_handlers._dsh_policy_origin=True
        SessionPluginManager.filter_handlers_by_session=staticmethod(filter_handlers)
    _wrap_event_policy(SessionPluginManager,'filter_handlers_by_session')
    get_config=Context.get_config
    if not getattr(get_config,'_dsh_policy_origin',False):
        @functools.wraps(get_config)
        def config(self,umo=None): return get_config(self,umo=policy_origin(umo))
        config._dsh_policy_origin=True
        Context.get_config=config
    _guard_profile_routes(ConfigRoutingService,'set_route',True)
    _guard_profile_routes(ConfigRoutingService,'replace_route_mapping',False)


async def check_framework_policy(event):
    module=sys.modules.get('astrbot.core.platform.astr_message_event')
    event_type=getattr(module,'AstrMessageEvent',None)
    if event_type is None or not isinstance(event,event_type): return
    from astrbot.core.star.session_llm_manager import SessionServiceManager
    from astrbot.core.star.session_plugin_manager import SessionPluginManager
    umo=event.unified_msg_origin
    if (not await SessionServiceManager.is_session_enabled(umo)
            or not await SessionPluginManager.is_plugin_enabled_for_session(umo,'dsh_soul')):
        # Initial framework admission preceded rekeying. Do not fall back to a
        # generic unisolated LLM pipeline when this required guard is disabled.
        raise asyncio.CancelledError('framework session or isolation plugin disabled')


def _key(prefix, *parts):
    raw=json.dumps(parts,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    return prefix+hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Target:
    platform: str
    instance: str
    bot: str
    kind: str
    address: str
    message_id: str = ''
    event_id: str = ''
    received_at: float = 0

    @property
    def umo(self):
        if self.kind not in ('group','private') or not self.instance or not self.address:
            raise ValueError('missing or unsupported destination')
        return f'{self.instance}:{"GroupMessage" if self.kind=="group" else "FriendMessage"}:{self.address}'

    def endpoint(self, resource):
        if self.platform!='qq_official' or resource not in ('files','messages'):
            raise ValueError('unsupported destination or resource')
        self.umo  # validate before selecting an API
        from urllib.parse import quote
        return '/v2/'+('groups' if self.kind=='group' else 'users')+'/'+quote(self.address,safe='')+'/'+resource


@dataclass(frozen=True)
class Scope:
    platform: str
    instance: str
    bot: str
    sender: str
    group: str
    message_id: str
    private: bool
    event_id: str = ''
    received_at: float = 0

    @property
    def memory_key(self): return _key('p2_',self.platform,self.instance,self.bot,self.sender)
    @property
    def key(self): return self.memory_key if self.private else _key('c2_',self.platform,self.instance,self.bot,self.group,self.sender)
    @property
    def group_key(self): return '' if self.private else _key('g2_',self.platform,self.instance,self.bot,self.group)
    @property
    def conversation_key(self): return self.memory_key if self.private else self.group_key
    @property
    def target(self): return Target(self.platform,self.instance,self.bot,'private' if self.private else 'group',self.sender if self.private else self.group,self.message_id,self.event_id,self.received_at)
    def source(self): return asdict(self)


def bind_scope(event):
    """Run before AstrBot's model lock/history/workspace selection. Never infer old routes."""
    obj=getattr(event,'message_obj',None)
    raw=getattr(obj,'raw_message',None)
    data=raw if isinstance(raw,dict) else getattr(raw,'raw_data',{})
    self_id=str(getattr(obj,'self_id','') or '')
    if (self_id and event.get_sender_id()==self_id) or (isinstance(data,dict) and data.get('post_type')=='message_sent'):
        if callable(getattr(event,'stop_event',None)): event.stop_event()
        raise asyncio.CancelledError('platform self message is not a new user request')
    existing=event.get_extra('_dsh_scope')
    if isinstance(existing,Scope): return existing
    from tool_permissions import caller
    who=caller(event)
    if who is None: raise ValueError('untrusted event identity')
    obj=getattr(event,'message_obj',None)
    stamp=getattr(obj,'timestamp',None)
    try: stamp=float(stamp.timestamp() if hasattr(stamp,'timestamp') else stamp)
    except (TypeError,ValueError): stamp=time.time()
    # Missing receive time is bound once on the event, never refreshed by hooks.
    stamp=min(stamp,time.time())
    scope=Scope(who.platform,who.instance,str(getattr(obj,'self_id','') or ''),who.sender,who.group or '',
                str(getattr(obj,'message_id','') or ''),who.private,
                str(getattr(getattr(obj,'raw_message',None),'event_id','') or ''),stamp)
    origin=event.get_extra('_dsh_original_umo') or event.unified_msg_origin
    event.set_extra('_dsh_original_umo',origin)
    event.session_id=scope.conversation_key
    module=sys.modules.get('astrbot.core.platform.astr_message_event')
    framework_event=getattr(module,'AstrMessageEvent',None)
    if framework_event is not None and isinstance(event,framework_event):
        install_policy_adapters()
        # Dashboard's shared alias anchors to the whole group. Event-bound
        # policy calls retain their original actor policy via work_context.
        _policy_origins[event.unified_msg_origin]=origin if scope.private else scope.target.umo
    event.set_extra('_dsh_scope',scope)
    return scope
