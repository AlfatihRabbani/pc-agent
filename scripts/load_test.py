"""Diagnostic: load the E4B in 4-bit while logging RAM, to see if loading OOMs."""
import sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pc_agent.hf_cache  # noqa
import psutil

stop = threading.Event()
def mon():
    while not stop.is_set():
        v = psutil.virtual_memory()
        print(f"   [ram] {v.percent:.0f}% used, {v.available/1e9:.1f} GB free", flush=True)
        time.sleep(4)
threading.Thread(target=mon, daemon=True).start()

import torch
from transformers import AutoModelForCausalLM, BitsAndBytesConfig
q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                       bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
print("loading 16GB model in 4-bit (low_cpu_mem_usage)...", flush=True)
t = time.time()
m = AutoModelForCausalLM.from_pretrained(
    "huihui-ai/Huihui-gemma-4-E4B-it-abliterated",
    quantization_config=q, device_map="auto", low_cpu_mem_usage=True)
stop.set()
print(f"LOADED in {time.time()-t:.0f}s | GPU alloc {torch.cuda.memory_allocated()/1e9:.1f} GB", flush=True)
