"""Actual gate methods; synthetic event IDs, points, media and delivery only."""
import asyncio
import ast
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from repair_pipeline_support import load_pipeline
from test_repair_session_scope import ScopeEvent
from qq_delivery import DeliveryResult
from event_admission import Admissions,reserve
from state_store import read_json,write_json
from unittest.mock import patch


class EventAdmissionRegression(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_duplicate_local_command_charges_sends_and_records_once(self):
        with tempfile.TemporaryDirectory() as root:
            obj, ns = load_pipeline(root, names=('gate',))
            self.addAsyncCleanup(obj.runtime.stop); self.addAsyncCleanup(obj.resources.close)
            ns.update(MASTER_SWITCH_RE=re.compile('^NEVER$'), REMIND_CMD_RE=re.compile('^NEVER$'),
                      STATUS_RE=re.compile('^状态$'), Image=type('Image', (), {}),File=type('File', (), {}),
                      _conf=lambda k:k in ('enabled','points_enabled'),person_ledger_key=lambda s,p:s.key,POINTS_FILE='unused')
            obj.names={};obj.n_path=str(Path(root)/'names.json');obj.sil={}
            obj._owner=lambda *a:False;obj._perm=lambda *a:True;obj._match_sleep_cmd=lambda *a:None
            obj._status_text=lambda *a:'synthetic status';charges=[];sends=[]
            ns['_points_charge']=lambda uid:(charges.append(uid) or True,False)
            tree=ast.parse((Path(__file__).resolve().parents[1]/'plugin/astrbot_plugin_dsh_soul/main.py').read_text(encoding='utf-8-sig'))
            fn=next(n for n in tree.body if getattr(n,'name','')=='_points_charge')
            ns.update(_load=read_json,_save=write_json,_conf_val=lambda key,default:default,POINTS_FILE=str(Path(root)/'points.json'))
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'<actual-points>','exec'),ns)
            actual_charge=ns['_points_charge']
            ns['_points_charge']=lambda uid:(charges.append(uid) or actual_charge(uid))
            async def send(*a):
                sends.append(True);await asyncio.sleep(.01)
                return DeliveryResult('accepted',message_id='synthetic-output')
            obj._send=send
            def event(mid='platform-1',group='',instance='bot-one'):
                e=ScopeEvent('synthetic',group,instance);e.message_str='状态';e.message_obj.message_id=mid
                e.stop_event=lambda:None
                return e
            await asyncio.gather(*(obj.gate(event()) for _ in range(5)))
            self.assertEqual(len(charges),1);self.assertEqual(len(sends),1)
            self.assertEqual(sum(map(len,obj.h.values())),2)
            self.assertEqual(sum(v['spent'] for v in read_json(ns['POINTS_FILE'],{}).values()),1)
            for e in (event('platform-2'),event(group='another-group'),event(instance='another-instance')):await obj.gate(e)
            self.assertEqual(len(charges),4);self.assertEqual(len(sends),4)

    async def test_media_and_model_boundary_once_and_cancelled_admission_not_retried(self):
        with tempfile.TemporaryDirectory() as root:
            obj,ns=load_pipeline(root,names=('gate',));self.addAsyncCleanup(obj.runtime.stop);self.addAsyncCleanup(obj.resources.close)
            class Image:
                @staticmethod
                def fromFileSystem(p):return Image()
            ns.update(MASTER_SWITCH_RE=re.compile('^NEVER$'),REMIND_CMD_RE=re.compile('^NEVER$'),STATUS_RE=re.compile('^NEVER$'),
                Image=Image,File=type('File',(),{}),_conf=lambda k:k=='enabled',MAX_ITEMS=10,BATCH_DONE_MINLEN=8,BATCH_END_PUNCT='。',BATCH_STREAK_GAP=8)
            obj.names={};obj.n_path=str(Path(root)/'names.json');obj.sil={};obj._owner=lambda *a:False;obj._perm=lambda *a:True;obj._match_sleep_cmd=lambda *a:None
            obj.context=SimpleNamespace(get_config=lambda **kw:{})
            obj.last_msg_at={};obj.batch_skipwait={};obj.batch_buf={};counts=dict(download=0,model=0,tools=0,send=0)
            async def image(*a):counts['download']+=1;await asyncio.sleep(.02);return ['synthetic.png']
            obj._save_inbox_images=image;obj._spawn=lambda coro:coro.close()
            def event(mid):
                e=ScopeEvent('synthetic');e.message_obj.message_id=mid;e.message_obj.message=[Image()];e.stopped=False;e.stop_event=lambda:setattr(e,'stopped',True);return e
            async def pipeline(e):
                await obj.gate(e)
                if not e.stopped and e.get_extra('_dsh_admitted'):
                    # External model/tool/delivery substitutes only after real admission.
                    for key in ('model','tools','send'):counts[key]+=1
            module=SimpleNamespace(normalize_agent_runner=lambda v:{'config':{'misc':{'max_steps':2}}})
            with patch.dict('sys.modules',{'astrbot.core.config.agent_runner':module}):
                await asyncio.gather(*(pipeline(event('media-1')) for _ in range(5)))
                self.assertEqual(counts,dict(download=1,model=1,tools=1,send=1))
                await pipeline(event('media-2'));self.assertEqual(counts['download'],2)
                obj.batch_wait.clear()
                entered=asyncio.Event()
                async def cancelled(*a):entered.set();await asyncio.Event().wait()
                obj._save_inbox_images=cancelled
                task=asyncio.create_task(pipeline(event('cancelled')));await entered.wait();task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
                duplicate=event('cancelled');await pipeline(duplicate);self.assertTrue(duplicate.stopped)
            self.assertEqual(counts['model'],1)  # second new event was batched, no extra model

    def test_capacity_retention_active_failure_no_id_and_restart_semantics(self):
        now=[0];a=Admissions(capacity=1,retention=10,clock=lambda:now[0])
        self.assertEqual(a.reserve(None),'unidentified');self.assertEqual(a.reserve('a'),'reserved')
        now[0]=20;self.assertEqual(a.reserve('a'),'duplicate');self.assertEqual(a.reserve('b'),'capacity')
        a.retain('a','unknown');self.assertEqual(a.reserve('a'),'duplicate')
        now[0]=31;self.assertEqual(a.reserve('b'),'reserved');self.assertEqual(Admissions().reserve('a'),'reserved')

    def test_authenticated_app_is_part_of_event_key(self):
        owner=SimpleNamespace()
        for app,want in [('app-a',True),('app-b',True),('app-a',False)]:
            e=ScopeEvent('synthetic');e.stop_event=lambda:None
            e.bot=SimpleNamespace(api=SimpleNamespace(_http=SimpleNamespace(_token=SimpleNamespace(app_id=app))))
            self.assertEqual(reserve(owner,e),want)


if __name__=='__main__':unittest.main()
