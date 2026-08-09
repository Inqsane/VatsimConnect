import tkinter as tk
from tkinter import font as tkfont
import time

import pairing
from bridge_server import STATE, local_ips


class AppUI:
    def __init__(self, root, on_new_code, on_clear_devices, on_remove_device, on_test_alert):
        self.root = root
        self.on_new_code = on_new_code
        self.on_clear_devices = on_clear_devices
        self.on_remove_device = on_remove_device
        self.on_test_alert = on_test_alert
        self.root.title("VatsimConnect")
        self.root.geometry("520x720")
        self.root.minsize(480, 640)
        self.root.configure(bg="#14171c")
        self.root.resizable(True, True)

        self.brand = tkfont.Font(family="Segoe UI Semibold", size=18)
        self.muted = tkfont.Font(family="Segoe UI", size=10)
        self.code_font = tkfont.Font(family="Consolas", size=28, weight="bold")
        self.body = tkfont.Font(family="Segoe UI", size=11)
        self.small = tkfont.Font(family="Segoe UI", size=9)

        canvas = tk.Canvas(root, bg="#14171c", highlightthickness=0)
        scroll = tk.Scrollbar(root, orient="vertical", command=canvas.yview)
        self.page = tk.Frame(canvas, bg="#14171c")
        self.page.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self.page, anchor="nw", tags="page")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        def _resize(event):
            canvas.itemconfigure("page", width=event.width)

        canvas.bind("<Configure>", _resize)

        def _wheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _wheel)

        pad = {"padx": 28}
        parent = self.page

        top = tk.Frame(parent, bg="#14171c")
        top.pack(fill="x", pady=(28, 8), **pad)
        tk.Label(top, text="VatsimConnect", font=self.brand, fg="#e8eaed", bg="#14171c").pack(anchor="w")
        tk.Label(
            top,
            text="ATC text alerts to your phone",
            font=self.muted,
            fg="#8b919a",
            bg="#14171c",
        ).pack(anchor="w", pady=(4, 0))

        rule = tk.Frame(parent, bg="#2a3038", height=1)
        rule.pack(fill="x", pady=16, **pad)

        tk.Label(parent, text="ONE-TIME CODE", font=self.small, fg="#c28b2a", bg="#14171c").pack(
            anchor="w", **pad
        )
        self.code_var = tk.StringVar(value="------")
        self.code_label = tk.Label(
            parent,
            textvariable=self.code_var,
            font=self.code_font,
            fg="#f0f2f5",
            bg="#1c2128",
            padx=18,
            pady=14,
            anchor="center",
        )
        self.code_label.pack(fill="x", pady=(8, 10), **pad)

        btn_row = tk.Frame(parent, bg="#14171c")
        btn_row.pack(fill="x", pady=16, **pad)
        self.new_btn = tk.Button(
            btn_row,
            text="New code",
            command=self._new_code,
            bg="#c28b2a",
            fg="#14171c",
            activebackground="#d4a017",
            activeforeground="#14171c",
            relief="flat",
            font=self.body,
            padx=16,
            pady=8,
            cursor="hand2",
        )
        self.new_btn.pack(side="left")
        self.test_btn = tk.Button(
            btn_row,
            text="Test alert",
            command=self._test_alert,
            bg="#2a3038",
            fg="#e8eaed",
            activebackground="#3a424c",
            activeforeground="#e8eaed",
            relief="flat",
            font=self.body,
            padx=16,
            pady=8,
            cursor="hand2",
        )
        self.test_btn.pack(side="left", padx=(10, 0))

        status_box = tk.Frame(parent, bg="#1c2128")
        status_box.pack(fill="x", pady=(4, 8), **pad)
        inner = tk.Frame(status_box, bg="#1c2128")
        inner.pack(fill="x", padx=14, pady=12)
        self.plugin_var = tk.StringVar(value="vPilot: not detected")
        self.vatsim_var = tk.StringVar(value="VATSIM: offline")
        self.ip_var = tk.StringVar(value="PC IP: —")
        for var in (self.plugin_var, self.vatsim_var, self.ip_var):
            tk.Label(inner, textvariable=var, font=self.body, fg="#c5cad1", bg="#1c2128", anchor="w").pack(
                fill="x", pady=2
            )

        head = tk.Frame(parent, bg="#14171c")
        head.pack(fill="x", pady=(16, 6), **pad)
        tk.Label(head, text="PHONES", font=self.small, fg="#c28b2a", bg="#14171c").pack(side="left")
        tk.Button(
            head,
            text="Remove all",
            command=self._clear_devices,
            bg="#2a3038",
            fg="#e8eaed",
            activebackground="#3a424c",
            activeforeground="#e8eaed",
            relief="flat",
            font=self.small,
            padx=10,
            pady=4,
            cursor="hand2",
        ).pack(side="right")

        self.devices_frame = tk.Frame(parent, bg="#1c2128")
        self.devices_frame.pack(fill="x", pady=(0, 8), **pad)
        self._devices_sig = None
        self._plugin_text = None
        self._network_text = None
        self._ip_text = None

        tk.Label(parent, text="RECENT", font=self.small, fg="#c28b2a", bg="#14171c").pack(
            anchor="w", pady=(12, 6), **pad
        )
        self.log = tk.Listbox(
            parent,
            height=8,
            bg="#1c2128",
            fg="#d7dbe0",
            selectbackground="#2a3038",
            selectforeground="#f0f2f5",
            relief="flat",
            highlightthickness=0,
            font=self.small,
            activestyle="none",
        )
        self.log.pack(fill="both", expand=True, pady=(0, 28), **pad)

        self.refresh_ips()
        self.refresh_devices()

    def _new_code(self):
        code = self.on_new_code()
        self.set_code(code)

    def _test_alert(self):
        self.on_test_alert()
        self.note("Sent test alert to phone")

    def _clear_devices(self):
        self.on_clear_devices()
        self.refresh_devices(force=True)
        self.note("Removed all phones")

    def set_code(self, code):
        clean = (code or "").strip().upper().replace(" ", "")
        if len(clean) != 6:
            clean = (clean + "------")[:6]
        self.code_var.set(clean[0:3] + "  " + clean[3:6])

    def clear_code(self):
        self.code_var.set("—  —")

    def refresh_ips(self):
        ips = local_ips()
        if ips:
            text = "PC IP: " + ips[0] + ((" · " + ips[1]) if len(ips) > 1 else "")
        else:
            text = "PC IP: —"
        if text != self._ip_text:
            self._ip_text = text
            self.ip_var.set(text)

    def _device_online(self, token):
        now = time.time()
        if token in STATE.clients:
            return True
        last = STATE.last_poll.get(token) or 0
        return (now - last) < 8

    def refresh_devices(self, force=False):
        state = pairing.load_state()
        devices = state.get("devices", [])
        sig = tuple(
            (
                d.get("token"),
                d.get("name") or "Phone",
                self._device_online(d.get("token")),
            )
            for d in devices
        )
        if not force and sig == self._devices_sig:
            return
        self._devices_sig = sig
        for child in self.devices_frame.winfo_children():
            child.destroy()
        if not devices:
            tk.Label(
                self.devices_frame,
                text="No phones paired",
                font=self.body,
                fg="#8b919a",
                bg="#1c2128",
                anchor="w",
                padx=14,
                pady=12,
            ).pack(fill="x")
            return
        for device in devices:
            row = tk.Frame(self.devices_frame, bg="#1c2128")
            row.pack(fill="x", padx=10, pady=6)
            label = device.get("name") or "Phone"
            online = self._device_online(device.get("token"))
            extra = " · connected" if online else " · offline"
            tk.Label(
                row,
                text=label + extra,
                font=self.body,
                fg="#c5cad1",
                bg="#1c2128",
                anchor="w",
            ).pack(side="left", fill="x", expand=True)
            token = device.get("token")
            tk.Button(
                row,
                text="Remove",
                command=lambda t=token: self._remove_one(t),
                bg="#2a3038",
                fg="#e8eaed",
                activebackground="#3a424c",
                relief="flat",
                font=self.small,
                padx=10,
                pady=3,
                cursor="hand2",
            ).pack(side="right")

    def _remove_one(self, token):
        self.on_remove_device(token)
        self.refresh_devices(force=True)
        self.note("Removed phone")

    def set_plugin(self, ready, watching=False, vpilot_open=False):
        if ready:
            text = "vPilot: linked (plugin)"
        elif watching:
            text = "vPilot: watching live"
        elif vpilot_open:
            text = "vPilot: open · restart vPilot to load plugin"
        else:
            text = "vPilot: not detected"
        if text != self._plugin_text:
            self._plugin_text = text
            self.plugin_var.set(text)

    def set_network(self, connected, callsign):
        clean = None
        if callsign:
            text = str(callsign).strip()
            if text and text.lower() not in ("null", "none", "undefined"):
                clean = text
        if connected and clean:
            text = "VATSIM: " + clean
        elif connected:
            text = "VATSIM: online"
        else:
            text = "VATSIM: offline"
        if text != self._network_text:
            self._network_text = text
            self.vatsim_var.set(text)

    def add_message(self, kind, from_who, body):
        line = f"{kind.upper()}  {from_who}: {body}"
        if len(line) > 72:
            line = line[:69] + "..."
        self.log.insert(0, line)
        if self.log.size() > 40:
            self.log.delete(40, tk.END)

    def note(self, text):
        self.log.insert(0, text)
