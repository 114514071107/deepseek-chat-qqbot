"""Installed botpy authentication events, no network or production clients."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from repair_pipeline_support import PLUGIN
import admin_bridge
from botpy.gateway import BotWebSocket

class ResumeReadiness(unittest.IsolatedAsyncioTestCase):
    async def test_pinned_adapter_connector_installs_before_resumed_event(self):
        with tempfile.TemporaryDirectory(prefix='dsh pinned connector ') as temp:
            env={**os.environ,'ASTRBOT_ROOT':temp,'TEMP':temp,'TMP':temp,'PYTHONIOENCODING':'utf-8'}
            result=await asyncio.to_thread(subprocess.run,[sys.executable,'-B',str(Path(__file__).resolve()),'--pinned-connector'],cwd=temp,env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=45)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('pinned connector observed current RESUMED',result.stdout)
    async def socket(self,session_id='synthetic-session'):
        events=[]
        async def inert(*args,**kwargs):pass
        connection=NS(parser={'resumed':lambda msg:events.append('resumed'),'ready':lambda msg:events.append('ready')},loop=asyncio.get_running_loop(),add=lambda session:None)
        session=dict(session_id=session_id,shards=dict(shard_id=0,shard_count=1),intent=1,last_seq=0,token=NS(check_token=inert,get_string=lambda:'synthetic-token'))
        socket=BotWebSocket(session,connection)
        socket._send_heart=inert
        socket.send_msg=inert
        conn=NS(closed=False)
        # Existing implementation lacks this observer: still execute the real
        # SDK path and assert its readiness, rather than fail on an import.
        getattr(admin_bridge,'observe_socket',lambda value:None)(socket)
        await socket.on_connected(conn)
        return socket,events

    def status(self,*sockets):
        client=NS(_active_websockets=set(sockets),is_closed=lambda:False)
        ctx=NS(platform_manager=NS(platform_insts=[NS(meta=lambda:NS(name='qq_official'),client=client)]))
        return admin_bridge.qq_connection_status(ctx)['status']

    async def test_authenticated_resumed_is_ready_then_invalid_session_revokes(self):
        socket,events=await self.socket()
        self.assertNotEqual(self.status(socket),'ready','Open socket and old session are insufficient')
        await socket.on_message(socket._conn,json.dumps(dict(op=0,s=2,t='RESUMED',d={})))
        self.assertIn('resumed',events)
        self.assertEqual(self.status(socket),'ready','S03: SDK accepted RESUMED but readiness still connecting')
        await socket.on_message(socket._conn,json.dumps(dict(op=9,s=3,d=False)))
        self.assertNotEqual(self.status(socket),'ready')

    async def test_first_ready_on_observed_connection_is_confirmed(self):
        socket,events=await self.socket('')
        data=dict(version=1,session_id='synthetic-fresh',shard=[0,1],user=dict(id='synthetic',username='synthetic'))
        await socket.on_message(socket._conn,json.dumps(dict(op=0,s=1,t='READY',d=data)))
        self.assertIn('ready',events)
        self.assertEqual(self.status(socket),'ready')

    async def test_resume_without_current_auth_attempt_is_not_ready(self):
        socket,_=await self.socket()
        socket._conn=NS(closed=False)  # a different connection without Resume
        await socket.on_message(socket._conn,json.dumps(dict(op=0,s=4,t='RESUMED',d={})))
        self.assertNotEqual(self.status(socket),'ready')

    async def test_closed_old_socket_and_unconfirmed_second_socket_never_prove_ready(self):
        first,_=await self.socket();second,_=await self.socket()
        await first.on_message(first._conn,json.dumps(dict(op=0,s=2,t='RESUMED',d={})))
        self.assertEqual(self.status(first),'ready')
        self.assertNotEqual(self.status(first,second),'ready')
        first._conn.closed=True
        self.assertNotEqual(self.status(first),'ready')
        self.assertNotEqual(self.status(second),'ready')

    async def test_auth_failure_open_connection_invalidates_confirmation(self):
        socket,_=await self.socket()
        await socket.on_message(socket._conn,json.dumps(dict(op=0,s=2,t='RESUMED',d={})))
        self.assertEqual(self.status(socket),'ready')
        await socket.on_closed(4004,'synthetic')
        self.assertNotEqual(self.status(socket),'ready')

    async def test_sequential_runtime_reload_preserves_same_connection_receipt(self):
        from qq_readiness import release_observers,observe_socket
        socket,_=await self.socket()
        await socket.on_message(socket._conn,json.dumps(dict(op=0,s=2,t='RESUMED',d={})))
        self.assertEqual(self.status(socket),'ready')
        original=lambda:None;installed=lambda:None
        client=NS(_active_websockets={socket},is_closed=lambda:False,_connection=NS(_connect=installed),_dsh_ready_connector=(original,installed,{'old-runtime'}))
        context=NS(platform_manager=NS(platform_insts=[NS(meta=lambda:NS(name='qq_official'),client=client)]))
        release_observers(context,'old-runtime')
        observe_socket(socket)
        self.assertEqual(self.status(socket),'ready','Same authenticated RESUMED connection became unready on sequential plugin reload')
        await socket.on_message(socket._conn,json.dumps(dict(op=9,s=3,d=False)))
        self.assertNotEqual(self.status(socket),'ready','Owner-free observation must still revoke invalid auth')


async def pinned_connector_case():
    from unittest.mock import patch
    from astrbot.core.platform.sources.qqofficial import qqofficial_platform_adapter as adapter
    from qq_readiness import ensure_client_observer
    client=object.__new__(adapter.botClient);client._closed=False;client._shutting_down=False;client._active_websockets=set()
    client._connection=NS(_connect=client.bot_connect,parser={'resumed':lambda msg:None},loop=asyncio.get_running_loop(),add=lambda session:None)
    context=NS(platform_manager=NS(platform_insts=[NS(meta=lambda:NS(name='qq_official'),client=client)]))
    async def inert(*args,**kw):pass
    class OfflineSocket(adapter.ManagedBotWebSocket):
        async def ws_connect(self):
            self._send_heart=inert;self.send_msg=inert
            conn=NS(closed=False)
            await self.on_connected(conn)
            assert admin_bridge.qq_connection_status(context)['status']!='ready'
            await self.on_message(conn,json.dumps(dict(op=0,s=2,t='RESUMED',d={})))
            assert admin_bridge.qq_connection_status(context)['status']=='ready'
            await self.on_message(conn,json.dumps(dict(op=9,s=3,d=False)))
            assert admin_bridge.qq_connection_status(context)['status']!='ready'
            conn.closed=True
    with patch.object(adapter,'ManagedBotWebSocket',OfflineSocket):
        assert ensure_client_observer(client,'synthetic-runtime')
        token=NS(check_token=inert,get_string=lambda:'synthetic')
        await client._connection._connect(dict(session_id='synthetic',last_seq=0,shards={},token=token))
    assert not client._active_websockets
    print('pinned connector observed current RESUMED')


if __name__=='__main__' and '--pinned-connector' in sys.argv:asyncio.run(pinned_connector_case())
