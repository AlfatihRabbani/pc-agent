"""Screen capture — lets the agent 'look at the screen'."""
from __future__ import annotations

import time
from pathlib import Path

from ..safety import Risk
from .registry import tool

_SHOTS = Path(__file__).resolve().parent.parent.parent / "logs" / "screenshots"


@tool(
    name="take_screenshot",
    description="Capture the current screen to a PNG and return the file path. Use this to "
                "'look at the screen' so a vision model can read or analyze what's shown.",
    parameters={},
    required=[],
    risk=Risk.READ,
)
def take_screenshot() -> str:
    import pyautogui
    _SHOTS.mkdir(parents=True, exist_ok=True)
    path = _SHOTS / f"screen_{int(time.time())}.png"
    img = pyautogui.screenshot()
    img.save(path)
    return str(path)
