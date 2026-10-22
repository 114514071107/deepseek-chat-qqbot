"""Acceptance regressions: event provenance and delivery deadline boundaries.

Framework imports run only in disposable subprocesses; QQ I/O is replaced.
"""
import asyncio
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

from repair_pipeline_support import load_pipeline, PLUGIN
from qq_delivery import QQDelivery
from resource_budget import Resources
from session_scope import Target
from task_runtime import work_context


class DeliveryDeadlineRegression(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='dsh-w4-deadline-')
        self.obj, ns = load_pipeline(self.tmp.name, names=('_send',))
        self.obj.resources = Resources({'deadline': 1, 'media_timeout': .2})
        self.token = self.obj.runtime.begin('fixture')
        self.posts = []; self.preparations = []; self.receipts = []
        self.context = SimpleNamespace(platform_manager=SimpleNamespace(platform_insts=[
            SimpleNamespace(meta=lambda: SimpleNamespace(id='bot', name='qq_official'))]))
        self.target = Target('qq_official', 'bot', '', 'private', 'fixture', 'trigger', received_at=time.time())
        self.chain = SimpleNamespace(chain=[SimpleNamespace(type='Image')])
        # Execute the actual constructor callback, without constructing the
        # plugin (which would register hooks and start background tasks).
        tree = ast.parse((PLUGIN/'main.py').read_text(encoding='utf-8-sig'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DshSoul')
        init = next(n for n in cls.body if getattr(n, 'name', '') == '__init__')
        call = next(n for n in ast.walk(init) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'QQDelivery')
        callback = next(k.value for k in call.keywords if k.arg == 'media_run')
        media_run = eval(compile(ast.Expression(callback), '<actual media callback>', 'eval'), dict(ns, self=self.obj))
        self.obj.delivery = QQDelivery(self.context, parse=self.parse, request=self.request,
            audit=lambda target, result: self.receipts.append(result.public()),
            media_run=media_run,
            media_thread=self.obj._thread)

    async def asyncTearDown(self):
        await self.obj.runtime.stop(); await self.obj.resources.close(); self.tmp.cleanup()

    async def parse(self, chain):
        self.preparations.append(True)
        return 'text', 'AA==', None, None, None, None, None

    async def request(self, platform, endpoint, payload):
        self.posts.append((endpoint, payload.copy()))
        return (200, {'file_info': 'upload'}) if endpoint.endswith('/files') else (200, {'id': 'accepted-id'})

    async def test_expired_request_starts_neither_prepare_nor_post(self):
        with work_context(self.token):
            self.obj._budget().expires = time.monotonic() - 1
            result = await self.obj._send(self.target, self.chain)
        self.assertEqual(self.preparations, [])
        self.assertEqual(self.posts, [])
        self.assertEqual((result.status, result.stage, result.category), ('skipped', 'prepare', 'deadline'))
        self.assertEqual(self.receipts[-1]['attempt_id'], result.attempt_id)

    async def test_preparation_cannot_run_past_remaining_deadline(self):
        async def slow(chain):
            self.preparations.append(True)
            await asyncio.Event().wait()
        self.obj.delivery.parse = slow
        with work_context(self.token):
            budget = self.obj._budget(); budget.expires = time.monotonic() + .025
            result = await self.obj._send(self.target, self.chain)
        self.assertEqual(self.posts, [])
        self.assertEqual((result.status, result.stage, result.category), ('skipped', 'prepare', 'deadline'))
        metrics = [row for row in self.obj.resources.metrics if row['stage'] == 'media']
        self.assertTrue(metrics)
        self.assertEqual({row['request_id'] for row in metrics}, {self.token.request})

    async def test_upload_finishing_after_deadline_cannot_start_message(self):
        with work_context(self.token):
            budget = self.obj._budget()
            async def late_upload(*args):
                value = await self.request(*args)
                budget.expires = time.monotonic() - 1
                return value
            self.obj.delivery.request = late_upload
            result = await self.obj._send(self.target, self.chain)
        self.assertEqual([p[0] for p in self.posts], ['/v2/users/fixture/files'])
        self.assertEqual((result.status, result.stage, result.category), ('skipped', 'upload', 'deadline'))

    async def test_in_flight_message_deadline_is_unknown_and_never_retried(self):
        async def hanging_message(*args):
            value = await self.request(*args)
            if args[1].endswith('/messages'): await asyncio.sleep(.08)
            return value
        self.obj.delivery.request = hanging_message
        with work_context(self.token):
            budget = self.obj._budget(); budget.expires = time.monotonic() + .025
            result = await self.obj._send(self.target, self.chain)
            again = await self.obj._send(self.target, self.chain)
        self.assertEqual((result.status, result.stage, result.category), ('unknown', 'message', 'deadline'))
        self.assertFalse(again)
        self.assertEqual(len(self.posts), 2)
        self.assertEqual(self.receipts[-2]['status'], 'unknown')

    async def test_known_acceptance_survives_deadline_crossing(self):
        with work_context(self.token):
            budget = self.obj._budget()
            async def late_accept(*args):
                value = await self.request(*args)
                if args[1].endswith('/messages'): budget.expires = time.monotonic() - 1
                return value
            self.obj.delivery.request = late_accept
            result = await self.obj._send(self.target, self.chain)
        self.assertEqual((result.status, result.message_id), ('accepted', 'accepted-id'))
        self.assertEqual(len(self.posts), 2)
        self.assertEqual(self.receipts[-1]['status'], 'accepted')

    async def test_plain_text_checks_deadline_after_preparation_too(self):
        self.chain = SimpleNamespace(chain=[SimpleNamespace(type='Plain')])
        with work_context(self.token):
            budget = self.obj._budget()
            async def late_plain(chain):
                budget.expires = time.monotonic() - 1
                return 'text', None, None, None, None, None, None
            self.obj.delivery.parse = late_plain
            result = await self.obj._send(self.target, self.chain)
        self.assertEqual(self.posts, [])
        self.assertEqual((result.status, result.category), ('skipped', 'deadline'))

    async def test_successful_media_stages_keep_original_request_id(self):
        with work_context(self.token): result = await self.obj._send(self.target, self.chain)
        self.assertTrue(result)
        stages = [m for m in self.obj.resources.metrics if m['stage'] in ('media', 'send')]
        self.assertEqual([m['stage'] for m in stages], ['media', 'media', 'send'])
        self.assertEqual({m['request_id'] for m in stages}, {self.token.request})

    async def test_waiting_for_credential_lock_honors_deadline(self):
        from qq_delivery import Permit
        permit = Permit(time.time()+300, 4)
        key = ('bot', '', 'private', 'fixture', 'message', 'trigger')
        self.obj.delivery.permits[key] = permit
        await permit.lock.acquire()
        try:
            with work_context(self.token):
                self.obj._budget().expires = time.monotonic()+.025
                result = await asyncio.wait_for(self.obj._send(self.target, self.chain), .5)
        finally: permit.lock.release()
        self.assertEqual((result.status, result.category), ('skipped', 'deadline'))
        self.assertEqual((self.posts, self.preparations, permit.used), ([], [], 0))

    async def test_post_authentication_deadline_check_prevents_http_post(self):
        from unittest.mock import patch
        from qq_delivery import request_once
        with work_context(self.token):
            budget = self.obj._budget()
            async def authenticate(): budget.expires = time.monotonic()-1
            def http_post(**kwargs):
                self.fail('HTTP POST started after authentication exhausted the deadline')
            http = SimpleNamespace(check_session=authenticate, is_sandbox=False,
                _headers={}, _session=SimpleNamespace(request=http_post))
            platform = self.context.platform_manager.platform_insts[0]
            platform.client = SimpleNamespace(api=SimpleNamespace(_http=http))
            # Route and response transport are replaced; no real QQ I/O.
            with patch.dict(sys.modules, {'botpy.http': SimpleNamespace(Route=lambda *a, **kw: SimpleNamespace(url='https://offline.invalid'))}):
                self.obj.delivery.request = request_once
                self.chain = SimpleNamespace(chain=[SimpleNamespace(type='Plain')])
                async def plain(chain): return 'text', None, None, None, None, None, None
                self.obj.delivery.parse = plain
                result = await self.obj._send(self.target, self.chain)
        self.assertEqual((result.status, result.category), ('skipped', 'deadline'))

    async def test_deadline_crossing_in_receipt_write_does_not_claim_dispatch(self):
        with work_context(self.token):
            budget = self.obj._budget()
            def audit(target, result):
                self.receipts.append(result.public())
                if result.category == 'in_flight': budget.expires = time.monotonic()-1
            self.obj.delivery.audit = audit
            result = await self.obj._send(self.target, self.chain)
        self.assertEqual([p[0] for p in self.posts], ['/v2/users/fixture/files'])
        self.assertEqual((result.status, result.category), ('skipped', 'deadline'))

    async def test_authentication_wait_timeout_does_not_close_unused_credential(self):
        import aiohttp  # warm the transport import before starting the deadline
        from unittest.mock import patch
        from qq_delivery import request_once
        with work_context(self.token):
            budget = self.obj._budget(); budget.expires = time.monotonic()+.025
            async def authenticate(): await asyncio.sleep(.2)
            def http_post(**kwargs): self.fail('HTTP POST started during slow authentication')
            http = SimpleNamespace(check_session=authenticate, is_sandbox=False,
                _headers={}, _session=SimpleNamespace(request=http_post))
            self.context.platform_manager.platform_insts[0].client = SimpleNamespace(api=SimpleNamespace(_http=http))
            with patch.dict(sys.modules, {'botpy.http': SimpleNamespace(Route=lambda *a, **kw: SimpleNamespace(url='https://offline.invalid'))}):
                self.obj.delivery.request = request_once
                self.chain = SimpleNamespace(chain=[SimpleNamespace(type='Plain')])
                async def plain(chain): return 'text', None, None, None, None, None, None
                self.obj.delivery.parse = plain
                result = await self.obj._send(self.target, self.chain)
        self.assertEqual((result.status, result.category), ('skipped', 'deadline'))
        self.assertFalse(next(iter(self.obj.delivery.permits.values())).closed)

    async def test_actual_http_transport_started_timeout_remains_unknown(self):
        import aiohttp  # this test must actually reach the replacement transport
        from unittest.mock import patch
        from qq_delivery import request_once
        with work_context(self.token):
            budget = self.obj._budget(); budget.expires = time.monotonic()+.025
            async def authenticate(): pass
            class PendingResponse:
                async def __aenter__(inner): await asyncio.sleep(.2)
                async def __aexit__(inner, *args): pass
            def http_post(**kwargs): self.posts.append(kwargs); return PendingResponse()
            http = SimpleNamespace(check_session=authenticate, is_sandbox=False,
                _headers={}, _session=SimpleNamespace(request=http_post))
            self.context.platform_manager.platform_insts[0].client = SimpleNamespace(api=SimpleNamespace(_http=http))
            with patch.dict(sys.modules, {'botpy.http': SimpleNamespace(Route=lambda *a, **kw: SimpleNamespace(url='https://offline.invalid'))}):
                self.obj.delivery.request = request_once
                self.chain = SimpleNamespace(chain=[SimpleNamespace(type='Plain')])
                async def plain(chain): return 'text', None, None, None, None, None, None
                self.obj.delivery.parse = plain
                result = await self.obj._send(self.target, self.chain)
        self.assertEqual((result.status, result.category), ('unknown', 'deadline'))
        self.assertEqual(len(self.posts), 1)
        self.assertTrue(next(iter(self.obj.delivery.permits.values())).closed)

    async def test_custom_media_reader_cannot_start_or_run_after_deadline(self):
        completed = []
        with work_context(self.token):
            budget = self.obj._budget()
            async def audio(chain): return '', None, None, '/fixture/audio', None, None, None
            async def slow_reader(*args, **kwargs):
                await asyncio.sleep(.08); completed.append(True); return b'fixture'
            self.obj.delivery.parse = audio
            self.obj.delivery.media_thread = slow_reader
            budget.expires = time.monotonic()+.025
            result = await self.obj._send(self.target, self.chain)
        self.assertEqual(completed, [], 'media reader ignores remaining request deadline')
        self.assertEqual(self.posts, [])
        self.assertEqual((result.status, result.category), ('skipped', 'deadline'))

    async def test_media_task_queued_on_loop_cannot_start_after_expiry(self):
        from resource_budget import BudgetExceeded
        started = []
        with work_context(self.token):
            budget = self.obj._budget()
            # This callback runs after Resources.thread has checked admission,
            # but before its newly scheduled worker task gets CPU time.
            asyncio.get_running_loop().call_soon(setattr, budget, 'expires', time.monotonic()-1)
            with self.assertRaises(BudgetExceeded): await self.obj._thread(lambda: started.append(True))
            await self.obj.resources.close()
        self.assertEqual(started, [], 'queued media task started after deadline')

    async def test_executor_queued_media_does_not_start_after_caller_timeout(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        started = []; occupied = threading.Event(); release = threading.Event(); queued = asyncio.Event()
        class Executor(ThreadPoolExecutor):
            submissions = 0
            def submit(inner, *args, **kw):
                future = super().submit(*args, **kw)
                inner.submissions += 1
                if inner.submissions == 2: queued.set()
                return future
        executor = Executor(max_workers=1)
        loop = asyncio.get_running_loop(); loop.set_default_executor(executor)
        def occupy(): occupied.set(); release.wait(2)
        blocker = loop.run_in_executor(None, occupy)
        try:
            while not occupied.is_set(): await asyncio.sleep(0)
            with work_context(self.token):
                self.obj._budget().expires = time.monotonic()+.025
                work = asyncio.create_task(self.obj._thread(lambda: started.append(True)))
                await asyncio.wait_for(queued.wait(), 1)
                with self.assertRaises(TimeoutError): await work
                release.set(); await blocker; await self.obj.resources.close()
            self.assertEqual(started, [], 'executor began media after original caller deadline')
        finally:
            release.set(); await blocker; executor.shutdown(wait=True)


class EventProvenanceRegression(unittest.TestCase):
    def isolated(self, ordering):
        with tempfile.TemporaryDirectory(prefix='dsh-w4-provenance-') as tmp:
            env = os.environ.copy(); env.update(ASTRBOT_ROOT=tmp, TEMP=tmp, TMP=tmp, PYTHONIOENCODING='utf-8')
            result = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), ordering],
                cwd=tmp, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout[-7000:])

    def test_supplemental_image_slow_during_first_inject(self): self.isolated('--later-slow')

    def test_first_image_slow_during_supplemental_gate(self): self.isolated('--first-slow')


