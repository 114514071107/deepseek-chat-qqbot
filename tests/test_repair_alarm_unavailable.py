"""No new reminder promise/storage and no old delivery while F09 is deferred."""
import json
from pathlib import Path
import tempfile
import unittest
from repair_pipeline_support import load_pipeline
from test_repair_session_scope import ScopeEvent
from tool_permissions import authorize


class AlarmUnavailable(unittest.IsolatedAsyncioTestCase):
    async def test_new_source_cannot_create_and_old_data_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj,ns=load_pipeline(tmp,names=('set_alarm','_check_alarms'))
            self.addAsyncCleanup(obj.runtime.stop);self.addAsyncCleanup(obj.resources.close)
            path=Path(tmp)/'alarms.json';old=b'[{"uid":"synthetic-legacy","enabled":true}]';path.write_bytes(old)
            ns['ALARMS_PATH']=str(path)
            def forbidden(*a,**kw):self.fail('unavailable alarm path must not load/write/fire')
            ns['_alarm_add']=ns['_alarms_load']=ns['_alarms_save']=forbidden
            obj._fire_alarm=forbidden
            event=ScopeEvent('new-source');obj._scope(event)
            text=await obj.set_alarm(event,'daily','12:00','synthetic')
            self.assertIn('不可用',text);self.assertNotIn('已定为',text)
            await obj._check_alarms();self.assertEqual(path.read_bytes(),old)
            event.set_extra('_dsh_admitted',True);event.set_extra('_dsh_tool_limit',8)
            self.assertIsNotNone(authorize(event,'set_alarm','owner',lambda *a:True,owner_instance='bot-one'))
