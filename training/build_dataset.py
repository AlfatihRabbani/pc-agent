"""Download (cached) + normalize all committed datasets into one SFT file.

Output: data/train.jsonl  — every line is {"messages": [...]} ready for train_qlora.py.

Run:  python training/build_dataset.py
Pre-req: python training/synth_windows_actions.py --n 3000   (for the synth part)

NOTE: HF dataset schemas drift. This uses best-effort field detection and prints a
sample from each source so you can eyeball it. Adjust the *_to_messages() helpers
if a repo's columns differ from what's assumed.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "train.jsonl"
CFG = ROOT / "training" / "datasets.yaml"


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": str(content)}


def fc_to_messages(row: dict) -> dict | None:
    """Function-calling rows -> chat. Handles xlam + hermes-ish schemas."""
    # xlam-function-calling-60k: {query, tools, answers}
    if "query" in row and "answers" in row:
        sys = "You can call tools. Available:\n" + str(row.get("tools", ""))
        return {"messages": [_msg("system", sys), _msg("user", row["query"]),
                             _msg("assistant", json.dumps(row["answers"]))]}
    # hermes-function-calling-v1: conversations [{from,value}] or {role,content}
    convo = row.get("conversations") or row.get("messages")
    if isinstance(convo, list) and convo:
        msgs = []
        for t in convo:
            role = t.get("role") or {"human": "user", "gpt": "assistant",
                                     "system": "system", "tool": "tool"}.get(t.get("from"), "user")
            msgs.append(_msg(role, t.get("content") or t.get("value", "")))
        return {"messages": msgs}
    return None


def code_to_messages(row: dict) -> dict | None:
    # Magicoder-Evol-Instruct-110K: {instruction, response}
    if "instruction" in row and "response" in row:
        return {"messages": [_msg("user", row["instruction"]),
                             _msg("assistant", row["response"])]}
    # Code-Feedback: {messages:[...]} or {query, answer}
    if isinstance(row.get("messages"), list):
        return {"messages": [_msg(m.get("role", "user"), m.get("content", "")) for m in row["messages"]]}
    if "query" in row and "answer" in row:
        return {"messages": [_msg("user", row["query"]), _msg("assistant", row["answer"])]}
    return None


def general_to_messages(row: dict) -> dict | None:
    # OpenHermes-2.5: {conversations:[{from,value}]}
    convo = row.get("conversations")
    if isinstance(convo, list):
        msgs = [_msg({"human": "user", "gpt": "assistant", "system": "system"}.get(t.get("from"), "user"),
                     t.get("value", "")) for t in convo]
        return {"messages": msgs}
    return None


CONVERTERS_BY_KIND = {"fc": fc_to_messages, "code": code_to_messages,
                      "general": general_to_messages}


def load_hf(repo: str, split: str, sample: int):
    """Stream + take `sample` rows so we never download a whole multi-GB set
    just to keep a slice. Shuffles within a buffer for variety."""
    from datasets import load_dataset
    ds = load_dataset(repo, split=split, streaming=True)
    if sample:
        ds = ds.shuffle(seed=7, buffer_size=min(max(sample, 1000), 20000)).take(sample)
    return ds


def write_sources(out, entries: list[dict]) -> int:
    written = 0
    for entry in entries or []:
        repo, split, sample = entry["repo"], entry.get("split", "train"), entry.get("sample", 0)
        conv = CONVERTERS_BY_KIND[entry["kind"]]
        print(f"[{entry['kind']}] loading {repo} (sample={sample}) …")
        try:
            ds = load_hf(repo, split, sample)
            kept = 0
            for i, row in enumerate(ds):
                m = conv(dict(row))
                if m and m["messages"]:
                    out.write(json.dumps(m, ensure_ascii=False) + "\n")
                    kept += 1
                    if i == 0:
                        print(f"  sample -> {json.dumps(m)[:160]}")
            print(f"  kept {kept}")
            written += kept
        except Exception as e:  # noqa: BLE001
            print(f"  !! skipped {repo}: {e}")
    return written


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--brain", action="store_true",
                    help="build the OPTIONAL brain set (coding+general) -> data/train_brain.jsonl")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(CFG, encoding="utf-8"))
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if args.brain:
        out_path = ROOT / "data" / "train_brain.jsonl"
        with open(out_path, "w", encoding="utf-8") as out:
            written = write_sources(out, cfg.get("brain_optional", []))
        print(f"\nDONE -> {out_path}  ({written} examples)")
        return

    # Default: the DISPATCHER set = function-calling + synth Windows-actions.
    written = 0
    with open(OUT, "w", encoding="utf-8") as out:
        written += write_sources(out, cfg.get("dispatcher", []))
        for entry in cfg.get("synth", []) or []:
            path = ROOT / entry["file"]
            weight = int(entry.get("weight", 1))
            if not path.exists():
                print(f"  !! synth missing: {path} (run synth_windows_actions.py first)")
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            for _ in range(weight):
                for ln in lines:
                    out.write(ln + "\n")
                    written += 1
            print(f"[synth] {len(lines)} x{weight} = {len(lines) * weight}")
    print(f"\nDONE -> {OUT}  ({written} examples)")


if __name__ == "__main__":
    main()
