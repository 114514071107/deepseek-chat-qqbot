"""Read-only QQ SDK metadata; no transport, identities or credentials serialized."""
import json
from types import SimpleNamespace as NS
import unittest
from repair_pipeline_support import PLUGIN
import admin_bridge


class PlatformReady(unittest.TestCase):
    def context(self,sockets,closed=False):
        client=NS(_active_websockets=sockets,is_closed=lambda:closed)
        return NS(platform_manager=NS(platform_insts=[NS(meta=lambda:NS(name='qq_official'),client=client)]))

    def socket(self,**kw):
        values=dict(_conn=NS(closed=False),_session={'session_id':'synthetic-session-secret','token':'synthetic-token-secret'},user={'id':'synthetic-bot-id'})
        values.update(kw);return NS(**values)

    def test_only_current_ready_and_open_sockets_count(self):
        value=admin_bridge.qq_connection_status(self.context([self.socket()]))
        self.assertEqual(value,{'status':'ready','configured':1,'ready':1})
        self.assertNotIn('synthetic',json.dumps(value))
        for sockets in ([],[self.socket(_conn=NS(closed=True))],[self.socket(user=None)],[self.socket(_session={})],[self.socket(),self.socket(user=None)]):
            self.assertNotEqual(admin_bridge.qq_connection_status(self.context(sockets))['status'],'ready')
        self.assertNotEqual(admin_bridge.qq_connection_status(self.context([self.socket()],closed=True))['status'],'ready')

    def test_missing_or_changed_sdk_contract_is_unknown(self):
        self.assertEqual(admin_bridge.qq_connection_status(None)['status'],'unknown')
        context=self.context([]);context.platform_manager.platform_insts[0].client=NS()
        self.assertEqual(admin_bridge.qq_connection_status(context)['status'],'unknown')


class InstalledSDKReadyContract(unittest.IsolatedAsyncioTestCase):
    async def test_installed_ready_handler_produces_required_metadata(self):
        from botpy.gateway import BotWebSocket
        socket=BotWebSocket({'session_id':'','shards':{}},NS(parser={}))
        socket._conn=NS(closed=False)
        context=PlatformReady().context([socket])
        self.assertNotEqual(admin_bridge.qq_connection_status(context)['status'],'ready')
        await socket._ready_handler({'d':{'version':1,'session_id':'synthetic-only','shard':[0,1],'user':{'id':'synthetic-only'}}})
        self.assertEqual(admin_bridge.qq_connection_status(context)['status'],'ready')
        socket._conn.closed=True
        self.assertNotEqual(admin_bridge.qq_connection_status(context)['status'],'ready')
