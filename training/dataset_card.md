# Dataset card — PC-Agent dispatcher fine-tune

This is the **before-training checkpoint**: the datasets we committed to, why, and
the honest assessment. Edit `training/datasets.yaml` to change what gets pulled.

## What we train and why

We fine-tune the **dispatcher** (Gemma 4 E4B) — the router that turns
"open About PC" into `{"action":"tool","tool":"open_about_page","args":{}}`.
We do **not** retrain the 12B brain (it keeps its general knowledge; retraining it
would risk catastrophic forgetting and won't fit the 12 GB card alongside training).

## Committed datasets

### A · Dispatcher / tool-calling (the core skill)
| Dataset | Size | License | Verdict |
|---|---|---|---|
| `Salesforce/xlam-function-calling-60k` | 60K, 3,673 APIs | CC-BY-4.0 | ⭐ Cleanest executable function calls — primary |
| `NousResearch/hermes-function-calling-v1` | multi-turn, json-mode, agentic | Apache-2.0 | ⭐ Teaches multi-step plans |

### B · Coding ("for coding tasks")
| Dataset | Size | License | Verdict |
|---|---|---|---|
| `ise-uiuc/Magicoder-Evol-Instruct-110K` | 110K | Apache-2.0 | ⭐ High-quality instruct code |
| `m-a-p/Code-Feedback` | ~67K | Apache-2.0 | ⭐ Multi-turn + execution feedback (debugging) |

### C · General knowledge (kept light on purpose)
| Dataset | Size | License | Verdict |
|---|---|---|---|
| `teknium/OpenHermes-2.5` | ~1M (we sample 8K) | other | Tone/instruction-following only — small slice |

### D · Custom Windows-actions (generated locally) ⭐ highest value
`data/synth_windows_actions.jsonl` — produced by `synth_windows_actions.py` directly
from our tool registry. Maps real requests → the exact tool calls our Executor
exposes (About PC, Control Panel applets, Task Scheduler, winget, second-cursor
input). Oversampled ×3 because it's small but the most on-target. **Nothing on HF
covers your specific Windows actions, so this is what makes the agent actually work.**

## Optional adds (not pulled by default — for richer GUI grounding later)
| Dataset | Why you'd add it | Cost |
|---|---|---|
| `xlangai/AgentNet` | 22.6K real desktop trajectories incl. Windows | Large; vision-oriented |
| `ServiceNow/ui-vision` | click/drag/key grounding across 83 apps | Eval-grade, license-permissive |
| GUI-360 | 1.2M steps in Windows Office apps | Very large; sample only |

These are **screenshot/pixel** datasets. They only help if you go the
vision-grounding route (heavy on a 12 GB card). Our design drives Windows via
structured APIs, so they're optional — add a sampled slice only if you want the
agent to also click arbitrary on-screen targets by sight.

## Honest assessment — is it enough, or add more?
- **Tool-calling + coding: strong, sufficient.** xlam + hermes is the standard,
  proven recipe; Magicoder + Code-Feedback are top-tier for code.
- **The real lever is the custom synth set (D)** — start at `--n 3000`, grow to
  ~8–10K and add more phrasings/edge-cases if routing misfires.
- **Don't over-add general data (C)** — more isn't better; it dilutes the routing
  signal and can dumb the model down.
- **Add the GUI sets (optional) only if** you later want pixel-level clicking.

## Sources
- xlam: https://huggingface.co/datasets/Salesforce/xlam-function-calling-60k
- hermes: https://huggingface.co/datasets/NousResearch/hermes-function-calling-v1
- Magicoder: https://huggingface.co/datasets/ise-uiuc/Magicoder-Evol-Instruct-110K
- Code-Feedback: https://huggingface.co/datasets/m-a-p/Code-Feedback
- OpenHermes-2.5: https://huggingface.co/datasets/teknium/OpenHermes-2.5
- AgentNet: https://huggingface.co/datasets/xlangai/AgentNet
- UI-Vision: https://huggingface.co/datasets/ServiceNow/ui-vision
