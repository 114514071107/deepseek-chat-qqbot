"""Bounded, expiring management-identity canary. No gateway or model calls."""
import hashlib, hmac, json, os, re, tempfile, time
from pathlib import Path
FILE = 'union_rollout_v1.json'
OBSERVATIONS = 'union_rollout_observations_v1.json'
def fingerprint(source, app):
    fields=[source['platform'],source['instance'],source['bot'],'private' if source['private'] else 'group',source['group'],source['sender'],app]
    return hashlib.sha256(json.dumps(fields,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def read_policy(root):
    try:
        p=Path(root)/FILE
        if p.stat().st_size>16384:return None
        v=json.loads(p.read_text(encoding='utf-8-sig'));now=time.time()
        if (not isinstance(v,dict) or v.get('version')!=1 or v.get('mode') not in ('observe','apply')
                or type(v.get('expires_at')) not in (int,float) or not now<v['expires_at']<=now+86400
                or not isinstance(v.get('fingerprints'),list) or not 1<=len(v['fingerprints'])<=32
                or any(not isinstance(x,str) or not re.fullmatch(r'[a-f0-9]{64}',x) for x in v['fingerprints'])
                or not isinstance(v.get('comparison_key'),str) or not re.fullmatch(r'[a-f0-9]{64}',v['comparison_key'])):return None
        return v
    except (OSError,ValueError,TypeError):return None
def policy_for(event,scope,root):
    if scope.platform!='qq_official':return None
    sdk=getattr(getattr(getattr(getattr(event,'bot',None),'api',None),'_http',None),'_token',None)
    app=getattr(sdk,'app_id',None)
    if isinstance(app,bool) or not isinstance(app,(str,int)) or not str(app):return None
    v=read_policy(root)
    return v if v and fingerprint(scope.source(),str(app)) in v['fingerprints'] else None
def observe_canary(event,scope,root,policy):
    from union_user_profiles import observe
    row=observe(event,scope)
    identity=(row or {}).get('identity') or {}
    valid=identity.get('namespace')=='qq_union_openid'
    raw=getattr(getattr(event,'message_obj',None),'raw_message',None)
    raw=raw if isinstance(raw,dict) else getattr(raw,'raw_data',None)
    if isinstance(raw,dict) and raw.get('op')==0 and isinstance(raw.get('d'),dict):
        raw=raw['d']
    author=raw.get('author') if isinstance(raw,dict) else None
    candidate=author.get('union_openid') if isinstance(author,dict) else None
    digest=lambda value:hmac.new(bytes.fromhex(policy['comparison_key']),value.encode(),hashlib.sha256).hexdigest()
    item=dict(at=time.time(),scope_key=scope.key,private=scope.private,accepted=row is not None,union_valid=valid,
              union_present=isinstance(author,dict) and 'union_openid' in author,
              union_nonempty=isinstance(candidate,str) and bool(candidate),
              app_digest=digest((row or {}).get('app','')),union_digest=digest(identity['value']) if valid else None)
    p=Path(root)/OBSERVATIONS
    try:
        if p.exists() and p.stat().st_size>262144:return
        v=json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else dict(version=1,rows=[])
        if v.get('version')!=1 or not isinstance(v.get('rows'),list):return
        v['rows']=(v['rows']+[item])[-64:]
        fd,name=tempfile.mkstemp(prefix='.union-canary-',dir=p.parent)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as out:json.dump(v,out,ensure_ascii=False)
            os.replace(name,p)
        finally:
            if os.path.exists(name):os.unlink(name)
    except (OSError,ValueError,TypeError):return
