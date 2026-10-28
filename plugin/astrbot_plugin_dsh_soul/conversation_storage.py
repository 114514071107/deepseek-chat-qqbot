"""Legacy personal memory ambiguity is fail-closed until explicit cleanup."""
import json
from pathlib import Path
from session_scope import Scope

def memory_available(root,key):
 if not key.startswith('p2_'):return True
 root=Path(root)
 def read(name,default):
  p=root/name
  return json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else default
 collision=any(not s.get('private') and Scope(**s).memory_key==key for s in read('scopes_v2.json',{}).values())
 marker=read('conversation_storage_v1.json',{})
 return not collision or (marker.get('version')==1 and key in marker.get('cleaned_ambiguous_private',[]))

def prepare_new_memory(root,key):
    """Initialize new, empty private storage; never relabel an existing file."""
    if memory_available(root,key): return True
    root=Path(root)
    files=[root/folder/(key+'.md') for folder in ('memories','profiles','memes')]+[root/('session_'+key+'.json')]
    if any(p.exists() for p in files):return False
    for name in ('thoughts_v2.json','thoughts_all.json'):
        p=root/name
        if p.exists() and json.loads(p.read_text(encoding='utf-8-sig')).get(key):return False
    p=root/'conversation_storage_v1.json'
    data=json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else {'version':1,'cleaned_ambiguous_private':[]}
    if data.get('version')!=1:return False
    data['cleaned_ambiguous_private']=sorted(set(data.get('cleaned_ambiguous_private',[]))|{key})
    from state_store import write_json
    write_json(p,data)
    return True
