"""System audio control — master volume and mute (via Windows Core Audio / pycaw)."""
from __future__ import annotations

from ..safety import Risk
from .registry import tool


def _endpoint():
    """Get the default speaker's IAudioEndpointVolume interface (modern pycaw)."""
    from pycaw.utils import AudioUtilities
    return AudioUtilities.GetSpeakers().EndpointVolume


@tool(
    name="get_volume",
    description="Get the current system master volume (0-100) and mute state.",
    parameters={},
    required=[],
    risk=Risk.READ,
)
def get_volume() -> str:
    try:
        ep = _endpoint()
        pct = round(ep.GetMasterVolumeLevelScalar() * 100)
        muted = bool(ep.GetMute())
        return f"Volume: {pct}%{' (muted)' if muted else ''}"
    except Exception as e:  # noqa: BLE001
        return f"Could not read volume: {e}"


@tool(
    name="set_volume",
    description="Set the system master volume to an absolute level from 0 to 100 percent.",
    parameters={"level": {"type": "integer", "description": "Volume 0-100."}},
    required=["level"],
    risk=Risk.SETTINGS,
)
def set_volume(level: int) -> str:
    import ctypes
    import time
    level = max(0, min(100, int(level)))
    try:
        ep = _endpoint()
        cur = round(ep.GetMasterVolumeLevelScalar() * 100)
        # Tap the media volume keys so Windows shows its on-screen volume overlay,
        # animating from the current level toward the target (~2% per tap). Fast.
        vk = 0xAF if level >= cur else 0xAE          # VK_VOLUME_UP / VK_VOLUME_DOWN
        u32 = ctypes.windll.user32
        for _ in range(int(round(abs(level - cur) / 2.0))):
            u32.keybd_event(vk, 0, 0, 0)
            u32.keybd_event(vk, 0, 2, 0)             # KEYEVENTF_KEYUP
            time.sleep(0.012)
        ep.SetMasterVolumeLevelScalar(level / 100.0, None)   # snap to the exact target
        return f"Volume set to {level}% (shown on the volume overlay)."
    except Exception as e:  # noqa: BLE001
        return f"Could not set volume: {e}"


@tool(
    name="set_mute",
    description="Mute or unmute the system audio.",
    parameters={"mute": {"type": "boolean", "description": "True to mute, False to unmute."}},
    required=["mute"],
    risk=Risk.SETTINGS,
)
def set_mute(mute: bool) -> str:
    try:
        _endpoint().SetMute(1 if mute else 0, None)
        return "Muted." if mute else "Unmuted."
    except Exception as e:  # noqa: BLE001
        return f"Could not change mute: {e}"
