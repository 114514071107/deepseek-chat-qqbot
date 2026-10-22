import ast
import asyncio
from pathlib import Path
import re
import time
import unittest
import io
import socket
import sys
import types
import http.client
from unittest.mock import patch, Mock

MAIN = Path(__file__).resolve().parents[1] / 'plugin/astrbot_plugin_dsh_soul/main.py'
sys.path.insert(0,str(MAIN.parent))
import network_safety as net


class WireSocket:
    def __init__(self, raw, peer='8.8.8.8'):
        self.raw, self.peer, self.targets, self.sent = raw, peer, [], []
    def connect(self,address): self.targets.append(address)
    def getpeername(self): return (self.peer,80)
    def settimeout(self,timeout): pass
    def do_handshake(self): pass
    def sendall(self,data): self.sent.append(data)
    def makefile(self,*args): return io.BytesIO(self.raw)
    def shutdown(self,*args): pass
    def close(self): pass


def addresses(host,port,**kwargs):
    ip = '127.0.0.1' if host == 'internal.invalid' else '8.8.8.8'
    return [(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,port))]


class PublicNetworkTests(unittest.TestCase):
    def fetch(self,url='http://public.invalid/',raw=b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok', **kwargs):
        wire = WireSocket(raw)
        with patch.object(net.socket,'getaddrinfo',side_effect=addresses), patch.object(net.socket,'socket',return_value=wire):
            result = net.fetch_public_bytes(url, **kwargs)
        return result, wire

    def test_normal_fetch_binds_numeric_address_and_preserves_host(self):
        result,wire=self.fetch()
        self.assertEqual(result,b'ok')
        self.assertEqual(wire.targets,[('8.8.8.8',80)])
        self.assertIn(b'Host: public.invalid',b''.join(wire.sent))

    def test_redirect_to_private_and_abnormal_protocols(self):
        for location in ('http://internal.invalid/','file:///secret','ftp://public.invalid/a',
                         'http://user:password@public.invalid/','http://[::1]/'):
            with self.subTest(location=location), self.assertRaises(net.FetchDenied):
                # IPv6 loopback fixture must resolve to loopback too.
                def dns(host,port,**kwargs):
                    return addresses('internal.invalid' if host == '::1' else host,port)
                with patch.object(net.socket,'getaddrinfo',side_effect=dns), patch.object(net.socket,'socket',
                    return_value=WireSocket(('HTTP/1.1 302 Found\r\nLocation: '+location+'\r\n\r\n').encode())):
                    net.fetch_public_bytes('http://public.invalid/')

    def test_multihop_and_redirect_cap(self):
        responses=[WireSocket(b'HTTP/1.1 302 Found\r\nLocation: /next\r\n\r\n'),
                   WireSocket(b'HTTP/1.1 302 Found\r\nLocation: http://internal.invalid/\r\n\r\n')]
        with patch.object(net.socket,'getaddrinfo',side_effect=addresses), patch.object(net.socket,'socket',side_effect=responses), self.assertRaises(net.FetchDenied):
            net.fetch_public_bytes('http://public.invalid/')
        with self.assertRaises(net.FetchDenied):
            self.fetch(raw=b'HTTP/1.1 302 Found\r\nLocation: /again\r\n\r\n',max_redirects=1)

    def test_mixed_dns_rebinding_and_actual_peer(self):
        with patch.object(net.socket,'getaddrinfo',return_value=addresses('public',80)+addresses('internal.invalid',80)), patch.object(net.socket,'socket') as create, self.assertRaises(net.FetchDenied):
            net.fetch_public_bytes('http://public.invalid/')
        create.assert_not_called()
        dns=Mock(side_effect=[addresses('public',80),addresses('internal.invalid',80)])
        wire=WireSocket(b'HTTP/1.1 200 OK\r\n\r\nok')
        with patch.object(net.socket,'getaddrinfo',dns),patch.object(net.socket,'socket',return_value=wire):
            self.assertEqual(net.fetch_public_bytes('http://public.invalid/'),b'ok')
        self.assertEqual(dns.call_count,1)  # connection cannot trigger a second lookup
        wire.peer='127.0.0.1'
        with patch.object(net.socket,'getaddrinfo',side_effect=addresses),patch.object(net.socket,'socket',return_value=wire),self.assertRaises(net.FetchDenied):
            net.fetch_public_bytes('http://public.invalid/')

    def test_size_limit_with_and_without_content_length(self):
        for raw in (b'HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n', b'HTTP/1.1 200 OK\r\n\r\n12345',
                    b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n5\r\n12345\r\n0\r\n\r\n'):
            with self.assertRaises(net.FetchDenied): self.fetch(raw=raw,max_bytes=4)

    def test_tls_checks_hostname(self):
        wire=WireSocket(b'HTTP/1.1 200 OK\r\n\r\nok')
        tls=Mock(); tls.wrap_socket.return_value=wire
        with patch.object(net.socket,'getaddrinfo',side_effect=addresses),patch.object(net.socket,'socket',return_value=wire),patch.object(net.ssl,'create_default_context',return_value=tls):
            self.assertEqual(net.fetch_public_bytes('https://public.invalid/'),b'ok')
        self.assertEqual(tls.wrap_socket.call_args.kwargs['server_hostname'],'public.invalid')

    def test_truncated_body_is_not_accepted_as_complete(self):
        with self.assertRaises(net.FetchDenied):
            self.fetch(raw=b'HTTP/1.1 200 OK\r\nContent-Length: 20\r\n\r\nshort')

    def test_slow_dns_times_out_without_unbounded_workers(self):
        import threading
        release,finished=threading.Event(),threading.Event()
        def slow(*args,**kwargs):
            release.wait(2); finished.set(); return addresses('public',80)
        slots=threading.BoundedSemaphore(1)
        with patch.object(net,'_dns_slots',slots),patch.object(net.socket,'getaddrinfo',side_effect=slow):
            try:
                began=time.monotonic()
                with self.assertRaises(TimeoutError):
                    net.fetch_public_bytes('http://public.invalid/',timeout=.04)
                self.assertLess(time.monotonic()-began,.5)
                with self.assertRaises(net.FetchDenied):
                    net.fetch_public_bytes('http://public.invalid/',timeout=.04)
            finally:
                release.set(); finished.wait(1)

    def test_slow_headers_and_body_end_within_total_deadline(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    if self.path == '/headers':
                        for c in b'HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n':
                            self.connection.sendall(bytes([c])); time.sleep(.03)
                    else:
                        self.send_response(200); self.end_headers()
                        for _ in range(100):
                            self.wfile.write(b'x'); self.wfile.flush(); time.sleep(.03)
                except (OSError,ConnectionError): pass
            def log_message(self,*args): pass
        server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        real_socket = socket.socket
        class MappedSocket:
            def __init__(self,*args): self.inner=real_socket(*args)
            def connect(self,address): self.inner.connect(server.server_address)
            def getpeername(self): return ('8.8.8.8',80)
            def __getattr__(self,name): return getattr(self.inner,name)
        sockets = types.SimpleNamespace(AF_INET=socket.AF_INET,AF_INET6=socket.AF_INET6,
            SOCK_STREAM=socket.SOCK_STREAM,SHUT_RDWR=socket.SHUT_RDWR,getaddrinfo=addresses,socket=MappedSocket)
        try:
            for route in ('/headers','/body'):
                began=time.monotonic()
                with patch.object(net,'socket',sockets), self.assertRaises((TimeoutError,OSError,net.FetchDenied,http.client.HTTPException)):
                    net.fetch_public_bytes('http://public.invalid'+route,timeout=.2)
                self.assertLess(time.monotonic()-began,1.0)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


class FetchRegression(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_does_not_follow_public_redirect_to_loopback(self):
        tree = ast.parse(MAIN.read_text(encoding='utf-8-sig'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DshSoul')
        method = next(n for n in cls.body if getattr(n, 'name', '') == 'fetch_url')
        method.decorator_list = []
        ns = dict(AstrMessageEvent=object, asyncio=asyncio, re=re, time=time, NL='\n',fetch_public_bytes=net.fetch_public_bytes,
                  _is_internal_url=lambda url: False)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])), '<fetch_url>', 'exec'), ns)
        event = Mock(); event.get_sender_id.return_value='fixture'
        obj = Mock(); obj.tool_react_at={'fixture':time.time()}
        obj._scope.return_value=__import__('types').SimpleNamespace(key='fixture',target=__import__('types').SimpleNamespace(umo='fixture'))
        response = Mock(); response.read.return_value=b'<title>private sentinel</title>private sentinel'
        import sys, types
        fake_web = types.SimpleNamespace(strip_html=lambda s: re.sub('<[^>]+>', '', s))
        wire=WireSocket(b'HTTP/1.1 302 Found\r\nLocation: http://internal.invalid/\r\n\r\n')
        sockets = types.SimpleNamespace(AF_INET=socket.AF_INET, AF_INET6=socket.AF_INET6,
            SOCK_STREAM=socket.SOCK_STREAM, SHUT_RDWR=socket.SHUT_RDWR, getaddrinfo=addresses,
            socket=lambda *args: wire)
        with patch.dict(sys.modules, websearch=fake_web), patch('urllib.request.urlopen',return_value=response), patch.object(net,'socket',sockets):
            result = await ns['fetch_url'](obj,event,'https://public.invalid/redirect')
        self.assertNotIn('private sentinel',result)


if __name__ == '__main__': unittest.main()
