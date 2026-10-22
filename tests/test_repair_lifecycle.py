import asyncio
import tempfile
from types import SimpleNamespace
import unittest
from repair_pipeline_support import load_pipeline


class LifecycleRegression(unittest.IsolatedAsyncioTestCase):
    async def test_person_resource_job_is_not_duplicated_by_another_group(self):
        from task_runtime import Runtime
        runtime=Runtime(lambda *a:True)
        async def worker():await asyncio.Event().wait()
        first=runtime.spawn(worker(),key='group-a',exclusive='person-proactive')
        second=runtime.spawn(worker(),key='group-b',exclusive='person-proactive')
        self.assertIs(first,second);self.assertEqual(len(runtime.tasks),1)
        await runtime.stop()

    async def test_stop_cancels_and_waits_for_delayed_and_model_work(self):
        from task_runtime import Runtime, work_context
        runtime=Runtime(lambda key,feature:True)
        reached=asyncio.Event(); changes=[]
        async def worker():
            reached.set()
            await asyncio.Event().wait()
            changes.append('late write')
        runtime.spawn(worker(),key='scope',feature='reply')
        await reached.wait(); await runtime.stop()
        self.assertEqual(changes,[]); self.assertFalse(runtime.tasks)
        self.assertFalse(runtime.alive)

    async def test_delete_or_switch_while_model_waits_prevents_commit(self):
        from task_runtime import Runtime, work_context
        enabled=True
        runtime=Runtime(lambda key,feature:enabled)
        release=asyncio.Event(); started=asyncio.Event(); saved=[]
        async def worker():
            started.set(); await release.wait()
            runtime.check(); saved.append('resurrected')
        runtime.spawn(worker(),key='scope',feature='reply')
        await started.wait(); enabled=False; release.set()
        await asyncio.gather(*list(runtime.tasks),return_exceptions=True)
        self.assertEqual(saved,[])
        enabled=True
        token=runtime.token('scope','reply'); runtime.invalidate('scope')
        with work_context(token):
            with self.assertRaises(asyncio.CancelledError): runtime.check()
        await runtime.stop()

    async def test_previous_request_finally_cannot_clear_new_marker(self):
        from task_runtime import Runtime, work_context
        runtime=Runtime(lambda *args:True)
        old=runtime.begin('scope'); new=runtime.begin('scope')
        self.assertFalse(runtime.valid(old)); self.assertTrue(runtime.valid(new))
        with work_context(old):
            with self.assertRaises(asyncio.CancelledError): runtime.check()
        await runtime.stop()

    async def test_actual_loaded_hook_does_not_duplicate_loops_and_terminate_waits(self):
        from task_runtime import Runtime
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp,names=('on_loaded','terminate','_spawn'))
            obj.runtime=Runtime(lambda *args:True); obj._loop_started=False
            async def one(): await asyncio.Event().wait()
            async def two(): await asyncio.Event().wait()
            async def three(): await asyncio.Event().wait()
            async def four(): await asyncio.Event().wait()
            async def five(): await asyncio.Event().wait()
            obj._proactive_loop=one; obj._desire_loop=two; obj._alarm_loop=three; obj._startup_greet=four; obj._admin_loop=five
            obj._owner_target=lambda:None
            await obj.on_loaded(); count=len(obj.runtime.tasks)
            await obj.on_loaded()
            self.assertEqual(count,4); self.assertEqual(len(obj.runtime.tasks),count)
            await obj.terminate(); self.assertFalse(obj.runtime.tasks)


if __name__=='__main__': unittest.main()
