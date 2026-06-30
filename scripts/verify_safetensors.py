"""Verify a safetensors file is fully readable (catches the silent data corruption
that snapshot_download's size-only check misses). Reads every tensor's bytes.

Exit 0 = all tensors read OK. Non-zero / segfault (139) = corrupt.
    python scripts/verify_safetensors.py <path-to-model.safetensors>
"""
import sys
import time

from safetensors import safe_open

path = sys.argv[1]
print(f"verifying {path} ...", flush=True)
t = time.time()
n = 0
with safe_open(path, "pt") as f:
    for k in f.keys():
        x = f.get_tensor(k)   # actually reads the bytes; segfaults on corruption
        del x
        n += 1
print(f"OK: {n} tensors fully readable in {time.time()-t:.0f}s", flush=True)
