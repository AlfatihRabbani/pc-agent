"""Windows Settings + Control Panel control via ms-settings: URIs and control.exe."""
from __future__ import annotations

import subprocess

from ..safety import Risk
from .registry import tool

# Friendly name -> ms-settings: URI (the modern Settings app)
SETTINGS_PAGES = {
    "about": "ms-settings:about",
    "display": "ms-settings:display",
    "sound": "ms-settings:sound",
    "notifications": "ms-settings:notifications",
    "power": "ms-settings:powersleep",
    "battery": "ms-settings:batterysaver",
    "storage": "ms-settings:storagesense",
    "bluetooth": "ms-settings:bluetooth",
    "wifi": "ms-settings:network-wifi",
    "network": "ms-settings:network-status",
    "vpn": "ms-settings:network-vpn",
    "windows_update": "ms-settings:windowsupdate",
    "apps": "ms-settings:appsfeatures",
    "default_apps": "ms-settings:defaultapps",
    "startup": "ms-settings:startupapps",
    "personalization": "ms-settings:personalization",
    "background": "ms-settings:personalization-background",
    "themes": "ms-settings:themes",
    "accounts": "ms-settings:yourinfo",
    "windows_security": "ms-settings:windowsdefender",
    "privacy": "ms-settings:privacy",
    "date_time": "ms-settings:dateandtime",
    "language": "ms-settings:regionlanguage",
    "developers": "ms-settings:developers",
    "recovery": "ms-settings:recovery",
}

# Friendly name -> classic Control Panel applet
CONTROL_PANEL_APPLETS = {
    "programs_and_features": "appwiz.cpl",
    "uninstall_programs": "appwiz.cpl",
    "network_connections": "ncpa.cpl",
    "sound": "mmsys.cpl",
    "power_options": "powercfg.cpl",
    "system": "sysdm.cpl",
    "mouse": "main.cpl",
    "device_manager": "devmgmt.msc",
    "disk_management": "diskmgmt.msc",
    "services": "services.msc",
    "firewall": "firewall.cpl",
    "user_accounts": "netplwiz",
    "region": "intl.cpl",
}


@tool(
    name="open_settings",
    description="Open a Windows Settings page by name. Examples: 'about', 'display', "
                "'wifi', 'windows_update', 'apps', 'bluetooth', 'power'.",
    parameters={
        "page": {
            "type": "string",
            "description": f"Settings page. One of: {', '.join(SETTINGS_PAGES)}.",
        }
    },
    required=["page"],
    risk=Risk.SETTINGS,
)
def open_settings(page: str) -> str:
    key = page.strip().lower().replace(" ", "_")
    uri = SETTINGS_PAGES.get(key)
    if not uri:
        return (f"Unknown settings page '{page}'. "
                f"Available: {', '.join(sorted(SETTINGS_PAGES))}")
    subprocess.Popen(["cmd", "/c", "start", uri], shell=False)
    return f"Opened Settings page: {key} ({uri})"


@tool(
    name="open_settings_uri",
    description="Open ANY Windows Settings page by its raw ms-settings URI key, for pages not "
                "covered by open_settings. Example key: 'nightlight', 'mobile-devices', "
                "'crossdevice', 'windowsinsider'. Pass just the part after 'ms-settings:'.",
    parameters={
        "uri_key": {"type": "string", "description": "The ms-settings: key, e.g. 'nightlight'."}
    },
    required=["uri_key"],
    risk=Risk.SETTINGS,
)
def open_settings_uri(uri_key: str) -> str:
    key = uri_key.strip().replace("ms-settings:", "").lstrip(":")
    subprocess.Popen(["cmd", "/c", "start", f"ms-settings:{key}"], shell=False)
    return f"Opened ms-settings:{key}"


@tool(
    name="open_control_panel",
    description="Open a classic Control Panel applet by name, e.g. 'programs_and_features', "
                "'device_manager', 'network_connections', 'services', 'power_options'.",
    parameters={
        "applet": {
            "type": "string",
            "description": f"Applet. One of: {', '.join(CONTROL_PANEL_APPLETS)}.",
        }
    },
    required=["applet"],
    risk=Risk.SETTINGS,
)
def open_control_panel(applet: str) -> str:
    key = applet.strip().lower().replace(" ", "_")
    target = CONTROL_PANEL_APPLETS.get(key)
    if not target:
        return (f"Unknown applet '{applet}'. "
                f"Available: {', '.join(sorted(CONTROL_PANEL_APPLETS))}")
    # 'start' resolves .cpl (Control Panel), .msc (MMC snap-in) and bare exes uniformly.
    subprocess.Popen(["cmd", "/c", "start", "", target], shell=False)
    return f"Opened Control Panel: {key} ({target})"
