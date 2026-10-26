"""Local authenticated console uses a bounded file inbox; only the plugin applies state."""
import asyncio
from pathlib import Path
import re
import time
import os
import logging
from build_info import BUILD_VERSION
from state_store import read_json, write_json, StateError
from task_runtime import work_context
from qq_readiness import observe_socket, socket_ready, ensure_client_observer, release_observers


def qq_connection_status(context,owner=None):
    """Read-only AstrBot 4.29.1 / installed botpy observation, no network calls.

    ManagedBotWebSocket.user and session_id are assigned by _ready_handler;
    neither an open TCP socket nor Client._ready (unused here) proves READY.
    RESUMED requires a current connection authentication receipt. Never return SDK data.
    """
    configured=ready=0
    try:
        for platform in context.platform_manager.platform_insts:
            if platform.meta().name!='qq_official':continue
            configured+=1;client=platform.client
            if type(client).__module__.startswith('astrbot.') and not ensure_client_observer(client,owner):
                return {'status':'unknown','configured':configured,'ready':ready}
            sockets=list(client._active_websockets)
            if not client.is_closed() and sockets and all(
                socket_ready(socket)
                for socket in sockets):ready+=1
        return {'status':'ready' if configured and ready==configured else 'connecting' if configured else 'unknown',
                'configured':configured,'ready':ready}
    except (AttributeError,TypeError,RuntimeError,ImportError):
        return {'status':'unknown','configured':configured,'ready':ready}


async def _io(call,*args):
    """Retry only filesystem failures, bounded; never replay an applied command."""
    for attempt in range(4):
        try:return call(*args)
        except (OSError,StateError) as error:
            if isinstance(error,StateError) and not isinstance(error.__cause__,OSError):raise
            if attempt==3:raise
            await asyncio.sleep((.05,.15,.3)[attempt])


async def serve_inbox(root,runtime,apply):
    root=Path(root)/'admin_v2'; requests=root/'requests'; responses=root/'responses'; processing=root/'processing'
    requests.mkdir(parents=True,exist_ok=True); responses.mkdir(parents=True,exist_ok=True); processing.mkdir(parents=True,exist_ok=True)
    reason='runtime_stopped';context=getattr(getattr(apply,'__self__',None),'context',None);claimed_lease=False
    try:
        while runtime.alive:
            context=getattr(getattr(apply,'__self__',None),'context',None)
            def publish_lease():
                if claimed_lease and read_json(root/'live.json',{}).get('instance')!=runtime.id:return False
                write_json(root/'live.json',{'instance':runtime.id,'at':time.time(),'pid':os.getpid(),'version':BUILD_VERSION,
                                           'qq_connection':qq_connection_status(context,runtime.id)})
                return True
            if not await _io(publish_lease):
                reason='superseded';break
            claimed_lease=True
            for path in sorted(requests.glob('*.json'))[:32]:
                if not re.fullmatch(r'[a-f0-9]{32}\.json',path.name): continue
                # At most once: interruption or acknowledgment failure must not
                # repeat points grants / sends. An unfinished claim stays unknown.
                claimed=processing/path.name
                await _io(path.replace,claimed)
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
                    if not runtime.alive or asyncio.current_task().cancelling(): raise
                    result={'ok':False,'applied':'unknown','error':'本次工作已撤销，结果未确认；管理通道继续可用','instance':runtime.id,'id':path.stem}
                except Exception as error:
                    result={'ok':False,'applied':False,'error':type(error).__name__+': '+str(error)[:200],'instance':runtime.id,'id':path.stem}
                await _io(write_json,responses/path.name,result)
                await _io(path.unlink)
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        reason='runtime_stopped' if not runtime.alive else 'cancelled_while_alive'
        raise
    except (OSError,StateError):
        reason='io_failure'
        raise
    except Exception:
        reason='unexpected_error'
        raise
    finally:
        release_observers(context,runtime.id)
        # Do not erase the new instance's lease on a reload.
        with work_context(None):
            try:
                await _io(write_json,root/('exit-'+runtime.id+'.json'),
                          {'instance':runtime.id,'at':time.time(),'pid':os.getpid(),'reason':reason})
                def revoke_lease():
                    lease=read_json(root/'live.json',{})
                    if lease.get('instance')==runtime.id:
                        write_json(root/'live.json',{'instance':runtime.id,'at':0,'stopped':True,'reason':reason})
                await _io(revoke_lease)
            except (OSError,StateError):
                logging.getLogger(__name__).error('Management exit persistence failed; reason=%s pid=%s',reason,os.getpid())
