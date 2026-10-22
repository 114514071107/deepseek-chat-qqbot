"""Load real plugin methods without registration, constructors or production data."""
import ast
import asyncio
import json
import os
from pathlib import Path
import re
import sys
import time

PLUGIN=Path(__file__).resolve().parents[1]/'plugin/astrbot_plugin_dsh_soul'
sys.path.insert(0,str(PLUGIN))
from chat_style import CHAT_STYLE, format_qq_text, preserve_literal_message, split_chat_actions
from tool_permissions import trusted_plugin_tool
from session_scope import Scope, Target, bind_scope


class Plain:
    def __init__(self,text): self.text=text


class ResultChain:
    def __init__(self,text): self.chain=[Plain(text)]
    def get_plain_text(self): return ''.join(c.text for c in self.chain if isinstance(c,Plain))


def load_pipeline(root, names=('capture','_clear_text_result','_set_first_bubble_result','inject'), guarded=False):
    root=Path(root)
    tree=ast.parse((PLUGIN/'main.py').read_text(encoding='utf-8-sig'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DshSoul')
    cls.bases=[]; cls.decorator_list=[]
    helpers=('_person_key','_reset_request','_scope','_source','_private','_owner','_perm','_group_append')
    cls.body=[n for n in cls.body if getattr(n,'name','') in names+helpers]
    for fn in cls.body:
        fn.decorator_list=[d for d in fn.decorator_list if guarded and isinstance(d,ast.Name) and d.id=='managed']
    globals_to_keep={'_cap_bubbles','_bubbles_napcat','_split_bubbles','_llm_text','_qq_plain'}
    fns=[n for n in tree.body if getattr(n,'name','') in globals_to_keep]
    def save(path,value): Path(path).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    def archive(uid,entry):
        with (root/'archive.jsonl').open('a',encoding='utf-8') as out:
            out.write(json.dumps(entry,ensure_ascii=False)+'\n')
    ns=dict(AstrMessageEvent=object, re=re,os=os,time=time,asyncio=asyncio,NL='\n',Plain=Plain,
        BUBBLE_CAP=2,BATCH_WAIT=0,MASTER_OPENID='owner',DATA=str(root),
        CHAT_STYLE=CHAT_STYLE,format_qq_text=format_qq_text,preserve_literal_message=preserve_literal_message,split_chat_actions=split_chat_actions,
        Scope=Scope,Target=Target,bind_scope=bind_scope,work_context=__import__('task_runtime').work_context,managed=__import__('task_runtime').managed,check_current=__import__('task_runtime').check_current,
        trusted_plugin_tool=trusted_plugin_tool,CHATTER_DISCIPLINE='',TOOL_GUIDE_LINES=[],PLATFORM_LINE='',
        _save=save,_load=lambda *a:{},_jf=lambda uid,name:str(root/(name+'.json')),
        _archive_append=archive,_read_notes=lambda uid:[],_read_memes=lambda *args:[],
        _meme_catalog_text=lambda:'',_now_period_line=lambda:'fixture',_user_perm=lambda *a:True,
        EMOTION_ALIAS={},_pick_sticker=lambda query:None)
    exec(compile(ast.fix_missing_locations(ast.Module(body=fns+[cls],type_ignores=[])),str(PLUGIN/'main.py'),'exec'),ns)
    obj=ns['DshSoul']()
    for name in ('h','umo','interrupt','interrupted_note','run_active','pending_sticker','last_sticker',
                 'last_reply','pending_reply','pending_drip','turn_count','extract_at','batch_wait',
                 'tool_round','last_react'):
        setattr(obj,name,{})
    obj.scopes={}; obj.groups={}; obj.scopes_path=str(root/'scopes.json'); obj.group_path=str(root/'groups.json')
    obj.h_path=str(root/'history.json'); obj.u_path=str(root/'umo.json')
    obj._h=lambda uid:obj.h.setdefault(uid,[])
    obj._th=lambda uid:[]
    obj._bump_turns=lambda *args:None
    def error(tag,exc): raise AssertionError(f'{tag}: {exc}')
    obj._err=error
    return obj,ns
