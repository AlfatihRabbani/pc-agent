"""PC-Agent chat app — a popup chatbot that controls your PC.

* Loads the model automatically on launch (background thread; UI stays responsive).
* CLOSE (X) fully quits and frees the GPU/VRAM. Minimize (–) or the tray "Hide"
  keeps it loaded/warm; Ctrl+Alt+A toggles. Relaunching focuses the running one
  (single instance — no double-load crash).
* "📋 Show logs" (top-left) opens a console with the full log from startup, live.

Launch with pythonw (no console):   pythonw app\chat_app.py
or just double-click  PC-Agent.bat
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LOG_PATH = ROOT / "logs" / "app.log"
_LOCK_PORT = 49517   # single-instance guard: only one app binds this localhost port

BG = "#0f1117"
PANEL = "#161922"
USER = "#5ab0ff"
AGENT = "#7CFC9A"
SYS = "#888da8"
TXT = "#e6e6ec"


class ChatApp:
    def __init__(self, listener=None):
        self.core = None
        self.ready = False
        self._last_external = None   # hwnd of the last window the user used (not us)
        self._listener = listener    # single-instance socket (relaunch -> show this one)

        self.root = tk.Tk()
        self.root.title("PC-Agent")
        self.root.geometry("440x600")
        self.root.configure(bg=BG)
        self.root.minsize(360, 420)
        try:
            self.root.attributes("-topmost", True)
        except Exception:  # noqa: BLE001
            pass

        # top bar: "Show logs" (left) + status (fills the rest)
        top = tk.Frame(self.root, bg=PANEL)
        top.pack(fill="x", side="top")
        self.settings_btn = tk.Label(top, text="⚙ Settings", bg=PANEL, fg=USER,
                                     font=("Segoe UI", 9, "underline"), cursor="hand2", padx=8, pady=2)
        self.settings_btn.pack(side="left")
        self.settings_btn.bind("<Button-1>", lambda e: self._open_settings())
        self.clear_btn = tk.Label(top, text="🗑 Clear chat", bg=PANEL, fg=USER,
                                  font=("Segoe UI", 9, "underline"), cursor="hand2", padx=8, pady=2)
        self.clear_btn.pack(side="right")
        self.clear_btn.bind("<Button-1>", lambda e: self._clear_chat())
        self.status = tk.Label(top, text="Starting…", bg=PANEL, fg=SYS,
                               anchor="w", padx=6, font=("Segoe UI", 9))
        self.status.pack(side="left", fill="x", expand=True)

        # transcript
        self.log = scrolledtext.ScrolledText(
            self.root, bg=BG, fg=TXT, insertbackground=TXT, wrap="word",
            font=("Segoe UI", 10), borderwidth=0, padx=10, pady=8, state="disabled")
        self.log.pack(fill="both", expand=True)
        self.log.tag_config("you", foreground=USER, font=("Segoe UI", 10, "bold"))
        self.log.tag_config("agent", foreground=AGENT)
        self.log.tag_config("sys", foreground=SYS, font=("Segoe UI", 9, "italic"))

        # "Switching Models…" overlay (shown while the chat model loads)
        self.loading_frame = tk.Frame(self.log, bg=BG)
        self.loading_label = tk.Label(self.loading_frame, text="Switching Models",
                                      bg=BG, fg=AGENT, font=("Segoe UI", 13, "bold"))
        self.loading_label.pack(pady=(0, 12))
        self.loading_bar = ttk.Progressbar(self.loading_frame, mode="indeterminate", length=220)
        self.loading_bar.pack()
        self._dots_job = None
        self._dots = 0

        # input row
        row = tk.Frame(self.root, bg=PANEL)
        row.pack(fill="x", side="bottom")
        self.entry = tk.Entry(row, bg=PANEL, fg=TXT, insertbackground=TXT,
                              relief="flat", font=("Segoe UI", 11))
        self.entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(10, 6), pady=8)
        self.entry.bind("<Return>", lambda e: self._send())
        self.send_btn = tk.Button(row, text="Send", command=self._send, relief="flat",
                                  bg="#2a4a8a", fg="white", activebackground="#365fb0",
                                  font=("Segoe UI", 10, "bold"), padx=14)
        self.send_btn.pack(side="right", padx=(0, 10), pady=8)
        self._set_enabled(False)

        self.root.protocol("WM_DELETE_WINDOW", self.quit)   # X = quit, releases the GPU
        self._add("PC-Agent", "Booting up — loading the model. One moment…", "sys")

        self._init_tray()
        self._init_hotkey()
        self.root.after(1200, self._track_foreground)   # remember the last window in use
        if self._listener is not None:                  # relaunch -> focus this instance
            threading.Thread(target=self._serve_instance, daemon=True).start()

        # auto-load the model on open
        threading.Thread(target=self._load_model, daemon=True).start()

    def _serve_instance(self):
        """A second launch connects to our socket — bring this window to the front."""
        while True:
            try:
                conn, _ = self._listener.accept()
                conn.close()
                self.show()
            except Exception:  # noqa: BLE001
                break

    def _log(self, msg: str):
        """Everything also goes to logs/app.log (stdout is redirected there)."""
        try:
            import datetime
            print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)
        except Exception:  # noqa: BLE001
            pass

    # ── model-switching loader ──────────────────────────────────────
    def _on_loading(self, loading: bool):
        def do():
            if loading:
                self._dots = 0
                self.loading_frame.place(relx=0.5, rely=0.4, anchor="center")
                self.loading_bar.start(12)
                self._animate_dots()
                self.status.config(text="Switching models…")
            else:
                if self._dots_job:
                    self.root.after_cancel(self._dots_job)
                    self._dots_job = None
                try:
                    self.loading_bar.stop()
                    self.loading_frame.place_forget()
                except Exception:  # noqa: BLE001
                    pass
        self._ui(do)

    def _animate_dots(self):
        self._dots = (self._dots % 3) + 1
        self.loading_label.config(text="Switching Models" + "." * self._dots)
        self._dots_job = self.root.after(400, self._animate_dots)

    # ── settings ────────────────────────────────────────────────────
    def _list_dispatch_models(self):
        import glob
        import os
        vals = []
        for d in sorted(glob.glob(str(ROOT / "models" / "dispatcher-*"))):
            if (os.path.exists(os.path.join(d, "adapter_model.safetensors"))
                    or glob.glob(os.path.join(d, "checkpoint-*"))):
                vals.append(os.path.basename(d))
        vals.append("prompt (base, no adapter)")
        return vals

    def _list_chat_models(self):
        vals = ["E2B (built-in)"]
        try:
            import json
            import urllib.request
            r = json.loads(urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3).read())
            vals += [m["name"] for m in r.get("models", []) if m.get("name")]
        except Exception:  # noqa: BLE001
            pass
        return vals

    def _open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("PC-Agent — Settings")
        win.configure(bg=BG)
        win.geometry("440x320")
        win.attributes("-topmost", True)
        tk.Label(win, text="Settings", bg=BG, fg=TXT, font=("Segoe UI", 14, "bold")).pack(pady=(16, 12))

        tk.Label(win, text="Dispatch model (the task router):", bg=BG, fg=SYS,
                 anchor="w", font=("Segoe UI", 9)).pack(fill="x", padx=18)
        disp_vals = self._list_dispatch_models()
        cur_disp = self.core.adapter_name if self.core else disp_vals[0]
        disp_var = tk.StringVar(value=(cur_disp if cur_disp in disp_vals else disp_vals[0]))
        ttk.Combobox(win, textvariable=disp_var, values=disp_vals, state="readonly").pack(fill="x", padx=18, pady=(2, 12))

        tk.Label(win, text="Chat / writing model (the 12B):", bg=BG, fg=SYS,
                 anchor="w", font=("Segoe UI", 9)).pack(fill="x", padx=18)
        chat_vals = self._list_chat_models()
        if self.core and self.core.chat_backend == "ollama":
            cur_chat = self.core.chat_model if self.core.chat_model in chat_vals else chat_vals[0]
        else:
            cur_chat = "E2B (built-in)"
        chat_var = tk.StringVar(value=cur_chat)
        ttk.Combobox(win, textvariable=chat_var, values=chat_vals, state="readonly").pack(fill="x", padx=18, pady=(2, 14))

        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", padx=18)
        tk.Button(row, text="📋 Show logs", command=self._show_logs, relief="flat",
                  bg=PANEL, fg=USER, font=("Segoe UI", 9)).pack(side="left")
        tk.Button(row, text="Save", command=lambda: self._save_settings(disp_var.get(), chat_var.get(), win),
                  relief="flat", bg="#2a4a8a", fg="white", font=("Segoe UI", 9, "bold"), padx=16).pack(side="right")
        tk.Label(win, text="Chat model applies immediately. Dispatch model needs a restart.",
                 bg=BG, fg=SYS, font=("Segoe UI", 8)).pack(pady=(12, 0))

    def _save_settings(self, disp: str, chat: str, win):
        try:
            import yaml
            cfgp = ROOT / "config.yaml"
            with open(cfgp, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            cfg.setdefault("chat", {})
            if chat.startswith("E2B"):
                cfg["chat"]["backend"] = "e2b"
            else:
                cfg["chat"]["backend"] = "ollama"
                cfg["chat"]["model"] = chat
            if self.core:                                   # apply chat model live
                self.core.chat_backend = cfg["chat"]["backend"]
                self.core.chat_model = cfg["chat"].get("model", "")
            restart = False
            if not disp.startswith("prompt"):
                cfg.setdefault("dispatcher", {})["adapter_dir"] = f"models/{disp}"
                restart = bool(self.core and disp != self.core.adapter_name)
            with open(cfgp, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)
            win.destroy()
            self._add("PC-Agent", "Settings saved."
                      + (" Restart the app to load the new dispatch model." if restart else ""), "sys")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("PC-Agent", f"Could not save settings: {e}")

    def _clear_chat(self):
        """Wipe the transcript and reset the conversation history (model starts fresh)."""
        if self.core is not None:
            self.core.history = []

        def do():
            self.log.config(state="normal")
            self.log.delete("1.0", "end")
            self.log.config(state="disabled")
        self._ui(do)
        self._log("[clear] chat + history reset")
        self._add("PC-Agent", "Chat cleared.", "sys")

    def _show_logs(self):
        """Open a console showing the full log (from startup) and following it live."""
        try:
            subprocess.Popen(
                ["powershell", "-NoExit", "-NoProfile", "-Command",
                 f"Write-Host 'PC-Agent logs — {LOG_PATH}' -ForegroundColor Cyan; "
                 f"Get-Content -LiteralPath '{LOG_PATH}' -Encoding utf8 -Wait"],
                creationflags=0x00000010)   # CREATE_NEW_CONSOLE
        except Exception as e:  # noqa: BLE001
            self._log(f"[show logs failed] {e}")

    # remember the most recent foreground window that isn't us, so input actions
    # without a named target still land where the user was working.
    def _track_foreground(self):
        try:
            import ctypes
            u = ctypes.windll.user32
            h = u.GetForegroundWindow()
            n = u.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(h, b, n + 1)
                if "PC-Agent" not in b.value and "confirm action" not in b.value:
                    self._last_external = h
        except Exception:  # noqa: BLE001
            pass
        self.root.after(800, self._track_foreground)

    def _drop_focus(self):
        """Last-resort: minimize ourselves so we aren't the keystroke target."""
        self._ui(self.root.iconify)

    # ── UI helpers (always marshalled to the main thread) ───────────
    def _ui(self, fn):
        self.root.after(0, fn)

    def _set_status(self, text):
        self._log(f"[status] {text}")
        self._ui(lambda: self.status.config(text=text))

    def _set_enabled(self, on: bool):
        state = "normal" if on else "disabled"
        self.entry.config(state=state)
        self.send_btn.config(state=state)
        if on:
            self.entry.focus_set()

    def _set_busy(self, busy: bool):
        """Toggle the action button between Send (idle) and a red Stop (generating)."""
        if busy:
            self.entry.config(state="disabled")
            self.send_btn.config(text="Stop", bg="#c0392b", activebackground="#e74c3c",
                                 fg="white", state="normal", command=self._stop)
        else:
            self.entry.config(state="normal")
            self.send_btn.config(text="Send", bg="#2a4a8a", activebackground="#365fb0",
                                 fg="white", state="normal", command=self._send)
            self.entry.focus_set()

    def _stop(self):
        """Cancel the in-flight turn (stops generation at the next token)."""
        if self.core:
            self.core.request_stop()
        self._set_status("Stopping…")
        self.send_btn.config(state="disabled")

    def _add(self, who: str, text: str, tag: str):
        self._log(f"{who}: {text}")

        def do():
            self.log.config(state="normal")
            self.log.insert("end", f"{who}: ", tag)
            self.log.insert("end", f"{text}\n\n")
            self.log.config(state="disabled")
            self.log.see("end")
        self._ui(do)

    # ── model load ──────────────────────────────────────────────────
    def _load_model(self):
        try:
            from app.agent_core import AgentCore
            self.core = AgentCore(status=self._set_status,
                                  get_external_hwnd=lambda: self._last_external,
                                  before_input=self._drop_focus)
            self.core.on_loading = self._on_loading   # 'Switching Models…' overlay
            self.ready = True
            try:
                (ROOT / "logs" / "app_ready.flag").write_text("ready", encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
            self._set_status(f"Ready · adapter: {self.core.adapter_name}")
            self._add("PC-Agent", "Ready. Ask me anything, or tell me to do something on your PC "
                      "(e.g. \"what's my volume\", \"open notepad\", \"what are my specs\").", "sys")
            self._ui(lambda: self._set_busy(False))
        except Exception as e:  # noqa: BLE001
            import traceback
            self._set_status("Model failed to load.")
            self._add("error", f"{e}\n{traceback.format_exc()}", "sys")

    # ── sending ─────────────────────────────────────────────────────
    def _send(self):
        if not self.ready:
            return
        msg = self.entry.get().strip()
        if not msg:
            return
        self.entry.delete(0, "end")
        self._add("you", msg, "you")
        self._set_busy(True)
        self._set_status("Thinking… (Stop to cancel)")
        threading.Thread(target=self._work, args=(msg,), daemon=True).start()

    def _work(self, msg: str):
        try:
            reply = self.core.handle(msg, confirm=self._confirm)
        except Exception as e:  # noqa: BLE001
            import traceback
            try:
                (ROOT / "logs" / "app_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
            reply = f"[error: {type(e).__name__}: {e}]"
        self._add("PC-Agent", reply, "agent")
        self._set_status(f"Ready · adapter: {self.core.adapter_name}")
        self._ui(lambda: self._set_busy(False))

    def _confirm(self, prompt: str) -> bool:
        """Risky actions ask first — runs the dialog on the main thread, waits here."""
        box = {}
        ev = threading.Event()

        def ask():
            box["v"] = messagebox.askyesno("PC-Agent — confirm action", prompt)
            ev.set()
        self._ui(ask)
        ev.wait()
        return bool(box.get("v"))

    # ── show / hide (tray + hotkey) ─────────────────────────────────
    def show(self):
        def do():
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.entry.focus_set()
        self._ui(do)

    def hide(self):
        self._ui(self.root.withdraw)

    def toggle(self):
        self._ui(lambda: self.hide() if self.root.state() != "withdrawn" else self.show())

    def quit(self):
        self._log("[quit] releasing model + GPU and exiting")
        try:
            if getattr(self, "tray", None):
                self.tray.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self.core is not None:
                import gc
                import torch
                try:
                    del self.core.model
                except Exception:  # noqa: BLE001
                    pass
                self.core = None
                gc.collect()
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.root.destroy()
        except Exception:  # noqa: BLE001
            pass
        os._exit(0)   # hard-exit so the process (and all its VRAM) is fully released

    # ── tray icon ───────────────────────────────────────────────────
    def _init_tray(self):
        self.tray = None
        try:
            import pystray
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (64, 64), BG)
            d = ImageDraw.Draw(img)
            d.ellipse((8, 8, 56, 56), fill="#2a4a8a")
            d.text((24, 20), "A", fill="white")
            menu = pystray.Menu(
                pystray.MenuItem("Show PC-Agent", lambda *_: self.show(), default=True),
                pystray.MenuItem("Hide", lambda *_: self.hide()),
                pystray.MenuItem("Quit", lambda *_: self.quit()),
            )
            self.tray = pystray.Icon("PC-Agent", img, "PC-Agent", menu)
            threading.Thread(target=self.tray.run, daemon=True).start()
        except Exception as e:  # noqa: BLE001
            # no tray (pystray missing): closing the window will just iconify instead
            self.root.protocol("WM_DELETE_WINDOW", lambda: self.root.iconify())
            print("tray unavailable:", e)

    def _init_hotkey(self):
        try:
            from pynput import keyboard
            self._hk = keyboard.GlobalHotKeys({"<ctrl>+<alt>+a": self.toggle})
            self._hk.start()
        except Exception as e:  # noqa: BLE001
            print("hotkey unavailable:", e)

    def run(self):
        self.root.mainloop()


def _single_instance():
    """Bind a localhost port so only ONE app runs. A second launch tells the first to
    show itself, then exits — prevents the double-model-load crash."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", _LOCK_PORT))
        s.listen(5)
        return s
    except OSError:
        try:
            c = socket.create_connection(("127.0.0.1", _LOCK_PORT), timeout=2)
            c.sendall(b"show")
            c.close()
        except Exception:  # noqa: BLE001
            pass
        return None


if __name__ == "__main__":
    listener = _single_instance()
    if listener is None:
        sys.exit(0)   # already running — asked that instance to show itself
    # mirror everything (incl. model-loading output) to logs/app.log for "Show logs"
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _logf = open(LOG_PATH, "w", buffering=1, encoding="utf-8", errors="replace")
        sys.stdout = _logf
        sys.stderr = _logf
        print("=== PC-Agent starting (model is loading) ===", flush=True)
    except Exception:  # noqa: BLE001
        pass
    ChatApp(listener=listener).run()
