import json
import os
import random
import secrets
import time
from pathlib import Path

ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_LEN = 6
CODE_TTL = 1800
STORE = Path(os.environ.get("APPDATA", ".")) / "VatsimConnect" / "session.json"


def _ensure_dir():
    STORE.parent.mkdir(parents=True, exist_ok=True)


def load_state():
    _ensure_dir()
    if not STORE.exists():
        return {"devices": [], "pending_code": None, "pending_until": 0}
    try:
        with STORE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if "devices" not in data:
            data["devices"] = []
        return data
    except Exception:
        return {"devices": [], "pending_code": None, "pending_until": 0}


def save_state(state):
    _ensure_dir()
    with STORE.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def make_code():
    return "".join(random.choice(ALPHABET) for _ in range(CODE_LEN))


def issue_code(state):
    code = make_code()
    while len(code) != CODE_LEN:
        code = make_code()
    state["pending_code"] = code
    state["pending_until"] = time.time() + CODE_TTL
    save_state(state)
    return code


def code_valid(state, code):
    if not code or not state.get("pending_code"):
        return False
    if time.time() > float(state.get("pending_until") or 0):
        return False
    return code.strip().upper().replace(" ", "") == state["pending_code"]


def consume_code(state, code, device_name):
    if not code_valid(state, code):
        return None
    token = secrets.token_urlsafe(24)
    device = {
        "token": token,
        "name": device_name or "Android",
        "paired_at": time.time(),
    }
    state["devices"].append(device)
    state["pending_code"] = None
    state["pending_until"] = 0
    save_state(state)
    return device


def find_device(state, token):
    for device in state.get("devices", []):
        if device.get("token") == token:
            return device
    return None


def remove_device(state, token):
    state["devices"] = [d for d in state.get("devices", []) if d.get("token") != token]
    save_state(state)


def clear_devices(state):
    state["devices"] = []
    save_state(state)
