"""Self-contained inference core for the PC-Agent chat app.

Loads ONE model — the E2B abliterated base + the trained `dispatcher-final`
LoRA adapter — and uses it two ways:
  * routing  : adapter ON  + compact prompt  -> {"action": ...} tool decision
  * chatting : adapter OFF (clean base)       -> natural conversation
Tool calls run through the existing pc_agent tools + SafetyGate.

This keeps VRAM to ~5 GB (one 4-bit model) instead of loading the 12B brain
and the E2B dispatcher separately.
"""
from __future__ import annotations

import re
import sys
import threading
from contextlib import nullcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pc_agent.hf_cache  # noqa: E402,F401  (pin HF cache to E: before transformers)
from pc_agent import dispatcher           # noqa: E402
from pc_agent.config import load          # noqa: E402
from pc_agent.safety import SafetyGate    # noqa: E402
from pc_agent.tools import get as get_tool  # noqa: E402
from pc_agent.tools.apps import SITE_SEARCH  # noqa: E402
from pc_agent.tools.registry import REGISTRY  # noqa: E402

# Matches a domain/URL in a message (youtube.com, https://github.com, rule34.xxx, www.reddit.com/r/x).
_URL_RE = re.compile(
    r"\b(?:https?://)?(?:www\.)?[a-z0-9-]+\.(?:com|org|net|io|gg|tv|co|dev|gov|edu|me|app|"
    r"xyz|info|ai|us|uk|ca|de|jp|in|ru|to|cc|biz|online|store|site|tech|xxx|porn|sex|adult|"
    r"fun|moe|fm|tk|ws|gl|su|cat|stream|wiki)(?:/[^\s]*)?\b", re.I)

PERSONA = ("You are PC-Agent, a friendly assistant running locally on the user's "
           "Windows PC. You can chat normally and you can control the PC (open apps, "
           "change settings, read system info, move the mouse, etc.). Keep replies concise.")

# Few-shot routing prompt for the FALLBACK (base model, adapter off). The trained
# E2B adapter handles simple one-tool reads, but fumbles compound/arg-heavy commands;
# the base model with these examples reliably produces plans and fills arguments.
FALLBACK_SYSTEM = """Convert the user's request into ONE JSON object for a Windows control agent.
Output JSON only — no prose.
  one action  -> {"action":"tool","tool":"<name>","args":{...}}
  several, in order -> {"action":"plan","steps":[{"tool":"<name>","args":{...}}, ...]}
  just chatting -> {"action":"chat"}
Always include EVERY required argument, taking values from the user's exact words.

TOOLS (name(args): purpose):
{tools}

EXAMPLES:
user: open notepad
{"action":"tool","tool":"open_app","args":{"app":"notepad"}}
user: what are my pc specs
{"action":"tool","tool":"get_system_info","args":{}}
user: set the volume to 30
{"action":"tool","tool":"set_volume","args":{"level":30}}
user: open notepad and type hello world
{"action":"plan","steps":[{"tool":"open_app","args":{"app":"notepad"}},{"tool":"type_text","args":{"text":"hello world"}}]}
user: open calculator then type 2+2
{"action":"plan","steps":[{"tool":"open_app","args":{"app":"calculator"}},{"tool":"type_text","args":{"text":"2+2"}}]}
user: search for roblox
{"action":"tool","tool":"web_search","args":{"query":"roblox"}}
user: open firefox and search roblox
{"action":"tool","tool":"web_search","args":{"query":"roblox"}}
user: look up the weather in tokyo
{"action":"tool","tool":"web_search","args":{"query":"weather in tokyo"}}
user: youtube.com
{"action":"tool","tool":"open_url","args":{"url":"youtube.com"}}
user: open github.com
{"action":"tool","tool":"open_url","args":{"url":"github.com"}}
user: open youtube.com and search deltarune
{"action":"tool","tool":"site_search","args":{"site":"youtube.com","query":"deltarune"}}
user: search cats on youtube
{"action":"tool","tool":"site_search","args":{"site":"youtube","query":"cats"}}
user: play radiant emerald on youtube
{"action":"tool","tool":"play_youtube","args":{"query":"radiant emerald"}}
user: play diamonds in the sky from sonic r
{"action":"tool","tool":"play_youtube","args":{"query":"diamonds in the sky from sonic r"}}
user: how are you today
{"action":"chat"}

user: {msg}
JSON:"""


