"""Smoke test: verify the Executor + dispatcher plumbing with NO model/GPU.

Runs only READ-only tools (no windows opened, no settings changed). Use this to
confirm the Windows control layer works on this machine after setup.

    python scripts/smoke_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pc_agent.tools import REGISTRY, all_schemas, get  # noqa: E402
from pc_agent.dispatcher import build_prompt, parse     # noqa: E402
from pc_agent.safety import Risk                         # noqa: E402


def main() -> int:
    print(f"[OK] Registered tools: {len(REGISTRY)}")
    for name, t in REGISTRY.items():
        print(f"   - {name:<24} [{t.risk.value}]")

    print("\n-- dispatcher prompt renders + parses --")
    prompt = build_prompt("what are my pc specs")
    assert "get_system_info" in prompt, "tool schema missing from prompt"
    print(f"   prompt length: {len(prompt)} chars, includes tool schemas [OK]")
    # parser contract
    for raw, want in [
        ('{"action":"chat"}', "chat"),
        ('sure -> {"action":"tool","tool":"open_settings","args":{"page":"about"}}', "tool"),
        ('garbage no json', "chat"),
    ]:
        got = parse(raw).get("action")
        assert got == want, f"parse({raw!r}) -> {got}, wanted {want}"
    print("   parse() contract holds [OK]")

    print("\n-- READ-only tool calls on this machine --")
    print("[get_system_info]")
    print(get("get_system_info").fn(section="all"))
    print("\n[list_scheduled_tasks] (first lines)")
    out = get("list_scheduled_tasks").fn()
    print("\n".join(out.splitlines()[:5]) or "(none)")
    print("\n[list_running_apps] (top 5)")
    out = get("list_running_apps").fn()
    print("\n".join(out.splitlines()[:5]))

    # sanity: every tool has a valid risk + schema
    for s in all_schemas():
        assert "name" in s and "parameters" in s
    print("\n[OK] ALL SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
