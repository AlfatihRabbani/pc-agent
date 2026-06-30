"""Wi-Fi and network control via netsh."""
from __future__ import annotations

import os
import tempfile

from ..safety import Risk
from .registry import tool
from ._shell import run


@tool(
    name="get_wifi_status",
    description="Show current Wi-Fi connection: SSID, signal strength, and state.",
    parameters={},
    required=[],
    risk=Risk.READ,
)
def get_wifi_status() -> str:
    out = run(["netsh", "wlan", "show", "interfaces"], timeout=20)
    keep = [ln.strip() for ln in out.splitlines()
            if any(k in ln for k in ("SSID", "State", "Signal", "Radio", "Authentication"))
            and "BSSID" not in ln]
    return "\n".join(keep) or out[:400]


@tool(
    name="list_wifi_networks",
    description="List Wi-Fi networks currently in range.",
    parameters={},
    required=[],
    risk=Risk.READ,
)
def list_wifi_networks() -> str:
    out = run(["netsh", "wlan", "show", "networks"], timeout=25)
    ssids = [ln.split(":", 1)[1].strip() for ln in out.splitlines()
             if ln.strip().startswith("SSID") and ":" in ln]
    ssids = [s for s in ssids if s]
    return "In range:\n" + "\n".join(f"  - {s}" for s in ssids) if ssids else "No networks found."


@tool(
    name="list_saved_wifi",
    description="List saved Wi-Fi profiles this PC can auto-connect to.",
    parameters={},
    required=[],
    risk=Risk.READ,
)
def list_saved_wifi() -> str:
    out = run(["netsh", "wlan", "show", "profiles"], timeout=20)
    names = [ln.split(":", 1)[1].strip() for ln in out.splitlines()
             if "All User Profile" in ln and ":" in ln]
    return "Saved:\n" + "\n".join(f"  - {n}" for n in names) if names else "No saved profiles."


@tool(
    name="connect_wifi",
    description="Connect to a Wi-Fi network. For a saved network just give ssid; for a new "
                "one also give password (creates a WPA2 profile and connects).",
    parameters={
        "ssid": {"type": "string", "description": "Network name."},
        "password": {"type": "string", "description": "Password (omit for a saved network)."},
    },
    required=["ssid"],
    risk=Risk.SETTINGS,
)
def connect_wifi(ssid: str, password: str = "") -> str:
    if password:
        xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>{ssid}</name>
  <SSIDConfig><SSID><name>{ssid}</name></SSID></SSIDConfig>
  <connectionType>ESS</connectionType><connectionMode>auto</connectionMode>
  <MSM><security>
    <authEncryption><authentication>WPA2PSK</authentication><encryption>AES</encryption>
      <useOneX>false</useOneX></authEncryption>
    <sharedKey><keyType>passPhrase</keyType><protected>false</protected>
      <keyMaterial>{password}</keyMaterial></sharedKey>
  </security></MSM>
</WLANProfile>"""
        fd, path = tempfile.mkstemp(suffix=".xml")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(xml)
            run(["netsh", "wlan", "add", "profile", f"filename={path}"], timeout=20)
        finally:
            os.unlink(path)
    out = run(["netsh", "wlan", "connect", f"name={ssid}", f"ssid={ssid}"], timeout=25)
    return out or f"Connecting to {ssid}…"


@tool(
    name="disconnect_wifi",
    description="Disconnect from the current Wi-Fi network.",
    parameters={},
    required=[],
    risk=Risk.SETTINGS,
)
def disconnect_wifi() -> str:
    return run(["netsh", "wlan", "disconnect"], timeout=20) or "Disconnected."


@tool(
    name="set_wifi_adapter",
    description="Enable or disable the Wi-Fi adapter entirely (needs admin rights).",
    parameters={"enabled": {"type": "boolean", "description": "True to enable, False to disable."}},
    required=["enabled"],
    risk=Risk.SETTINGS,
)
def set_wifi_adapter(enabled: bool) -> str:
    state = "enable" if enabled else "disable"
    out = run(["netsh", "interface", "set", "interface", "Wi-Fi", state], timeout=20)
    if "requires elevation" in out.lower() or "Access is denied" in out:
        return "Need admin rights to toggle the adapter. Run the agent as administrator."
    return out or f"Wi-Fi adapter {state}d."
