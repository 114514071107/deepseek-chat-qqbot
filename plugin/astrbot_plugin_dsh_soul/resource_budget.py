"""Local protective limits, not a claim about upstream capacity or money."""
import asyncio
import copy
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
import math
import time

DEFAULTS = dict(foreground=2, background=1, media=2, background_media=1, queue=8, deadline=120,
                model_timeout=45, tool_timeout=15, media_timeout=65,
                model_calls=6, tool_steps=8, output_tokens=1024,
                input_chars=48000, output_chars=8192, tool_chars=4000, tasks=64,
                archive_bytes=32*1024*1024, archive_rows=4000)
_lease = ContextVar('dsh_resource_lease', default=None)
_output_cap = ContextVar('dsh_output_cap', default=None)


class BudgetExceeded(RuntimeError): pass
class ImageUnavailable(BudgetExceeded): pass


def limits(config):
    result = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        value = config.get(key, default) if isinstance(config, dict) else default
        ceiling = 256*1024*1024 if key=='archive_bytes' else 600 if key.endswith('timeout') or key == 'deadline' else 32 if key in ('foreground','background','media','background_media') else 128 if key in ('queue','tasks') else 1_000_000
        if type(value) not in (int, float) or not math.isfinite(value): continue
        minimum = 0 if key == 'queue' else .01 if key.endswith('timeout') or key == 'deadline' else 1
        result[key] = max(minimum, min(ceiling, value))
        if key != 'deadline' and not key.endswith('timeout'): result[key] = int(result[key])
    return result


class Budget:
    def __init__(self, config, identity='', guard=lambda: None, parent=None):
        self.config = config; self.identity = identity; self.guard = guard
        self.expires = time.monotonic() + config['deadline']
        self.counters = parent.counters if parent else {'calls':0,'steps':0}

    @property
    def calls(self): return self.counters['calls']

    @property
    def steps(self): return self.counters['steps']

    def check(self):
        self.guard()
        if time.monotonic() >= self.expires: raise BudgetExceeded('本轮处理已超时')

    def model(self):
        self.check()
        if self.calls >= self.config['model_calls']: raise BudgetExceeded('本轮模型调用额度已用尽')
        self.counters['calls'] += 1

    def tool(self):
        self.check()
        if self.steps >= self.config['tool_steps']: raise BudgetExceeded('本轮工具步数已用尽')
        self.counters['steps'] += 1

    def input(self, count):
        self.check()
        if count > self.config['input_chars']: raise BudgetExceeded('本轮模型输入超过字符预算')

    def tool_result(self, text):
        count = self.config['tool_chars']
        if len(text) <= count: return text
        label = '[工具结果截断]'
        return text[:max(0, count-len(label))] + label[:count]


class Pool:
    def __init__(self, size, queue):
        self.semaphore = asyncio.Semaphore(size); self.waiting = 0; self.queue = queue

    async def acquire(self):
        if self.semaphore.locked() and self.waiting >= self.queue:
            raise BudgetExceeded('处理队列已满，请稍后重试')
        self.waiting += 1
        try: await self.semaphore.acquire()
        finally: self.waiting -= 1


