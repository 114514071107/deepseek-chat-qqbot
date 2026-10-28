"""Bounded process-local ingress reservation; never an exactly-once ledger.

No ID: allow without dedup. Fail/cancel/unknown: retain, never retry implicitly.
Capacity: reject new identified events rather than evict protected reservations.
Restart/reload loses this window. No business files or delivery outcomes rewritten.
"""
import hashlib
import json
import threading
import time
from session_scope import bind_scope


class Admissions:
    def __init__(self, capacity=8192, retention=86400, clock=time.monotonic):
        self.capacity, self.retention, self.clock = capacity, retention, clock
        self.rows = {}
        self.lock = threading.Lock()

    def reserve(self, key):
        if key is None:return 'unidentified'
        with self.lock:
            now=self.clock()
            self.rows={k:v for k,v in self.rows.items() if v[0]=='processing' or v[1]>now}
            if key in self.rows:return 'duplicate'
            if len(self.rows)>=self.capacity:return 'capacity'
            self.rows[key]=('processing',now+self.retention)
            return 'reserved'

    def retain(self, key, state):
        if key is None:return
        with self.lock:
            if key in self.rows:self.rows[key]=(state,self.clock()+self.retention)


def reserve(owner, event):
    scope=bind_scope(event)
    http=getattr(getattr(getattr(event,'bot',None),'api',None),'_http',None)
    app=getattr(getattr(http,'_token',None),'app_id','')
    # Scope comes from the adapter; app only from authenticated SDK, not raw JSON.
    key=hashlib.sha256(json.dumps([scope.platform,scope.instance,scope.bot,str(app or ''),
        scope.private,scope.group,scope.sender,scope.message_id],ensure_ascii=False).encode()).hexdigest() if scope.message_id else None
    # Event hooks run on this instance's event loop; reservation itself also
    # uses a thread lock and has no await between lookup and insert.
    if not hasattr(owner,'event_admissions'):owner.event_admissions=Admissions()
    result=owner.event_admissions.reserve(key)
    event.set_extra('_dsh_event_key',key)
    event.set_extra('_dsh_event_admission','reserved' if result in ('reserved','unidentified') else result)
    if result in ('duplicate','capacity'):
        event.set_extra('_dsh_admitted',False)
        event.stop_event()
        return False
    return True


def retain(owner,event,state):
    registry=getattr(owner,'event_admissions',None)
    if registry:registry.retain(event.get_extra('_dsh_event_key'),state)
