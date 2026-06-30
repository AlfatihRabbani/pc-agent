"""Download Gemma 4 weights into the HF cache (where brain.py / train_qlora.py load
them from by repo id). Requires a logged-in token + accepted licenses.

    python scripts/download_models.py            # both (E4B first, then 12B)
    python scripts/download_models.py --dispatcher   # just E4B (needed for training)
    python scripts/download_models.py --brain        # just the 12B brain
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pc_agent.hf_cache  # noqa: F401,E402  (HF cache -> E: before downloads)
from pc_agent.config import load  # noqa: E402


def fetch(repo: str, attempts: int = 7) -> bool:
    """Download with exponential backoff so a 429 rate-limit storm self-heals."""
    import time
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import GatedRepoError
    delay = 60
    for i in range(1, attempts + 1):
        print(f"-> [{i}/{attempts}] downloading {repo} ...", flush=True)
        try:
            snapshot_download(
                repo, max_workers=1,   # one file at a time = most stable on a flaky line
                allow_patterns=["*.safetensors", "*.json", "*.model", "*.txt", "tokenizer*"],
            )
            print(f"[OK] done: {repo}", flush=True)
            return True
        except GatedRepoError:
            print(f"[X] GATED: accept the license at https://huggingface.co/{repo}", flush=True)
            return False
        except Exception as e:  # noqa: BLE001
            # Retry on ANYTHING transient: 429 rate-limits AND connection stalls/drops.
            print(f"[X] attempt {i} failed: {type(e).__name__} {str(e)[:120]}", flush=True)
            if i < attempts:
                print(f"   retrying in {delay}s (resumes from partial) ...", flush=True)
                time.sleep(delay)
                delay = min(delay * 2, 300)
    print(f"[X] gave up on {repo} after {attempts} attempts (still rate-limited)", flush=True)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brain", action="store_true")
    ap.add_argument("--dispatcher", action="store_true")
    args = ap.parse_args()
    both = not (args.brain or args.dispatcher)
    cfg = load()

    ok = True
    if args.dispatcher or both:               # E4B first — it unblocks training
        ok &= fetch(cfg.get("dispatcher.base_model_id"))
    if args.brain or both:
        ok &= fetch(cfg.get("brain.model_id"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
