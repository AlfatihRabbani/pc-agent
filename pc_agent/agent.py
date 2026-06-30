"""Orchestrator: route -> safety-gate -> (confirm) -> execute -> audit -> reply."""
from __future__ import annotations

from typing import Callable

from .config import Config
from .dispatcher import route
from .safety import SafetyGate
from .tools import get as get_tool


class Agent:
    def __init__(self, cfg: Config, brain, dispatcher,
                 confirm_fn: Callable[[str], bool] | None = None):
        self.cfg = cfg
        self.brain = brain
        self.dispatcher = dispatcher
        self.gate = SafetyGate(cfg)
        # confirm_fn(prompt) -> bool. Default: deny when no UI is wired.
        self.confirm = confirm_fn or (lambda _msg: False)
        self.history: list[dict] = []
        # fine-tuned dispatcher uses the short prompt it was trained on
        self.compact = cfg.get("dispatcher.mode", "prompt") == "finetuned"

    # ── execution ────────────────────────────────────────────────
    def _run_tool(self, name: str, args: dict) -> str:
        tool = get_tool(name)
        if tool is None:
            return f"[unknown tool: {name}]"
        decision = self.gate.evaluate(tool.risk, raw_command=f"{name} {args}")
        if not decision.allowed:
            self.gate.audit(name, args, decision.reason, approved=False)
            return f"[blocked] {decision.reason}"
        if decision.needs_confirm:
            ok = self.confirm(f"Allow {name}({args})? [{tool.risk.value}]")
            if not ok:
                self.gate.audit(name, args, "user denied", approved=False)
                return f"[denied by user] {name}"
        try:
            result = tool.fn(**args)
        except TypeError as e:
            result = f"[bad arguments for {name}: {e}]"
        except Exception as e:  # noqa: BLE001
            result = f"[error in {name}: {e}]"
        self.gate.audit(name, args, str(result), approved=True)
        return str(result)

    # ── top-level turn ──────────────────────────────────────────
    def handle(self, user_message: str) -> str:
        self.history.append({"role": "user", "content": user_message})
        decision = route(user_message, self.dispatcher.generate, compact=self.compact)
        action = decision.get("action", "chat")

        if action == "chat":
            reply = self.brain.chat(self.history)
            self.history.append({"role": "assistant", "content": reply})
            return reply

        if action == "tool":
            out = self._run_tool(decision.get("tool", ""), decision.get("args", {}))
            return self._narrate(user_message, [out])

        if action == "plan":
            outs = []
            for step in decision.get("steps", []):
                outs.append(self._run_tool(step.get("tool", ""), step.get("args", {})))
            return self._narrate(user_message, outs)

        return "I wasn't sure how to handle that."

    def _narrate(self, user_message: str, results: list[str]) -> str:
        """Let the brain turn raw tool output into a natural reply."""
        joined = "\n".join(f"- {r}" for r in results)
        prompt = (f"The user asked: {user_message!r}\n"
                  f"You performed actions on their Windows PC with these results:\n{joined}\n\n"
                  f"Reply to the user conversationally, confirming what was done. Be concise.")
        reply = self.brain.generate(prompt, max_new_tokens=256, temperature=0.5)
        self.history.append({"role": "assistant", "content": reply})
        return reply
