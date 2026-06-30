"""Display control — brightness (WMI), resolution (Win32), and display info.

Note: WMI brightness works on laptop panels and some monitors; many desktop
monitors only accept brightness over DDC/CI and will report 'not supported'.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from ..safety import Risk
from .registry import tool
from ._shell import powershell


# ── brightness (WMI) ─────────────────────────────────────────────
@tool(
    name="get_brightness",
    description="Get the current display brightness percent (laptop/integrated panels).",
    parameters={},
    required=[],
    risk=Risk.READ,
)
def get_brightness() -> str:
    out = powershell(
        "(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness "
        "-ErrorAction Stop).CurrentBrightness"
    )
    if not out or "Exception" in out or "Error" in out:
        return "Brightness not available via WMI (external monitors use DDC/CI)."
    return f"Brightness: {out.strip()}%"


@tool(
    name="set_brightness",
    description="Set display brightness to an absolute percent 0-100 (laptop/integrated panels).",
    parameters={"level": {"type": "integer", "description": "Brightness 0-100."}},
    required=["level"],
    risk=Risk.SETTINGS,
)
def set_brightness(level: int) -> str:
    level = max(0, min(100, int(level)))
    out = powershell(
        "$m = Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods "
        f"-ErrorAction SilentlyContinue; if ($m) {{ $m.WmiSetBrightness(1, {level}); 'ok' }} "
        "else { 'unsupported' }"
    )
    if "ok" in out:
        return f"Brightness set to {level}%."
    return "Brightness control not supported on this display (likely an external monitor)."


# ── resolution / display info (Win32) ────────────────────────────
class _DEVMODE(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32), ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD), ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD), ("dmFields", wintypes.DWORD),
        ("dmOrientation", ctypes.c_short), ("dmPaperSize", ctypes.c_short),
        ("dmPaperLength", ctypes.c_short), ("dmPaperWidth", ctypes.c_short),
        ("dmScale", ctypes.c_short), ("dmCopies", ctypes.c_short),
        ("dmDefaultSource", ctypes.c_short), ("dmPrintQuality", ctypes.c_short),
        ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short), ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short), ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", wintypes.WORD), ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD), ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD), ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD), ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD), ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD), ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD), ("dmPanningHeight", wintypes.DWORD),
    ]


_ENUM_CURRENT = -1
_DM_PELSWIDTH = 0x80000
_DM_PELSHEIGHT = 0x100000


@tool(
    name="get_display_info",
    description="Get current screen resolution, refresh rate, color depth and monitor count.",
    parameters={},
    required=[],
    risk=Risk.READ,
)
def get_display_info() -> str:
    user32 = ctypes.windll.user32
    dm = _DEVMODE()
    dm.dmSize = ctypes.sizeof(_DEVMODE)
    user32.EnumDisplaySettingsW(None, _ENUM_CURRENT, ctypes.byref(dm))
    monitors = user32.GetSystemMetrics(80)  # SM_CMONITORS
    return (f"Resolution: {dm.dmPelsWidth}x{dm.dmPelsHeight} @ {dm.dmDisplayFrequency}Hz, "
            f"{dm.dmBitsPerPel}-bit color, monitors: {monitors}")


@tool(
    name="set_resolution",
    description="Set the primary display resolution, e.g. width 1920 height 1080.",
    parameters={
        "width": {"type": "integer"},
        "height": {"type": "integer"},
    },
    required=["width", "height"],
    risk=Risk.SETTINGS,
)
def set_resolution(width: int, height: int) -> str:
    user32 = ctypes.windll.user32
    dm = _DEVMODE()
    dm.dmSize = ctypes.sizeof(_DEVMODE)
    user32.EnumDisplaySettingsW(None, _ENUM_CURRENT, ctypes.byref(dm))
    dm.dmPelsWidth, dm.dmPelsHeight = int(width), int(height)
    dm.dmFields = _DM_PELSWIDTH | _DM_PELSHEIGHT
    rc = user32.ChangeDisplaySettingsExW(None, ctypes.byref(dm), None, 0, None)
    if rc == 0:  # DISP_CHANGE_SUCCESSFUL
        return f"Resolution set to {width}x{height}."
    return f"Resolution change failed (code {rc}); {width}x{height} may be unsupported."
