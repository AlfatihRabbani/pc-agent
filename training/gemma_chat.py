"""Normalize arbitrary chat data into a shape Gemma's chat template accepts:
only user/assistant roles, strict alternation, starting with user.

Gemma rejects 'system'/'tool' roles and non-alternating turns, so multi-role
function-calling datasets must be normalized before apply_chat_template().
"""
from __future__ import annotations

ROLE_MAP = {
    "system": "system", "user": "user", "human": "user", "tool": "user",
    "function": "user", "observation": "user", "function_response": "user",
    "assistant": "assistant", "gpt": "assistant", "model": "assistant",
}


def normalize_for_gemma(msgs: list[dict]) -> list[dict]:
    sys_txt, norm = "", []
    for m in msgs:
        role = ROLE_MAP.get(m.get("role", "user"), "user")
        content = m.get("content", "") or ""
        if role == "system":
            sys_txt += ("\n\n" if sys_txt else "") + content
            continue
        norm.append({"role": role, "content": content})
    if sys_txt:                                  # fold system into first user turn
        for m in norm:
            if m["role"] == "user":
                m["content"] = f"{sys_txt}\n\n{m['content']}"
                break
        else:
            norm.insert(0, {"role": "user", "content": sys_txt})
    merged: list[dict] = []                      # collapse consecutive same-role
    for m in norm:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1]["content"] += "\n\n" + m["content"]
        else:
            merged.append(dict(m))
    if merged and merged[0]["role"] != "user":   # must start with user
        merged.insert(0, {"role": "user", "content": "(continue)"})
    return merged
