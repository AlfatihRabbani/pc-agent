"""Focus the PC-Agent window and save a tightly-cropped shot of just that window."""
import ctypes, time
from ctypes import wintypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass
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
cur = kernel32.GetCurrentThreadId()
fg = user32.GetForegroundWindow()
user32.AttachThreadInput(cur, user32.GetWindowThreadProcessId(fg, None), True)
user32.AttachThreadInput(cur, user32.GetWindowThreadProcessId(h, None), True)
user32.ShowWindow(h, 9)
user32.BringWindowToTop(h)
user32.SetForegroundWindow(h)
user32.AttachThreadInput(cur, user32.GetWindowThreadProcessId(fg, None), False)
user32.AttachThreadInput(cur, user32.GetWindowThreadProcessId(h, None), False)
time.sleep(0.7)

r = wintypes.RECT()
user32.GetWindowRect(h, ctypes.byref(r))
import pyautogui
from PIL import Image
shot = pyautogui.screenshot()
box = (max(r.left, 0), max(r.top, 0), r.right, r.bottom)
crop = shot.crop(box)
w, hh = crop.size
crop = crop.resize((int(w * 1.5), int(hh * 1.5)))
crop.save(r"E:\aitest\pc-agent\logs\screenshots\app_view.png")
open(r"E:\aitest\pc-agent\logs\app_view.txt", "w").write(f"rect={box} size={crop.size}")
