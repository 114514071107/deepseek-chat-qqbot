"""Trusted conversation names only; never cross-scene identity associations."""
import json,os,tempfile,re
from pathlib import Path

def observe(event,scope):
 raw=getattr(getattr(event,'message_obj',None),'raw_message',None)
 data=raw if isinstance(raw,dict) else getattr(raw,'raw_data',None)
 if not isinstance(data,dict) or str(data.get('id',data.get('message_id',''))) != scope.message_id:return None
 a=data.get('author',{})
 field='user_openid' if scope.private else 'member_openid'
 if scope.platform=='qq_official' and (a.get(field)!=scope.sender or not scope.private and data.get('group_openid')!=scope.group):return None
 name=a.get('username') if scope.private else data.get('group_name')
 if not isinstance(name,str):name=''
 name=re.sub(r'[\x00-\x1f\x7f]','',name).strip()[:128]
 return dict(platform=scope.platform,instance=scope.instance,bot=scope.bot,kind='private' if scope.private else 'group',address=scope.sender if scope.private else scope.group,name=name,at=scope.received_at)

def record_profile(event,scope,directory):
 if event.get_extra('_dsh_profile_observed'):return
 row=observe(event,scope)
 if row is None:return
 file=Path(directory)/'conversation_profiles_v1.json'
 store=json.loads(file.read_text(encoding='utf-8-sig')) if file.exists() else dict(version=1,sources={})
 if store.get('version')!=1 or not isinstance(store.get('sources'),dict):raise ValueError('unsupported conversation profiles')
 old=store['sources'].get(scope.conversation_key,{})
 if not row['name']:row['name']=old.get('name','')
 store['sources'][scope.conversation_key]=row
 fd,tmp=tempfile.mkstemp(prefix='.conversation-',dir=file.parent)
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as out:json.dump(store,out,ensure_ascii=False);out.flush();os.fsync(out.fileno())
  os.replace(tmp,file)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 event.set_extra('_dsh_profile_observed',True)
