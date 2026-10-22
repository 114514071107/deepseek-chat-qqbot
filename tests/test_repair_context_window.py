import asyncio
import importlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from repair_pipeline_support import load_pipeline
from test_repair_session_scope import ScopeEvent


class ContextRegression(unittest.IsolatedAsyncioTestCase):
    async def test_history_is_role_messages_not_repeated_current_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj, ns = load_pipeline(tmp); Path(tmp,'persona.md').write_text('fixture', encoding='utf-8')
            event = ScopeEvent(group='g1'); scope = obj._scope(event)
            obj.h[scope.key] = [dict(role='user', text='previous request', ts=1, source=dict(scope.source(),message_id='old')),
                dict(role='assistant', text='accepted answer', ts=2, delivery={'status':'accepted'}, source=scope.source()),
                dict(role='assistant', text='UNSENT', ts=3, delivery={'status':'unknown'}, source=scope.source()),
                dict(role='user', text='new question', ts=4, source=scope.source())]
            event.set_extra('_dsh_current_ids', [scope.message_id])
            req = SimpleNamespace(prompt='new question', contexts=[],system_prompt='',func_tool=None)
            await obj.inject(event,req)
            self.assertNotIn('previous request',req.prompt)
            self.assertIn('previous request',str(req.contexts))
            self.assertIn('accepted answer',str(req.contexts))
            self.assertNotIn('UNSENT',str(req.contexts))
            self.assertNotIn('new question',str(req.contexts))
            self.assertIn('当前群',req.system_prompt)

    async def test_extractive_summary_has_provenance_budget_and_no_new_facts(self):
        try: api=importlib.import_module('context_window')
        except ImportError: self.fail('no verifiable context compression exists')
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp);scope=obj._scope(ScopeEvent())
            rows=[]
            for n in range(100):
                text=('目标：做一个离线工具。确认：不得联网。待办：补测试。约定：保留原档。' if n==0 else f'原话{n} '+ '材料'*120)
                rows.append(dict(id=str(n), role='user', text=text, ts=n, source=dict(scope.source(),message_id=str(n))))
            window=api.build_window(rows,[],scope,4000)
            self.assertLessEqual(len(json.dumps(window['messages'],ensure_ascii=False)),7000)
            self.assertIn('目标：做一个离线工具',str(window))
            for entry in window['summary']['entries']:
                self.assertIn(entry['text'],rows[int(entry['id'])]['text'])
                self.assertEqual(entry['sender'],scope.sender)
            self.assertEqual(window['summary']['source_version'],api.fingerprint(rows))
            self.assertNotEqual(api.fingerprint(rows),api.fingerprint(rows[:-1]))
            foreign=dict(rows[0],source=dict(scope.source(),group='other',private=False))
            self.assertNotIn('目标：',str(api.build_window([foreign],[],scope,4000)['messages']))

    async def test_legacy_summary_never_reappears_after_delete_or_new_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp); Path(tmp,'persona.md').write_text('fixture',encoding='utf-8')
            ns['_load']=lambda *a:{'summary':'DELETED-OLD-SECRET','mood':'STALE-STATE'}
            req=SimpleNamespace(prompt='hello',contexts=[],system_prompt='',func_tool=None)
            await obj.inject(ScopeEvent(),req)
            self.assertNotIn('DELETED-OLD-SECRET',str(vars(req)))
            self.assertNotIn('STALE-STATE',str(vars(req)))

    async def test_summary_snapshot_race_cannot_overwrite_newer_turn(self):
        from state_store import read_json,write_json
        from task_runtime import work_context
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp,names=('_refresh_summary',),guarded=True)
            event=ScopeEvent();scope=obj._scope(event);token=obj.runtime.begin(scope.key)
            row=dict(id='old',role='user',text='old goal',source=scope.source(),ts=1)
            obj.h[scope.key]=[row]
            ns.update(_load=read_json,_save=write_json)
            started=asyncio.Event();release=asyncio.Event();thread=obj._thread
            async def blocked(fn,*args,**kw):
                started.set();await release.wait();return await thread(fn,*args,**kw)
            obj._thread=blocked
            async def refresh():
                with work_context(token):await obj._refresh_summary(scope.key)
            task=asyncio.create_task(refresh());await started.wait()
            obj.h[scope.key].append(dict(row,id='new',text='new confirmed goal',ts=2))
            Path(tmp,'session.json').write_text('{"context":{"version":777}}')
            release.set();await task
            self.assertEqual(read_json(Path(tmp,'session.json'),{})['context']['version'],777)

    async def test_compaction_survives_rolling_window_without_reviving_cleared_history(self):
        from context_window import build_window
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp);scope=obj._scope(ScopeEvent())
            rows=[dict(id=str(n),role='user',text='目标：必须离线' if n==0 else f'content{n}',source=dict(scope.source(),message_id=str(n))) for n in range(30)]
            first=build_window(rows,[],scope,4000)
            next_rows=rows[20:]+[dict(rows[0],id='next',text='待办：完成测试')]
            second=build_window(next_rows,[],scope,4000,first['summary'])
            self.assertIn('必须离线',str(second['messages']))
            self.assertNotIn('必须离线',str(build_window([],[],scope,4000,first['summary'])['messages']))

    async def test_background_requests_receive_actual_recent_context_and_group_identity(self):
        from task_runtime import work_context
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp,names=('_chat',),guarded=True);scope=obj._scope(ScopeEvent(group='g1'))
            obj.h[scope.key]=[dict(id='h',role='user',text='RECENT-TOPIC',source=scope.source())]
            seen=[]
            class Provider:
                async def text_chat(self,**kw):seen.append(kw);return None
            obj.context=SimpleNamespace(get_using_provider=lambda:Provider())
            token=obj.runtime.token(scope.key,request='')
            with work_context(token):
                for tag in ('desire','proactive','revive'):await obj._chat(tag,prompt='fixture')
            self.assertEqual(len(seen),3)
            for call in seen:
                self.assertIn('RECENT-TOPIC',str(call['contexts']))
                self.assertIn('当前群',call['system_prompt'])

    async def test_private_archive_scan_does_not_block_other_conversations(self):
        import threading
        from test_repair_permissions import load_methods,Event
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_methods();started=threading.Event();release=threading.Event()
            def archive(uid,**kw):started.set();release.wait(1);return []
            ns.update(_archive_read=archive,_read_notes=lambda uid:[],_read_memes=lambda uid:[])
            task=asyncio.create_task(obj.recall(Event('friend'),'keyword'))
            # If archive is still a synchronous call, it blocks until its timeout
            # and the heartbeat observes the completed task, not an active scan.
            await asyncio.sleep(.02)
            pending=not task.done();release.set();await task
            self.assertTrue(pending,'archive scan blocked the event loop')

    async def test_failed_inject_cannot_continue_with_unfiltered_framework_history(self):
        from resource_budget import BudgetExceeded
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp);Path(tmp,'persona.md').write_text('fixture',encoding='utf-8')
            event=ScopeEvent();event.stop_event=lambda:event.set_extra('stopped',True)
            async def overloaded(*a,**kw):raise BudgetExceeded('queue full')
            obj._thread=overloaded;obj._err=lambda *a:None
            req=SimpleNamespace(prompt='question',contexts=[{'role':'user','content':'UNFILTERED-OLD'}],system_prompt='',func_tool=None)
            await obj.inject(event,req)
            self.assertTrue(event.get_extra('stopped'), 'failed request hook continued to model')
            self.assertNotIn('UNFILTERED-OLD',str(req.contexts))

    async def test_archive_reader_returns_bounded_recent_slice_and_reports_omission(self):
        import ast
        from repair_pipeline_support import PLUGIN
        from state_store import StateError,read_text
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp,'archive.jsonl')
            archive.write_text(''.join(json.dumps(dict(uid='fixture',ts=n,text='row'+str(n)))+'\n' for n in range(20)))
            tree=ast.parse((PLUGIN/'main.py').read_text(encoding='utf-8'))
            fn=next(n for n in tree.body if getattr(n,'name','')=='_archive_read')
            ns=dict(ARCHIVE=str(archive),json=json,StateError=StateError,read_text=read_text)
            exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'<actual archive reader>','exec'),ns)
            try:rows=ns['_archive_read']('fixture',max_bytes=512,max_rows=3)
            except TypeError:self.fail('archive recall still materializes an unlimited entire archive')
            self.assertEqual([row['text'] for row in rows],['row17','row18','row19'])
            self.assertTrue(rows.truncated)

    async def test_periodic_background_turns_get_fresh_budgets_on_same_loop_task(self):
        from resource_budget import Resources
        from task_runtime import work_context,managed
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp,names=('_chat',),guarded=True);scope=obj._scope(ScopeEvent())
            obj.resources=Resources({'deadline':.2,'model_calls':1})
            calls=[]
            class Provider:
                async def text_chat(self,**kw):calls.append(kw);return None
            obj.context=SimpleNamespace(get_using_provider=lambda:Provider())
            @managed
            async def periodic(self,uid):return await self._chat('desire',prompt='fixture')
            with work_context(obj.runtime.token()):
                await periodic(obj,scope.key)
                await asyncio.sleep(.21)
                await periodic(obj,scope.key)
            self.assertEqual(len(calls),2)


if __name__=='__main__':unittest.main()
