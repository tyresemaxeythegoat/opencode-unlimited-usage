"""
Opencode Unlimited - Smart Lane Proxy for Windows
Intercepts requests to opencode.ai and routes them directly over IPv6
to a randomly chosen Cloudflare Anycast edge node.
"""

import sys
import os
import time
import socket
import select
import threading
import argparse
import http.client
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# Handle pythonw.exe where stdout and stderr are None
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# Add current dir to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import (
    DEFAULT_PROXY_PORT,
    TARGET_HOSTS,
    pick_random_edge,
    get_warp_mode,
    socks5_connect,
)

_WARP_MODE_LOCK = threading.Lock()
_WARP_MODE_CACHE: tuple[float, int | None] = (0.0, None)
_LOCAL_HOSTNAMES = {"127.0.0.1", "localhost", "::1", socket.gethostname().lower()}


def _get_warp_socks_port(ttl: float = 3.0) -> int | None:
    """Return WARP local SOCKS5 port when in WarpProxy mode, cached briefly."""
    global _WARP_MODE_CACHE
    now = time.time()
    with _WARP_MODE_LOCK:
        cached_at, cached_port = _WARP_MODE_CACHE
        if (now - cached_at) < ttl:
            return cached_port
    mode, port = get_warp_mode()
    result = port if (mode == "proxy" and port) else None
    with _WARP_MODE_LOCK:
        _WARP_MODE_CACHE = (time.time(), result)
    return result


def _is_local_host(host: str) -> bool:
    clean = host.strip("[]").lower()
    return clean in _LOCAL_HOSTNAMES or clean.startswith("127.")


