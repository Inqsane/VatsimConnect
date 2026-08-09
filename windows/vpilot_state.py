import os
import re
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

VPILOT_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "vPilot"
CALLSIGN_ATTR = re.compile(r'Callsign="([^"]+)"', re.IGNORECASE)


def _today_log():
    stamp = datetime.now().strftime("%Y%m%d")
    return VPILOT_DIR / f"log{stamp}.txt"


def read_last_callsign():
    cfg = VPILOT_DIR / "vPilotConfig.xml"
    if not cfg.exists():
        return None
    try:
        raw = cfg.read_text(encoding="utf-8", errors="ignore")
        # Prefer LastConnectInfo specifically.
        m = re.search(
            r'<LastConnectInfo[^>]*Callsign="([^"]+)"',
            raw,
            re.IGNORECASE,
        )
        if m:
            return m.group(1).strip().upper() or None
        m = CALLSIGN_ATTR.search(raw)
        if m:
            return m.group(1).strip().upper() or None
    except Exception:
        pass
    try:
        root = ET.parse(cfg).getroot()
        node = root.find("LastConnectInfo")
        if node is not None:
            cs = (node.get("Callsign") or "").strip().upper()
            return cs or None
    except Exception:
        pass
    return None


def read_network_connected():
    """True/False/None from today's vPilot log (last connect/disconnect line)."""
    log = _today_log()
    if not log.exists():
        return None
    try:
        # Read tail cheaply.
        data = log.read_bytes()
        if len(data) > 200_000:
            data = data[-200_000:]
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        return None
    connected = None
    for line in text.splitlines():
        lower = line.lower()
        if "connected to network" in lower and "disconnected" not in lower:
            connected = True
        elif "disconnected from network" in lower:
            connected = False
    return connected


def snapshot():
    return {
        "connected": read_network_connected(),
        "callsign": read_last_callsign(),
    }
