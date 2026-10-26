"""Local authenticated console uses a bounded file inbox; only the plugin applies state."""
import asyncio
from pathlib import Path
import re
import time
import os
from build_info import BUILD_VERSION
from state_store import read_json, write_json
from task_runtime import work_context


def qq_connection_status(context):
    """Read-only AstrBot 4.29.1 / installed botpy observation, no network calls.

    ManagedBotWebSocket.user and session_id are assigned by _ready_handler;
    neither an open TCP socket nor Client._ready (unused here) proves READY.
    A resumed socket without this proof is not ready. Never return SDK data.
    """
    configured=ready=0
    try:
        for platform in context.platform_manager.platform_insts:
            if platform.meta().name!='qq_official':continue
            configured+=1;client=platform.client
            sockets=list(client._active_websockets)
            if not client.is_closed() and sockets and all(
                getattr(socket,'_conn',None) is not None and socket._conn.closed is False
                and isinstance(getattr(socket,'_session',None),dict) and bool(socket._session.get('session_id'))
                and isinstance(getattr(socket,'user',None),dict) and bool(socket.user.get('id'))
                for socket in sockets):ready+=1
        return {'status':'ready' if configured and ready==configured else 'connecting' if configured else 'unknown',
                'configured':configured,'ready':ready}
    except (AttributeError,TypeError,RuntimeError):
        return {'status':'unknown','configured':configured,'ready':ready}


async def serve_inbox(root,runtime,apply):
    root=Path(root)/'admin_v2'; requests=root/'requests'; responses=root/'responses'; processing=root/'processing'
    requests.mkdir(parents=True,exist_ok=True); responses.mkdir(parents=True,exist_ok=True); processing.mkdir(parents=True,exist_ok=True)
    try:
        while runtime.alive:
            context=getattr(getattr(apply,'__self__',None),'context',None)
            write_json(root/'live.json',{'instance':runtime.id,'at':time.time(),'pid':os.getpid(),'version':BUILD_VERSION,
                                       'qq_connection':qq_connection_status(context)})
            for path in sorted(requests.glob('*.json'))[:32]:
                if not re.fullmatch(r'[a-f0-9]{32}\.json',path.name): continue
                # At most once: interruption or acknowledgment failure must not
                # repeat points grants / sends. An unfinished claim stays unknown.
                claimed=processing/path.name
                path.replace(claimed)
                path=claimed
                try:
                    if path.stat().st_size>65536: raise ValueError('command too large')
                    command=read_json(path,{})
                    if command.get('instance')!=runtime.id or command.get('deadline',0)<time.time():
                        result={'ok':False,'applied':False,'error':'命令已过期或运行实例已更换，请刷新后重试'}
                    else:
                        result=await apply(command['operation'],command.get('body',{}))
                    result={**result,'instance':runtime.id,'id':path.stem}
                except asyncio.CancelledError:
                    if not runtime.alive: raise
                    result={'ok':False,'applied':'unknown','error':'本次工作已撤销，结果未确认；管理通道继续可用','instance':runtime.id,'id':path.stem}
                except Exception as error:
                    result={'ok':False,'applied':False,'error':type(error).__name__+': '+str(error)[:200],'instance':runtime.id,'id':path.stem}
                write_json(responses/path.name,result)
                path.unlink()
            await asyncio.sleep(0.1)
    finally:
        # Do not erase the new instance's lease on a reload.
        with work_context(None):
            lease=read_json(root/'live.json',{})
            if lease.get('instance')==runtime.id:
                write_json(root/'live.json',{'instance':runtime.id,'at':0,'stopped':True})
