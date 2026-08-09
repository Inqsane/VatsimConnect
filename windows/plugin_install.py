import os
import shutil
import sys
from pathlib import Path


def ensure_plugin_installed():
    plugins = Path(os.environ.get("LOCALAPPDATA", "")) / "vPilot" / "Plugins"
    if not plugins.exists():
        return False
    dest = plugins / "VatsimConnect.dll"
    candidates = []
    here = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates.append(here / "VatsimConnect.dll")
    candidates.append(Path(__file__).resolve().parent.parent / "dist" / "VatsimConnect.dll")
    candidates.append(Path(__file__).resolve().parent / "VatsimConnect.dll")
    src = None
    for item in candidates:
        if item.exists():
            src = item
            break
    if src is None:
        return dest.exists()
    try:
        if (not dest.exists()) or (src.stat().st_mtime > dest.stat().st_mtime + 1):
            shutil.copy2(src, dest)
        return True
    except Exception:
        return dest.exists()