class Resources:
    def __init__(self, config):
        self.config = limits(config)
        self.pools = {name: Pool(self.config[name], self.config['queue']) for name in ('foreground','background','media','background_media')}
        self.metrics = deque(maxlen=512); self.budgets = {}; self.workers = set()

    def budget(self, identity, guard=lambda: None, parent=None):
        # Expired entries are never recreated for the same request. Runtime
        # supplies a fresh UUID on a new request; the bounded cache is metadata.
        if identity not in self.budgets:
            if len(self.budgets) >= 512:
                # Only revoked identities may be discarded. Evicting a live
                # budget would grant its caller a fresh set of model calls.
                for key, budget in list(self.budgets.items()):
                    try: budget.guard()
                    except asyncio.CancelledError: self.budgets.pop(key, None)
                if len(self.budgets) >= 512: raise BudgetExceeded('请求身份预算表已满')
            self.budgets[identity] = Budget(self.config, identity, guard, parent)
        return self.budgets[identity]

    def note(self, stage, started, budget=None, status='ok', lane='', request_id=''):
        self.metrics.append(dict(stage=stage, seconds=round(time.monotonic()-started, 6),
                                 request_id=budget.identity if budget else request_id, status=status, lane=lane))

    @contextmanager
    def timer(self, stage, budget=None, request_id=''):
        start = time.monotonic(); status = 'ok'
        try: yield
        except BaseException:
            status = 'interrupted'; raise
        finally: self.note(stage, start, budget, status, request_id=request_id)

    async def run(self, lane, factory, budget=None, stage='model', timeout=None):
        if budget: budget.check()
        pool = self.pools[lane]; queued = time.monotonic(); acquired = False
        owner = (id(self), lane, asyncio.current_task())
        nested = _lease.get() == owner
        ttl = timeout or self.config['media_timeout' if lane in ('media','background_media') else 'model_timeout']
        if budget: ttl = min(ttl, budget.expires-time.monotonic())
        try:
            async with asyncio.timeout(ttl):
                if not nested:
                    await pool.acquire(); acquired = True
                self.note('queue', queued, budget, lane=lane)
                if budget: budget.check()
                lease = _lease.set(owner)
                try:
                    with self.timer(stage, budget):
                        result = await factory()
                        if budget: budget.check()
                        return result
                finally: _lease.reset(lease)
        except TimeoutError as exc:
            raise BudgetExceeded('本阶段处理已超时') from exc
        finally:
            if acquired: pool.semaphore.release()
            elif not nested:self.note('queue', queued, budget, 'interrupted', lane)

    async def thread(self, fn, *args, _lane='media', _budget=None, **kwargs):
        # A cancelled to_thread await does not stop its worker. Keep its lease
        # until the actual worker ends; do not admit an unbounded replacement.
        pool = self.pools[_lane]; queued = time.monotonic()
        if _budget:_budget.check()
        ttl=min(self.config['media_timeout'],_budget.expires-time.monotonic()) if _budget else self.config['media_timeout']
        expires=time.monotonic()+ttl
        try:
            async with asyncio.timeout(ttl): await pool.acquire()
        except BaseException:
            self.note('queue',queued,_budget,'interrupted',_lane);raise
        self.note('queue', queued, _budget, lane=_lane)
        try:
            if _budget:_budget.check()
        except BaseException:
            pool.semaphore.release();raise
        active=True
        def invoke():
            # The shared executor can queue this work after our caller times
            # out. Recheck in the actual worker before touching media/state.
            if not active: raise BudgetExceeded('媒体调用已结束')
            if _budget:_budget.check()
            if time.monotonic()>=expires: raise BudgetExceeded('媒体任务已超时')
            return fn(*args, **kwargs)
        async def run():
            try:
                with self.timer('media',_budget):
                    if _budget:_budget.check()
                    if time.monotonic()>=expires: raise BudgetExceeded('媒体任务已超时')
                    return await asyncio.to_thread(invoke)
            finally: pool.semaphore.release()
        task = asyncio.create_task(run()); self.workers.add(task)
        def done(work):
            self.workers.discard(work)
            if not work.cancelled(): work.exception()
        task.add_done_callback(done)
        try:
            async with asyncio.timeout(max(0,expires-time.monotonic())):
                result=await asyncio.shield(task)
                if _budget:_budget.check()
                return result
        finally: active=False

    async def close(self):
        if self.workers: await asyncio.gather(*list(self.workers), return_exceptions=True)


def payload_size(value):
    """Text chars, not token count. Exclude encoded image bytes from text count."""
    if isinstance(value, str): return len(value)
    if isinstance(value, dict): return sum(payload_size(v) for k,v in value.items() if k not in ('image_url','audio_url','data'))
    if isinstance(value, (list,tuple)): return sum(payload_size(v) for v in value)
    return 0


def image_count(value):
    if isinstance(value, dict):
        if value.get('type') == 'image_url': return 1
        return sum(image_count(v) for v in value.values())
    if isinstance(value, (list,tuple)): return sum(image_count(v) for v in value)
    return 0


