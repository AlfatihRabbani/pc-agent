"""Dispatcher — decides whether a message is plain chat or a PC-control action,
and if an action, emits a structured tool call.

Output contract (the model must return exactly one JSON object):
    {"action": "chat"}
    {"action": "tool", "tool": "<name>", "args": { ... }}
    {"action": "plan", "steps": [ {"tool": "...", "args": {...}}, ... ]}
"""
from __future__ import annotations

import json
import re
from typing import Callable

from .tools import all_schemas

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

SYSTEM = """You are the dispatcher for a Windows PC-control agent.
Decide what to do with the user's message and reply with ONE JSON object only — no prose.

If the user is just chatting or asking a general question, reply:
{"action": "chat"}

If the user wants something done on the PC, choose a tool and reply:
{"action": "tool", "tool": "<tool_name>", "args": {<arguments>}}

If it needs several steps, reply:
{"action": "plan", "steps": [{"tool": "<name>", "args": {...}}, ...]}

Rules:
- Use ONLY the tools listed below. Match argument names exactly.
- Never invent tools or arguments.
- Prefer the most specific tool (e.g. get_system_info for specs, open_settings for settings pages).
- Output JSON only. No markdown, no explanation.

AVAILABLE TOOLS:
{tools}
"""

# Compact prompt for the FINE-TUNED dispatcher: the model has memorized the tools,
# so a short signature list is enough. Keeps each example well under the train
# seq length (the verbose JSON-schema prompt is ~2.5k tokens and truncates answers).
COMPACT_SYSTEM = """You are the dispatcher for a Windows PC-control agent.
Reply with ONE JSON object only:
  chat       -> {"action":"chat"}
  one action -> {"action":"tool","tool":"<name>","args":{...}}
  multi-step -> {"action":"plan","steps":[{"tool":"<name>","args":{...}}]}
Use ONLY these tools, with exact arg names:
{tools}"""


def compact_tool_list() -> str:
    lines = []
    for s in all_schemas():
        args = ", ".join(s["parameters"]["properties"].keys())
        desc = s["description"].split(".")[0]
        lines.append(f"- {s['name']}({args}): {desc}")
    return "\n".join(lines)


def build_prompt(user_message: str, compact: bool = False) -> str:
    if compact:
        sys = COMPACT_SYSTEM.replace("{tools}", compact_tool_list())
    else:
        sys = SYSTEM.replace("{tools}", json.dumps(all_schemas(), indent=2))
    return f"{sys}\n\nUSER: {user_message}\nJSON:"


def parse(raw: str) -> dict:
    """Extract the first JSON object from the model output; fall back to chat."""
    m = _JSON_RE.search(raw or "")
    if not m:
        return {"action": "chat"}
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"action": "chat"}
    if not isinstance(obj, dict) or "action" not in obj:
        return {"action": "chat"}
    return obj


def route(user_message: str, generate: Callable[[str], str], compact: bool = False) -> dict:
    """generate(prompt) -> model text. Returns the parsed dispatch decision.
    Use compact=True with the fine-tuned dispatcher, compact=False in prompt mode."""
    raw = generate(build_prompt(user_message, compact=compact))
    return parse(raw)
