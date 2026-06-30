"""System information — 'About PC', specs, OS version, hardware."""
from __future__ import annotations

import json

from ..safety import Risk
from .registry import tool
from ._shell import powershell


@tool(
    name="get_system_info",
    description="Get 'About PC' style info: OS edition, version/build, CPU, RAM, GPU, "
                "device name and manufacturer. Use for questions about the computer's specs.",
    parameters={
        "section": {
            "type": "string",
            "enum": ["all", "os", "cpu", "ram", "gpu", "device"],
            "description": "Which part to report. 'all' returns everything.",
        }
    },
    required=[],
    risk=Risk.READ,
)
def get_system_info(section: str = "all") -> str:
    script = r"""
$os  = Get-CimInstance Win32_OperatingSystem
$cs  = Get-CimInstance Win32_ComputerSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$gpu = Get-CimInstance Win32_VideoController | Select-Object -First 1
# Win32_VideoController.AdapterRAM is a 32-bit field that caps at 4GB. Read the
# true VRAM from the display-class registry (qwMemorySize, a 64-bit value).
$vram = 0
try {
  $base = 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
  foreach ($k in (Get-ChildItem $base -ErrorAction SilentlyContinue)) {
    $q = (Get-ItemProperty $k.PSPath -ErrorAction SilentlyContinue).'HardwareInformation.qwMemorySize'
    if ($q -and $q -gt $vram) { $vram = $q }
  }
} catch {}
if ($vram -le 0) { $vram = $gpu.AdapterRAM }
[pscustomobject]@{
  device       = $cs.Name
  manufacturer = $cs.Manufacturer
  model        = $cs.Model
  os           = $os.Caption
  version      = $os.Version
  build        = $os.BuildNumber
  cpu          = $cpu.Name.Trim()
  cores        = $cpu.NumberOfCores
  threads      = $cpu.NumberOfLogicalProcessors
  ram_gb       = [math]::Round($cs.TotalPhysicalMemory/1GB, 1)
  gpu          = $gpu.Name
  gpu_vram_gb  = [math]::Round($vram/1GB, 1)
} | ConvertTo-Json
"""
    raw = powershell(script)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw  # surface the error text
    if section == "all":
        return json.dumps(data, indent=2)
    mapping = {
        "os": ["os", "version", "build"],
        "cpu": ["cpu", "cores", "threads"],
        "ram": ["ram_gb"],
        "gpu": ["gpu", "gpu_vram_gb"],
        "device": ["device", "manufacturer", "model"],
    }
    keys = mapping.get(section, list(data.keys()))
    return json.dumps({k: data[k] for k in keys if k in data}, indent=2)


@tool(
    name="open_about_page",
    description="Open the Windows Settings 'About' page (System > About) in the UI.",
    parameters={},
    required=[],
    risk=Risk.READ,
)
def open_about_page() -> str:
    import subprocess
    subprocess.Popen(["cmd", "/c", "start", "ms-settings:about"], shell=False)
    return "Opened Settings > System > About."