class BudgetProvider:
    def __init__(self, provider, resources, budget, lane, expected_images=0):
        self.original = provider; self.resources = resources; self.budget = budget
        self.lane = lane; self.expected_images = expected_images
        # Versioned 4.29.1 OpenAI adapter: its compatibility loop can strip
        # pictures or rotate keys independently of request_max_retries. Use a
        # request-local copy, stop that loop and count each physical _query.
        self.physical = any(c.__module__ == 'astrbot.core.provider.sources.openai_source' and c.__name__ == 'ProviderOpenAIOfficial' for c in type(provider).__mro__)
        if self.physical:
            self.original = copy.copy(provider)
            self.original.provider_config = dict(provider.provider_config)
            extra = dict(provider.provider_config.get('custom_extra_body') or {})
            for field in ('max_tokens','max_completion_tokens'): extra.pop(field, None)
            self.original.provider_config['custom_extra_body'] = extra
            if hasattr(provider, 'client'): self.original.client = copy.copy(provider.client)
            def guard_payload(args,kw):
                payload = args[0] if args else kw.get('payloads', {})
                # 4.29.1's _prepare_chat_payload drops arbitrary kwargs,
                # including max_tokens. Enforce on the physical payload too.
                payload['max_tokens'] = min(_output_cap.get() or self.budget.config['output_tokens'],self.budget.config['output_tokens'])
                self.budget.input(payload_size(payload))
                if self.expected_images and image_count(payload.get('messages', [])) < self.expected_images:
                    raise ImageUnavailable('图片在提供商转换阶段被移除，未送入模型')
                self.budget.model()
                kw['request_max_retries'] = 1
            query = self.original._query
            async def bounded_query(*args, **kw):
                guard_payload(args,kw)
                return await query(*args, **kw)
            query_stream = self.original._query_stream
            async def bounded_stream(*args, **kw):
                guard_payload(args,kw)
                stream=query_stream(*args, **kw)
                try:
                    async for chunk in stream:yield chunk
                finally:await stream.aclose()
            async def no_compatibility_retry(error, *args, **kw): raise error
            self.original._query = bounded_query
            self.original._query_stream = bounded_stream
            self.original._handle_api_error = no_compatibility_retry

    def __getattr__(self, name): return getattr(self.original, name)

    def prepare(self, kw):
        self.budget.input(payload_size(kw.get('contexts', [])) + payload_size(kw.get('prompt','')) + payload_size(kw.get('system_prompt','')))
        if self.expected_images:
            modalities = self.provider_config.get('modalities')
            count = len(kw.get('image_urls') or []) + image_count(kw.get('contexts', []))
            if modalities != [] and (not isinstance(modalities, list) or 'image' not in modalities):
                raise ImageUnavailable('当前模型未启用图片能力，图片未送入模型；不能声称已看图')
            if count < self.expected_images:
                raise ImageUnavailable('图片在准备或能力过滤阶段被移除，未送入模型；不能声称已看图')
        kw['max_tokens'] = min(kw.get('max_tokens') or self.budget.config['output_tokens'], self.budget.config['output_tokens'])
        kw['request_max_retries'] = 1  # AstrBot means total attempts (minimum one).
        return kw

    async def text_chat(self, **kw):
        kw = self.prepare(kw)
        async def invoke():
            if not self.physical: self.budget.model()
            saved=_output_cap.set(kw['max_tokens'])
            try:
                result=await self.original.text_chat(**kw)
                self.check_output(result)
                return result
            finally:_output_cap.reset(saved)
        return await self.resources.run(self.lane, invoke, self.budget)

    async def text_chat_stream(self, **kw):
        # QQ uses nonstreaming replies under F07. Still bound unexpected callers;
        # consume under one lease and one deadline, never an unbounded stream.
        kw = self.prepare(kw)
        async def invoke():
            if not self.physical:self.budget.model()
            chunks = []; chars=0
            saved=_output_cap.set(kw['max_tokens'])
            stream = self.original.text_chat_stream(**kw)
            try:
                async for chunk in stream:
                    size=self.check_output(chunk)
                    chars=chars+size if getattr(chunk,'is_chunk',False) else max(chars,size)
                    if chars>self.budget.config['output_chars']:raise BudgetExceeded('模型流式输出超过字符预算')
                    chunks.append(chunk)
                    if len(chunks) > self.budget.config['output_tokens'] * 2:
                        raise BudgetExceeded('模型流式输出超过预算')
            finally:
                await stream.aclose();_output_cap.reset(saved)
            return chunks
        for chunk in await self.resources.run(self.lane, invoke, self.budget): yield chunk

    def check_output(self, response):
        size=sum(payload_size(getattr(response,name,None)) for name in ('completion_text','reasoning_content','tools_call_args'))
        if size>self.budget.config['output_chars']:raise BudgetExceeded('模型输出超过字符预算')
        return size
