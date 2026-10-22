"""Short-lived IPC test worker; never imports or constructs a production plugin."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'plugin/astrbot_plugin_dsh_soul'))
from admin_bridge import serve_inbox
from session_scope import Scope
from state_store import StateController,write_json
from task_runtime import Runtime


async def main():
    root=Path(sys.argv[1])/'dsh_data'
    scope=Scope('qq_official','fixture-instance','fixture-self','fixture-user','fixture-group','fixture-msg',False)
    runtime=Runtime(lambda *args:True)
    plugin=SimpleNamespace(runtime=runtime,scopes={scope.key:scope.source()},h={scope.key:[{'text':'fixture'}]},th={},groups={},
                           names={},blocked=set(),sil={},h_path=str(root/'history_v2.json'),t_path=str(root/'thoughts_v2.json'),group_path=str(root/'groups_v2.json'))
    write_json(root/'scopes_v2.json',plugin.scopes);write_json(plugin.h_path,plugin.h)
    async def clear(key): pass
    async def send(scope,text): write_json(root/'sent_fixture.json',{'kind':scope.target.kind,'instance':scope.instance,'address':scope.target.address})
    plugin._admin_send=send
    controller=StateController(plugin,root,clear_framework=clear)
    async def apply(operation,body):
        result=await controller.apply(operation,body)
        write_json(root/'runtime_fixture.json',{'h':plugin.h,'names':plugin.names})
        return result
    await serve_inbox(root,runtime,apply)


if __name__=='__main__': asyncio.run(main())
