"""Burst trainer that survives GPU context-loss hangs (TDR / driver reset).

Trains the dispatcher in short checkpointed chunks. Each burst warm-starts from the
best-so-far adapter; a watchdog kills a burst if step progress stalls, then the next
burst resumes from the latest checkpoint. Net forward progress despite repeated hangs.

    python scripts/train_burst.py --bursts 6 --burst_steps 200
Result adapter accumulates at: models/dispatcher-cur/
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
CUR = ROOT / "models" / "dispatcher-cur"                              # best-so-far
BURST_OUT = ROOT / "models" / "dispatcher-burst"                     # per-burst output
SEED = ROOT / "models" / "dispatcher-e4b-qlora" / "checkpoint-200"   # starting point
LOG = ROOT / "data" / "burst.log"
TRAIN = ROOT / "training" / "train_qlora.py"


def latest_adapter(d: Path) -> Path | None:
    d = Path(d)
    if (d / "adapter_model.safetensors").exists():
        return d
    cks = [c for c in glob.glob(str(d / "checkpoint-*"))
           if (Path(c) / "adapter_model.safetensors").exists()]
    cks.sort(key=lambda p: int(p.split("-")[-1]))
    return Path(cks[-1]) if cks else None


def kill_tree(proc):
    try:
        parent = psutil.Process(proc.pid)
        for ch in parent.children(recursive=True):
            try: ch.kill()
            except Exception: pass
        parent.kill()
    except Exception: pass


def last_step() -> int:
    try:
        txt = open(LOG, encoding="utf-8", errors="ignore").read().replace("\r", "\n")
    except Exception:
        return 0
    ms = [m for ln in txt.splitlines() if "Loading weights" not in ln
          for m in [re.search(r"(\d+)/\d+ \[", ln)] if m]
    return int(ms[-1].group(1)) if ms else 0


def vram_free_gb() -> float:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True)
        return float(out.stdout.strip().splitlines()[0]) / 1024
    except Exception:
        return 99.0


def wait_for_vram(min_gb=7.0, timeout=90):
    t = time.time()
    while time.time() - t < timeout:
        if vram_free_gb() >= min_gb:
            return True
        time.sleep(5)
    return False


def run_burst(src: Path, max_steps: int) -> int:
    if BURST_OUT.exists():
        shutil.rmtree(BURST_OUT, ignore_errors=True)
    env = dict(os.environ, HF_HUB_DISABLE_XET="1")
    cmd = [sys.executable, str(TRAIN), "--epochs", "1", "--seq_len", "512",
           "--max_steps", str(max_steps), "--save_steps", "100", "--throttle", "1.5",
           "--from_adapter", str(src), "--out", str(BURST_OUT)]
    with open(LOG, "w", encoding="utf-8") as f:
        proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)
    start = time.time()
    last_seen, changed = -1, time.time()
    while proc.poll() is None:
        time.sleep(15)
        s = last_step()
        if s > last_seen:
            last_seen, changed = s, time.time()
        elif last_seen < 1 and time.time() - start > 360:
            print("  [watchdog] model load hung; killing burst", flush=True)
            kill_tree(proc); break
        elif last_seen >= 1 and time.time() - changed > 150:
            print(f"  [watchdog] training hung at step {last_seen}; killing burst", flush=True)
            kill_tree(proc); break
    try:
        proc.wait(timeout=20)
    except Exception:
        kill_tree(proc)
    return last_seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bursts", type=int, default=6)
    ap.add_argument("--burst_steps", type=int, default=200)
    args = ap.parse_args()

    if latest_adapter(CUR) is None:
        shutil.rmtree(CUR, ignore_errors=True)
        shutil.copytree(SEED, CUR)
        print(f"seeded CUR from {SEED}", flush=True)

    for i in range(1, args.bursts + 1):
        if not wait_for_vram():
            print("  [warn] VRAM not free; proceeding anyway", flush=True)
        src = latest_adapter(CUR)
        print(f"\n=== BURST {i}/{args.bursts}  (warm-start {src}) ===", flush=True)
        reached = run_burst(src, args.burst_steps)
        new = latest_adapter(BURST_OUT)
        if new is not None:
            shutil.rmtree(CUR, ignore_errors=True)
            shutil.copytree(new, CUR)
            print(f"  burst reached step {reached}; advanced CUR <- {new.name}", flush=True)
        else:
            print("  burst saved no checkpoint (hung before step 50); retrying", flush=True)
        time.sleep(12)  # let VRAM release before next burst
    print(f"\n[OK] burst training done. Adapter at {CUR}", flush=True)


if __name__ == "__main__":
    main()
