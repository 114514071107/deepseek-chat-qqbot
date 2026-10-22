import asyncio
import importlib
import sys
from pathlib import Path
import time
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'plugin/astrbot_plugin_dsh_soul'))


class ResourceRegression(unittest.IsolatedAsyncioTestCase):
    def api(self):
        try: return importlib.import_module('resource_budget')
        except ImportError: self.fail('actual model/media paths have no bounded resource controller')

    async def test_queue_bound_and_foreground_reserved(self):
        api = self.api(); resources = api.Resources({'background': 1, 'foreground': 1, 'queue': 1})
        started = asyncio.Event(); release = asyncio.Event()
        async def slow(): started.set(); await release.wait(); return 'done'
        first = asyncio.create_task(resources.run('background', slow)); await started.wait()
        second = asyncio.create_task(resources.run('background', slow)); await asyncio.sleep(.01)
        with self.assertRaises(api.BudgetExceeded): await resources.run('background', slow)
        self.assertEqual(await resources.run('foreground', lambda: asyncio.sleep(0, result='front')), 'front')
        second.cancel(); await asyncio.gather(second, return_exceptions=True)
        release.set(); await first
        self.assertEqual(resources.pools['background'].waiting, 0)

    async def test_deadline_model_calls_output_and_retry_are_actual_boundaries(self):
        api = self.api(); resources = api.Resources({'model_calls': 2, 'output_tokens': 31, 'deadline': .2})
        calls = []
        class Provider:
            provider_config = {'modalities': ['text', 'image']}
            async def text_chat(self, **kw): calls.append(kw); return SimpleNamespace(completion_text='ok')
        budget = resources.budget('fixture')
        provider = api.BudgetProvider(Provider(), resources, budget, 'foreground')
        for _ in range(2): await provider.text_chat(prompt='fixture', request_max_retries=8)
        with self.assertRaises(api.BudgetExceeded): await provider.text_chat(prompt='fixture')
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]['request_max_retries'], 1)
        self.assertEqual(calls[0]['max_tokens'], 31)
        self.assertTrue(any(r['stage']=='model' for r in resources.metrics))
        await asyncio.sleep(.21)
        with self.assertRaises(api.BudgetExceeded): await provider.text_chat(prompt='fixture')

    async def test_cancelled_media_keeps_slot_until_thread_finishes(self):
        import threading
        api = self.api(); resources = api.Resources({'media': 1, 'queue': 0})
        started = threading.Event(); release = threading.Event()
        def blocking(): started.set(); release.wait(2); return 'data'
        work = asyncio.create_task(resources.thread(blocking))
        while not started.is_set(): await asyncio.sleep(.005)
        work.cancel(); await asyncio.gather(work, return_exceptions=True)
        with self.assertRaises(api.BudgetExceeded): await resources.thread(lambda: 'other')
        release.set(); await resources.close()
        self.assertEqual(await resources.thread(lambda:'next'), 'next')

    async def test_media_loss_and_removed_capability_never_reach_model(self):
        api = self.api(); resources = api.Resources({}); calls = []
        class Provider:
            provider_config = {'modalities': ['text']}
            async def text_chat(self, **kw): calls.append(kw)
        provider = api.BudgetProvider(Provider(), resources, resources.budget('fixture'), 'foreground', expected_images=1)
        for contexts in ([], [{'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,AA=='}}]}]):
            with self.assertRaises(api.ImageUnavailable): await provider.text_chat(contexts=contexts)
        self.assertEqual(calls, [])

    async def test_tool_steps_input_and_elapsed_budget(self):
        api = self.api(); resources = api.Resources({'tool_steps': 1, 'input_chars': 100, 'tool_chars': 12, 'deadline': .05})
        budget = resources.budget('fixture')
        budget.tool(); self.assertRaises(api.BudgetExceeded, budget.tool)
        self.assertRaises(api.BudgetExceeded, budget.input, 101)
        self.assertEqual(len(budget.tool_result('x'*200)), 12)
        await asyncio.sleep(.06)
        self.assertRaises(api.BudgetExceeded, budget.check)

    async def test_active_budget_cannot_be_evicted_to_reset_call_count(self):
        api=self.api();resources=api.Resources({'model_calls':1})
        original=resources.budget('same-request');original.model()
        for n in range(600):
            try:resources.budget(str(n))
            except api.BudgetExceeded:pass
        self.assertIs(resources.budget('same-request'),original)
        self.assertRaises(api.BudgetExceeded,resources.budget('same-request').model)

    async def test_same_pool_nested_tool_model_call_does_not_deadlock(self):
        api=self.api();resources=api.Resources({'foreground':1,'model_timeout':.1,'tool_timeout':.1})
        budget=resources.budget('fixture')
        async def tool():
            return await resources.run('foreground',lambda:asyncio.sleep(0,result='result'),budget,stage='model')
        self.assertEqual(await resources.run('foreground',tool,budget,stage='tool'), 'result')

    async def test_intentional_delayed_phase_has_new_deadline_but_same_call_quota(self):
        api=self.api();resources=api.Resources({'deadline':.02,'model_calls':1})
        parent=resources.budget('trigger');parent.model()
        await asyncio.sleep(.03)
        try:child=resources.budget('trigger:revive',parent=parent)
        except TypeError:self.fail('delayed follow-up cannot preserve shared quota without expiring')
        child.check()
        self.assertRaises(api.BudgetExceeded,child.model)

    async def test_qq_media_prepare_and_upload_share_bounded_media_pool(self):
        from qq_delivery import QQDelivery
        from session_scope import Target
        api=self.api();resources=api.Resources({'media':1,'queue':2})
        active=0;peak=0;posted=[]
        async def parse(chain):
            nonlocal active,peak
            active+=1;peak=max(peak,active);await asyncio.sleep(.02);active-=1
            return '', 'AA==',None,None,None,None,None
        async def request(platform,endpoint,payload):
            posted.append(endpoint)
            return (200,{'file_info':'fixture'}) if endpoint.endswith('/files') else (200,{'id':'accepted'})
        context=SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[SimpleNamespace(meta=lambda:SimpleNamespace(id='bot',name='qq_official'))]))
        try:
            delivery=QQDelivery(context,request=request,parse=parse,
                media_run=lambda factory:resources.run('media',factory,stage='media'),media_thread=resources.thread)
        except TypeError:self.fail('QQ media conversion/upload bypasses resource bounds')
        target=Target('qq_official','bot','','private','fixture')
        result=await asyncio.gather(*(delivery.send(target,SimpleNamespace(chain=[SimpleNamespace(type='Image')]),mode='proactive') for _ in range(2)))
        self.assertTrue(all(result),result);self.assertEqual(peak,1);self.assertEqual(len(posted),4)

    async def test_busy_background_media_cannot_prevent_foreground_text(self):
        from qq_delivery import QQDelivery
        from session_scope import Target
        api=self.api();resources=api.Resources({'media':1,'queue':0})
        release=asyncio.Event();started=asyncio.Event();posted=[]
        async def block():started.set();await release.wait()
        work=asyncio.create_task(resources.run('media',block));await started.wait()
        async def parse(chain):return 'text',None,None,None,None,None,None
        async def request(*args):posted.append(True);return 200,{'id':'accepted'}
        context=SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[SimpleNamespace(meta=lambda:SimpleNamespace(id='bot',name='qq_official'))]))
        delivery=QQDelivery(context,parse=parse,request=request,media_run=lambda fn:resources.run('media',fn))
        try:result=await delivery.send(Target('qq_official','bot','','private','fixture'),SimpleNamespace(chain=[SimpleNamespace(type='Plain')]),mode='proactive')
        finally:release.set();await work
        self.assertTrue(result,result);self.assertEqual(len(posted),1)

    async def test_foreground_media_has_capacity_reserved_from_background(self):
        import threading
        api=self.api();resources=api.Resources({'media':1,'background_media':1,'queue':0})
        started=threading.Event();release=threading.Event()
        def block():started.set();release.wait(1)
        work=asyncio.create_task(resources.thread(block,_lane='background_media'))
        await asyncio.sleep(.02)
        try:
            self.assertTrue(started.is_set(),'background media has no separate lane')
            self.assertEqual(await resources.thread(lambda:'foreground'),'foreground')
        finally:release.set();await asyncio.gather(work,return_exceptions=True)

    async def test_actual_tool_entry_enforces_configured_step_budget(self):
        from test_repair_permissions import load_methods,Event
        api=self.api();obj,ns=load_methods();obj.resources=api.Resources({'tool_steps':1})
        ns['time']=time
        event=Event('friend')
        self.assertNotIn('资源限制',await obj.get_current_time(event))
        self.assertIn('资源限制',await obj.get_current_time(event))


if __name__ == '__main__': unittest.main()
