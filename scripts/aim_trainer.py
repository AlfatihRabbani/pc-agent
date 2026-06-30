"""Aim trainer used as a CLICK-CONTROL TEST ENVIRONMENT for the PC-Agent.

This is NOT a human reflex/speed game. It exists so the agent can be asked to
click targets and have its click pipeline validated: targets spawn at known
screen coordinates, and each incoming click is scored hit/miss by distance.

State is mirrored (atomically) to logs/aim_state.json so a separate clicker
process knows where the current target is, in SCREEN pixels, and when it
advances. See scripts/test_click.py for the driver.

    python scripts/aim_trainer.py --targets 10 --radius 40
"""
from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path

# DPI-aware FIRST so tkinter coordinates equal physical pixels and therefore
# match what pynput / pyautogui use (otherwise clicks land offset on scaled displays).
try:
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # per-monitor v2
    except Exception:  # noqa: BLE001
        ctypes.windll.user32.SetProcessDPIAware()
except Exception:  # noqa: BLE001
    pass

import tkinter as tk

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "logs" / "aim_state.json"


class AimTrainer:
    def __init__(self, total: int = 10, radius: int = 40, w: int = 900, h: int = 650, seed=None):
        self.total, self.radius, self.w, self.h = total, radius, w, h
        self.rng = random.Random(seed)
        self.index = self.hits = self.misses = self.seq = 0
        self.tx = self.ty = 0

        self.root = tk.Tk()
        self.root.title("PC-Agent Aim Trainer  (click-control test)")
        self.root.attributes("-topmost", True)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        self.canvas = tk.Canvas(self.root, width=w, height=h, bg="#0b0b12", highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_click)
        self.info = self.canvas.create_text(12, 10, anchor="nw", fill="#8888aa",
                                            font=("Consolas", 12), text="")
        STATE.parent.mkdir(parents=True, exist_ok=True)
        self.root.after(350, self.spawn)   # let the window map before first target
        self.root.mainloop()

    def spawn(self):
        if self.index >= self.total:
            return self.finish()
        m = self.radius + 20
        self.tx = self.rng.randint(m, self.w - m)
        self.ty = self.rng.randint(m + 30, self.h - m)
        self.index += 1
        self.seq += 1
        self.draw()
        self.write("spawn")

    def draw(self):
        c, r = self.canvas, self.radius
        c.delete("tgt")
        c.create_oval(self.tx - r, self.ty - r, self.tx + r, self.ty + r,
                      fill="#e23b3b", outline="", tags="tgt")
        c.create_oval(self.tx - r * .6, self.ty - r * .6, self.tx + r * .6, self.ty + r * .6,
                      fill="#f2f2f2", outline="", tags="tgt")
        c.create_oval(self.tx - r * .22, self.ty - r * .22, self.tx + r * .22, self.ty + r * .22,
                      fill="#e23b3b", outline="", tags="tgt")
        c.itemconfigure(self.info,
                        text=f"target {self.index}/{self.total}   hits {self.hits}  misses {self.misses}")

    def screen_center(self):
        # canvas widget origin (screen px) + target canvas coords = absolute screen target.
        return self.canvas.winfo_rootx() + self.tx, self.canvas.winfo_rooty() + self.ty

    def write(self, event: str):
        sx, sy = self.screen_center()
        data = {
            "status": "done" if event == "done" else "running",
            "index": self.index, "total": self.total,
            "target": {"sx": sx, "sy": sy, "r": self.radius},
            "hits": self.hits, "misses": self.misses, "seq": self.seq, "last_event": event,
        }
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        os.replace(tmp, STATE)   # atomic — reader never sees a half-written file

    def on_click(self, e):
        hit = ((e.x - self.tx) ** 2 + (e.y - self.ty) ** 2) ** 0.5 <= self.radius
        if hit:
            self.hits += 1
        else:
            self.misses += 1
        self.write("hit" if hit else "miss")
        self.root.after(120, self.spawn)

    def finish(self):
        self.canvas.delete("tgt")
        acc = 100.0 * self.hits / max(1, self.total)
        self.canvas.create_text(self.w // 2, self.h // 2, fill="#7CFC00", font=("Consolas", 24),
                                text=f"DONE   {self.hits}/{self.total} hits   ({acc:.0f}%)")
        self.write("done")
        self.root.after(1800, self.root.destroy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", type=int, default=10)
    ap.add_argument("--radius", type=int, default=40)
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    AimTrainer(total=a.targets, radius=a.radius, seed=a.seed)


if __name__ == "__main__":
    main()
