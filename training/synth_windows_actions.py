"""Generate the custom Windows-actions dataset.

This is the dataset that matters most for YOUR goal: it teaches the dispatcher to
map natural requests -> the exact tool calls our Executor exposes (About PC,
Control Panel, Task Scheduler, winget, second-cursor input, etc.).

Output: data/synth_windows_actions.jsonl  (one chat example per line, in the same
dispatcher format the model is trained/served with).

Run:  python training/synth_windows_actions.py --n 3000
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pc_agent.dispatcher import build_prompt    # noqa: E402
from pc_agent.tools.settings import SETTINGS_PAGES, CONTROL_PANEL_APPLETS  # noqa: E402

random.seed(7)

# Natural-language templates per tool -> (phrasings, arg-factory)
# arg-factory returns a dict of args; phrasing may use {slot} filled from args.
TEMPLATES: list[tuple[str, list[str], callable]] = [
    ("get_system_info",
     ["what are my pc specs", "tell me about this computer", "how much ram do i have",
      "what cpu is in here", "show me my system info", "what gpu do i have",
      "what windows version am i on", "open about pc"],
     lambda: {"section": random.choice(["all", "all", "cpu", "ram", "gpu", "os"])}),
    ("open_about_page",
     ["open the about page", "show the about this pc window", "go to about pc settings"],
     lambda: {}),
    ("open_settings",
     ["open {page} settings", "take me to {page}", "i need the {page} settings page",
      "open {page}", "show me {page} settings"],
     lambda: {"page": random.choice(list(SETTINGS_PAGES))}),
    ("open_control_panel",
     ["open {applet}", "launch {applet} in control panel", "i want to open {applet}",
      "bring up {applet}"],
     lambda: {"applet": random.choice(list(CONTROL_PANEL_APPLETS))}),
    ("open_app",
     ["open {app}", "launch {app}", "start {app}", "can you open {app}", "fire up {app}"],
     lambda: {"app": random.choice(
         ["notepad", "calculator", "paint", "edge", "task manager", "file explorer",
          "powershell", "snipping tool", "registry editor"])}),
    ("close_app",
     ["close {process_name}", "kill {process_name}", "quit {process_name}",
      "shut down {process_name}"],
     lambda: {"process_name": random.choice(
         ["notepad.exe", "mspaint.exe", "calc.exe", "chrome.exe"])}),
    ("list_running_apps",
     ["what's running right now", "show running apps", "list open programs",
      "what apps are using memory"],
     lambda: {}),
    ("search_software",
     ["search for {query} to install", "find {query} in winget", "is {query} available to download",
      "look up {query} package"],
     lambda: {"query": random.choice(["firefox", "vlc", "7zip", "discord", "steam", "obs", "git"])}),
    ("download_software",
     ["install {package_id}", "download and install {package_id}", "get {package_id} for me",
      "set up {package_id}"],
     lambda: {"package_id": random.choice(
         ["Mozilla.Firefox", "VideoLAN.VLC", "7zip.7zip", "Valve.Steam",
          "OBSProject.OBSStudio", "Git.Git"])}),
    ("list_scheduled_tasks",
     ["list my scheduled tasks", "what tasks are scheduled", "show task scheduler entries"],
     lambda: {}),
    ("create_scheduled_task",
     ["schedule {program} to run {schedule_type_l} at {start_time}",
      "make a task that runs {program} {schedule_type_l}",
      "set up a {schedule_type_l} task for {program}"],
     lambda: {"name": "AgentTask" + str(random.randint(1, 99)),
              "program": random.choice(["notepad.exe", "C:\\\\backup.bat", "calc.exe"]),
              "schedule_type": random.choice(["DAILY", "ONCE", "WEEKLY", "ONLOGON"]),
              "start_time": random.choice(["09:00", "14:30", "22:00"])}),
    ("run_scheduled_task",
     ["run the task {name} now", "trigger {name}", "execute scheduled task {name}"],
     lambda: {"name": "AgentTask" + str(random.randint(1, 99))}),
    ("delete_scheduled_task",
     ["delete the task {name}", "remove scheduled task {name}", "get rid of {name} task"],
     lambda: {"name": "AgentTask" + str(random.randint(1, 99))}),
    ("move_cursor",
     ["move the cursor to {x},{y}", "put the second cursor at {x} {y}"],
     lambda: {"x": random.randint(0, 1920), "y": random.randint(0, 1080)}),
    ("click_at",
     ["click at {x},{y}", "left click on {x} {y}", "click the spot at {x},{y}"],
     lambda: {"x": random.randint(0, 1920), "y": random.randint(0, 1080),
              "button": "left"}),
    ("type_text",
     ["type {text}", "write out {text}", "enter the text {text}"],
     lambda: {"text": random.choice(["hello world", "meeting at 5pm", "test123"])}),
    ("press_hotkey",
     ["press {combo}", "hit {combo}", "do {combo}"],
     lambda: {"keys": random.choice([["ctrl", "c"], ["ctrl", "v"], ["alt", "tab"],
                                     ["ctrl", "shift", "esc"], ["cmd", "d"]])}),
    # ── volume / audio ──
    ("get_volume", ["what's the volume", "current volume level", "is the audio muted"], lambda: {}),
    ("set_volume",
     ["set volume to {level}", "turn the volume to {level} percent", "make it {level}% volume",
      "change the volume to {level}", "volume {level}"],
     lambda: {"level": random.choice([0, 10, 25, 30, 50, 70, 75, 100])}),
    ("set_mute",
     ["{mute_word} the sound", "{mute_word} the audio", "{mute_word} it"],
     lambda: {"mute": random.choice([True, False])}),
    # ── brightness ──
    ("get_brightness", ["what's the brightness", "current screen brightness", "how bright is the screen"],
     lambda: {}),
    ("set_brightness",
     ["set brightness to {level}", "dim the screen to {level}", "brightness {level} percent",
      "make the screen {level}% bright", "set screen brightness to {level}"],
     lambda: {"level": random.choice([10, 20, 40, 50, 60, 80, 100])}),
    # ── display / resolution ──
    ("get_display_info",
     ["what's my resolution", "screen resolution and refresh rate", "display info", "what refresh rate am i on"],
     lambda: {}),
    ("set_resolution",
     ["set resolution to {width}x{height}", "change resolution to {width} by {height}",
      "switch to {width}x{height}"],
     lambda: {"width": random.choice([1280, 1600, 1920, 2560]),
              "height": random.choice([720, 900, 1080, 1440])}),
    # ── wifi / network ──
    ("get_wifi_status", ["am i connected to wifi", "what wifi am i on", "wifi status", "check my wifi"],
     lambda: {}),
    ("list_wifi_networks", ["what wifi networks are around", "scan for wifi", "list available wifi",
                            "show nearby networks"], lambda: {}),
    ("list_saved_wifi", ["what wifi networks are saved", "list saved wifi profiles", "show my saved wifi"],
     lambda: {}),
    ("connect_wifi",
     ["connect to wifi {ssid}", "join the network {ssid}", "connect to {ssid}", "hop on {ssid}"],
     lambda: {"ssid": random.choice(["HomeWiFi", "Office_5G", "NETGEAR42", "TP-Link_2.4", "Starlink"])}),
    ("disconnect_wifi", ["disconnect wifi", "turn off the wifi connection", "drop the wifi"], lambda: {}),
    ("set_wifi_adapter",
     ["turn the wifi adapter {onoff}", "{onoff} the wifi adapter", "switch wifi {onoff}"],
     lambda: {"enabled": random.choice([True, False])}),
    # ── any settings page ──
    ("open_settings_uri",
     ["open the {uri_key} settings page", "go to ms-settings {uri_key}", "open {uri_key} in settings"],
     lambda: {"uri_key": random.choice(["nightlight", "mobile-devices", "crossdevice",
                                        "windowsinsider", "clipboard", "gaming-gamebar", "taskbar"])}),
]

# A handful of pure-chat examples so the model also learns NOT to over-trigger tools.
CHAT_EXAMPLES = [
    "who are you", "what can you do", "tell me a joke", "what's the capital of france",
    "explain what ram is", "how does task scheduler work", "thanks", "good morning",
    "what's 2+2", "write me a haiku about windows",
]


def phrase(template: str, args: dict) -> str:
    slots = dict(args)
    slots["page"] = str(args.get("page", "")).replace("_", " ")
    slots["applet"] = str(args.get("applet", "")).replace("_", " ")
    slots["schedule_type_l"] = str(args.get("schedule_type", "")).lower()
    slots["combo"] = "+".join(args.get("keys", [])) if "keys" in args else ""
    slots["mute_word"] = "mute" if args.get("mute") else "unmute"
    slots["onoff"] = "on" if args.get("enabled") else "off"
    slots["uri_key"] = str(args.get("uri_key", ""))
    try:
        return template.format(**slots)
    except (KeyError, IndexError):
        return template


def make_example(tool: str, phrasing: str, args: dict) -> dict:
    # User turn embeds the compact dispatcher prompt — identical to inference, so
    # train and serve formats match and examples stay short (fits the train seq len).
    target = json.dumps({"action": "tool", "tool": tool, "args": args}, ensure_ascii=False)
    return {"messages": [
        {"role": "user", "content": build_prompt(phrasing, compact=True)},
        {"role": "assistant", "content": target},
    ]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3000, help="approx number of action examples")
    ap.add_argument("--out", default="data/synth_windows_actions.jsonl")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    out_path = root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    per = max(1, args.n // len(TEMPLATES))
    for tool, phrasings, factory in TEMPLATES:
        for _ in range(per):
            a = factory()
            p = phrase(random.choice(phrasings), a)
            rows.append(make_example(tool, p, a))

    # chat negatives (~10%)
    for _ in range(max(1, args.n // 10)):
        msg = random.choice(CHAT_EXAMPLES)
        rows.append({"messages": [
            {"role": "user", "content": build_prompt(msg, compact=True)},
            {"role": "assistant", "content": json.dumps({"action": "chat"})},
        ]})

    random.shuffle(rows)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Wrote {len(rows)} examples -> {out_path}")


if __name__ == "__main__":
    main()
