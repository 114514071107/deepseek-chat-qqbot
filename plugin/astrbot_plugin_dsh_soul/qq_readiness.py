"""Versioned AstrBot 4.29.1 / botpy connector observation; no SDK files changed.

Only a successful SDK READY or the reply to Resume on that same connection
is confirmation. Neither an old session nor an open socket is confirmation.
"""
import importlib
import importlib.metadata
import json


def observe_socket(socket):
    if hasattr(socket,'_dsh_ready_observation'):return True
    required=('on_message','ws_resume','on_closed','on_error','_ready_handler','_is_system_event')
    if not all(callable(getattr(socket,name,None)) for name in required):return False
    originals={name:getattr(socket,name) for name in required[:4]}
    conn=getattr(socket,'_conn',None)
    session=getattr(socket,'_session',{})
    user=getattr(socket,'user',None)
    # The pinned adapter creates a fresh socket for every connection. Existing
    # READY metadata can be adopted; RESUMED needs an observed current event.
    boot=bool(conn is not None and conn.closed is False and isinstance(user,dict) and user.get('id') and session.get('session_id'))
    state={'confirmed':conn if boot else None,'session':session.get('session_id') if boot else None,'resume':None,'resume_session':None,'originals':originals,'wrappers':{}}
    socket._dsh_ready_observation=state
    def invalidate():state.update(confirmed=None,session=None,resume=None,resume_session=None)
    async def resume(*args,**kwargs):
        invalidate();current=socket._conn;session_id=socket._session.get('session_id')
        result=await originals['ws_resume'](*args,**kwargs)
        if current is socket._conn and current is not None and current.closed is False and session_id:
            state.update(resume=current,resume_session=session_id)
        return result
    async def message(ws,raw):
        payload=json.loads(raw)
        if payload.get('op') in (7,9):invalidate()
        try:result=await originals['on_message'](ws,raw)
        except BaseException:
            invalidate();raise
        if payload.get('op')==0 and socket._conn is ws and not ws.closed:
            event=payload.get('t');session_id=socket._session.get('session_id')
            ready=event=='READY' and isinstance(getattr(socket,'user',None),dict) and bool(socket.user.get('id'))
            resumed=event=='RESUMED' and state['resume'] is ws and state['resume_session']==session_id
            if session_id and (ready or resumed):state.update(confirmed=ws,session=session_id)
        return result
    def invalidating(name):
        async def wrapped(*args,**kwargs):
            invalidate();return await originals[name](*args,**kwargs)
        return wrapped
    wrappers={'on_message':message,'ws_resume':resume,'on_closed':invalidating('on_closed'),'on_error':invalidating('on_error')}
    for name,wrapped in wrappers.items():setattr(socket,name,wrapped)
    state['wrappers']=wrappers
    return True


def socket_ready(socket):
    conn=getattr(socket,'_conn',None);session=getattr(socket,'_session',None)
    if conn is None or conn.closed is not False or not isinstance(session,dict) or not session.get('session_id'):return False
    state=getattr(socket,'_dsh_ready_observation',None)
    if state is not None:return state['confirmed'] is conn and state['session']==session.get('session_id')
    # Read-only compatibility for READY metadata; unknown/resumed sockets have
    # no user. The production connector below installs before any event.
    user=getattr(socket,'user',None)
    return isinstance(user,dict) and bool(user.get('id'))


def ensure_client_observer(client,owner=None):
    """Use ConnectionSession's connector seam, scoped to one existing client.

    The callback body matches pinned botClient.bot_connect. Unknown versions
    or another integration owning the seam fail closed instead of replacing it.
    """
    if hasattr(client,'_dsh_ready_connector'):
        if owner:client._dsh_ready_connector[2].add(owner)
        return True
    module_name=type(client).__module__
    if module_name!='astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter':return False
    if importlib.metadata.version('astrbot')!='4.29.1' or importlib.metadata.version('qq-botpy')!='1.2.1':return False
    module=importlib.import_module(module_name)
    connection=client._connection;original=connection._connect
    if getattr(original,'__self__',None) is not client or getattr(original,'__func__',None) is not module.botClient.bot_connect:return False
    async def connect(session):
        socket=module.ManagedBotWebSocket(session,connection,client)
        if not observe_socket(socket):raise RuntimeError('Unsupported QQ socket observation contract')
        client._active_websockets.add(socket)
        try:
            await socket.ws_connect()
        except Exception as error:
            if not client.is_shutting_down:await socket.on_error(error)
        finally:
            client._active_websockets.discard(socket)
    client._dsh_ready_connector=(original,connect,{owner} if owner else set())
    connection._connect=connect
    for socket in list(client._active_websockets):
        if not observe_socket(socket):return False
    return True


def release_observers(context,owner=None):
    for platform in getattr(getattr(context,'platform_manager',None),'platform_insts',[]):
        if platform.meta().name!='qq_official':continue
        client=platform.client;installed=getattr(client,'_dsh_ready_connector',None)
        if installed:
            if owner:
                installed[2].discard(owner)
                if installed[2]:continue
            # The authenticated receipt belongs to this live client/connection,
            # not a plugin runtime. Keep observing invalidation across a
            # sequential unload/load; no runtime object or task is retained.
            if not client.is_closed():continue
            if client._connection._connect is installed[1]:client._connection._connect=installed[0]
            del client._dsh_ready_connector
        for socket in list(getattr(client,'_active_websockets',[])):
            state=getattr(socket,'_dsh_ready_observation',None)
            if state:
                for name,wrapped in state['wrappers'].items():
                    if getattr(socket,name,None) is wrapped:setattr(socket,name,state['originals'][name])
                del socket._dsh_ready_observation
