import ctypes
import re
import threading
import time
from ctypes import wintypes

from bridge_server import STATE, handle_plugin_payload
import vpilot_state

MSG_RE = re.compile(
    r"^\[(\d{1,2}:\d{2}:\d{2})\]\s+(\S+)\s+on\s+([\d.]+):\s*(.+)$",
    re.IGNORECASE,
)
CALLSIGN_RE = re.compile(r"\b([A-Z]{2,4}\d{1,5}[A-Z]?)\b")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

TH32CS_SNAPPROCESS = 0x00000002


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


def vpilot_pids():
    pids = set()
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return pids
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    try:
        if kernel32.Process32First(snap, ctypes.byref(entry)):
            while True:
                name = entry.szExeFile.decode("utf-8", errors="ignore").lower()
                if name == "vpilot.exe":
                    pids.add(int(entry.th32ProcessID))
                if not kernel32.Process32Next(snap, ctypes.byref(entry)):
                    break
    finally:
        kernel32.CloseHandle(snap)
    return pids


def find_vpilot_hwnds():
    pids = vpilot_pids()
    found = []
    if not pids:
        return found

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) in pids:
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            found.append((int(hwnd), buf.value or ""))
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return found


def _window_text(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return (buf.value or "").strip()


def collect_vpilot_texts():
    """Top-level titles + child control labels (callsign lives here, not in the title)."""
    texts = []
    for hwnd, title in find_vpilot_hwnds():
        if title:
            texts.append(title)
        children = []

        def child_cb(child, _):
            try:
                name = _window_text(child)
            except Exception:
                return True
            if name:
                children.append(name)
            return True

        try:
            user32.EnumChildWindows(hwnd, EnumWindowsProc(child_cb), 0)
        except Exception:
            pass
        texts.extend(children)
    seen = set()
    out = []
    for item in texts:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def callsign_from_texts(texts):
    for text in texts:
        cand = text.strip().upper()
        if cand in ("VPILOT", "TX", "RX", "IDENT", "MODE C", "SETTINGS", "DISCONNECT", "CONNECT", "MESSAGES", "NOTES", "FLIGHT PLAN"):
            continue
        if re.fullmatch(r"[A-Z]{2,4}\d{1,5}[A-Z]?", cand):
            return cand
    for text in texts:
        cand = text.strip().upper()
        if cand in ("VPILOT",) or ("ON " in cand and ":" in cand):
            continue
        m = CALLSIGN_RE.search(cand)
        if m:
            hit = m.group(1)
            if not hit.startswith("122") and not hit.startswith("123"):
                return hit
    return None


def connected_from_texts(texts):
    joined = " | ".join(t.lower() for t in texts)
    if re.search(r"\bdisconnect\b", joined):
        return True
    if re.search(r"\bconnect\b", joined) and "disconnect" not in joined:
        return False
    return None


class UiWatcher:
    def __init__(self):
        self._seen = set()
        self._primed = False
        self.active = False
        self.vpilot_seen = False
        self._thread = None
        self._callsign = None
        self._live_source = False

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while True:
            try:
                if STATE.plugin_ready and STATE.callsign and STATE.network_connected:
                    self.active = False
                    self.vpilot_seen = True
                    time.sleep(2)
                    continue
                self._scan(callsign_only=bool(STATE.plugin_ready))
                if not STATE.plugin_ready:
                    self._apply_file_snapshot()
            except Exception:
                self.active = False
            time.sleep(1.0)

    def _apply_file_snapshot(self):
        connected = vpilot_state.read_network_connected()
        if self._live_source and self._callsign:
            callsign = self._callsign
        elif STATE.callsign:
            callsign = STATE.callsign
        else:
            callsign = None 

        if connected is True:
            handle_plugin_payload(
                {
                    "type": "status",
                    "connected": True,
                    "callsign": callsign or "",
                }
            )
        elif connected is False and not self._live_source:
            self._callsign = None
            handle_plugin_payload(
                {
                    "type": "status",
                    "connected": False,
                    "callsign": "",
                }
            )

    def _scan(self, callsign_only=False):
        pids = vpilot_pids()
        if not pids:
            self.vpilot_seen = False
            self.active = False
            self._live_source = False
            return

        self.vpilot_seen = True
        texts = collect_vpilot_texts()

        try:
            import uiautomation as auto
        except Exception:
            auto = None
        if auto is not None:
            for hwnd, _title in find_vpilot_hwnds():
                try:
                    win = auto.ControlFromHandle(int(hwnd))
                    if win is None:
                        continue
                    for ctrl, _depth in auto.WalkControl(win, maxDepth=45):
                        try:
                            name = (ctrl.Name or "").strip()
                        except Exception:
                            continue
                        if name:
                            texts.append(name)
                except Exception:
                    continue

        self.active = not callsign_only
        live_cs = callsign_from_texts(texts)
        live_conn = connected_from_texts(texts)

        if live_cs:
            self._callsign = live_cs
            self._live_source = True

        if live_conn is True or (live_conn is None and vpilot_state.read_network_connected() is True):
            if self._callsign:
                handle_plugin_payload(
                    {
                        "type": "status",
                        "connected": True,
                        "callsign": self._callsign,
                    }
                )
            else:
                handle_plugin_payload(
                    {
                        "type": "status",
                        "connected": True,
                        "callsign": STATE.callsign or "",
                    }
                )
        elif live_conn is False:
            self._callsign = None
            self._live_source = False
            handle_plugin_payload(
                {
                    "type": "status",
                    "connected": False,
                    "callsign": "",
                }
            )

        if callsign_only:
            return

        fresh = []
        for line in texts:
            key = line.lower().strip()
            if not key or key in self._seen:
                continue
            if len(key) < 3:
                continue
            fresh.append(line)

        if not self._primed:
            for line in fresh:
                self._seen.add(line.lower().strip())
            self._primed = True
            return

        for line in fresh:
            self._seen.add(line.lower().strip())
            self._emit_line(line)

        if len(self._seen) > 5000:
            self._seen = set(list(self._seen)[-2500:])

    def _emit_line(self, line):
        text = line.strip()
        lower = text.lower()
        my = (self._callsign or "").lower()

        m = MSG_RE.match(text)
        if m:
            who = m.group(2).strip()
            body = m.group(4).strip()
            if my and who.lower() == my:
                return
            if my and my not in body.lower() and my not in lower:
                return
            handle_plugin_payload(
                {
                    "type": "message",
                    "kind": "radio",
                    "from": who,
                    "body": body,
                }
            )
            return

        if "selcal" in lower:
            handle_plugin_payload(
                {
                    "type": "message",
                    "kind": "selcal",
                    "from": "SELCAL",
                    "body": text,
                }
            )
            return

        m = re.match(r"^\[(\d{1,2}:\d{2}:\d{2})\]\s+(.+)$", text)
        if m:
            rest = m.group(2).strip()
            if my and my not in rest.lower():
                return
            pm = re.match(r"^(\S+)\s*:\s*(.+)$", rest)
            if pm:
                handle_plugin_payload(
                    {
                        "type": "message",
                        "kind": "private",
                        "from": pm.group(1),
                        "body": pm.group(2),
                    }
                )
                return
            handle_plugin_payload(
                {
                    "type": "message",
                    "kind": "radio",
                    "from": "ATC",
                    "body": rest,
                }
            )