# Tools that inject keystrokes/clicks into whatever window has OS focus.
INPUT_TOOLS = {"type_text", "click_at", "move_cursor", "press_hotkey"}

# command keyword -> a substring of the target window's title bar.
APP_HINTS = {
    "firefox": "Firefox", "chrome": "Chrome", "edge": "Edge", "brave": "Brave",
    "notepad": "Notepad", "wordpad": "WordPad", "word": "Word", "excel": "Excel",
    "calculator": "Calculator", "calc": "Calculator", "paint": "Paint",
    "explorer": "File Explorer", "discord": "Discord", "steam": "Steam",
    "spotify": "Spotify", "blender": "Blender", "vscode": "Visual Studio Code",
    "terminal": "Terminal", "powershell": "PowerShell", "cmd": "Command Prompt",
}


def _find_adapter() -> str | None:
    import glob
    for name in ("dispatcher-final", "dispatcher-cur", "dispatcher-burst", "dispatcher-e4b-qlora"):
        d = ROOT / "models" / name
        if (d / "adapter_model.safetensors").exists():
            return str(d)
        cks = glob.glob(str(d / "checkpoint-*"))
        if cks:
            cks.sort(key=lambda p: int(p.split("-")[-1]))
            return cks[-1]
    return None


_NUMERIC_KEYS = {"level", "x", "y", "value", "brightness", "percent", "volume", "width", "height"}


def _coerce_args(tool_name: str, args) -> dict:
    """Make args a dict even when the model returns a bare scalar (e.g. set_volume -> 50),
    and turn numeric strings into ints. Prevents 'argument of type int is not iterable'."""
    if not isinstance(args, dict):
        t = get_tool(tool_name)
        if t and len(t.required) == 1 and args is not None and not isinstance(args, (list, dict)):
            args = {t.required[0]: args}
        else:
            args = {}
    for k, v in list(args.items()):
        if k.lower() in _NUMERIC_KEYS and isinstance(v, str) and v.strip().lstrip("-").isdigit():
            args[k] = int(v)
    return args


def _normalize(dec: dict) -> dict:
    """Accept the dispatcher's shorthand {'action':'<tool>'} as a proper tool call, and
    make sure every tool call's args is a clean dict."""
    if not isinstance(dec, dict):
        return {"action": "chat"}
    act = dec.get("action")
    if act == "open_app":                       # common shorthand: app name in 'tool'/'app'
        args = dict(dec.get("args") or {}) if isinstance(dec.get("args"), dict) else {}
        args.setdefault("app", dec.get("tool") or dec.get("app") or "")
        return {"action": "tool", "tool": "open_app", "args": args}
    if act not in ("chat", "tool", "plan") and act in REGISTRY:
        dec = {"action": "tool", "tool": act, "args": dec.get("args", {})}
        act = "tool"
    if act == "tool":
        dec["args"] = _coerce_args(dec.get("tool", ""), dec.get("args"))
    elif act == "plan":
        for s in (dec.get("steps") or []):
            if isinstance(s, dict):
                s["args"] = _coerce_args(s.get("tool", ""), s.get("args"))
    elif act != "chat":
        return {"action": "chat"}
    return dec


