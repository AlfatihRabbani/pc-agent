"""Drive the PC-Agent click pipeline against scripts/aim_trainer.py.

Launches the aim trainer, then for each target reads its screen coordinates
from logs/aim_state.json and clicks it with the AGENT'S OWN executor
(input_control.click_at -> pynput -> OS). Reports hit accuracy: does the
agent's click actually land on the target?

Modes:
  coords    (default) feed the known target coords straight to click_at. Tests
            the control/execution half end-to-end (no model needed).
  dispatch  route a natural-language "left click at X, Y" through the trained
            dispatcher, execute whatever tool-call it emits. Tests model-driven
            clicking. Loads the model -> needs a free GPU (re-cap first).

    python scripts/test_click.py --targets 10
    python scripts/test_click.py --targets 10 --mode dispatch

NOTE: this moves the REAL mouse cursor. Don't fight it while it runs.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pc_agent.hf_cache  # noqa: E402,F401
from pc_agent.tools import get  # noqa: E402
from pc_agent.tools.registry import REGISTRY  # noqa: E402

STATE = ROOT / "logs" / "aim_state.json"


def read_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:  # noqa: BLE001  (atomic writer can still race the very first read)
        return None


def wait_advance(seq: int, timeout: float = 5.0):
    """Block until the trainer spawns a new target (seq changes) or times out."""
    t = time.time()
    while time.time() - t < timeout:
        s = read_state()
        if s and s["seq"] != seq:
            return s
        time.sleep(0.05)
    return read_state()


def _normalize(dec: dict) -> dict:
    """Accept the dispatcher's shorthand {'action': '<tool>'} as a tool call."""
    if dec.get("action") == "tool":
        return dec
    act = dec.get("action")
    if act in REGISTRY:                      # shorthand: tool name landed in 'action'
        return {"action": "tool", "tool": act, "args": dec.get("args", {})}
    if act == "open_app" and "tool" in dec:  # observed open-app shorthand
        return {"action": "tool", "tool": "open_app", "args": {"name": dec["tool"], **dec.get("args", {})}}
    return dec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", type=int, default=10)
    ap.add_argument("--radius", type=int, default=40)
    ap.add_argument("--mode", choices=["coords", "dispatch"], default="coords")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    if STATE.exists():
        STATE.unlink()

    cmd = [sys.executable, str(ROOT / "scripts" / "aim_trainer.py"),
           "--targets", str(a.targets), "--radius", str(a.radius)]
    if a.seed is not None:
        cmd += ["--seed", str(a.seed)]
    proc = subprocess.Popen(cmd)

    # wait for the first target to appear
    s = None
    t0 = time.time()
    while time.time() - t0 < 20:
        s = read_state()
        if s and s.get("target"):
            break
        time.sleep(0.1)
    if not s or not s.get("target"):
        print("[FAIL] aim trainer never reported a target")
        proc.kill()
        return

    click = get("click_at")
    gen = parse = build_prompt = None
    if a.mode == "dispatch":
        import torch  # noqa: F401
        from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig
        from peft import PeftModel
        from pc_agent.config import load
        from pc_agent import dispatcher
        import glob
        cfg = load()
        base = cfg.get("dispatcher.base_model_id")
        adapter = None
        for name in ("dispatcher-final", "dispatcher-cur"):
            d = ROOT / "models" / name
            if (d / "adapter_model.safetensors").exists():
                adapter = str(d)
                break
        print(f"dispatch mode: base={base} adapter={adapter}", flush=True)
        q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                               bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
        proc_m = AutoProcessor.from_pretrained(base)
        model = AutoModelForImageTextToText.from_pretrained(base, quantization_config=q, device_map="auto")
        if adapter:
            model = PeftModel.from_pretrained(model, adapter)
        model.eval()
        build_prompt = lambda m: dispatcher.build_prompt(m, compact=True)  # noqa: E731
        parse = dispatcher.parse

        def gen(prompt: str) -> str:
            inp = proc_m.apply_chat_template([{"role": "user", "content": [{"type": "text", "text": prompt}]}],
                                             add_generation_prompt=True, tokenize=True,
                                             return_dict=True, return_tensors="pt").to(model.device)
            with torch.no_grad():
                out = model.generate(**inp, max_new_tokens=64, do_sample=False)
            return proc_m.decode(out[0][inp["input_ids"].shape[1]:], skip_special_tokens=True).strip()

    print(f"\n=== AIM CLICK TEST  ({a.mode} mode, {a.targets} targets) ===", flush=True)
    attempts = 0
    while attempts < a.targets:
        s = read_state()
        if not s or s.get("status") == "done":
            break
        tgt, seq = s["target"], s["seq"]
        sx, sy = tgt["sx"], tgt["sy"]
        before = s["hits"]
        print(f"target {s['index']}/{a.targets} @ screen ({sx},{sy})", flush=True)

        if a.mode == "coords":
            click.fn(x=sx, y=sy)
        else:
            raw = gen(build_prompt(f"left click at screen coordinates x={sx}, y={sy}"))
            dec = _normalize(parse(raw))
            print(f"  routed -> {dec}")
            if dec.get("action") == "tool" and dec.get("tool") in ("click_at", "move_cursor"):
                args = dec.get("args", {})
                args.setdefault("x", sx)
                args.setdefault("y", sy)
                get(dec["tool"]).fn(**args)
                if dec["tool"] == "move_cursor":   # dispatcher only moved; finish the click
                    click.fn(x=args["x"], y=args["y"])
            else:
                print("  (no click tool routed — counting as miss)")
                # nudge the trainer so the loop advances
                click.fn(x=0, y=0)

        ns = wait_advance(seq)
        hit = bool(ns and ns["hits"] > before)
        print(f"  -> {'HIT' if hit else 'MISS'}   (hits {ns['hits'] if ns else '?'} / misses {ns['misses'] if ns else '?'})",
              flush=True)
        attempts += 1

    time.sleep(0.4)
    fs = read_state() or {}
    hits = fs.get("hits", 0)
    acc = 100.0 * hits / max(1, a.targets)
    print(f"\n[RESULT] {hits}/{a.targets} targets hit   ({acc:.0f}% click accuracy)   mode={a.mode}", flush=True)
    try:
        proc.wait(timeout=4)
    except Exception:  # noqa: BLE001
        proc.kill()


if __name__ == "__main__":
    main()
