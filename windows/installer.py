"""
VatsimConnect installer / uninstaller.

Bundled as VatsimConnect-Setup.exe. Installs the app under
%LOCALAPPDATA%\\Programs\\VatsimConnect, creates Desktop + Start Menu
shortcuts, installs the vPilot plugin, and registers Add/Remove Programs.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

APP_NAME = "VatsimConnect"
APP_PUBLISHER = "Inqsane"
APP_VERSION = "1.0.0"


def resource_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def install_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / APP_NAME


def desktop_dir() -> Path:
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "[Environment]::GetFolderPath('Desktop')",
            ],
            text=True,
        ).strip()
        if out:
            return Path(out)
    except Exception:
        pass
    return Path.home() / "Desktop"


def start_menu_dir() -> Path:
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "[Environment]::GetFolderPath('Programs')",
            ],
            text=True,
        ).strip()
        if out:
            return Path(out)
    except Exception:
        pass
    return (
        Path(os.environ.get("APPDATA", str(Path.home())))
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
    )


def bundled_files():
    base = resource_dir()
    exe = base / "VatsimConnect.exe"
    dll = base / "VatsimConnect.dll"
    icon = base / "icon.ico"
    return exe, dll, icon


def create_shortcut(link_path: Path, target: Path, workdir: Path, icon: Path | None):
    link_path.parent.mkdir(parents=True, exist_ok=True)
    icon_part = str(icon) if icon and icon.exists() else str(target)
    ps = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{str(link_path).replace("'", "''")}')
$s.TargetPath = '{str(target).replace("'", "''")}'
$s.WorkingDirectory = '{str(workdir).replace("'", "''")}'
$s.IconLocation = '{icon_part.replace("'", "''")}'
$s.Description = 'ATC alerts from vPilot to your phone'
$s.Save()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        check=False,
        capture_output=True,
        text=True,
    )


def install_plugin(dll_src: Path) -> bool:
    plugins = Path(os.environ.get("LOCALAPPDATA", "")) / "vPilot" / "Plugins"
    if not plugins.exists():
        return False
    try:
        shutil.copy2(dll_src, plugins / "VatsimConnect.dll")
        return True
    except Exception:
        return False


def write_uninstall_script(dest: Path, exe_path: Path):
    # Re-use this setup binary for uninstall when possible; fall back to a bat.
    setup = dest / "VatsimConnect-Setup.exe"
    bat = dest / "Uninstall.bat"
    if setup.exists():
        bat.write_text(
            f'@echo off\r\n"{setup}" --uninstall\r\n',
            encoding="utf-8",
        )
    else:
        bat.write_text(
            "\r\n".join(
                [
                    "@echo off",
                    f'rmdir /s /q "{dest}"',
                    f'del /q "%USERPROFILE%\\Desktop\\{APP_NAME}.lnk" 2>nul',
                    f'del /q "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\{APP_NAME}.lnk" 2>nul',
                    "exit /b 0",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    return bat


def register_arp(dest: Path, exe_path: Path, uninstall: Path):
    try:
        import winreg
    except ImportError:
        return
    key_path = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}"
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, APP_PUBLISHER)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(dest))
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(exe_path))
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{uninstall}"')
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)


def unregister_arp():
    try:
        import winreg

        winreg.DeleteKey(
            winreg.HKEY_CURRENT_USER,
            rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}",
        )
    except Exception:
        pass


def do_install(create_desktop: bool = True, launch: bool = True) -> Path:
    exe_src, dll_src, icon_src = bundled_files()
    if not exe_src.exists():
        raise FileNotFoundError("VatsimConnect.exe missing from installer package")

    dest = install_root()
    dest.mkdir(parents=True, exist_ok=True)

    exe_dst = dest / "VatsimConnect.exe"
    dll_dst = dest / "VatsimConnect.dll"
    icon_dst = dest / "icon.ico"

    shutil.copy2(exe_src, exe_dst)
    if dll_src.exists():
        shutil.copy2(dll_src, dll_dst)
        install_plugin(dll_dst)
    if icon_src.exists():
        shutil.copy2(icon_src, icon_dst)

    # Copy this setup EXE into the install folder for later uninstall.
    try:
        if getattr(sys, "frozen", False):
            shutil.copy2(sys.executable, dest / "VatsimConnect-Setup.exe")
    except Exception:
        pass

    uninstall = write_uninstall_script(dest, exe_dst)
    setup_dst = dest / "VatsimConnect-Setup.exe"
    if setup_dst.exists():
        register_arp(dest, exe_dst, f'"{setup_dst}" --uninstall')
    else:
        register_arp(dest, exe_dst, f'"{uninstall}"')

    create_shortcut(
        start_menu_dir() / f"{APP_NAME}.lnk",
        exe_dst,
        dest,
        icon_dst if icon_dst.exists() else exe_dst,
    )
    if create_desktop:
        create_shortcut(
            desktop_dir() / f"{APP_NAME}.lnk",
            exe_dst,
            dest,
            icon_dst if icon_dst.exists() else exe_dst,
        )

    if launch:
        subprocess.Popen([str(exe_dst)], cwd=str(dest))

    return dest


def do_uninstall():
    dest = install_root()
    for link in (
        desktop_dir() / f"{APP_NAME}.lnk",
        start_menu_dir() / f"{APP_NAME}.lnk",
    ):
        try:
            if link.exists():
                link.unlink()
        except Exception:
            pass
    unregister_arp()
    # Remove plugin copy (optional — leave if user wants; remove for clean uninstall)
    plugin = Path(os.environ.get("LOCALAPPDATA", "")) / "vPilot" / "Plugins" / "VatsimConnect.dll"
    try:
        if plugin.exists():
            plugin.unlink()
    except Exception:
        pass
    # Delete install folder after short delay so this process can exit if running from there.
    if dest.exists():
        cmd = f'ping 127.0.0.1 -n 2 >nul & rmdir /s /q "{dest}"'
        subprocess.Popen(["cmd", "/c", cmd], creationflags=subprocess.CREATE_NO_WINDOW)


class InstallerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} Setup")
        self.root.geometry("420x320")
        self.root.resizable(False, False)
        self.root.configure(bg="#14171c")
        try:
            icon = resource_dir() / "icon.ico"
            if icon.exists():
                self.root.iconbitmap(default=str(icon))
        except Exception:
            pass

        pad = {"padx": 28}
        tk.Label(
            self.root,
            text=APP_NAME,
            font=("Segoe UI Semibold", 18),
            fg="#e8eaed",
            bg="#14171c",
        ).pack(anchor="w", pady=(28, 4), **pad)
        tk.Label(
            self.root,
            text="Install the Windows bridge and create a Desktop shortcut,\nor remove an existing install.",
            font=("Segoe UI", 10),
            fg="#8b919a",
            bg="#14171c",
            wraplength=360,
            justify="left",
        ).pack(anchor="w", **pad)

        self.desktop_var = tk.BooleanVar(value=True)
        self.launch_var = tk.BooleanVar(value=True)
        opts = tk.Frame(self.root, bg="#14171c")
        opts.pack(fill="x", pady=(18, 8), **pad)
        tk.Checkbutton(
            opts,
            text="Create Desktop shortcut",
            variable=self.desktop_var,
            bg="#14171c",
            fg="#c5cad1",
            activebackground="#14171c",
            activeforeground="#e8eaed",
            selectcolor="#1c2128",
            font=("Segoe UI", 10),
        ).pack(anchor="w")
        tk.Checkbutton(
            opts,
            text="Launch when finished",
            variable=self.launch_var,
            bg="#14171c",
            fg="#c5cad1",
            activebackground="#14171c",
            activeforeground="#e8eaed",
            selectcolor="#1c2128",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(4, 0))

        installed = (install_root() / "VatsimConnect.exe").exists()
        status = "Currently installed" if installed else "Not installed yet"
        tk.Label(
            self.root,
            text=status + "\n" + str(install_root()),
            font=("Segoe UI", 9),
            fg="#8b919a",
            bg="#14171c",
            justify="left",
        ).pack(anchor="w", pady=(8, 0), **pad)

        row = tk.Frame(self.root, bg="#14171c")
        row.pack(fill="x", pady=20, padx=28)
        tk.Button(
            row,
            text="Remove",
            command=self._remove,
            bg="#2a3038",
            fg="#e8eaed",
            activebackground="#3a424c",
            activeforeground="#e8eaed",
            relief="flat",
            font=("Segoe UI", 11),
            padx=18,
            pady=8,
            cursor="hand2",
            state=("normal" if installed else "disabled"),
        ).pack(side="left")
        tk.Button(
            row,
            text="Install",
            command=self._install,
            bg="#c28b2a",
            fg="#14171c",
            activebackground="#d4a017",
            relief="flat",
            font=("Segoe UI", 11),
            padx=18,
            pady=8,
            cursor="hand2",
        ).pack(side="right")

    def _install(self):
        try:
            do_install(create_desktop=self.desktop_var.get(), launch=self.launch_var.get())
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Install failed:\n{ex}")
            return
        messagebox.showinfo(
            APP_NAME,
            "Installed.\n\nUse the Desktop / Start Menu shortcut to open VatsimConnect.\n"
            "Restart vPilot once so the plugin can load.",
        )
        self.root.destroy()

    def _remove(self):
        if not messagebox.askyesno(APP_NAME, f"Remove {APP_NAME} from this PC?"):
            return
        try:
            do_uninstall()
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Remove failed:\n{ex}")
            return
        messagebox.showinfo(APP_NAME, f"{APP_NAME} was removed.")
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--silent", action="store_true")
    args, _ = parser.parse_known_args()

    if args.uninstall:
        if not args.silent:
            root = tk.Tk()
            root.withdraw()
            ok = messagebox.askyesno(APP_NAME, f"Uninstall {APP_NAME}?")
            root.destroy()
            if not ok:
                return
        do_uninstall()
        return

    if args.silent:
        do_install(create_desktop=True, launch=False)
        return

    InstallerApp().run()


if __name__ == "__main__":
    main()
