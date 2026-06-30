"""Inspect the multimodal module structure (no weights), then try a 4-bit load
that SKIPS the vision/audio towers — the likely segfault source."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pc_agent.hf_cache  # noqa
import torch
from transformers import AutoConfig, AutoModelForCausalLM, BitsAndBytesConfig
from accelerate import init_empty_weights

repo = "huihui-ai/Huihui-gemma-4-E4B-it-abliterated"
cfg = AutoConfig.from_pretrained(repo)
with init_empty_weights():
    skeleton = AutoModelForCausalLM.from_config(cfg)
print("class:", type(skeleton).__name__, flush=True)
print("top children:", [n for n, _ in skeleton.named_children()], flush=True)

mm = set()
for n, _ in skeleton.named_modules():
    low = n.lower()
    if any(k in low for k in ("vision", "audio", "multi_modal", "multimodal")):
        mm.add(n.split(".")[0])
skip = sorted(mm) + ["lm_head"]
print("skip in quant:", skip, flush=True)

q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                       bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True,
                       llm_int8_skip_modules=skip)
print("loading 4-bit with skip_modules, forcing all on GPU...", flush=True)
import time
t = time.time()
m = AutoModelForCausalLM.from_pretrained(repo, quantization_config=q,
                                         device_map={"": 0}, low_cpu_mem_usage=True)
print(f"LOADED in {time.time()-t:.0f}s | GPU alloc {torch.cuda.memory_allocated()/1e9:.1f} GB", flush=True)