class _SocksHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection whose TCP socket connects through a local SOCKS5 proxy."""

    def __init__(self, proxy_port: int, dest_host: str, dest_port: int = 80, timeout: float = 30):
        super().__init__(dest_host, dest_port, timeout=timeout)
        self._proxy_port = proxy_port
        self._dest_host = dest_host
        self._dest_port = dest_port

    def connect(self):
        self.sock = socks5_connect(
            "127.0.0.1",
            self._proxy_port,
            self._dest_host,
            self._dest_port,
            timeout=self.timeout or 10.0,
        )


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class SmartLaneProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress noisy logging unless debug is set
        if os.environ.get("OUC_DEBUG"):
            sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

    def do_CONNECT(self):
        """Handle HTTPS tunneling (CONNECT method)"""
        try:
            if ":" in self.path:
                host_part, _, port_part = self.path.rpartition(":")
                target_host = host_part.strip("[]")
                target_port = int(port_part)
            else:
                target_host = self.path.strip("[]")
                target_port = 443
        except Exception as e:
            self.send_error(400, f"Invalid CONNECT address: {e}")
            return

        remote_sock = None
        try:
            is_target = target_host.lower() in TARGET_HOSTS
            warp_socks_port = None if _is_local_host(target_host) else _get_warp_socks_port()

            if warp_socks_port:
                # Route via WARP's isolated SOCKS5 tunnel; never fall back to direct ISP IP
                dial_host = pick_random_edge() if is_target else target_host
                last_err: Exception | None = None
                for _ in range(4):
                    try:
                        remote_sock = socks5_connect(
                            "127.0.0.1",
                            warp_socks_port,
                            dial_host,
                            target_port,
                            timeout=10.0,
                        )
                        break
                    except Exception as err:
                        last_err = err
                        if is_target:
                            dial_host = pick_random_edge()
                        time.sleep(0.5)
                if remote_sock is None:
                    raise last_err or ConnectionError("WARP SOCKS5 proxy unreachable")
            elif is_target:
                # System WARP mode: pin to random Cloudflare IPv6 edge
                chosen_edge = pick_random_edge()
                remote_sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                remote_sock.settimeout(10)
                remote_sock.connect((chosen_edge, target_port))
            else:
                # Local or normal target in system mode
                remote_sock = socket.create_connection((target_host, target_port), timeout=10)

            # Acknowledge tunnel establishment to client
            self.send_response(200, "Connection Established")
            self.end_headers()

            try:
                self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                remote_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except Exception:
                pass

            # Splice client and remote sockets
            self._pipe_sockets(self.connection, remote_sock)

        except Exception as e:
            try:
                self.send_error(502, f"SmartLane Gateway Error: {e}")
            except Exception:
                pass
        finally:
            if remote_sock:
                try:
                    remote_sock.close()
                except Exception:
                    pass

    def do_GET(self):
        if self.path in ("/health", "/_ouc_health", "/_ouc_ping"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK: opencode-unlimited-proxy")
            return

        # Forward standard HTTP request
        self._forward_http("GET")

    def do_POST(self):
        self._forward_http("POST")

    def do_HEAD(self):
        self._forward_http("HEAD")

    def do_OPTIONS(self):
        self._forward_http("OPTIONS")

    def do_PUT(self):
        self._forward_http("PUT")

    def do_PATCH(self):
        self._forward_http("PATCH")

    def do_DELETE(self):
        self._forward_http("DELETE")

    def _forward_http(self, method: str):
        conn = None
        try:
            content_len = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(content_len) if content_len > 0 else None

            parsed = urllib.parse.urlsplit(self.path)
            host = parsed.hostname or ""
            is_https = parsed.scheme == "https"
            port = parsed.port or (443 if is_https else 80)
            if not host:
                self.send_error(400, f"Invalid proxy URL: {self.path}")
                return

            rel_path = parsed.path or "/"
            if parsed.query:
                rel_path += f"?{parsed.query}"

            warp_socks_port = None if _is_local_host(host) else _get_warp_socks_port()
            fwd_headers = {
                k: v
                for k, v in self.headers.items()
                if k.lower() not in ("proxy-connection", "connection")
            }

            if warp_socks_port and not is_https:
                dest = pick_random_edge() if host.lower() in TARGET_HOSTS else host
                conn = _SocksHTTPConnection(warp_socks_port, dest, port, timeout=30)
            elif is_https:
                conn = http.client.HTTPSConnection(host, port, timeout=30)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=30)

            conn.request(method, rel_path, body=body, headers=fwd_headers)
            res = conn.getresponse()

            self.send_response(res.status, res.reason)
            for k, v in res.getheaders():
                if k.lower() not in ("transfer-encoding", "connection", "keep-alive"):
                    self.send_header(k, v)
            self.end_headers()
            if method != "HEAD":
                while True:
                    chunk = res.read(16384)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except Exception as e:
            self.send_error(502, f"Proxy forward error: {e}")
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _pipe_sockets(self, sock1, sock2):
        """Lossless bidirectional blocking relay with half-close support."""
        sock1.settimeout(300)
        sock2.settimeout(300)

        def forward(src, dst):
            try:
                while True:
                    data = src.recv(65536)
                    if not data:
                        try:
                            dst.shutdown(socket.SHUT_WR)
                        except Exception:
                            pass
                        break
                    dst.sendall(data)
            except Exception:
                try:
                    dst.close()
                except Exception:
                    pass

        t1 = threading.Thread(target=forward, args=(sock1, sock2), daemon=True)
        t2 = threading.Thread(target=forward, args=(sock2, sock1), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()


def is_proxy_running(port: int = DEFAULT_PROXY_PORT) -> bool:
    url = f"http://127.0.0.1:{port}/_ouc_health"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ouc-check"})
        with urllib.request.urlopen(req, timeout=1.0) as res:
            return res.read().strip() == b"OK: opencode-unlimited-proxy"
    except Exception:
        return False


def start_proxy_server(port: int = DEFAULT_PROXY_PORT):
    server = ThreadingHTTPServer(("127.0.0.1", port), SmartLaneProxyHandler)
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Opencode Unlimited Smart Lane Proxy")
    parser.add_argument("--port", type=int, default=DEFAULT_PROXY_PORT, help="Port to listen on")
    args = parser.parse_args()

    if is_proxy_running(args.port):
        print(f"Proxy is already active on 127.0.0.1:{args.port}")
        sys.exit(0)

    print(f"Starting Smart Lane Proxy on 127.0.0.1:{args.port}...")
    try:
        start_proxy_server(args.port)
    except KeyboardInterrupt:
        print("\nProxy stopped.")
