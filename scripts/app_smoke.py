"""Smoke-test the running chat app: focus it, type a read-only query, screenshot."""
import sys, time, ctypes
from ctypes import wintypes
sys.path.insert(0, r"E:\aitest\pc-agent")
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass
from pc_agent.tools import get

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def find(sub):
    res = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(h, b, n + 1)
                if sub in b.value:
                    res.append(h)
        return True
    user32.EnumWindows(cb, 0)
    return res[0] if res else None


h = find("PC-Agent")
log = open(r"E:\aitest\pc-agent\logs\app_smoke.txt", "w")
if not h:
    log.write("PC-Agent window not found"); log.close(); sys.exit()

cur = kernel32.GetCurrentThreadId()
fg = user32.GetForegroundWindow()
user32.AttachThreadInput(cur, user32.GetWindowThreadProcessId(fg, None), True)
user32.AttachThreadInput(cur, user32.GetWindowThreadProcessId(h, None), True)
user32.ShowWindow(h, 9)
user32.BringWindowToTop(h)
user32.SetForegroundWindow(h)
user32.AttachThreadInput(cur, user32.GetWindowThreadProcessId(fg, None), False)
user32.AttachThreadInput(cur, user32.GetWindowThreadProcessId(h, None), False)
time.sleep(0.6)

r = wintypes.RECT()
user32.GetWindowRect(h, ctypes.byref(r))
ex, ey = r.left + 120, r.bottom - 26
get("click_at").fn(x=ex, y=ey)
time.sleep(0.2)
get("click_at").fn(x=ex, y=ey)     # 2nd click — 1st is swallowed as window activation
time.sleep(0.3)
_msg = " ".join(sys.argv[1:]) or "what are my pc specs"
get("type_text").fn(text=_msg)
time.sleep(0.3)
get("press_hotkey").fn(keys=["enter"])
log.write(f"hwnd={h} rect=({r.left},{r.top},{r.right},{r.bottom}) click=({ex},{ey})\n")
log.close()

time.sleep(12)   # let route + tool + reply complete
import pyautogui
pyautogui.screenshot().save(r"E:\aitest\pc-agent\logs\screenshots\app_test.png")
