"""Instance lease ownership and real state-store replacement failures, synthetic paths only."""
import asyncio
import ast
import ctypes
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from repair_pipeline_support import PLUGIN
import admin_bridge
import state_store
from task_runtime import Runtime,work_context

class AdminServiceRegression(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(os.name=='nt','Windows sharing violation')
    async def test_actual_windows_reader_lock_is_transient_not_permanent_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'admin_v2';root.mkdir();path=root/'live.json'
            path.write_text('{}',encoding='utf-8')
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
            kernel.CreateFileW.restype=ctypes.c_void_p;kernel.CloseHandle.argtypes=[ctypes.c_void_p]
            handle=kernel.CreateFileW(str(path),0x80000000,3,None,3,0,None)
            self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
            runtime=Runtime(lambda *args:True)
            async def apply(*args):return {'ok':True}
            task=runtime.spawn(admin_bridge.serve_inbox(temp,runtime,apply),key='',feature='admin')
            try:
                await asyncio.sleep(.15)
                kernel.CloseHandle(handle);handle=None
                await asyncio.sleep(.4)
                self.assertFalse(task.done())
                self.assertGreater(json.loads(path.read_text())['at'],0)
            finally:
                if handle:kernel.CloseHandle(handle)
                await runtime.stop()

    async def test_old_runtime_shutdown_does_not_revoke_new_runtime_lease(self):
        with tempfile.TemporaryDirectory() as temp:
            old=Runtime(lambda *args:True);new=Runtime(lambda *args:True)
            async def apply(*args):return {'ok':True}
            old.spawn(admin_bridge.serve_inbox(temp,old,apply),key='',feature='admin')
            await asyncio.sleep(.15)
            new.spawn(admin_bridge.serve_inbox(temp,new,apply),key='',feature='admin')
            await asyncio.sleep(.15)
            try:
                await old.stop()
                value=json.loads((Path(temp)/'admin_v2/live.json').read_text())
                self.assertEqual(value['instance'],new.id)
                self.assertFalse(value.get('stopped',False))
            finally:await old.stop();await new.stop()

    async def test_transient_atomic_replace_conflict_does_not_end_service(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime=Runtime(lambda *args:True)
            async def apply(*args):return {'ok':True}
            real_replace=state_store.os.replace
            remaining=1
            def conflict(source,target):
                nonlocal remaining
                if Path(target).name=='live.json' and remaining:
                    remaining-=1
                    raise PermissionError(13,'synthetic sharing violation')
                return real_replace(source,target)
            with patch.object(state_store.os,'replace',side_effect=conflict):
                task=runtime.spawn(admin_bridge.serve_inbox(temp,runtime,apply),key='',feature='admin')
                try:
                    await asyncio.sleep(.6)
                    self.assertFalse(task.done(),'S09: one transient live.json replace conflict permanently ended management')
                    live=json.loads((Path(temp)/'admin_v2/live.json').read_text())
                    self.assertGreater(live['at'],0)
                    self.assertFalse(live.get('stopped',False))
                finally:await runtime.stop()
            self.assertTrue(json.loads((Path(temp)/'admin_v2/live.json').read_text())['stopped'])

    async def test_service_started_under_chat_context_survives_request_revocation(self):
        source=ast.parse((PLUGIN/'main.py').read_text(encoding='utf-8-sig'))
        cls=next(node for node in source.body if isinstance(node,ast.ClassDef))
        wanted={'_spawn','_admin_loop','on_loaded'}
        methods=[node for node in cls.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in wanted]
        module=ast.Module(body=[ast.ClassDef(name='Subject',bases=[],keywords=[],body=methods,decorator_list=[])],type_ignores=[])
        with tempfile.TemporaryDirectory() as temp:
            namespace=dict(serve_inbox=admin_bridge.serve_inbox,DATA=temp)
            exec(compile(ast.fix_missing_locations(module),'synthetic-main-service','exec'),namespace)
            obj=namespace['Subject']();obj.runtime=Runtime(lambda *args:True);obj.scopes={};obj._loop_started=False
            obj.context=None
            async def apply(*args):return {'ok':True}
            async def idle():await asyncio.Event().wait()
            obj._apply_admin=apply;obj._proactive_loop=idle;obj._desire_loop=idle;obj._alarm_loop=idle;obj._owner_target=lambda:None
            token=obj.runtime.begin('synthetic-chat')
            with work_context(token):await obj.on_loaded()
            await asyncio.sleep(.15)
            obj.runtime.invalidate('synthetic-chat')
            await asyncio.sleep(.2)
            try:
                live=json.loads((Path(temp)/'admin_v2/live.json').read_text())
                self.assertFalse(live.get('stopped',False),'S09: request cancellation revoked the instance management service')
                self.assertGreater(live['at'],0)
            finally:await obj.runtime.stop()

    async def test_permanent_io_failure_records_explicit_exit_reason(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime=Runtime(lambda *args:True)
            async def apply(*args):return {'ok':True}
            real_replace=state_store.os.replace
            def denied(source,target):
                if Path(target).name=='live.json':raise PermissionError(13,'synthetic permanent denial')
                return real_replace(source,target)
            with patch.object(state_store.os,'replace',side_effect=denied):
                task=runtime.spawn(admin_bridge.serve_inbox(temp,runtime,apply),key='',feature='admin')
                await asyncio.sleep(1.5)
                try:
                    self.assertTrue(task.done(),'Permanent failure must end after bounded retries')
                    path=Path(temp)/'admin_v2'/('exit-'+runtime.id+'.json')
                    self.assertTrue(path.exists(),'S09: no durable reason for management exit')
                    self.assertEqual(json.loads(path.read_text())['reason'],'io_failure')
                finally:await runtime.stop()
