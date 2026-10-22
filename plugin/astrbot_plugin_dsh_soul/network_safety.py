"""Bounded public HTTP(S), no proxies, no second DNS lookup at connection time."""
import http.client
import ipaddress
import socket
import ssl
import threading
import time
from urllib.parse import urljoin, urlsplit


class FetchDenied(ValueError):
    pass


_dns_slots = threading.BoundedSemaphore(4)  # three existing parallel search engines + one page


def _remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError('抓取总时间已到')
    return seconds


def _resolve(host, port, deadline):
    # A stuck system resolver must not accumulate unbounded worker threads.
    slots = _dns_slots
    if not slots.acquire(blocking=False):
        raise FetchDenied('DNS 解析繁忙，请稍后再试')
    done, result = threading.Event(), []

    def resolve():
        try:
            result.append(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except Exception:
            result.append(None)
        finally:
            slots.release()
            done.set()

    threading.Thread(target=resolve, daemon=True, name='dsh-public-dns').start()
    if not done.wait(_remaining(deadline)):
        raise TimeoutError('DNS 解析超时')
    if not result[0]:
        raise FetchDenied('DNS 解析失败')
    return result[0]


def _public_ip(address):
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def _destination(url, deadline):
    if not isinstance(url, str) or len(url) > 8192 or any(ord(c) < 33 for c in url) or '\\' in url:
        raise FetchDenied('URL 格式被拒绝')
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port or (443 if parts.scheme == 'https' else 80)
        if parts.scheme not in ('http', 'https') or not host or parts.username is not None or parts.password is not None:
            raise ValueError()
        host = host.encode('idna').decode('ascii').lower()
        if '%' in host or host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise FetchDenied('只允许无凭据的公网 HTTP(S) 地址') from None
    infos = _resolve(host, port, deadline)
    for family, socktype, proto, _, address in infos:
        if family not in (socket.AF_INET, socket.AF_INET6) or not _public_ip(address[0]):
            raise FetchDenied('地址含本机、内网或保留地址')
    return parts, host, port, infos


def fetch_public_bytes(url, *, max_bytes=2 * 1024 * 1024, timeout=15, max_redirects=5, headers=None):
    """One deadline covers DNS, connection, TLS, redirects, headers and body.

    All resolved addresses must be public. Connect to a validated numeric
    sockaddr; TLS SNI/certificate checks and Host still use the hostname.
    """
    if max_bytes < 1 or timeout <= 0 or max_redirects < 0:
        raise ValueError('抓取限制无效')
    deadline = time.monotonic() + timeout
    active = []
    expired = threading.Event()

    def abort():
        expired.set()
        for sock in active[:]:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    watchdog = threading.Timer(timeout, abort)
    watchdog.daemon = True
    watchdog.start()
    try:
        for hop in range(max_redirects + 1):
            parts, host, port, infos = _destination(url, deadline)
            family, socktype, proto, _, address = infos[0]
            sock = socket.socket(family, socktype, proto)
            active.append(sock)
            conn = None
            try:
                sock.settimeout(_remaining(deadline))
                sock.connect(address)  # numeric, already validated; never resolves again
                if not _public_ip(sock.getpeername()[0]) or ipaddress.ip_address(sock.getpeername()[0]) != ipaddress.ip_address(address[0]):
                    raise FetchDenied('实际连接地址与核准地址不符')
                if parts.scheme == 'https':
                    sock.settimeout(_remaining(deadline))
                    sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host, do_handshake_on_connect=False)
                    active.append(sock)
                    sock.do_handshake()
                conn = http.client.HTTPConnection(host, port, timeout=_remaining(deadline))
                conn.sock = sock
                target = parts.path or '/'
                if parts.query:
                    target += '?' + parts.query
                authority = ('[' + host + ']') if ':' in host else host
                if port != (443 if parts.scheme == 'https' else 80):
                    authority += ':' + str(port)
                request_headers = {'User-Agent':'Mozilla/5.0', 'Accept-Encoding':'identity', 'Host':authority, 'Connection':'close'}
                if headers:
                    request_headers.update({k:v for k,v in headers.items() if k.lower() in ('user-agent','accept','accept-language','referer','cache-control')})
                sock.settimeout(_remaining(deadline))
                conn.request('GET', target, headers=request_headers)
                response = conn.getresponse()
                with response:
                    if response.status in (301,302,303,307,308):
                        location = response.getheader('Location')
                        if not location or hop == max_redirects:
                            raise FetchDenied('重定向缺少目标或超过次数上限')
                        url = urljoin(url, location)
                        continue
                    if response.status != 200:
                        raise FetchDenied('HTTP 状态 ' + str(response.status))
                    length = response.getheader('Content-Length')
                    if length and (not length.isdecimal() or int(length) > max_bytes):
                        raise FetchDenied('响应超过读取上限或长度无效')
                    if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                        raise FetchDenied('不接受压缩响应')
                    chunks, total = [], 0
                    while True:
                        sock.settimeout(_remaining(deadline))
                        chunk = response.read1(min(65536, max_bytes + 1 - total))
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > max_bytes:
                            raise FetchDenied('响应超过读取上限')
                        chunks.append(chunk)
                    _remaining(deadline)
                    if length and total != int(length):
                        raise FetchDenied('响应正文提前结束')
                    if expired.is_set():
                        raise TimeoutError('抓取总时间已到')
                    return b''.join(chunks)
            finally:
                if conn:
                    conn.close()
                sock.close()
                active.clear()
        raise FetchDenied('重定向次数过多')
    finally:
        watchdog.cancel()
