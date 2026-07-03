# PC-Agent

A **local AI that controls a Windows PC** — runs entirely on your own machine, no
cloud, no API keys. Chat with it in a little pop-up, or tell it to *do* things:
open apps, change settings, set the volume, search the web or a specific site,
type and click — all driven by a fine-tuned language model and a deterministic
tool layer.

Built and tuned to run on a single **RTX 3080 Ti (12 GB)**.

*Made by **AlfatihRabbani**.*

[![Model on Hugging Face](https://img.shields.io/badge/%F0%9F%A4%97%20Model-onevloth%2Fpc--agent--dispatcher--gemma4--e2b-yellow)](https://huggingface.co/onevloth/pc-agent-dispatcher-gemma4-e2b)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D6)](#)

**🤗 [Model on Hugging Face](https://huggingface.co/onevloth/pc-agent-dispatcher-gemma4-e2b)** · **⬇ [Download the app](https://github.com/AlfatihRabbani/pc-agent/releases/latest)** · **🛠 [Installation](#installation)**

> ⚠️ Research/hobby project. It can move your mouse, type, and change settings —
> read the **Safety** section before pointing it at anything you care about.

---

## Demo

![PC-Agent demo](video/demo.gif)

*Full clips: [demo 1](video/demo1.mp4) · [demo 2](video/demo2.mp4) · [demo 3](video/demo3.mp4) · [demo 4](video/demo4.mp4)*

---

## What it does

- 💬 **Chats** locally (uncensored Gemma 4 E2B).
- 🖥️ **Controls Windows** through tools, not pixel-guessing:
  - open **any installed app** by name (searches your Start-menu shortcuts — no exe names needed)
  - **volume / brightness / resolution**, system info, settings pages
  - **open URLs** and **search the web** or **a specific site** (`open youtube.com and search deltarune` → YouTube's own search)
  - **type / click / hotkeys** into the focused window
- 🪟 **Desktop app** (`app/`): a tray pop-up that **auto-loads the model on open**,
  a **Stop** button, **Show logs**, single-instance + close-frees-VRAM.

---

## Architecture

```
 you ─► Dispatcher ─► Safety gate ─► Executor (the "hands") ─► Windows
         (router)       (confirm)      pynput / PowerShell / winget / shortcuts
           │                                   │
           ▼                                   ▼
     same model, no adapter  ◄── narrate ──  tool output
        (plain chat)
```

| Layer | File | Role |
|---|---|---|
| **Dispatcher** | `pc_agent/dispatcher.py`, `app/agent_core.py` | NL → structured tool call (JSON) |
| **Executor** | `pc_agent/tools/*` | real Windows control, deterministic Python |
| **Safety** | `pc_agent/safety.py` | risk tiers, confirm, audit log |
| **App** | `app/chat_app.py` | tray pop-up UI |

**One model, two jobs:** the E2B base + a **QLoRA-fine-tuned LoRA adapter** routes
requests (adapter on); plain chat runs the **same** model with the adapter disabled.
Keeps VRAM ~8 GB.

**Why structured control instead of a vision model clicking pixels?** Far more
reliable and it fits 12 GB — the LLM decides *what*, deterministic code does it.

---

## Reality check

- You **can't pretrain** a big model on a 3080 Ti. This uses **pretrained Gemma 4**
  and **QLoRA-fine-tunes** the small **E2B** dispatcher — the realistic, effective path.
- The dispatcher was trained 2 epochs (~3.2k steps) on ~25.8k function-calling +
  synthetic Windows-action examples.
- **Perception is the open piece:** the model can't yet reliably *read the screen*
  (screenshot Q&A / locate UI by sight). Everything here works without it; in-page
  search for arbitrary sites would need it.

---

## Installation

**Requirements:** Windows 10/11, an NVIDIA GPU (~12 GB VRAM), Python 3.10, Git.

**1. Clone the repo**
```bat
git clone https://github.com/AlfatihRabbani/pc-agent
cd pc-agent
```

**2. Install (creates the venv + CUDA PyTorch + deps)**
```bat
scripts\setup.bat
```

**3. Get the model**
```bat
:: base E2B (downloads ~10 GB from Hugging Face into the local cache):
python scripts\download_models.py

:: the trained dispatcher adapter -> models\dispatcher-final\ :
.venv\Scripts\hf download onevloth/pc-agent-dispatcher-gemma4-e2b --local-dir models\dispatcher-final
```

**4. (Optional) Better chat/writing with a 12B model via [Ollama](https://ollama.com)**
```bat
ollama create pc-agent-12b -f build\Modelfile.gemma12b   :: point the FROM line at your GGUF
```
Then pick it in the app's **⚙ Settings → Chat model**. Skip this to use the built-in E2B.

**5. Run**
```bat
PC-Agent.vbs          :: the desktop app (auto-loads the model on open)
:: or:  python run.py --dry   (test the tools, no model)   |   python run.py   (REPL)
```

> Want a one-click launcher? Build `PC-Agent.exe` with `build\build_exe.bat`, or grab it
> from the [latest release](https://github.com/AlfatihRabbani/pc-agent/releases/latest).

---

## Train the dispatcher

```bat
python training\synth_windows_actions.py     :: custom NL→tool-call data
python training\build_dataset.py             :: + HF sets -> data\train.jsonl
python training\train_qlora.py --epochs 2 --seq_len 512 --throttle 1.5
```
QLoRA, NF4 4-bit, batch1/accum16 — tuned to fit 12 GB. On a 3080 Ti, cap power
(`nvidia-smi -pl 250`) to avoid TDR resets under sustained load.

---

## Safety

Every action is classified (`read` / `input` / `settings` / `download` / `task`) and
gated in `config.yaml > safety`. Downloads, settings changes, and scheduled tasks ask
for confirmation; a hard blocklist refuses destructive commands (`format`, `diskpart`,
`reg delete HKLM`, …). Everything is appended to `logs/actions.jsonl`.

`safety.confirm_input` toggles the prompt before raw typing/clicking.

---

## Layout

```
pc-agent/
├── config.yaml          # model ids, paths, safety, input backend
├── run.py               # REPL (--dry = tools only)
├── app/                 # desktop tray app
│   ├── chat_app.py      # UI: tray, Stop, Show logs, auto-load
│   └── agent_core.py    # routing (adapter) + chat (base) + tools
├── pc_agent/
│   ├── dispatcher.py    # NL -> tool-call JSON
│   ├── safety.py        # risk tiers, confirm, audit
│   └── tools/           # the Executor: apps, settings, audio, display,
│                        #   network, system_info, input_control, screen
└── training/            # synth data + dataset build + QLoRA fine-tune
```

---

## License

Code: **MIT** (see `LICENSE`). The trained adapter is a derivative of Google's
**Gemma 4** and is governed by the [Gemma Terms of Use](https://ai.google.dev/gemma/terms).
