"""Explicit, stopped-instance cleanup. Never imported or applied on bot startup.

Plan reads only metadata/JSON and hashes. Backups must be outside the business
root and protected by the operator. Raw chat/archives/points/media are untouched.
"""
import argparse,hashlib,json,os,shutil,tempfile,time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'plugin/astrbot_plugin_dsh_soul'))
from session_scope import Scope

def sha(p):
 digest=hashlib.sha256()
 with p.open('rb') as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
 return digest.hexdigest()
def read(p,default):return json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else default

def plan(root):
 root=Path(root).resolve();scopes=read(root/'scopes_v2.json',{});private=set();group=set();member=set();actor=set()
 for uid,s in scopes.items():
  try:
   v=Scope(**s)
   if not all((v.platform,v.instance,v.bot,v.sender)) or (not v.private and not v.group):continue
  except (TypeError,ValueError):continue
  if v.private:private.add(v.memory_key)
  else:group.add(v.group_key);member.add(v.memory_key);actor.add(uid)
 # A shared legacy file cannot be credited to private just because a private
 # source also exists. Ambiguous files leave normal reads, never copied to group.
 marker=read(root/'conversation_storage_v1.json',{}) or {}
 cleaned=set(marker.get('cleaned_ambiguous_private',[])) if marker.get('version')==1 else set()
 safe=(private-member)|(private&cleaned)|group;actions=[]
 def add(p,reason,replacement=None):
  if p.is_symlink() or not p.resolve().is_relative_to(root):raise ValueError('unsafe file')
  row=dict(relative=p.relative_to(root).as_posix(),sha256=sha(p),size=p.stat().st_size,reason=reason)
  if replacement is not None:row['replacement']=replacement
  actions.append(row)
 for folder in ('memories','profiles','memes'):
  d=root/folder
  if d.exists():
   for p in d.glob('*.md'):
    if p.stem not in safe:add(p,'confirmed_group_member' if p.stem in member or p.stem in actor else 'mixed_or_unattributed')
 for p in root.glob('session_*.json'):
  if p.stem[len('session_'):] not in safe:add(p,'retired_actor_or_unattributed_summary')
 for name in ('thoughts_v2.json','thoughts_all.json'):
  p=root/name
  if p.exists():
   values=read(p,{})
   kept={k:v for k,v in values.items() if k in safe}
   if kept!=values:add(p,'remove_retired_actor_thought_index',kept)
 for name in ('console_people_v1.json','user_directory_v1.json','workbench_profiles_v1.json','union_rollout_v1.json','union_observations_v1.json','union_canary_v1.json','memes.md'):
  p=root/name
  if p.exists():add(p,'retired_identity_or_unscoped_shared_material')
 return dict(version=1,root=str(root),actions=sorted(actions,key=lambda x:x['relative']),private_keys=len(private),group_keys=len(group),ambiguous_keys=len(private&member),cleaned_ambiguous_private=sorted(private&member),storage_marker_before=read(root/'conversation_storage_v1.json',None),raw_chat_action_count=0)

def atomic(p,value):
 p.parent.mkdir(parents=True,exist_ok=True);fd,name=tempfile.mkstemp(prefix='.conversation-cleanup-',dir=p.parent)
 try:
  with os.fdopen(fd,'wb') as f:f.write(json.dumps(value,ensure_ascii=False,indent=2).encode());f.flush();os.fsync(f.fileno())
  os.replace(name,p)
 finally:
  if os.path.exists(name):os.unlink(name)

