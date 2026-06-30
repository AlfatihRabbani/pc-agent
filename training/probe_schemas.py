"""Probe each committed dataset's real schema (streaming, no full download) and
show what our converters produce. Run before build_dataset.py to catch drift.

    python training/probe_schemas.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datasets import load_dataset  # noqa: E402
from training.build_dataset import (  # noqa: E402
    fc_to_messages, code_to_messages, general_to_messages,
)

PROBES = [
    ("Salesforce/xlam-function-calling-60k", "train", fc_to_messages),
    ("NousResearch/hermes-function-calling-v1", "train", fc_to_messages),
    ("ise-uiuc/Magicoder-Evol-Instruct-110K", "train", code_to_messages),
    ("m-a-p/Code-Feedback", "train", code_to_messages),
    ("teknium/OpenHermes-2.5", "train", general_to_messages),
]


def main():
    for repo, split, conv in PROBES:
        print(f"\n==== {repo} ====")
        try:
            ds = load_dataset(repo, split=split, streaming=True)
            row = next(iter(ds))
        except Exception as e:  # noqa: BLE001
            print(f"  !! load failed: {e}")
            continue
        print(f"  columns: {list(row.keys())}")
        out = conv(dict(row))
        if out and out.get("messages"):
            print(f"  converted: {len(out['messages'])} msgs; "
                  f"roles={[m['role'] for m in out['messages']]}")
            preview = json.dumps(out["messages"][-1])[:160]
            print(f"  last msg: {preview}")
        else:
            print("  !! CONVERTER RETURNED NOTHING — needs fixing")


if __name__ == "__main__":
    main()
