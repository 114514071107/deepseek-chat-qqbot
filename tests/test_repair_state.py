import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from repair_pipeline_support import load_pipeline
from test_repair_session_scope import ScopeEvent


class StateRegression(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_denial_revokes_inheriting_requests_but_respects_explicit_override(self):
        from state_store import StateController,write_json
        from task_runtime import Runtime
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp,names=());a=obj._scope(ScopeEvent('a','g1'));b=obj._scope(ScopeEvent('a','g2'))
            obj.runtime=Runtime(lambda *a:True)
            write_json(Path(tmp)/'friends_all.json',{b.key:{'reply':True}})
            old_a=obj.runtime.begin(a.key);old_b=obj.runtime.begin(b.key)
            state=StateController(obj,tmp,clear_framework=lambda key:asyncio.sleep(0))
            await state.apply('user',{'uid':'a','key':'reply','value':False})
            self.assertFalse(obj.runtime.valid(old_a));self.assertTrue(obj.runtime.valid(old_b))
            await obj.runtime.stop()

    async def test_actual_chat_charge_interleaves_with_admin_grants_without_lost_updates(self):
        import ast,time
        from repair_pipeline_support import PLUGIN
        from state_store import StateController,read_json,write_json
        from task_runtime import Runtime
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp,names=());scope=obj._scope(ScopeEvent('a','g1'));obj.runtime=Runtime(lambda *a:True)
            file=Path(tmp)/'points_all.json'
            write_json(file,{scope.memory_key:{'balance':10,'last':time.strftime('%Y-%m-%d'),'spent':0}})
            tree=ast.parse((PLUGIN/'main.py').read_text(encoding='utf-8'));fn=next(n for n in tree.body if getattr(n,'name','')=='_points_charge')
            ns=dict(POINTS_FILE=str(file),time=time,_load=read_json,_save=write_json,_conf_val=lambda *a:30)
            exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'<actual chat charge>','exec'),ns)
            state=StateController(obj,tmp,clear_framework=lambda key:asyncio.sleep(0))
            await state.apply('points',{'uid':scope.key,'mode':'add','value':5})
            self.assertEqual(ns['_points_charge'](scope.memory_key),(True,False))
            await state.apply('points',{'uid':scope.key,'mode':'add','value':2})
            ns['_points_charge'](scope.memory_key)
            final=read_json(file,{})[scope.memory_key]
            self.assertEqual(final['balance'],15);self.assertEqual(final['spent'],2)
            await obj.runtime.stop()

    async def test_rolling_history_does_not_trigger_framework_session_cascade(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp,names=('_clear_framework_history',));scope=obj._scope(ScopeEvent())
            manager=SimpleNamespace(get_conversations=AsyncMock(return_value=[SimpleNamespace(cid='fixture-cid')]),
                                    delete_conversation=AsyncMock(),delete_conversations_by_user_id=AsyncMock())
            obj.context=SimpleNamespace(conversation_manager=manager)
            await obj._clear_framework_history(scope.key)
            manager.delete_conversations_by_user_id.assert_not_awaited()
            manager.delete_conversation.assert_awaited_once_with(scope.target.umo.rsplit(':',1)[0]+':'+scope.key,'fixture-cid')

    async def test_existing_points_limit_is_not_reset_when_scope_keys_are_introduced(self):
        from state_store import StateController,write_json,read_json,person_ledger_key
        from task_runtime import Runtime
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp,names=());scope=obj._scope(ScopeEvent('a','g1'))
            obj.runtime=Runtime(lambda *a:True)
            file=Path(tmp)/'points_all.json';write_json(file,{'a':{'balance':0,'spent':17}})
            self.assertEqual(person_ledger_key(scope,read_json(file,{})),'a')
            state=StateController(obj,tmp,clear_framework=lambda key:asyncio.sleep(0))
            await state.apply('points',{'uid':scope.key,'mode':'add','value':3})
            ledger=read_json(file,{})
            self.assertEqual(ledger['a']['balance'],3);self.assertNotIn(scope.memory_key,ledger)
            await obj.runtime.stop()

    async def test_archive_corruption_is_not_reported_as_no_history(self):
        import ast
        from repair_pipeline_support import PLUGIN
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp)/'history_archive_v2.jsonl';archive.write_text('{broken\n')
            tree=ast.parse((PLUGIN/'main.py').read_text(encoding='utf-8'))
            fn=next(n for n in tree.body if getattr(n,'name','')=='_archive_read')
            from state_store import StateError,read_text
            ns=dict(ARCHIVE=str(archive),json=json,StateError=StateError,read_text=read_text)
            exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'<real archive reader>','exec'),ns)
            with self.assertRaises(StateError):ns['_archive_read']('fixture')

    async def test_media_referenced_by_another_scope_is_retained(self):
        from state_store import StateController,write_json
        from task_runtime import Runtime
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp,names=());scope=obj._scope(ScopeEvent())
            obj.runtime=Runtime(lambda *a:True)
            file=Path(tmp)/'media/inbox/shared.png';file.parent.mkdir(parents=True);file.write_bytes(b'fixture')
            write_json(Path(tmp)/'media_v2.json',{scope.key:['media/inbox/shared.png'],'another-source':['media/inbox/shared.png']})
            state=StateController(obj,tmp,clear_framework=lambda key:asyncio.sleep(0))
            result=await state.delete(scope.key,['media'])
            self.assertTrue(file.exists());self.assertFalse(result['ok'])
            self.assertEqual(result['layers']['media']['status'],'partial')
            await obj.runtime.stop()

    async def test_all_layers_delete_only_declared_scope_and_explicit_whole_backup(self):
        from state_store import StateController,write_json,LAYERS
        from task_runtime import Runtime
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);obj,_=load_pipeline(root,names=());scope=obj._scope(ScopeEvent());other=obj._scope(ScopeEvent('b'))
            obj.runtime=Runtime(lambda *a:True);obj.th={scope.key:[{'text':'fixture'}]};obj.t_path=str(root/'thoughts_v2.json')
            obj.h={scope.key:[{'text':'fixture'}],other.key:[{'text':'keep'}]};write_json(obj.h_path,obj.h);write_json(obj.t_path,obj.th)
            archive=root/'history_archive_v2.jsonl';archive.write_text(json.dumps({'uid':scope.key,'text':'fixture'})+'\n'+json.dumps({'uid':other.key,'text':'keep'})+'\n')
            for folder in ('memories','profiles','memes'):
                (root/folder).mkdir();(root/folder/(scope.key+'.md')).write_text('fixture');(root/folder/(other.key+'.md')).write_text('keep')
            (root/('session_'+scope.key+'.json')).write_text('{}')
            media=root/'media/inbox/own.png';media.parent.mkdir(parents=True);media.write_bytes(b'fixture')
            write_json(root/'media_v2.json',{scope.key:['media/inbox/own.png']})
            backup=root/'history_all.json.bak-console-fixture';backup.write_text('whole backup')
            state=StateController(obj,root,clear_framework=lambda key:asyncio.sleep(0))
            result=await state.delete(scope.key,list(LAYERS),backup_files=[backup.name],confirm_shared_backups=True)
            self.assertTrue(result['ok'],result);self.assertEqual(result['retained'],[])
            self.assertEqual(obj.h[scope.key],[]);self.assertEqual(obj.h[other.key],[{'text':'keep'}])
            self.assertNotIn(scope.key,archive.read_text());self.assertIn(other.key,archive.read_text())
            self.assertFalse(media.exists());self.assertFalse(backup.exists());self.assertFalse((root/'memories'/(scope.key+'.md')).exists())
            self.assertTrue((root/'memories'/(other.key+'.md')).exists());await obj.runtime.stop()

    async def test_corruption_and_permission_errors_are_not_empty_state(self):
        from state_store import read_json, write_json, StateError
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json'
            self.assertEqual(read_json(path,{}),{})
            path.write_text('{broken',encoding='utf-8')
            with self.assertRaises(StateError): read_json(path,{})
            original=path.read_bytes()
            with patch('state_store.os.replace',side_effect=PermissionError('fixture')):
                with self.assertRaises(StateError): write_json(path,{'new':1})
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(list(Path(tmp).glob('*.tmp')),[])

    async def test_selective_delete_keeps_archive_notes_and_backups_and_revokes_old_work(self):
        from state_store import StateController, write_json
        from task_runtime import Runtime, work_context
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp,names=())
            scope=obj._scope(ScopeEvent())
            obj.runtime=Runtime(lambda *args:True)
            obj.h[scope.key]=[{'role':'user','text':'fixture'}]
            obj.th={}; obj.t_path=str(Path(tmp)/'thoughts_v2.json')
            write_json(obj.h_path,obj.h)
            Path(tmp,'history_archive_v2.jsonl').write_text(json.dumps({'uid':scope.key,'text':'fixture'})+'\n')
            notes=Path(tmp,'memories',scope.key+'.md'); notes.parent.mkdir(); notes.write_text('private fixture')
            backup=Path(tmp,'history_all.json.bak-console-fixture'); backup.write_text('whole backup')
            token=obj.runtime.begin(scope.key)
            async def clear(key): self.assertEqual(key,scope.key)
            state=StateController(obj,tmp,clear_framework=clear)
            result=await state.delete(scope.key,['rolling'])
            self.assertTrue(result['ok']); self.assertEqual(obj.h.get(scope.key),[])
            self.assertEqual(json.loads(Path(obj.h_path).read_text())[scope.key],[])
            self.assertTrue(notes.exists()); self.assertTrue(backup.exists())
            self.assertIn('fixture',Path(tmp,'history_archive_v2.jsonl').read_text())
            with work_context(token):
                with self.assertRaises(asyncio.CancelledError): obj.runtime.check()
            await obj.runtime.stop()

    async def test_all_selection_reports_backup_confirmation_and_framework_failure_honestly(self):
        from state_store import StateController
        from task_runtime import Runtime
        with tempfile.TemporaryDirectory() as tmp:
            obj,_=load_pipeline(tmp,names=()); scope=obj._scope(ScopeEvent())
            obj.runtime=Runtime(lambda *args:True); obj.th={}; obj.t_path=str(Path(tmp)/'thoughts_v2.json')
            backup=Path(tmp,'history_all.json.bak-console-fixture'); backup.write_text('whole backup')
            async def failure(key): raise PermissionError('fixture')
            state=StateController(obj,tmp,clear_framework=failure)
            result=await state.delete(scope.key,['rolling','backups'])
            self.assertFalse(result['ok']); self.assertEqual(result['layers']['rolling']['status'],'partial')
            self.assertEqual(result['layers']['backups']['status'],'failed'); self.assertTrue(backup.exists())
            await obj.runtime.stop()


if __name__=='__main__': unittest.main()
