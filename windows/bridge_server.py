import asyncio
import json
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional, Set
from urllib.parse import parse_qs, urlparse

import websockets

import pairing

BRIDGE_PORT = 39271
WS_PORT = 39272
UDP_PORT = 39273
PHONE_HTTP_PORT = 39274


class BridgeState:
    def __init__(self):
        self.callsign = None
        self.network_connected = False
        self.plugin_ready = False
        self.clients: Set = set()
        self.on_event: Optional[Callable] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.lock = threading.Lock()
        self.recent = []
        self.queues = {}
        self.last_poll = {}

    def emit(self, event):
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:
                pass

    def push_recent(self, item):
        self.recent.insert(0, item)
        self.recent = self.recent[:40]
        with self.lock:
            for q in list(self.queues.values()):
                q.append(item)

    def push_status(self, item):
        """Push status/callsign updates to all phone HTTP queues (not into recent log)."""
        with self.lock:
            for q in list(self.queues.values()):
                q.append(item)


STATE = BridgeState()


def clean_callsign(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in ("null", "none", "undefined"):
        return None
    return text


def status_payload():
    return {
        "type": "status",
        "connected": STATE.network_connected,
        "callsign": STATE.callsign or "",
    }


def _bad_ip(ip):
    if not ip or ip.startswith("127."):
        return True
    parts = ip.split(".")
    if len(parts) != 4:
        return True
    if ip.startswith("192.168.56."):
        return True
    if ip.startswith("192.168.17."):
        return True
    if ip.startswith("169.254."):
        return True
    if ip.startswith("172.") and 16 <= int(parts[1]) <= 31:
        return True
    return False


def local_ips():
    found = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        if ip and not _bad_ip(ip) and ip not in found:
            found.append(ip)
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not _bad_ip(ip) and ip not in found:
                found.append(ip)
    except Exception:
        pass
    return found or ["127.0.0.1"]


def best_host_for(remote_ip, ips):
    try:
        remote_parts = remote_ip.split(".")
        if len(remote_parts) == 4:
            for ip in ips:
                parts = ip.split(".")
                if len(parts) == 4 and parts[0:3] == remote_parts[0:3]:
                    return ip
            for ip in ips:
                parts = ip.split(".")
                if len(parts) == 4 and parts[0:2] == remote_parts[0:2]:
                    return ip
    except Exception:
        pass
    return ips[0] if ips else "127.0.0.1"


def open_firewall():
    exe = sys.executable
    try:
        subprocess.run(
            [
                "netsh",
                "advfirewall",
                "firewall",
                "delete",
                "rule",
                "name=VatsimConnect",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        subprocess.run(
            [
                "netsh",
                "advfirewall",
                "firewall",
                "add",
                "rule",
                "name=VatsimConnect",
                "dir=in",
                "action=allow",
                "program=" + exe,
                "enable=yes",
                "profile=any",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        for port in (WS_PORT, UDP_PORT, PHONE_HTTP_PORT):
            subprocess.run(
                [
                    "netsh",
                    "advfirewall",
                    "firewall",
                    "add",
                    "rule",
                    "name=VatsimConnect Port " + str(port),
                    "dir=in",
                    "action=allow",
                    "protocol=UDP" if port == UDP_PORT else "TCP",
                    "localport=" + str(port),
                    "enable=yes",
                    "profile=any",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
    except Exception:
        pass


class PluginHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            self.send_response(400)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
        handle_plugin_payload(payload)


class PhoneHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(
                200,
                {
                    "ok": True,
                    "plugin": STATE.plugin_ready,
                    "connected": STATE.network_connected,
                    "callsign": STATE.callsign or "",
                },
            )
            return
        if parsed.path == "/wait":
            qs = parse_qs(parsed.query)
            token = (qs.get("token") or [""])[0]
            state = pairing.load_state()
            if not pairing.find_device(state, token):
                self._json(401, {"type": "error", "message": "Unknown device"})
                return
            with STATE.lock:
                if token not in STATE.queues:
                    STATE.queues[token] = []
                STATE.last_poll[token] = time.time()
            item = None
            for _ in range(25):
                with STATE.lock:
                    q = STATE.queues.get(token) or []
                    if q:
                        item = q.pop(0)
                    STATE.last_poll[token] = time.time()
                if item:
                    break
                threading.Event().wait(0.2)
            if item:
                self._json(200, item)
            else:
                self._json(200, status_payload())
            return
        self._json(404, {"type": "error", "message": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            self._json(400, {"type": "error", "message": "Bad JSON"})
            return
        if parsed.path == "/pair":
            state = pairing.load_state()
            device = pairing.consume_code(
                state, payload.get("code", ""), payload.get("name", "Android")
            )
            if not device:
                self._json(400, {"type": "error", "message": "Invalid or expired code"})
                return
            with STATE.lock:
                STATE.queues[device["token"]] = []
            STATE.emit({"type": "paired", "name": device["name"]})
            self._json(
                200,
                {
                    "type": "paired",
                    "token": device["token"],
                    "connected": STATE.network_connected,
                    "callsign": STATE.callsign or "",
                    "ws_port": WS_PORT,
                    "http_port": PHONE_HTTP_PORT,
                },
            )
            return
        if parsed.path == "/resume":
            token = payload.get("token", "")
            state = pairing.load_state()
            device = pairing.find_device(state, token)
            if not device:
                self._json(401, {"type": "error", "message": "Unknown device"})
                return
            with STATE.lock:
                if token not in STATE.queues:
                    STATE.queues[token] = []
            self._json(
                200,
                {
                    "type": "resumed",
                    "connected": STATE.network_connected,
                    "callsign": STATE.callsign or "",
                },
            )
            return
        self._json(404, {"type": "error", "message": "Not found"})


def handle_plugin_payload(payload):
    kind = payload.get("type")
    if kind == "plugin":
        STATE.plugin_ready = True
        STATE.emit({"type": "plugin", "ready": True})
        return
    if kind == "status":
        connected = bool(payload.get("connected"))
        # Keep previous callsign if an update omits/clears it while still connected.
        incoming = clean_callsign(payload.get("callsign"))
        if incoming:
            callsign = incoming
        elif connected:
            callsign = STATE.callsign
        else:
            callsign = None
        changed = (
            connected != STATE.network_connected
            or (callsign or None) != (STATE.callsign or None)
        )
        STATE.network_connected = connected
        STATE.callsign = callsign
        event = {
            "type": "status",
            "connected": STATE.network_connected,
            "callsign": STATE.callsign or "",
        }
        STATE.emit(event)
        broadcast(event)
        # Only push to phones when something actually changed (avoid queue spam).
        if changed:
            STATE.push_status(event)
        return
    if kind == "message":
        item = {
            "type": "message",
            "kind": payload.get("kind") or "private",
            "from": payload.get("from") or "ATC",
            "body": payload.get("body") or "",
        }
        STATE.push_recent(item)
        STATE.emit(item)
        broadcast(item)


def broadcast(payload):
    if STATE.loop is None:
        return
    asyncio.run_coroutine_threadsafe(_broadcast(payload), STATE.loop)


async def _broadcast(payload):
    dead = []
    data = json.dumps(payload)
    for client in list(STATE.clients):
        try:
            await client.send(data)
        except Exception:
            dead.append(client)
    for client in dead:
        STATE.clients.discard(client)


async def ws_handler(websocket):
    try:
        hello_raw = await asyncio.wait_for(websocket.recv(), timeout=20)
        hello = json.loads(hello_raw)
        action = hello.get("action")
        state = pairing.load_state()
        if action == "pair":
            device = pairing.consume_code(state, hello.get("code", ""), hello.get("name", "Android"))
            if not device:
                await websocket.send(json.dumps({"type": "error", "message": "Invalid or expired code"}))
                await websocket.close()
                return
            with STATE.lock:
                STATE.queues[device["token"]] = []
            await websocket.send(
                json.dumps(
                    {
                        "type": "paired",
                        "token": device["token"],
                        "callsign": STATE.callsign or "",
                        "connected": STATE.network_connected,
                    }
                )
            )
            STATE.emit({"type": "paired", "name": device["name"]})
        elif action == "resume":
            token = hello.get("token")
            device = pairing.find_device(state, token)
            if not device:
                await websocket.send(json.dumps({"type": "error", "message": "Unknown device"}))
                await websocket.close()
                return
            await websocket.send(
                json.dumps(
                    {
                        "type": "resumed",
                        "callsign": STATE.callsign or "",
                        "connected": STATE.network_connected,
                    }
                )
            )
        else:
            await websocket.send(json.dumps({"type": "error", "message": "Unknown action"}))
            await websocket.close()
            return
        STATE.clients.add(websocket)
        async for _ in websocket:
            pass
    except Exception:
        pass
    finally:
        STATE.clients.discard(websocket)


def start_http():
    server = ThreadingHTTPServer(("127.0.0.1", BRIDGE_PORT), PluginHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def start_phone_http():
    server = ThreadingHTTPServer(("0.0.0.0", PHONE_HTTP_PORT), PhoneHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def start_udp_discovery():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", UDP_PORT))
    sock.settimeout(1.0)

    def loop():
        while True:
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except Exception:
                continue
            try:
                msg = json.loads(data.decode("utf-8"))
            except Exception:
                continue
            if msg.get("action") != "discover":
                continue
            code = (msg.get("code") or "").upper()
            state = pairing.load_state()
            if not pairing.code_valid(state, code):
                continue
            ips = local_ips()
            host = best_host_for(addr[0], ips)
            reply = json.dumps(
                {
                    "action": "discover_ok",
                    "host": host,
                    "port": WS_PORT,
                    "http_port": PHONE_HTTP_PORT,
                    "ips": ips,
                }
            ).encode("utf-8")
            try:
                sock.sendto(reply, addr)
            except Exception:
                pass

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return sock


async def run_ws_server():
    STATE.loop = asyncio.get_running_loop()
    async with websockets.serve(
        ws_handler,
        "0.0.0.0",
        WS_PORT,
        ping_interval=20,
        ping_timeout=20,
    ):
        await asyncio.Future()


def start_async_servers():
    def runner():
        asyncio.run(run_ws_server())

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return thread
