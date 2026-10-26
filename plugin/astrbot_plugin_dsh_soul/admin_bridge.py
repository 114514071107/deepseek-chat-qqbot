"""Local authenticated console uses a bounded file inbox; only the plugin applies state."""
import asyncio
from pathlib import Path
import re
import time
import os
from build_info import BUILD_VERSION
from state_store import read_json, write_json
from task_runtime import work_context


async def serve_inbox(root,runtime,apply):
    root=Path(root)/'admin_v2'; requests=root/'requests'; responses=root/'responses'; processing=root/'processing'
    requests.mkdir(parents=True,exist_ok=True); responses.mkdir(parents=True,exist_ok=True); processing.mkdir(parents=True,exist_ok=True)
    try:
        while runtime.alive:
            write_json(root/'live.json',{'instance':runtime.id,'at':time.time(),'pid':os.getpid(),'version':BUILD_VERSION})
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
