"""Reproducible offline measurements; temporary synthetic archives and slow doubles.

Run from the development root with the existing Python, -B. No runtime import.
"""
import ast
import asyncio
import json
from pathlib import Path
import statistics
import subprocess
import tempfile
import time
from types import SimpleNamespace
from repair_pipeline_support import load_pipeline
from test_repair_session_scope import ScopeEvent
from state_store import read_text,read_json,write_json
from resource_budget import Resources,BudgetProvider
from context_window import build_window


async def scheduler(bounded):
    resources=Resources({});active={'foreground':0,'background':0};peak=dict(active);finished=[]
    start=time.perf_counter()
    class Provider:
        def __init__(self,lane):self.lane=lane
        async def text_chat(self,**kwargs):
            lane=self.lane;active[lane]+=1;peak[lane]=max(peak[lane],active[lane])
            await asyncio.sleep(.03);active[lane]-=1
            if lane=='foreground':finished.append((time.perf_counter()-start)*1000)
            return SimpleNamespace(completion_text='fixed offline response')
    async def call(lane,n):
        provider=Provider(lane)
        if bounded:provider=BudgetProvider(provider,resources,resources.budget(lane+str(n)),lane)
        await provider.text_chat(prompt='synthetic')
    await asyncio.gather(*[call('foreground',n) for n in range(5)],*[call('background',n) for n in range(6)])
    return dict(wall_ms=round((time.perf_counter()-start)*1000,2),peak=peak,
        foreground_median_ms=round(statistics.median(finished),2),foreground_max_ms=round(max(finished),2),
        queue_max_ms=round(max([r['seconds'] for r in resources.metrics if r['stage']=='queue'] or [0])*1000,2))


async def responsive(fn,threaded):
    done=False;gaps=[]
    async def heartbeat():
        previous=time.perf_counter()
        while not done:
            await asyncio.sleep(.001);now=time.perf_counter();gaps.append((now-previous)*1000);previous=now
    beat=asyncio.create_task(heartbeat());await asyncio.sleep(0)
    start=time.perf_counter()
    if threaded:
        resources=Resources({});rows=await resources.thread(fn);await resources.close()
    else:rows=fn()
    wall=(time.perf_counter()-start)*1000
    await asyncio.sleep(.005);done=True;await beat
    return dict(wall_ms=round(wall,2),heartbeat_max_gap_ms=round(max(gaps),2),matching_rows=len(rows))


async def main():
    baseline=subprocess.run(['git','show','HEAD:plugin/astrbot_plugin_dsh_soul/main.py'],check=True,stdout=subprocess.PIPE).stdout.decode('utf-8-sig')
    tree=ast.parse(baseline)
    with tempfile.TemporaryDirectory(prefix='dsh-w4-measure-') as tmp:
        root=Path(tmp);obj,ns=load_pipeline(root,names=('_refresh_summary',))
        scope=obj._scope(ScopeEvent('fictional-person','fictional-group'))
        history=[dict(id=str(n),role='user',text=('目标：制作离线报告。确认：不可联网。待办：补测试。约定：保留原档。' if n==0 else f'固定记录{n} '+ '固定材料'*90),
                      ts=n,source=dict(scope.source(),message_id='message-'+str(n))) for n in range(150)]
        obj.h[scope.key]=history
        compressed=build_window(history,[],scope,10000)
        raw=sum(len(row['text']) for row in history)
        old_excerpt=sum(len(row['text'][:120]) for row in history[-30:])
        old_class=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DshSoul')
        refresh=next(n for n in old_class.body if getattr(n,'name','')=='_refresh_summary');refresh.decorator_list=[]
        calls=[]
        async def model(*args,**kw):calls.append(kw);return SimpleNamespace(completion_text='[进展] 固定摘要\n[状态] 无额外判断')
        obj._chat=model
        exec(compile(ast.fix_missing_locations(ast.Module(body=[refresh],type_ignores=[])),'<baseline summary>','exec'),ns)
        await ns['_refresh_summary'](obj,scope.key);before=len(calls)
        await obj._refresh_summary(scope.key);after=len(calls)-before
        archive=root/'synthetic.jsonl'
        with archive.open('w',encoding='utf-8') as out:
            for n in range(20000):out.write(json.dumps(dict(uid='target' if n%2 else 'other',ts=n,text='固定材料'*80),ensure_ascii=False)+'\n')
        read=next(n for n in tree.body if getattr(n,'name','')=='_archive_read')
        read_ns=dict(read_text=read_text,ARCHIVE=str(archive),json=json,StateError=RuntimeError)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[read],type_ignores=[])),'<actual archive reader>','exec'),read_ns)
        current_tree=ast.parse((Path(__file__).resolve().parents[1]/'plugin/astrbot_plugin_dsh_soul/main.py').read_text(encoding='utf-8'))
        current_read=next(n for n in current_tree.body if getattr(n,'name','')=='_archive_read')
        current_ns=dict(read_ns)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[current_read],type_ignores=[])),'<bounded archive reader>','exec'),current_ns)
        sync=[];thread=[]
        for _ in range(3):
            sync.append(await responsive(lambda:read_ns['_archive_read']('target'),False))
            thread.append(await responsive(lambda:current_ns['_archive_read']('target'),True))
        report=dict(conditions=dict(fake_model_seconds=.03,foreground_sessions=5,background_tasks=6,
            archive_rows=20000,archive_bytes=archive.stat().st_size,archive_repeats=3,network_calls=0,
            python=__import__('sys').version.split()[0]),
            scheduler=dict(baseline=await scheduler(False),bounded=await scheduler(True)),
            archive=dict(baseline=sync,threaded=thread),
            context=dict(raw_source_chars=raw,old_last30_truncated_chars=old_excerpt,
                compressed_content_chars=compressed['context_chars'],compressed_json_chars=len(json.dumps(compressed['messages'],ensure_ascii=False)),
                old_goal_retained=False,new_goal_retained='不可联网' in str(compressed['messages']),
                summary_model_calls_before=before,summary_model_calls_after=after,
                token_count=None,actual_bill=None))
        print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':asyncio.run(main())
