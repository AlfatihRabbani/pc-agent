"""Non-destructive end-to-end test of the trained PC-Agent dispatcher + vision.

Run AFTER training, when the GPU is free. Loads the fine-tuned E2B (it's multimodal,
so it serves as BOTH the routing dispatcher AND the vision brain) and runs:
  1. Routes simple requests -> executes SAFE read tools (volume, resolution, specs).
  2. Opens an app (notepad) — visible but harmless.
  3. A safe control demo: read volume -> set -> restore.
  4. Vision: renders a question to an image and asks the model to read + solve it.

Nothing destructive. No settings left changed.
    python scripts/test_agent.py
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pc_agent.hf_cache  # noqa: E402,F401
from pc_agent.config import load          # noqa: E402
from pc_agent.tools import get             # noqa: E402
from pc_agent import dispatcher            # noqa: E402

cfg = load()
BASE = cfg.get("dispatcher.base_model_id")


def find_adapter() -> str | None:
    for name in ("dispatcher-final", "dispatcher-cur", "dispatcher-burst", "dispatcher-e4b-qlora"):
        out = ROOT / "models" / name
        if (out / "adapter_model.safetensors").exists():
            return str(out)
        cks = glob.glob(str(out / "checkpoint-*"))
        if cks:
            cks.sort(key=lambda p: int(p.split("-")[-1]))
            return cks[-1]
    return None


def main():
    import torch
    from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig
    from peft import PeftModel

    adapter = find_adapter()
    print(f"base: {BASE}\nadapter: {adapter or 'NONE (prompt-mode)'}\n", flush=True)
    q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                           bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    proc = AutoProcessor.from_pretrained(BASE)
    model = AutoModelForImageTextToText.from_pretrained(BASE, quantization_config=q, device_map="auto")
    if adapter:
        model = PeftModel.from_pretrained(model, adapter)
    model.eval()

    def gen(prompt: str, image=None, max_new=80) -> str:
        content = ([{"type": "image", "image": image}] if image is not None else []) + \
                  [{"type": "text", "text": prompt}]
        inputs = proc.apply_chat_template([{"role": "user", "content": content}],
                                          add_generation_prompt=True, tokenize=True,
                                          return_dict=True, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=max_new, do_sample=False)
        return proc.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()

    # 1) route + execute safe read tools
    print("=== DISPATCH + EXECUTE (read-only + open app) ===", flush=True)
    for cmd in ["what is the current volume", "what is my screen resolution",
                "what is the brightness", "what are my pc specs", "open notepad"]:
        dec = dispatcher.parse(gen(dispatcher.build_prompt(cmd, compact=True), max_new=64))
        print(f"\nYOU: {cmd}\n  routed -> {dec}")
        if dec.get("action") == "tool":
            tool = get(dec["tool"])
            if tool and (tool.risk.value == "read" or dec["tool"] == "open_app"):
                try:
                    print("  result ->", tool.fn(**dec.get("args", {})))
                except Exception as e:  # noqa: BLE001
                    print("  exec error:", e)
            else:
                print("  (non-read tool — skipped in auto-test)")

    # 2) safe control demo: volume set + restore
    print("\n=== CONTROL DEMO: set volume then restore ===", flush=True)
    try:
        from pc_agent.tools.audio import _endpoint
        orig = round(_endpoint().GetMasterVolumeLevelScalar() * 100)
        print("  original volume:", orig)
        print("  ->", get("set_volume").fn(level=40))
        print("  ->", get("set_volume").fn(level=orig), "(restored)")
    except Exception as e:  # noqa: BLE001
        print("  volume demo skipped:", e)

    # 3) vision: read + solve a question from an image
    print("\n=== VISION: see + solve ===", flush=True)
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (760, 240), "white")
    try:
        font = ImageFont.truetype("arial.ttf", 72)
    except Exception:  # noqa: BLE001
        font = ImageFont.load_default()
    ImageDraw.Draw(img).text((40, 80), "What is 17 + 25?", fill="black", font=font)
    img.save(ROOT / "logs" / "vision_question.png")
    ans = gen("Read the question shown in this image and give the answer.", image=img, max_new=64)
    print('  image says: "What is 17 + 25?"  (expected: 42)')
    print("  model sees + answers ->", ans)
    print("\n[OK] test complete — nothing left changed.")


if __name__ == "__main__":
    main()
