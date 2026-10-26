"""Single-instance task ownership and revocable request identities (no framework import)."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace, field
import functools
import inspect
import uuid
import weakref

_work=ContextVar('dsh_work',default=None)
_event=ContextVar('dsh_event',default=None)
_background=ContextVar('dsh_background',default=False)
_budget_job=ContextVar('dsh_budget_job',default=None)
_slots=weakref.WeakValueDictionary()
FEATURES={'_voice_reply':'voice','_sprinkle_later':'sprinkle','_revive_later':'revive',
          '_harvest_one':'harvest','_desire_for':'desire','_proactive_send':'proactive',
          '_send_reminder':'reminders','_startup_greet':'reply','_run_kimi':'kimi'}
FEATURES.update({name:'files' for name in ('read_local_file','list_files','write_local_file','send_local_file','search_in_files')})
FEATURES['_admin_loop']='admin'


@dataclass
class JobBudget:
    id: str = field(default_factory=lambda:uuid.uuid4().hex)
    active: bool = True


@dataclass(frozen=True)
class Token:
    runtime: object
    key: str
    epoch: int
    request: str
    feature: str
    source: object = field(default=None,compare=False)


@contextmanager
def work_context(token,event=None):
    saved=_work.set(token)
    source=_event.set(event) if event is not None else None
    try: yield
    finally:
        _work.reset(saved)
        if source is not None: _event.reset(source)


def current_event(): return _event.get()
def current_token(): return _work.get()
def background_work(): return _background.get()
def current_budget_job(): return _budget_job.get()


def check_current():
    token=_work.get()
    if token: token.runtime.check(token)


class Runtime:
    def __init__(self, allowed, slot=None):
        self.id=uuid.uuid4().hex; self.allowed=allowed; self.alive=True
        self.max_tasks=64
        self.tasks=set(); self.borrowed={}; self.epochs={}; self.requests={}; self.errors=[]; self.jobs={}; self.paused={}; self.exclusive={}
        if slot:
            old=_slots.get(slot)
            if old: old.close()
            _slots[slot]=self

    def token(self,key='',feature='reply',request=None):
        return Token(self,key,self.epochs.get(key,0),self.requests.get(key,'') if request is None else request,feature)

    def begin(self,key,feature='reply'):
        self.invalidate(key)
        self.requests[key]=uuid.uuid4().hex
        return self.token(key,feature)

    def valid(self,token):
        return (self.alive and token.runtime is self and self.epochs.get(token.key,0)==token.epoch
                and (not token.request or self.requests.get(token.key)==token.request)
                and (not token.key or self.allowed(token.key,token.feature)))

    def pause(self,key):
        self.paused.setdefault(key,asyncio.Event())

    def resume(self,key):
        waiting=self.paused.pop(key,None)
        if waiting: waiting.set()

    async def ready(self,key):
        waiting=self.paused.get(key)
        if waiting: await waiting.wait()

    def check(self,token=None):
        token=token or _work.get() or self.token()
        if not self.valid(token): raise asyncio.CancelledError('work identity was revoked')

    def borrow(self,token):
        task=asyncio.current_task()
        if task not in self.borrowed:
            task.add_done_callback(lambda t:self.borrowed.pop(t,None))
        self.borrowed[task]=token

    def spawn(self,coro,*,key=None,feature=None,exclusive=None,source=None):
        parent=_work.get()
        key=key if key is not None else (parent.key if parent and parent.runtime is self else '')
        name=coro.cr_frame.f_locals.get('name',coro.cr_code.co_name)
        feature=feature or FEATURES.get(name,'reply')
        token=self.token(key,feature,request=parent.request if parent and parent.key==key else '')
        token=replace(token,source=source or (parent.source if parent and parent.key==key else None))
        job=(key,name)
        if not self.alive or len(self.tasks)>=self.max_tasks or job in self.jobs or (exclusive and exclusive in self.exclusive):
            coro.close(); return self.jobs.get(job) or self.exclusive.get(exclusive)
        async def run():
            saved=_background.set(True)
            budget=JobBudget();saved_budget=_budget_job.set(budget)
            try:
                with work_context(token):
                    self.check(token)
                    return await coro
            finally:
                budget.active=False;_budget_job.reset(saved_budget);_background.reset(saved)
        task=asyncio.create_task(run(),name='dsh:'+name)
        self.tasks.add(task); self.jobs[job]=task
        if exclusive: self.exclusive[exclusive]=task
        def done(t):
            coro.close()  # also closes work cancelled before run() started
            self.tasks.discard(t)
            if self.jobs.get(job) is t: self.jobs.pop(job,None)
            if exclusive and self.exclusive.get(exclusive) is t: self.exclusive.pop(exclusive,None)
            if not t.cancelled():
                error=t.exception()
                if error: self.errors.append((name,type(error).__name__))
        task.add_done_callback(done)
        return task

    def invalidate(self,key):
        self.epochs[key]=self.epochs.get(key,0)+1
        self.requests.pop(key,None)
        current=asyncio.current_task()
        for (scope,_),task in list(self.jobs.items()):
            if scope==key and task is not current: task.cancel()
        for task,token in list(self.borrowed.items()):
            if token.key==key and task is not current: task.cancel()

    def revoke_feature(self,feature,key=None):
        current=asyncio.current_task()
        for (scope,name),task in list(self.jobs.items()):
            if (key is None or key==scope) and FEATURES.get(name,'reply')==feature and task is not current:
                task.cancel()

    def close(self):
        self.alive=False
        current=asyncio.current_task()
        for task in self.tasks | set(self.borrowed):
            if task is not current: task.cancel()

    async def stop(self):
        self.close()
        current=asyncio.current_task()
        tasks=[t for t in self.tasks | set(self.borrowed) if t is not current]
        if tasks: await asyncio.gather(*tasks,return_exceptions=True)
        self.tasks.clear()


def managed(fn):
    """Apply below framework registration decorators, so stored callbacks are guarded."""
    name=fn.__name__; signature=inspect.signature(fn)
    @functools.wraps(fn)
    async def run(self,*args,**kw):
        values=signature.bind(self,*args,**kw).arguments
        event=values.get('event'); parent=_work.get()
        own_budget=None;saved_budget=None
        try:
            if event is not None:
                scope=self._scope(event)
                if name=='gate':
                    instance=self.runtime.token()
                    self.runtime.borrow(instance)
                    await self.runtime.ready(scope.key)
                    self.runtime.check(instance)
                token=event.get_extra('_dsh_work')
                if token is None:
                    if not self.batch_wait.get(scope.key):
                        self._reset_request(scope.key)
                    token=(self.runtime.token(scope.key) if self.batch_wait.get(scope.key)
                           else self.runtime.begin(scope.key))
                    event.set_extra('_dsh_work',token)
                self.runtime.borrow(token)
                token=replace(token,source=scope,feature=self._entry_feature(event) if name=='gate' else 'harvest' if name=='harvest_images' else FEATURES.get(name,'reply'))
                event.set_extra('_dsh_work',token)
            elif parent and parent.runtime is self.runtime and parent.key:
                token=replace(parent,feature=FEATURES.get(name,parent.feature))
            else:
                key=values.get('uid','')
                if isinstance(values.get('scope'),__import__('session_scope').Scope): key=values['scope'].key
                key=key if key in self.scopes else ''
                token=self.runtime.token(key,FEATURES.get(name,'reply'),request='')
                if key:
                    own_budget=JobBudget();saved_budget=_budget_job.set(own_budget)
            if token.key and token.source is None:
                from session_scope import Scope
                source=values.get('scope')
                if not isinstance(source,Scope) and token.key in self.scopes: source=Scope(**self.scopes[token.key])
                token=replace(token,source=source)
            with work_context(token,event):
                self.runtime.check(token)
                if event is not None:
                    if not hasattr(self,'request_owners'): self.request_owners={}
                    if not hasattr(self,'request_events'): self.request_events={}
                    if self.request_owners.get(scope.key)!=token.request:
                        self.request_owners[scope.key]=token.request
                        self.request_events[scope.key]=event
                if event is not None:
                    from session_scope import check_framework_policy
                    await check_framework_policy(event)
                    self.runtime.check(token)
                result=await fn(self,*args,**kw)
                self.runtime.check(event.get_extra('_dsh_work') if name=='gate' else token)
                return result
        except asyncio.CancelledError:
            # AstrBot 4.29.1 catches BaseException in call_event_hook. Mark the
            # event stopped as well, or its pipeline can dispatch/send anyway.
            if event is not None and callable(getattr(event,'stop_event',None)):
                if callable(getattr(event,'set_result',None)): event.set_result(None)
                event.stop_event()
            raise
        finally:
            if own_budget is not None:
                own_budget.active=False;_budget_job.reset(saved_budget)
    run._dsh_managed=True
    return run
