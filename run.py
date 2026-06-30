"""PC-Agent REPL.

    python run.py            # full agent (loads Gemma 4 — needs the model + GPU)
    python run.py --dry      # dispatcher+tools only, no LLM: type a tool call as
                             #   <tool_name> {"arg": "value"}   to test the hands.
"""
from __future__ import annotations

import argparse
import json
import sys

from rich.console import Console

from pc_agent.config import load
from pc_agent.safety import SafetyGate
from pc_agent.tools import all_schemas, get as get_tool

console = Console()


def confirm(msg: str) -> bool:
    ans = console.input(f"[yellow]{msg}[/] (y/N) ").strip().lower()
    return ans in ("y", "yes")


def dry_loop(cfg):
    """No model: directly invoke tools to verify the Windows control layer."""
    gate = SafetyGate(cfg)
    console.print("[bold]Dry mode[/] — type:  toolname {\"arg\": \"val\"}   or 'list' / 'quit'")
    while True:
        line = console.input("[cyan]tool>[/] ").strip()
        if line in ("quit", "exit"):
            return
        if line == "list":
            for s in all_schemas():
                console.print(f"  [green]{s['name']}[/] — {s['description']}")
            continue
        name, _, rest = line.partition(" ")
        tool = get_tool(name)
        if not tool:
            console.print(f"[red]unknown tool[/]: {name}")
            continue
        try:
            args = json.loads(rest) if rest.strip() else {}
        except json.JSONDecodeError:
            console.print("[red]args must be JSON[/]")
            continue
        decision = gate.evaluate(tool.risk, f"{name} {args}")
        if decision.needs_confirm and not confirm(f"Run {name}? [{tool.risk.value}]"):
            console.print("[red]skipped[/]")
            continue
        console.print(tool.fn(**args))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="tools only, no LLM")
    args = ap.parse_args()
    cfg = load()

    if args.dry:
        dry_loop(cfg)
        return

    console.print("[dim]Loading Gemma 4 (4-bit)… first run downloads weights.[/]")
    from pc_agent.brain import load_brain, load_dispatcher
    from pc_agent.agent import Agent

    brain = load_brain(cfg)
    dispatcher = load_dispatcher(cfg, brain)
    agent = Agent(cfg, brain, dispatcher, confirm_fn=confirm)

    console.print("[bold green]PC-Agent ready.[/] Type a message, or 'quit'.")
    while True:
        try:
            msg = console.input("[cyan]you>[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if msg in ("quit", "exit"):
            break
        if not msg:
            continue
        console.print(f"[bold magenta]agent>[/] {agent.handle(msg)}")


if __name__ == "__main__":
    sys.exit(main())
