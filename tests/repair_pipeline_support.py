"""Load real plugin methods without registration, constructors or production data."""
import ast
import copy
import asyncio
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid
import random
from types import SimpleNamespace

PLUGIN=Path(__file__).resolve().parents[1]/'plugin/astrbot_plugin_dsh_soul'
sys.path.insert(0,str(PLUGIN))
from chat_style import CHAT_STYLE, format_qq_text, preserve_literal_message, split_chat_actions, preserve_sticker_literal
from tool_permissions import trusted_plugin_tool
from session_scope import Scope, Target, bind_scope
from qq_delivery import QQDelivery, DeliveryResult, failure
from reply_completion import ReplyPlan, owned
from task_runtime import Runtime
from batch_input import merge_request
from resource_budget import Resources, BudgetProvider, BudgetExceeded, payload_size
from context_window import build_window, fingerprint, evidence_rows


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
    helpers=('_person_key','_reset_request','_close_request','_feedback','_close_feedback','_settle_feedback','_set_reply_plan','_scope','_source','_private','_owner','_perm','_group_append',
             '_finish_reply','_complete_reply','_record_assistant_turn','_record_user_turn','_synthesize_voice',
             '_drip_interval','_persist_framework_reply','_text_fallback','_record_delivery_result','_write_media','_retain_sent_media','_thread','_budget','_context_rows')
    cls.body=[n for n in cls.body if getattr(n,'name','') in names+helpers]
    for fn in cls.body:
        fn.decorator_list=[d for d in fn.decorator_list if guarded and isinstance(d,ast.Name) and d.id=='managed']
    globals_to_keep={'_cap_bubbles','_bubbles_napcat','_split_bubbles','_llm_text','_qq_plain'}
    fns=[n for n in tree.body if getattr(n,'name','') in globals_to_keep]
    def save(path,value): Path(path).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    def archive(uid,entry):
        with (root/'archive.jsonl').open('a',encoding='utf-8') as out:
            out.write(json.dumps(entry,ensure_ascii=False)+'\n')
    ns=dict(AstrMessageEvent=object, re=re,os=os,time=time,asyncio=asyncio,NL='\n',Plain=Plain,random=random,uuid=uuid,copy=copy,
        QQDelivery=QQDelivery,DeliveryResult=DeliveryResult,failure=failure,ReplyPlan=ReplyPlan,owned=owned,json=json,merge_request=merge_request,
        Resources=Resources,BudgetProvider=BudgetProvider,BudgetExceeded=BudgetExceeded,payload_size=payload_size,build_window=build_window,fingerprint=fingerprint,evidence_rows=evidence_rows,
        MessageChain=lambda **kw:SimpleNamespace(**kw),Record=lambda **kw:SimpleNamespace(type='Record',**kw),
        BUBBLE_CAP=2,BATCH_WAIT=0,MASTER_OPENID='owner',DATA=str(root),
        CHAT_STYLE=CHAT_STYLE,format_qq_text=format_qq_text,preserve_literal_message=preserve_literal_message,split_chat_actions=split_chat_actions,preserve_sticker_literal=preserve_sticker_literal,
        Scope=Scope,Target=Target,bind_scope=bind_scope,current_token=__import__('task_runtime').current_token,work_context=__import__('task_runtime').work_context,managed=__import__('task_runtime').managed,check_current=__import__('task_runtime').check_current,
        background_work=__import__('task_runtime').background_work,
        current_budget_job=__import__('task_runtime').current_budget_job,
        trusted_plugin_tool=trusted_plugin_tool,CHATTER_DISCIPLINE='',TOOL_GUIDE_LINES=[],PLATFORM_LINE='',
        _save=save,_load=lambda *a:{},_jf=lambda uid,name:str(root/(name+'.json')),read_text=__import__('state_store').read_text,
        _archive_append=archive,_read_notes=lambda uid:[],_read_memes=lambda *args:[],
        _meme_catalog_text=lambda:'',_now_period_line=lambda:'fixture',_user_perm=lambda *a:True,
        EMOTION_ALIAS={},_pick_sticker=lambda query:None)
    exec(compile(ast.fix_missing_locations(ast.Module(body=fns+[cls],type_ignores=[])),str(PLUGIN/'main.py'),'exec'),ns)
    obj=ns['DshSoul']()
    obj.resources=Resources({})
    obj.runtime=Runtime(lambda *args:True)
    for name in ('h','umo','interrupt','interrupted_note','run_active','pending_sticker','last_sticker',
                 'last_reply','pending_reply','pending_drip','turn_count','extract_at','batch_wait',
                 'tool_round','last_react','drip_active'):
        setattr(obj,name,{})
    obj.scopes={}; obj.groups={}; obj.scopes_path=str(root/'scopes.json'); obj.group_path=str(root/'groups.json')
    obj.h_path=str(root/'history.json'); obj.u_path=str(root/'umo.json')
    obj._h=lambda uid:obj.h.setdefault(uid,[])
    obj._th=lambda uid:[]
    obj._bump_turns=lambda *args:None
    def error(tag,exc): raise AssertionError(f'{tag}: {exc}')
    obj._err=error
    return obj,ns
