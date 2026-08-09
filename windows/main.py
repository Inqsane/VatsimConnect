import tkinter as tk

import pairing
from app_ui import AppUI
from bridge_server import (
    STATE,
    open_firewall,
    start_async_servers,
    start_http,
    start_phone_http,
    start_udp_discovery,
)
from plugin_install import ensure_plugin_installed
from ui_watch import UiWatcher


def main():
    ensure_plugin_installed()
    open_firewall()
    start_http()
    start_phone_http()
    start_udp_discovery()
    start_async_servers()
    watcher = UiWatcher()
    watcher.start()

    root = tk.Tk()
    state = pairing.load_state()
    if pairing.code_valid(state, state.get("pending_code")):
        code = state["pending_code"]
    else:
        code = pairing.issue_code(state)

    def new_code():
        return pairing.issue_code(pairing.load_state())

    def clear_devices():
        st = pairing.load_state()
        pairing.clear_devices(st)

    def remove_device(token):
        st = pairing.load_state()
        pairing.remove_device(st, token)

    def test_alert():
        from bridge_server import handle_plugin_payload

        handle_plugin_payload(
            {
                "type": "message",
                "kind": "private",
                "from": "TEST_ATC",
                "body": "VatsimConnect test message",
            }
        )

    ui = AppUI(
        root,
        on_new_code=new_code,
        on_clear_devices=clear_devices,
        on_remove_device=remove_device,
        on_test_alert=test_alert,
    )
    ui.set_code(code)
    ui.set_plugin(False)
    ui.set_network(False, None)

    def on_event(event):
        def apply():
            et = event.get("type")
            if et == "plugin":
                ui.set_plugin(True)
            elif et == "status":
                ui.set_network(bool(event.get("connected")), event.get("callsign"))
            elif et == "message":
                ui.add_message(event.get("kind") or "msg", event.get("from") or "?", event.get("body") or "")
            elif et == "paired":
                ui.note("Paired: " + (event.get("name") or "phone"))
                ui.clear_code()
                ui.refresh_devices(force=True)

        root.after(0, apply)

    STATE.on_event = on_event

    def tick():
        ui.refresh_devices()
        ui.refresh_ips()
        ui.set_plugin(
            STATE.plugin_ready,
            watching=watcher.active and not STATE.plugin_ready,
            vpilot_open=watcher.vpilot_seen,
        )
        ui.set_network(STATE.network_connected, STATE.callsign)
        root.after(1500, tick)

    root.after(1500, tick)
    root.mainloop()


if __name__ == "__main__":
    main()
