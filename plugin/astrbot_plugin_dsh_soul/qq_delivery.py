"""QQ group/C2C delivery, single attempt, explicit receipts. No framework imports at load.

AGPL-3.0; local integration for AstrBot 4.29.1. Uses its media conversion and
authenticated session, deliberately bypasses SDK retries and proactive fallbacks.
"""
import asyncio
import base64
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
import time
import uuid
from session_scope import Target
from task_runtime import check_current, current_event
from resource_budget import BudgetExceeded


_delivery_budget = ContextVar('dsh_delivery_budget', default=None)
_message_dispatch = ContextVar('dsh_message_dispatch', default=None)


def check_delivery_budget():
    check_current()
    budget = _delivery_budget.get()
    if budget is not None: budget.check()


class DeliveryNotStarted(BudgetExceeded):
    """Authentication completed after the deadline; no HTTP POST was started."""


class DeliveryDeadline(BudgetExceeded):
    """The request's timeout fired (event-loop clocks may fire slightly early)."""


@asynccontextmanager
async def delivery_lock(lock):
    budget = _delivery_budget.get()
    check_delivery_budget()
    try:
        async with asyncio.timeout_at(budget.expires if budget else None):
            await lock.acquire()
    except TimeoutError as error:
        raise DeliveryDeadline('等待发送凭据超时') from error
    try: yield
    finally: lock.release()


@dataclass
class DeliveryResult:
    status: str
    stage: str = 'message'
    category: str = ''
    message_id: str = ''
    code: str = ''
    error: str = ''
    seq: int = 0
    ref_idx: str = ''
    persistence: dict = field(default_factory=dict)
    fallback_from: dict = field(default_factory=dict)
    attempt_id: str = field(default_factory=lambda:uuid.uuid4().hex)
    media: dict = field(default_factory=dict)

    def __bool__(self): return self.status == 'accepted'
    def public(self): return asdict(self)


def failure(status,stage,category,code='',seq=0):
    # Never retain SDK exception/body: they can contain target IDs, tokens or text.
    return DeliveryResult(status,stage,category,code=str(code),
                          error=f'{stage}:{category}',seq=seq)


class DeliveryCancelled(asyncio.CancelledError):
    def __init__(self,result):
        super().__init__('delivery cancelled')
        self.delivery_result=result


async def check_delivery_policy():
    check_delivery_budget()
    event=current_event()
    if event is not None:
        from session_scope import check_framework_policy
        await check_framework_policy(event)
    check_delivery_budget()


def classify(code,status):
    code=str(code or '')
    if code in {'40034105','304004','304036','304064','40034127','40054013','40054002'} or status in (401,403): return 'permission'
    if code in {'40034100','40034122','40034128'} or status==429: return 'rate_limit'
    if code in {'304103','40034005','40034026'}: return 'expired'
    if code=='40054005': return 'duplicate'
    if code in {'40034024','40034025','40034027','40034101','40054003','40054004','40054006','40054016'}: return 'route'
    if code in {'304080','40034004'}: return 'media'
    return 'platform'


async def parse_chain(chain):
    from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import QQOfficialMessageEvent
    parsed=await QQOfficialMessageEvent._parse_to_qqofficial(chain)
    # The framework silently swallows audio conversion failures. Surface them.
    from astrbot.api.message_components import Record
    if any(isinstance(c,Record) for c in chain.chain) and not parsed[3]:
        raise ValueError('audio conversion failed')
    return parsed


def read_upload(path):
    with open(path,'rb') as stream: data=stream.read(20*1024*1024+1)
    if len(data)>20*1024*1024: raise ValueError('media size limit')
    return data


def reply_reference(chain):
    # QQ v2 users/groups both document message_reference as unsupported.
    # A REFIDX prefix is not source authorization. Never substitute the
    # current message for a missing/foreign quote or claim a card was sent.
    return None


async def request_once(platform,endpoint,payload):
    """One HTTP POST. No botpy.request (it retries resets and swallows timeouts)."""
    import aiohttp
    from botpy.http import Route
    dispatch=_message_dispatch.get()
    if dispatch is not None: dispatch['started']=False
    http=platform.client.api._http
    await http.check_session()  # existing bot authentication; no config/secret lookup
    try: await check_delivery_policy()
    except BudgetExceeded:
        raise DeliveryNotStarted('发送前请求预算已耗尽') from None
    route=Route('POST',endpoint,is_sandbox=http.is_sandbox)
    if dispatch is not None: dispatch['started']=True
    async with http._session.request(method='POST',url=route.url,headers=http._headers,
            json=payload,timeout=aiohttp.ClientTimeout(total=20),allow_redirects=False) as response:
        try: data=await response.json(content_type=None)
        except (ValueError,TypeError): data=None
        return response.status,data


