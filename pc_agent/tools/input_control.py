"""The agent's 'second cursor and second keyboard'.

Backends (set input.backend in config.yaml):
  pynput        drives the system cursor/keyboard directly. Works out of the box,
                but shares the one Windows pointer with you (no isolation).
  mousemux      same injection, but you run MouseMux so the agent's virtual HID
                shows up as its OWN colored cursor/seat. See README "Second cursor".
  interception  per-physical-device targeting via the Interception driver (advanced;
                the only way to fully isolate the agent's input from yours).

Windows merges all pointers into one system cursor at the OS level, so a truly
independent second cursor needs MouseMux/Pluralinput (visible seat) or the
Interception driver (device-level). This module keeps a clean abstraction so the
backend can be swapped without touching the tools above it.
"""
from __future__ import annotations

import time

from ..config import Config
from ..safety import Risk
from .registry import tool

try:
    from pynput.mouse import Button, Controller as MouseController
    from pynput.keyboard import Controller as KeyboardController, Key
    _PYNPUT = True
except Exception:  # noqa: BLE001
    _PYNPUT = False


class SecondCursor:
    """Owns the agent's mouse + keyboard. One instance per process."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.backend = cfg.get("input.backend", "pynput")
        self.move_duration = float(cfg.get("input.move_duration_s", 0.25))
        if not _PYNPUT:
            raise RuntimeError("pynput not installed — run scripts/setup.bat")
        self._mouse = MouseController()
        self._kbd = KeyboardController()
        # NOTE: with backend == "mousemux", MouseMux must be running and configured
        # to bind this process's virtual device to the 'PC-Agent' seat (see README).

    def move_to(self, x: int, y: int):
        if self.move_duration <= 0:
            self._mouse.position = (x, y)
            return
        sx, sy = self._mouse.position
        steps = max(1, int(self.move_duration * 120))
        for i in range(1, steps + 1):
            t = i / steps
            self._mouse.position = (int(sx + (x - sx) * t), int(sy + (y - sy) * t))
            time.sleep(self.move_duration / steps)

    def click(self, x: int, y: int, button: str = "left", double: bool = False):
        self.move_to(x, y)
        btn = {"left": Button.left, "right": Button.right, "middle": Button.middle}[button]
        self._mouse.click(btn, 2 if double else 1)

    def type_text(self, text: str):
        self._kbd.type(text)

    def hotkey(self, *keys: str):
        resolved = [getattr(Key, k, k) for k in keys]
        for k in resolved:
            self._kbd.press(k)
        for k in reversed(resolved):
            self._kbd.release(k)


# Singleton, created lazily so importing tools never requires a display.
_CURSOR: SecondCursor | None = None


def _cursor() -> SecondCursor:
    global _CURSOR
    if _CURSOR is None:
        from ..config import load
        _CURSOR = SecondCursor(load())
    return _CURSOR


@tool(
    name="move_cursor",
    description="Move the agent's second cursor to screen coordinates (x, y) in pixels.",
    parameters={
        "x": {"type": "integer"},
        "y": {"type": "integer"},
    },
    required=["x", "y"],
    risk=Risk.INPUT,
)
def move_cursor(x: int, y: int) -> str:
    _cursor().move_to(int(x), int(y))
    return f"Moved cursor to ({x}, {y})."


@tool(
    name="click_at",
    description="Click at screen coordinates with the agent's second cursor.",
    parameters={
        "x": {"type": "integer"},
        "y": {"type": "integer"},
        "button": {"type": "string", "enum": ["left", "right", "middle"]},
        "double": {"type": "boolean", "description": "Double-click if true."},
    },
    required=["x", "y"],
    risk=Risk.INPUT,
)
def click_at(x: int, y: int, button: str = "left", double: bool = False) -> str:
    _cursor().click(int(x), int(y), button, bool(double))
    return f"{'Double-' if double else ''}{button}-clicked at ({x}, {y})."


@tool(
    name="type_text",
    description="Type text using the agent's second keyboard at the current focus.",
    parameters={"text": {"type": "string"}},
    required=["text"],
    risk=Risk.INPUT,
)
def type_text(text: str) -> str:
    _cursor().type_text(text)
    return f"Typed {len(text)} characters."


@tool(
    name="press_hotkey",
    description="Press a key combo with the agent's keyboard, e.g. ['ctrl','c'] or ['cmd','d']. "
                "Use lowercase modifier names: ctrl, alt, shift, cmd (Windows key).",
    parameters={
        "keys": {"type": "array", "items": {"type": "string"},
                 "description": "Keys to chord together, e.g. ['ctrl','shift','esc']."}
    },
    required=["keys"],
    risk=Risk.INPUT,
)
def press_hotkey(keys: list[str]) -> str:
    _cursor().hotkey(*keys)
    return f"Pressed {'+'.join(keys)}."
