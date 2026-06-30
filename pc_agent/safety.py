"""Safety gates: classify every action, ask before risky ones, audit everything."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .config import Config


class Risk(str, Enum):
    READ = "read"          # info gathering — safe
    INPUT = "input"        # raw cursor/keyboard
    SETTINGS = "settings"  # change settings / control panel
    DOWNLOAD = "download"  # install / download
    TASK = "task"          # scheduled tasks
    BLOCKED = "blocked"    # never allowed


@dataclass
class Decision:
    allowed: bool
    needs_confirm: bool
    reason: str


class SafetyGate:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.blocked = [c.lower() for c in cfg.get("safety.blocked_commands", [])]
        self.log_path = cfg.path("safety.audit_log", "logs/actions.jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def is_blocked(self, raw: str) -> bool:
        low = raw.lower()
        return any(b in low for b in self.blocked)

    def evaluate(self, risk: Risk, raw_command: str = "") -> Decision:
        if risk is Risk.BLOCKED or self.is_blocked(raw_command):
            return Decision(False, False, f"Hard-blocked: {raw_command!r}")

        s = self.cfg
        if risk is Risk.READ:
            return Decision(True, not s.get("safety.auto_approve_read", True), "read")
        gate = {
            Risk.DOWNLOAD: "safety.confirm_downloads",
            Risk.SETTINGS: "safety.confirm_settings",
            Risk.TASK: "safety.confirm_tasks",
            Risk.INPUT: "safety.confirm_input",
        }[risk]
        return Decision(True, bool(s.get(gate, True)), risk.value)

    def audit(self, tool: str, args: dict, result_summary: str, approved: bool):
        rec = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tool": tool,
            "args": args,
            "approved": approved,
            "result": result_summary[:500],
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