@dataclass
class Permit:
    expires: float
    limit: int
    used: int = 0
    closed: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class QQDelivery:
    def __init__(self,context,*,request=request_once,parse=parse_chain,clock=time.time,audit=None,retain_media=None,media_run=None,media_thread=None):
        self.context=context; self.request=request; self.parse=parse; self.clock=clock
        self.audit=audit
        self.retain_media=retain_media
        self.media_run=media_run
        self.media_thread=media_thread or asyncio.to_thread
        # Survives plugin helper reload on this context, but not process restart.
        if not hasattr(context,'_dsh_reply_permits'): context._dsh_reply_permits={}
        self.permits=context._dsh_reply_permits

    def record(self,target,result):
        if self.audit:
            try:
                self.audit(target,result)
                result.persistence['receipt']='saved'
            except (Exception,asyncio.CancelledError):
                result.persistence['receipt']='failed'

    async def send(self,target,chain,*,mode='reply',budget=None):
        attempt=uuid.uuid4().hex
        binding=_delivery_budget.set(budget)
        try:
            try: result=await self._send_once(target,chain,mode=mode,attempt=attempt)
            except BudgetExceeded:
                result=failure('skipped','prepare','deadline')
            except DeliveryCancelled as error:
                error.delivery_result.attempt_id=attempt
                self.record(target,error.delivery_result)
                raise
        finally: _delivery_budget.reset(binding)
        result.attempt_id=attempt
        if any(getattr(getattr(c,'type',None),'value',getattr(c,'type',None)) == 'Reply'
               for c in (getattr(chain,'chain',None) or [])):
            result.persistence['reference']='unsupported'
        self.record(target,result)
        return result

    async def _prepare(self,factory,*,pooled=True):
        """Bound even custom media callbacks to the original remaining time."""
        budget=_delivery_budget.get()
        check_delivery_budget()
        timeout=asyncio.timeout_at(budget.expires if budget else None)
        try:
            async with timeout:
                result=await self.media_run(factory) if pooled and self.media_run else await factory()
                check_delivery_budget()
                return result
        except (TimeoutError,BudgetExceeded) as error:
            if timeout.expired():
                raise DeliveryDeadline('发送媒体处理超时') from error
            raise

    async def _send_once(self,target,chain,*,mode,attempt):
        if not isinstance(target,Target) or target.platform!='qq_official' or mode not in ('reply','proactive'):
            return failure('failed','route','route')
        try: endpoint=target.endpoint('messages')
        except ValueError: return failure('failed','route','route')
        platforms=[p for p in self.context.platform_manager.platform_insts
                   if p.meta().id==target.instance and p.meta().name==target.platform]
        if len(platforms)!=1: return failure('failed','route','route')
        permit=None
        if mode=='reply':
            credential=target.message_id or target.event_id
            if not credential or not target.received_at: return failure('skipped','credential','missing_credential')
            key=(target.instance,target.bot,target.kind,target.address,
                 'message' if target.message_id else 'event',credential)
            # Prune only expired ledgers; old timestamps still fail before insertion.
            now=self.clock()
            if now>=target.received_at+300: return failure('skipped','credential','expired')
            for old,p in list(self.permits.items()):
                if now>=p.expires and not p.lock.locked(): self.permits.pop(old,None)
            permit=self.permits.setdefault(key,Permit(target.received_at+300,4 if target.kind=='private' else 5))
        async with delivery_lock(permit.lock if permit else asyncio.Lock()):
            if permit:
                if self.clock()>=permit.expires: return failure('skipped','credential','expired')
                if permit.closed: return failure('skipped','credential','closed')
                if permit.used>=permit.limit: return failure('skipped','credential','exhausted')
            stage='prepare';seq=0;message_started=False;message_timeout=None
            try:
                await check_delivery_policy()
                has_media=any(getattr(getattr(c,'type',None),'value',getattr(c,'type',None)) in ('Image','Video','Record','File')
                              for c in getattr(chain,'chain',[]) or [])
                parsed = await self._prepare(lambda:self.parse(chain),pooled=has_media)
                text,image,image_path,audio,video,file_path,file_name=parsed
                check_delivery_budget()
                media_parts=[(image,1,True),(audio,3,False),(video,2,False),(file_path,4,False)]
                media_parts=[part for part in media_parts if part[0]]
                if len(media_parts)>1: return failure('failed','prepare','media')
                if not text and not media_parts: return failure('skipped','prepare','empty')
                payload={'msg_type':0,'content':text} if text else {}
                upload=None
                origin=''
                if media_parts:
                    stage='upload';source,file_type,is_base64=media_parts[0]
                    wanted={1:'Image',2:'Video',3:'Record',4:'File'}[file_type]
                    components=[c for c in (getattr(chain,'chain',None) or [])
                                if getattr(getattr(c,'type',None),'value',getattr(c,'type',None))==wanted]
                    if components:
                        component=components[-1] if file_type==3 else components[0]
                        origin=str(getattr(component,'file_',None) or getattr(component,'url',None)
                                   or getattr(component,'file',None) or '')
                    upload={'file_type':file_type,'srv_send_msg':False}
                    if is_base64: upload['file_data']=source
                    else:
                        from pathlib import Path
                        if str(source).startswith(('http://','https://')):
                            if self.retain_media:
                                from network_safety import fetch_public_bytes
                                content=await self._prepare(lambda:self.media_thread(fetch_public_bytes,str(source),max_bytes=20*1024*1024,timeout=60),pooled=False)
                                check_delivery_budget()
                                upload['file_data']=base64.b64encode(content).decode('ascii')
                            else: upload['url']=str(source)
                        else:
                            content=await self._prepare(lambda:self.media_thread(read_upload,source),pooled=False)
                            check_delivery_budget()
                            upload['file_data']=base64.b64encode(content).decode('ascii')
                    if file_name: upload['file_name']=file_name
                    call=lambda:self.request(platforms[0],target.endpoint('files'),upload)
                    status,body=await self._prepare(call)
                    if status>=300 or not isinstance(body,dict) or not body.get('file_info'):
                        code=body.get('code','') if isinstance(body,dict) else ''
                        category=classify(code,status) if code or status>=300 else 'media'
                        return failure('failed','upload',category,code)
                    payload={'msg_type':7,'media':{'file_info':body['file_info']},**({'content':text} if text else {})}
                reference=reply_reference(chain)
                if reference: payload['message_reference']={'message_id':reference}
                await check_delivery_policy()
                if permit:
                    if self.clock()>=permit.expires: return failure('skipped','credential','expired')
                    permit.used+=1;seq=permit.used
                    payload['msg_id' if target.message_id else 'event_id']=target.message_id or target.event_id
                    payload['msg_seq']=seq
                stage='message'
                pending=failure('unknown',stage,'in_flight',seq=seq)
                pending.attempt_id=attempt
                self.record(target,pending)  # before handing bytes to an external service
                budget=_delivery_budget.get()
                # No post-send budget check: a known accepted receipt must
                # survive crossing the deadline. Timeout after dispatch is
                # unknown and consumes this credential; it never triggers retry.
                dispatch={'started':False}
                binding=_message_dispatch.set(dispatch)
                try:
                    message_timeout=asyncio.timeout_at(budget.expires if budget else None)
                    async with message_timeout:
                        check_delivery_budget()
                        # Custom transports are conservatively in-flight on
                        # entry. request_once refines this at the HTTP boundary,
                        # so cancellation during authentication is still unsent.
                        dispatch['started']=True
                        status,body=await self.request(platforms[0],endpoint,payload)
                finally:
                    message_started=dispatch['started']
                    _message_dispatch.reset(binding)
                code=body.get('code','') if isinstance(body,dict) else ''
                if status<300 and isinstance(body,dict) and body.get('id') and not code:
                    result=DeliveryResult('accepted',message_id=str(body['id']),seq=seq,
                        ref_idx=str((body.get('ext_info') or {}).get('ref_idx','')))
                    result.attempt_id=attempt
                    if upload and self.retain_media:
                        try:
                            result.media=self.retain_media(target,result,upload,origin) or {}
                            result.persistence['media']='saved'
                        except asyncio.CancelledError:
                            result.persistence['media']='cancelled'
                            raise DeliveryCancelled(result) from None
                        except Exception:
                            result.persistence['media']='failed'
                    return result
                if permit and not (status<500 and classify(code,status)=='media'): permit.closed=True
                return failure('unknown' if status>=500 or (status<300 and not code) else 'failed',
                               stage,classify(code,status),code,seq)
            except DeliveryCancelled:
                raise
            except BudgetExceeded as error:
                budget=_delivery_budget.get()
                expired=isinstance(error,DeliveryDeadline) or bool(budget and time.monotonic()>=budget.expires)
                in_flight=message_started and not isinstance(error,DeliveryNotStarted)
                if permit and in_flight: permit.closed=True
                return failure('unknown' if in_flight else 'skipped' if expired else 'failed',stage,
                               'deadline' if expired else 'media',seq=seq)
            except asyncio.CancelledError:
                if permit and message_started: permit.closed=True
                raise DeliveryCancelled(failure('unknown' if message_started else 'skipped',stage,'cancelled',seq=seq)) from None
            except Exception as error:
                if permit and message_started: permit.closed=True
                budget=_delivery_budget.get()
                if isinstance(error,TimeoutError) and ((message_timeout and message_timeout.expired()) or (budget and time.monotonic()>=budget.expires)):
                    return failure('unknown' if message_started else 'skipped',stage,'deadline',seq=seq)
                return failure('unknown' if message_started else 'failed',stage,
                               'network' if isinstance(error,(TimeoutError,OSError)) or message_started else 'media',seq=seq)