def apply_plan(root,backup,proposal):
 root=Path(root).resolve();backup=Path(backup).resolve()
 if backup.is_relative_to(root) or root.is_relative_to(backup):raise ValueError('backup must be disjoint from business root')
 if proposal.get('version')!=1 or proposal.get('root')!=str(root):raise ValueError('wrong root/plan')
 live=read(root/'admin_v2/live.json',{})
 if not live.get('stopped') and time.time()-live.get('at',0)<10:raise ValueError('instance must be stopped; active heartbeat')
 for row in proposal['actions']:
  p=root/row['relative']
  if not p.resolve().is_relative_to(root) or p.is_symlink() or sha(p)!=row['sha256']:raise ValueError('plan drift/unsafe source')
 if read(root/'conversation_storage_v1.json',None)!=proposal.get('storage_marker_before'):raise ValueError('storage marker drift')
 marker_target={'version':1,'cleaned_ambiguous_private':proposal.get('cleaned_ambiguous_private',[])}
 if not proposal['actions'] and (not proposal.get('cleaned_ambiguous_private') or proposal.get('storage_marker_before')==marker_target):return dict(applied=0)
 backup.mkdir(parents=True,exist_ok=True)
 # Refuse to overwrite an earlier recovery set. Interrupted operations resume
 # by planning remaining files into a NEW backup, never replacing originals.
 manifest=backup/'manifest.json'
 if manifest.exists():raise ValueError('backup already used; preserve recovery set')
 for row in proposal['actions']:
  p=root/row['relative'];dest=backup/'original'/row['relative'];dest.parent.mkdir(parents=True,exist_ok=True)
  with p.open('rb') as source,dest.open('xb') as f:
   shutil.copyfileobj(source,f);f.flush();os.fsync(f.fileno())
  if sha(dest)!=row['sha256'] or sha(p)!=row['sha256']:raise ValueError('backup drift')
 atomic(manifest,{**proposal,'status':'backed_up_before_cleanup'})
 for row in proposal['actions']:
  p=root/row['relative']
  if sha(p)!=row['sha256']:raise ValueError('source changed; recovery backup preserved')
  if 'replacement' in row:atomic(p,row['replacement'])
  else:p.unlink()
 atomic(root/'conversation_storage_v1.json',{'version':1,'cleaned_ambiguous_private':proposal.get('cleaned_ambiguous_private',[])})
 atomic(manifest,{**proposal,'status':'applied'})
 return dict(applied=len(proposal['actions']))

def restore(backup,expected_root=None):
 backup=Path(backup).resolve();m=read(backup/'manifest.json',{});root=Path(m['root']).resolve()
 if expected_root is not None and root!=Path(expected_root).resolve():raise ValueError('wrong recovery instance')
 if backup.is_relative_to(root) or root.is_relative_to(backup):raise ValueError('invalid backup boundary')
 live=read(root/'admin_v2/live.json',{})
 if not live.get('stopped') and time.time()-live.get('at',0)<10:raise ValueError('stop instance before restore')
 marker=root/'conversation_storage_v1.json'
 if read(marker,None)!={'version':1,'cleaned_ambiguous_private':m.get('cleaned_ambiguous_private',[])}:raise ValueError('storage marker changed; inspect before restore')
 for row in m['actions']:
  p=root/row['relative'];src=backup/'original'/row['relative']
  if not p.resolve().is_relative_to(root) or sha(src)!=row['sha256']:raise ValueError('recovery path/hash mismatch')
  if p.exists():
   if 'replacement' not in row or read(p,None)!=row['replacement']:raise ValueError('new business data exists; no automatic overwrite')
 # Revoke clean-memory permission BEFORE any old ambiguous file reappears.
 if m.get('storage_marker_before') is None:marker.unlink()
 else:atomic(marker,m['storage_marker_before'])
 for row in m['actions']:
  p=root/row['relative'];p.parent.mkdir(parents=True,exist_ok=True)
  fd,tmp=tempfile.mkstemp(prefix='.conversation-restore-',dir=p.parent)
  try:
   with os.fdopen(fd,'wb') as f,(backup/'original'/row['relative']).open('rb') as source:
    shutil.copyfileobj(source,f);f.flush();os.fsync(f.fileno())
   os.replace(tmp,p)
  finally:
   if os.path.exists(tmp):os.unlink(tmp)
 return dict(restored=len(m['actions']))

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--plan');ap.add_argument('--apply',action='store_true');ap.add_argument('--backup');ap.add_argument('--restore',action='store_true');a=ap.parse_args()
 if a.restore:result=restore(a.backup,a.root)
 elif a.apply:
  if not a.plan or not a.backup:ap.error('Apply requires reviewed --plan and external --backup')
  result=apply_plan(a.root,a.backup,read(Path(a.plan),{}))
 else:
  result=plan(a.root)
  if a.plan:atomic(Path(a.plan),result)
 print(json.dumps({k:v for k,v in result.items() if k not in ('actions','root')},ensure_ascii=False))