async def provenance_case(first_slow):
    import copy
    import re
    from unittest.mock import AsyncMock, patch
    from test_repair_batch_input import PNG
    from test_repair_p2_acceptance import real_event
    from session_scope import bind_scope
    from state_store import read_json, write_json
    from context_window import build_window
    from task_runtime import current_event
    from astrbot.core.message.components import Plain, Image
    from astrbot.core.provider.entities import ProviderRequest
    from astrbot.core.star.session_llm_manager import SessionServiceManager
    from astrbot.core.star.session_plugin_manager import SessionPluginManager
    root = Path(os.environ['ASTRBOT_ROOT']); (root/'persona.md').write_text('fixture', encoding='utf-8')
    path = root/'fixed.png'; path.write_bytes(PNG)
    obj, ns = load_pipeline(root, names=('gate', 'inject', '_save_inbox_images', '_save_inbox_files', '_entry_feature', 'recall'), guarded=True)
    ns.update(Plain=Plain, Image=Image, File=type('UnusedFile', (), {}), _save=write_json, _load=read_json,
        _conf=lambda key: key=='enabled', POINTS_FILE=str(root/'points.json'), _conf_val=lambda key, default: default,
        MASTER_SWITCH_RE=re.compile('^never$'), REMIND_CMD_RE=re.compile('^never$'), STATUS_RE=re.compile('^never$'),
        BATCH_STREAK_GAP=8, BATCH_DONE_MINLEN=8, BATCH_END_PUNCT='。!?', MAX_ITEMS=8,
        normalize_image=__import__('batch_input').normalize_image, read_local_image=__import__('batch_input').read_local_image,
        random=SimpleNamespace(random=lambda: 1), BATCH_WAIT=0)
    obj.names={}; obj.sil={}; obj.n_path=str(root/'names.json'); obj._match_sleep_cmd=lambda *a: None
    obj.batch_buf={}; obj.batch_skipwait={}; obj.last_msg_at={}
    obj.context=SimpleNamespace(get_config=lambda **kw: {'agent_runner': {'runner_type': 'local'}})
    first=real_event(group='race-group'); first.message_obj.message_id='slow-first'; first.message_str='待办首条'
    later=real_event(group='race-group'); later.message_obj.message_id='slow-later'; later.message_str='待办补图'
    first.message_obj.message=[Plain(first.message_str)]; later.message_obj.message=[Plain(later.message_str)]
    slow=first if first_slow else later
    slow.message_obj.message.append(Image.fromFileSystem(str(path)))
    actual_thread=obj._thread; entered=asyncio.Event(); release=asyncio.Event()
    async def delayed_thread(fn, *args, **kw):
        if fn is ns['read_local_image'] and current_event() is slow:
            entered.set(); await release.wait()
        return await actual_thread(fn, *args, **kw)
    obj._thread=delayed_thread
    with patch.object(SessionServiceManager, 'is_session_enabled', AsyncMock(return_value=True)), patch.object(SessionPluginManager, 'is_plugin_enabled_for_session', AsyncMock(return_value=True)):
        if first_slow:
            arrival=asyncio.create_task(obj.gate(first)); await asyncio.wait_for(entered.wait(), 2)
            await obj.gate(later); release.set(); await arrival
        else:
            await obj.gate(first)
            arrival=asyncio.create_task(obj.gate(later)); await asyncio.wait_for(entered.wait(), 2)
            injecting=asyncio.create_task(obj.inject(first, ProviderRequest(prompt='question')))
            await asyncio.sleep(.02); assert not injecting.done()
            release.set(); await asyncio.gather(arrival, injecting)
        scope=bind_scope(first)
        rolling=read_json(obj.h_path, {})[scope.key]
        archived=[json.loads(line) for line in (root/'archive.jsonl').read_text(encoding='utf-8').splitlines()]
        shared=read_json(obj.group_path, {})[scope.group_key]
        expected={'待办首条': 'slow-first', '待办补图': 'slow-later'}
        for label, rows in [('rolling', rolling), ('archive', archived), ('group', shared)]:
            assert {r['text']: r['source']['message_id'] for r in rows} == expected, (label, rows)
        # Force both original records into the compacted portion, then verify
        # both the retained quotations and real recall output, not just pixels.
        padded=copy.deepcopy(archived)
        for n in range(13):
            padded.append(dict(id='padding-'+str(n), role='user', text='padding', ts=n+100,
                source=dict(scope.source(), message_id='padding-'+str(n))))
        window=build_window(padded, [], scope)
        assert {r['text']: r['message_id'] for r in window['summary']['entries'] if r['text'].startswith('待办')} == expected, window
        recall=await obj.recall(first, '待办')
        assert '消息=slow-first]待办首条' in recall, recall
        assert '消息=slow-later]待办补图' in recall, recall
    await obj.runtime.stop(); await obj.resources.close()
    print('immutable provenance OK', 'first-slow' if first_slow else 'later-slow')


if __name__ == '__main__':
    if '--first-slow' in sys.argv or '--later-slow' in sys.argv:
        asyncio.run(provenance_case('--first-slow' in sys.argv))
    else: unittest.main()
