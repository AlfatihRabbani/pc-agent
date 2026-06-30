"""Focus Firefox, perform one UI action with the PC-Agent executor, screenshot.

Run with pythonw.exe (no console window) so nothing steals foreground from the
target before the action lands. Always writes a fresh screenshot to
logs/screenshots/last.png and a one-line status to logs/ui_status.txt.

    pythonw scripts/ui_do.py shot
    pythonw scripts/ui_do.py click 710 860
    pythonw scripts/ui_do.py clicktype 760 430 Alice Example
    pythonw scripts/ui_do.py type some words here
    pythonw scripts/ui_do.py key ctrl a
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# DPI aware so screenshot + click coords are all physical pixels.
try:
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        ctypes.windll.user32.SetProcessDPIAware()
except Exception:  # noqa: BLE001
    pass

from ctypes import wintypes  # noqa: E402

user32 = ctypes.windll.user32
SHOTS = ROOT / "logs" / "screenshots"
STATUS = ROOT / "logs" / "ui_status.txt"


def find_window(substr: str):
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if substr.lower() in buf.value.lower():
                    found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else (None, None)


def focus(substr="Mozilla Firefox") -> str:
    hwnd, title = find_window(substr)
    if not hwnd:
        return f"NO WINDOW '{substr}'"
    # AttachThreadInput unlocks foreground without sending any keystroke
    # (the ALT trick toggles Firefox's menu bar and shifts the page — avoid it).
    kernel32 = ctypes.windll.kernel32
    cur = kernel32.GetCurrentThreadId()
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    tgt_thread = user32.GetWindowThreadProcessId(hwnd, None)
    user32.AttachThreadInput(cur, fg_thread, True)
    user32.AttachThreadInput(cur, tgt_thread, True)
    user32.ShowWindow(hwnd, 9)            # SW_RESTORE
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    user32.AttachThreadInput(cur, fg_thread, False)
    user32.AttachThreadInput(cur, tgt_thread, False)
    time.sleep(0.45)
    return f"focused: {title}"


def shot() -> str:
    import pyautogui
    SHOTS.mkdir(parents=True, exist_ok=True)
    p = SHOTS / "last.png"
    pyautogui.screenshot().save(p)
    return str(p)


def main():
    from pc_agent.tools import get
    a = sys.argv[1:]
    cmd = a[0] if a else "shot"
    log = []

    if cmd == "shot":
        log.append(shot())
    elif cmd == "click":
        x, y = int(a[1]), int(a[2])
        log.append(focus())
        log.append(get("click_at").fn(x=x, y=y))
        time.sleep(0.7)
        log.append(shot())
    elif cmd == "clicktype":
        x, y, text = int(a[1]), int(a[2]), " ".join(a[3:])
        log.append(focus())
        log.append(get("click_at").fn(x=x, y=y))
        time.sleep(0.35)
        log.append(get("type_text").fn(text=text))
        time.sleep(0.5)
        log.append(shot())
    elif cmd == "scroll":
        import pyautogui
        amount = int(a[1]) if len(a) > 1 else -600
        log.append(focus())
        pyautogui.moveTo(760, 400)
        pyautogui.scroll(amount)            # negative = down
        time.sleep(0.5)
        log.append(f"scrolled {amount}")
        log.append(shot())
    elif cmd == "upload":
        path = " ".join(a[1:])
        used = None
        for t in ("File Upload", "Open"):
            r = focus(t)
            if not r.startswith("NO WINDOW"):
                used = t
                log.append(r)
                break
        log.append(f"dialog={used}")
        time.sleep(0.3)
        get("click_at").fn(x=665, y=831)     # File name field
        time.sleep(0.3)
        get("type_text").fn(text=path)
        time.sleep(0.3)
        get("press_hotkey").fn(keys=["enter"])
        time.sleep(1.6)
        log.append(f"typed path {path}")
        log.append(shot())
    elif cmd == "type":
        log.append(focus())
        log.append(get("type_text").fn(text=" ".join(a[1:])))
        time.sleep(0.5)
        log.append(shot())
    elif cmd == "key":
        log.append(focus())
        log.append(get("press_hotkey").fn(keys=a[1:]))
        time.sleep(0.5)
        log.append(shot())
    else:
        log.append(f"unknown cmd {cmd}")

    STATUS.write_text("\n".join(str(x) for x in log), encoding="utf-8")


if __name__ == "__main__":
    main()
