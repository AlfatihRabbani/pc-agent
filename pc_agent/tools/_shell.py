"""Shared helpers for running Windows shell/PowerShell commands."""
from __future__ import annotations

import subprocess


def powershell(script: str, timeout: int = 30) -> str:
    """Run a PowerShell script, return stdout (stderr appended on failure)."""
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=timeout,
    )
    out = proc.stdout.strip()
    if proc.returncode != 0:
        out = (out + "\n" + proc.stderr.strip()).strip()
    return out


def run(cmd: list[str], timeout: int = 30) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = proc.stdout.strip()
    if proc.returncode != 0:
        out = (out + "\n" + proc.stderr.strip()).strip()
    return out
