"""Pin the Hugging Face cache to the project dir on E:.

The C: SSD is too small for Gemma weights (~33 GB), so all model/dataset caching
must go to the E: drive. Importing this module sets HF_HOME *before* any HF library
is imported. Import it first in every entrypoint that loads models.
"""
import os
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / ".hf_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
# setdefault: respects an explicit HF_HOME if the user set one.
os.environ.setdefault("HF_HOME", str(CACHE_DIR))