class AgentCore:
    """Loads the model and answers messages (chat or PC-control)."""

    def __init__(self, status=lambda s: None, get_external_hwnd=None, before_input=None):
        import gc

        import torch
        from transformers import (AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
                                  StoppingCriteria, StoppingCriteriaList)

        self.torch = torch
        self.cfg = load()
        self.gate = SafetyGate(self.cfg)
        self.history: list[dict] = []
        self._stop = threading.Event()              # set by request_stop() to cancel a turn

        class _StopOnFlag(StoppingCriteria):
            def __init__(s, flag):
                s.flag = flag

            def __call__(s, input_ids, scores, **kwargs):
                return s.flag.is_set()
        self._stopcrit = StoppingCriteriaList([_StopOnFlag(self._stop)])
        self.get_external_hwnd = get_external_hwnd   # () -> hwnd of last non-PC-Agent window
        self.before_input = before_input             # () -> drop our own focus (last resort)

        base = self.cfg.get("dispatcher.base_model_id")
        # Prefer a local copy on a fast SSD if configured (reading ~10GB off the HDD is
        # what makes cold start slow). dispatcher.fast_dir in config.yaml.
        fast = self.cfg.path("dispatcher.fast_dir") if self.cfg.get("dispatcher.fast_dir") else None
        source = str(fast) if fast and Path(fast).exists() else base
        adapter = _find_adapter()
        status(f"Loading model {Path(source).name} (4-bit)…")

        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                   bnb_4bit_compute_dtype=torch.bfloat16,
                                   bnb_4bit_use_double_quant=True)
        self.tok = AutoTokenizer.from_pretrained(source)
        if self.tok.pad_token is None:
            self.tok.pad_token = self.tok.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(
            source, quantization_config=quant, torch_dtype=torch.bfloat16, device_map="auto")

        # Text-only app: drop the vision/audio towers to free ~1-2 GB VRAM.
        _b = getattr(self.model, "model", self.model)
        for _t in ("vision_tower", "audio_tower"):
            if getattr(_b, _t, None) is not None:
                setattr(_b, _t, None)
        gc.collect()
        torch.cuda.empty_cache()

        self.has_adapter = False
        if adapter:
            status(f"Attaching adapter {Path(adapter).name}…")
            from peft import PeftModel
            self.model = PeftModel.from_pretrained(self.model, adapter)
            self.has_adapter = True
        self.model.eval()
        self.adapter_name = Path(adapter).name if adapter else "none (prompt mode)"
        status("Ready.")

    # ── low-level generation ────────────────────────────────────────
    def _gen(self, messages: list[dict], max_new: int, temperature: float,
             use_adapter: bool) -> str:
        torch = self.torch
        enc = self.tok.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt",
            return_dict=True).to(self.model.device)
        ctx = nullcontext()
        if self.has_adapter and not use_adapter:
            ctx = self.model.disable_adapter()   # run the clean base model
        with ctx, torch.no_grad():
            out = self.model.generate(
                **enc, max_new_tokens=max_new,
                do_sample=temperature > 0, temperature=max(temperature, 1e-5),
                pad_token_id=self.tok.eos_token_id,
                stopping_criteria=self._stopcrit)
        n_in = enc["input_ids"].shape[1]
        return self.tok.decode(out[0][n_in:], skip_special_tokens=True).strip()

    def request_stop(self):
        """Cancel the current turn (stops generation at the next token)."""
        self._stop.set()

    # ── routing + chat ──────────────────────────────────────────────
    def _valid(self, dec: dict) -> bool:
        """A decision is usable only if every chosen tool exists with all required args."""
        a = dec.get("action")
        if a == "chat":
            return True
        if a == "tool":
            t = get_tool(dec.get("tool", ""))
            return bool(t) and all(k in dec.get("args", {}) for k in t.required)
        if a == "plan":
            steps = dec.get("steps", [])
            if not steps:
                return False
            for s in steps:
                t = get_tool(s.get("tool", ""))
                if not t or not all(k in s.get("args", {}) for k in t.required):
                    return False
            return True
        return False

    def _repair(self, dec: dict, msg: str) -> dict:
        """Best-effort fill of missing required args straight from the user's words."""
        import re

        def fix(step: dict):
            args = step.setdefault("args", {})
            if step.get("tool") == "type_text" and "text" not in args:
                m = re.search(r"\btype(?:\s+in)?\s+(.+)", msg, re.I)
                if m:
                    args["text"] = m.group(1).strip().strip("'\"")
            if step.get("tool") == "open_app":
                # use the FULL app phrase from the message (the model often truncates,
                # e.g. "open libreoffice writer" -> just "libreoffice").
                m = re.search(r"\b(?:open|launch|start|run)\s+([a-z0-9][a-z0-9 .+\-]*?)"
                              r"(?:\s+and\b|\s+then\b|$)", msg, re.I)
                if m:
                    full = m.group(1).strip()
                    if full and (not args.get("app") or len(full) > len(str(args.get("app", "")))):
                        args["app"] = full
            if step.get("tool") == "web_search" and not args.get("query"):
                m = re.search(r"\b(?:search(?:\s+for)?|look\s*up|google|browse)\s+(.+)", msg, re.I)
                if m:
                    q = re.sub(r"\s+(?:in|on|using|with)\s+\w+\s*$", "", m.group(1).strip(), flags=re.I)
                    args["query"] = q.strip().strip("'\"")
            if step.get("tool") == "open_url" and not args.get("url"):
                m = _URL_RE.search(msg)
                if m:
                    args["url"] = m.group(0)
            if step.get("tool") == "site_search":
                if not args.get("site"):
                    m = _URL_RE.search(msg)
                    if m:
                        args["site"] = m.group(0)
                    else:
                        for k in SITE_SEARCH:
                            if re.search(rf"\b{re.escape(k)}\b", msg, re.I):
                                args["site"] = k
                                break
                if not args.get("query"):
                    m = re.search(r"\bsearch(?:\s+for)?\s+(.+)", msg, re.I)
                    if m:
                        q = re.sub(r"\s+(?:on|in|at|using)\s+[\w.\-/:]+\s*$", "", m.group(1).strip(), flags=re.I)
                        args["query"] = q.strip().strip("'\"")
        if dec.get("action") == "tool":
            fix(dec)
        elif dec.get("action") == "plan":
            for s in dec.get("steps", []):
                fix(s)
        return dec

    @staticmethod
    def _multistep(msg: str) -> bool:
        """Heuristic: a compound request (>=2 action verbs joined by and/then) needs a plan,
        which the tiny adapter botches — send those straight to the plan-capable fallback."""
        import re
        verbs = re.findall(r"\b(open|launch|start|run|type|write|enter|search|set|change|"
                           r"close|press|click|download|install|mute|unmute|go to|take)\b", msg, re.I)
        connector = re.search(r"\b(and|then|after|,)\b", msg, re.I)
        return bool(connector) and len(verbs) >= 2

    @staticmethod
    def _force_fallback(msg: str) -> bool:
        """Use the few-shot fallback (not the tiny adapter) for compound requests, URLs/links,
        and web-search intents — the adapter mishandles all three."""
        if AgentCore._multistep(msg):
            return True
        if _URL_RE.search(msg):
            return True
        low = msg.lower()
        if re.search(r"\b(search|look ?up|google|browse)\b", low) and not \
           re.search(r"\b(software|app|apps|program|install|installed|package|winget|download)\b", low):
            return True
        return False

    def _coerce_site_search(self, msg: str) -> dict | None:
        """Deterministic URL/site handling — don't leave it to the model, which often does
        open_url + plain web_search instead of searching the site (or mis-handles 'search up X')."""
        url_m = _URL_RE.search(msg)
        # the query is whatever follows the LAST search verb ("...site and look up X")
        verbs = list(re.finditer(r"\b(?:search(?:\s+up|\s+for)?|look\s*up|find|google)\b", msg, re.I))

        site = url_m.group(0) if url_m else None
        if not site and verbs:
            # a bare site keyword counts ONLY when explicitly called out as the destination
            # ("... on youtube", "open youtube and ...") — not just any mention ("roblox video").
            for k in SITE_SEARCH:
                if re.search(rf"\b(?:on|in|at|from|inside|open|goto|go to|using)\s+{re.escape(k)}\b", msg, re.I):
                    site = k
                    break

        q = None
        if verbs:
            q = msg[verbs[-1].end():].strip()                      # text after the LAST search verb
            if site:
                q = re.sub(rf"\s+(?:on|in|at|from|inside|using)\s+{re.escape(site)}\b.*$", "", q, flags=re.I)
                q = re.sub(re.escape(site), "", q, flags=re.I)
            for k in SITE_SEARCH:                                  # strip a trailing "... on/inside <site>"
                q = re.sub(rf"\s+(?:on|in|at|from|inside|using)\s+{re.escape(k)}\b.*$", "", q, flags=re.I)
            q = re.sub(r"^(?:and\s+|please\s+|for\s+|up\s+)+", "", q.strip(), flags=re.I)   # leading filler
            q = q.strip().strip("'\"").strip()

        if site and q:
            return {"action": "tool", "tool": "site_search", "args": {"site": site, "query": q}}
        # a URL with no real query -> just open it ("youtube.com", "search up wikipedia.com")
        if url_m and not q:
            return {"action": "tool", "tool": "open_url", "args": {"url": url_m.group(0)}}
        return None

    def _coerce_play(self, msg: str) -> dict | None:
        """'play <song> [on youtube]' -> play_youtube (finds + plays the top result)."""
        m = re.match(r"^\s*(?:play|put on|start playing)\s+(.+)", msg.strip(), re.I)
        if not m:
            return None
        q = m.group(1).strip()
        q = re.sub(r"^(?:the\s+)?(?:song|track|music|video)\s+", "", q, flags=re.I)
        q = re.sub(r"\s+(?:on|in|from|via|using)\s+(?:youtube|yt|the\s+browser|browser)\s*$",
                   "", q, flags=re.I)
        q = q.strip().strip("'\"").strip()
        if not q:
            return None
        return {"action": "tool", "tool": "play_youtube", "args": {"query": q}}

    def _route(self, user_msg: str) -> dict:
        # 0) deterministic: "play X" -> youtube; "<site> ... search Y" -> that site's search
        for _coerce in (self._coerce_play, self._coerce_site_search):
            coerced = _coerce(user_msg)
            if coerced:
                self._flog(f"[route] msg={user_msg!r} COERCE dec={coerced}")
                return coerced

        # 1) fast path: trained adapter + compact prompt (great for simple one-tool reads).
        #    Skip it for compound/web-search requests — those need the plan-capable fallback.
        if self.has_adapter and not self._force_fallback(user_msg):
            raw = self._gen([{"role": "user", "content": dispatcher.build_prompt(user_msg, compact=True)}],
                            max_new=128, temperature=0.0, use_adapter=True)
            dec = self._repair(_normalize(dispatcher.parse(raw)), user_msg)
            self._flog(f"[route] msg={user_msg!r} FAST raw={raw!r} dec={dec}")
            if self._valid(dec) and dec.get("action") != "chat":
                return dec

        # 2) fallback: base model + few-shot (handles plans + argument extraction)
        fb_prompt = FALLBACK_SYSTEM.replace("{tools}", dispatcher.compact_tool_list()).replace("{msg}", user_msg)
        raw = self._gen([{"role": "user", "content": fb_prompt}],
                        max_new=200, temperature=0.0, use_adapter=False)
        dec = self._repair(_normalize(dispatcher.parse(raw)), user_msg)
        self._flog(f"[route] msg={user_msg!r} FALLBACK raw={raw!r} dec={dec} valid={self._valid(dec)}")
        if self._valid(dec):
            return dec
        # 3) nothing solid -> treat as chat
        return {"action": "chat"}

    def _chat(self) -> str:
        msgs = [dict(m) for m in self.history]
        msgs[0]["content"] = f"{PERSONA}\n\n{msgs[0]['content']}"   # fold persona into 1st user turn
        return self._gen(msgs, max_new=384, temperature=0.7, use_adapter=False)

    # ── window focus so injected input lands on the TARGET, not our chat box ──
    def _find_window(self, substr: str):
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def cb(h, _):
            if u.IsWindowVisible(h):
                n = u.GetWindowTextLengthW(h)
                if n:
                    b = ctypes.create_unicode_buffer(n + 1)
                    u.GetWindowTextW(h, b, n + 1)
                    if substr.lower() in b.value.lower() and "PC-Agent" not in b.value:
                        found.append(h)
            return True
        u.EnumWindows(cb, 0)
        return found[0] if found else None

    def _focus_hwnd(self, hwnd) -> bool:
        import ctypes
        u, k = ctypes.windll.user32, ctypes.windll.kernel32
        if not hwnd or not u.IsWindow(hwnd):
            return False
        cur = k.GetCurrentThreadId()
        fg = u.GetForegroundWindow()
        u.AttachThreadInput(cur, u.GetWindowThreadProcessId(fg, None), True)
        u.AttachThreadInput(cur, u.GetWindowThreadProcessId(hwnd, None), True)
        u.ShowWindow(hwnd, 9)
        u.BringWindowToTop(hwnd)
        u.SetForegroundWindow(hwnd)
        u.AttachThreadInput(cur, u.GetWindowThreadProcessId(fg, None), False)
        u.AttachThreadInput(cur, u.GetWindowThreadProcessId(hwnd, None), False)
        return True

    def _hotkey(self, *keys):
        t = get_tool("press_hotkey")
        if t:
            try:
                t.fn(keys=list(keys))
            except Exception:  # noqa: BLE001
                pass

    def _title_of(self, hwnd) -> str:
        import ctypes
        u = ctypes.windll.user32
        n = u.GetWindowTextLengthW(hwnd)
        if not n:
            return ""
        b = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, b, n + 1)
        return b.value

    def _flog(self, msg: str):
        try:
            with open(ROOT / "logs" / "focus_log.txt", "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:  # noqa: BLE001
            pass

    def _focus_target(self, msg: str):
        """Give OS focus to the window the user means, so the next keystroke/click
        lands there — never in our own chat entry."""
        import re
        import time
        low = msg.lower()
        # 1) an app named in the command
        for kw, title in APP_HINTS.items():
            if re.search(rf"\b{re.escape(kw)}\b", low):
                h = self._find_window(title)
                if h and self._focus_hwnd(h):
                    self._flog(f"named '{kw}' -> '{self._title_of(h)}'")
                    time.sleep(0.35)
                    if title in ("Firefox", "Chrome", "Edge", "Brave") and \
                       re.search(r"\b(search|address|url|bar)\b", low):
                        self._hotkey("ctrl", "l")    # focus the browser address/search bar
                        time.sleep(0.2)
                    return
        # 2) the last window the user was actually using
        if self.get_external_hwnd:
            h = self.get_external_hwnd()
            if h and self._focus_hwnd(h):
                self._flog(f"last-external -> '{self._title_of(h)}'")
                time.sleep(0.35)
                return
            self._flog(f"last-external EMPTY (hwnd={h})")
        # 3) last resort: drop our own focus so we aren't the keystroke target
        if self.before_input:
            self._flog("fallback: minimize self")
            self.before_input()
            time.sleep(0.4)

    def _run_tool(self, name: str, args: dict, confirm, focus_msg: str | None = None) -> str:
        tool = get_tool(name)
        if tool is None:
            return f"[unknown tool: {name}]"
        decision = self.gate.evaluate(tool.risk, raw_command=f"{name} {args}")
        if not decision.allowed:
            self.gate.audit(name, args, decision.reason, approved=False)
            return f"[blocked] {decision.reason}"
        if decision.needs_confirm and not confirm(f"Allow {name}({args})?  [{tool.risk.value}]"):
            self.gate.audit(name, args, "user denied", approved=False)
            return f"[denied] {name}"
        # After any confirm, just before injecting input, focus the intended window.
        if focus_msg is not None and name in INPUT_TOOLS:
            self._focus_target(focus_msg)
        try:
            result = str(tool.fn(**args))
        except Exception as e:  # noqa: BLE001
            result = f"[error in {name}: {e}]"
        self.gate.audit(name, args, result, approved=True)
        return result

    def handle(self, user_msg: str, confirm=lambda _m: False) -> str:
        """Route the message, run any tools, return the reply text."""
        self._stop.clear()
        self.history.append({"role": "user", "content": user_msg})
        dec = self._route(user_msg)
        action = dec.get("action", "chat")

        if self._stop.is_set():
            reply = "⏹ Stopped."
        elif action == "tool":
            out = self._run_tool(dec.get("tool", ""), dec.get("args", {}), confirm, focus_msg=user_msg)
            reply = f"✓ {dec.get('tool')}\n{out}"
        elif action == "plan":
            import time
            steps = dec.get("steps", [])
            outs = []
            prev = None
            for i, s in enumerate(steps):
                if self._stop.is_set():
                    break
                tool = s.get("tool", "")
                # a step that opens an app already focuses it; otherwise focus the target first
                focus_msg = None if prev == "open_app" else user_msg
                outs.append(self._run_tool(tool, s.get("args", {}), confirm, focus_msg=focus_msg))
                prev = tool
                if i < len(steps) - 1:
                    # give a just-launched app time to focus before the next step types into it
                    time.sleep(1.6 if tool == "open_app" else 0.5)
            reply = "\n".join(f"✓ {s.get('tool')}: {o}" for s, o in zip(steps, outs))
        else:
            reply = self._chat()
            if self._stop.is_set():
                reply = "⏹ Stopped."

        self.history.append({"role": "assistant", "content": reply})
        # keep history bounded
        if len(self.history) > 20:
            self.history = self.history[-20:]
        return reply
