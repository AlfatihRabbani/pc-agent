"""Materialize the E2B model from the E: HDD cache to the G: SSD for fast cold-load."""
import os
os.environ["HF_HOME"] = r"E:\aitest\pc-agent\.hf_cache"
os.environ["HF_HUB_OFFLINE"] = "1"
from huggingface_hub import snapshot_download

dst = r"G:\pc-agent-models\E2B-abliterated"
p = snapshot_download(
    "huihui-ai/Huihui-gemma-4-E2B-it-abliterated",
    local_dir=dst,
    allow_patterns=["*.safetensors", "*.json", "*.model", "*.txt",
                    "tokenizer*", "*.index.json"],
)
print("COPIED ->", p)
