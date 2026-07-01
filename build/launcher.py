"""PC-Agent launcher.

Compiled to PC-Agent.exe (with an administrator manifest) by PyInstaller. It simply
starts the real app using the project's virtual-env Python, so the heavy ML stack
stays in .venv (not bundled into the exe). Because the exe runs elevated, the
launched app inherits admin rights.
"""
import os
import subprocess
import sys


def _find_base() -> str:
    cands = []
    if getattr(sys, "frozen", False):
        cands.append(os.path.dirname(sys.executable))      # folder the exe sits in
    cands.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cands.append(r"E:\aitest\pc-agent")                    # known install path
    for b in cands:
        if (os.path.exists(os.path.join(b, ".venv", "Scripts", "pythonw.exe"))
                and os.path.exists(os.path.join(b, "app", "chat_app.py"))):
            return b
    return r"E:\aitest\pc-agent"


def main():
    base = _find_base()
    py = os.path.join(base, ".venv", "Scripts", "pythonw.exe")
    app = os.path.join(base, "app", "chat_app.py")
    if not os.path.exists(py):
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, f"Could not find the PC-Agent environment:\n{py}\n\n"
               "Run scripts\\setup.bat first.", "PC-Agent", 0x10)
        return
    subprocess.Popen([py, app], cwd=base, close_fds=True)


if __name__ == "__main__":
    main()
