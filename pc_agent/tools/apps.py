"""Launch/close applications and download/install software via winget."""
from __future__ import annotations

import os
import shutil
import subprocess

import psutil

from ..safety import Risk
from .registry import tool
from ._shell import run

# Where Windows keeps installed-app shortcuts (the same thing Start-menu search reads).
_START_DIRS = [
    os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                 r"Microsoft\Windows\Start Menu\Programs"),
    os.path.join(os.environ.get("APPDATA", ""),
                 r"Microsoft\Windows\Start Menu\Programs"),
]


def _find_shortcut(name: str):
    """Search installed-app shortcuts for the best match to `name` (like Start-menu search)."""
    want = name.strip().lower()
    words = want.split()
    cands = []
    for d in _START_DIRS:
        if not d or not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.lower().endswith(".lnk"):
                    cands.append((os.path.splitext(f)[0], os.path.join(root, f)))

    def score(stem: str) -> int:
        s = stem.lower()
        if s == want:
            return 100
        if s.startswith(want):
            return 85
        if words and all(w in s for w in words):
            return 70
        if want in s:
            return 55
        if words and all(any(w in t for t in s.split()) for w in words):
            return 40
        return 0

    best = max(cands, key=lambda c: score(c[0]), default=None)
    if best and score(best[0]) > 0:
        return best          # (display_name, full_lnk_path)
    return None

# Common apps -> launch command (extend freely)
KNOWN_APPS = {
    "notepad": "notepad",
    "calculator": "calc",
    "paint": "mspaint",
    "explorer": "explorer",
    "file explorer": "explorer",
    "task manager": "taskmgr",
    "cmd": "cmd",
    "command prompt": "cmd",
    "powershell": "powershell",
    "terminal": "wt",
    "edge": "msedge",
    "browser": "msedge",
    "chrome": "chrome",
    "settings": "ms-settings:",
    "snipping tool": "snippingtool",
    "registry editor": "regedit",
    "control panel": "control",
}


@tool(
    name="open_app",
    description="Open/launch any installed application by name (e.g. 'notepad', 'libreoffice writer', "
                "'discord', 'spotify'). Finds the app the way Start-menu search does — no exact "
                "executable name needed.",
    parameters={
        "app": {"type": "string", "description": "App name as a person would say it."}
    },
    required=["app"],
    risk=Risk.READ,   # opening a benign app; downloads are a separate, gated tool
)
def open_app(app: str) -> str:
    key = app.strip().lower()

    # 1) fast path for built-in system apps / settings URIs
    cmd = KNOWN_APPS.get(key)
    if cmd:
        try:
            args = ["cmd", "/c", "start", cmd] if cmd.startswith("ms-settings:") \
                else ["cmd", "/c", "start", "", cmd]
            subprocess.Popen(args, shell=False)
            return f"Launched '{app}'."
        except Exception as e:  # noqa: BLE001
            return f"Failed to launch '{app}': {e}"

    # 2) search the installed-app shortcuts (handles 'libreoffice writer', 'discord', etc.)
    hit = _find_shortcut(app)
    if hit:
        display, lnk = hit
        try:
            os.startfile(lnk)  # noqa: S606 — launching a user app shortcut
            return f"Opened '{display}'."
        except Exception as e:  # noqa: BLE001
            return f"Found '{display}' but failed to open it: {e}"

    # 3) last resort: treat the name as a runnable command/exe
    try:
        subprocess.Popen(["cmd", "/c", "start", "", app], shell=False)
        return f"Tried to launch '{app}' (no Start-menu match found)."
    except Exception as e:  # noqa: BLE001
        return f"Couldn't find or launch '{app}': {e}"


# site keyword -> that site's own search-results URL ({q} = url-encoded query).
SITE_SEARCH = {
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "google": "https://www.google.com/search?q={q}",
    "amazon": "https://www.amazon.com/s?k={q}",
    "reddit": "https://www.reddit.com/search/?q={q}",
    "github": "https://github.com/search?q={q}&type=repositories",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={q}",
    "twitter": "https://twitter.com/search?q={q}",
    "x": "https://x.com/search?q={q}",
    "ebay": "https://www.ebay.com/sch/i.html?_nkw={q}",
    "twitch": "https://www.twitch.tv/search?term={q}",
    "stackoverflow": "https://stackoverflow.com/search?q={q}",
    "spotify": "https://open.spotify.com/search/{q}",
    "netflix": "https://www.netflix.com/search?q={q}",
    "roblox": "https://www.roblox.com/search/users?keyword={q}",
    "rule34": "https://rule34.xxx/index.php?page=post&s=list&tags={q}",
    "pornhub": "https://www.pornhub.com/video/search?search={q}",
    "danbooru": "https://danbooru.donmai.us/posts?tags={q}",
    "gelbooru": "https://gelbooru.com/index.php?page=post&s=list&tags={q}",
}


@tool(
    name="open_url",
    description="Open a website/link DIRECTLY in the browser (e.g. 'youtube.com', "
                "'https://github.com'). Use when the user gives a domain or URL — not a search query.",
    parameters={"url": {"type": "string", "description": "A domain or full URL."}},
    required=["url"],
    risk=Risk.READ,
)
def open_url(url: str) -> str:
    import webbrowser
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    try:
        webbrowser.open(u)
        return f"Opening {u}."
    except Exception as e:  # noqa: BLE001
        return f"Failed to open {u}: {e}"


@tool(
    name="site_search",
    description="Search a query ON a specific website (e.g. search 'deltarune' on youtube.com). "
                "Opens that site's own search results — use when the user names a site AND a query.",
    parameters={
        "site": {"type": "string", "description": "Site/domain to search on, e.g. youtube.com."},
        "query": {"type": "string", "description": "What to search for on that site."},
    },
    required=["site", "query"],
    risk=Risk.READ,
)
def site_search(site: str, query: str) -> str:
    import webbrowser
    from urllib.parse import quote_plus
    key = site.lower().replace("www.", "").split(".")[0].strip()
    tmpl = SITE_SEARCH.get(key)
    if tmpl:
        url = tmpl.format(q=quote_plus(query))
    else:  # unknown site -> google site: search (results from that domain)
        host = site if "." in site else site + ".com"
        url = "https://www.google.com/search?q=" + quote_plus(f"{query} site:{host}")
    try:
        webbrowser.open(url)
        return f"Searching {site} for '{query}'."
    except Exception as e:  # noqa: BLE001
        return f"Failed: {e}"


@tool(
    name="play_youtube",
    description="Play a song/video on YouTube by name — finds the TOP result and opens it "
                "playing. Use for 'play <song>', 'play <song> on youtube'.",
    parameters={"query": {"type": "string", "description": "Song / video to play."}},
    required=["query"],
    risk=Risk.READ,
)
def play_youtube(query: str) -> str:
    import re as _re
    import urllib.parse
    import urllib.request
    import webbrowser
    results = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    try:
        req = urllib.request.Request(results, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"})
        html = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "ignore")
        m = _re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', html)   # first = top result
        if m:
            watch = f"https://www.youtube.com/watch?v={m.group(1)}"
            webbrowser.open(watch)
            return f"Playing '{query}' -> {watch}"
    except Exception:  # noqa: BLE001
        pass
    webbrowser.open(results)   # fallback: open the search results page
    return f"Opened YouTube search for '{query}' (couldn't auto-pick the video)."


@tool(
    name="web_search",
    description="Search the WEB for a query — opens the default browser straight to the "
                "results page. Use for 'search for X', 'look up X', 'google X', "
                "'search X in firefox/chrome'. NOT for installing software (that is search_software).",
    parameters={"query": {"type": "string", "description": "What to search the web for."}},
    required=["query"],
    risk=Risk.READ,
)
def web_search(query: str) -> str:
    import webbrowser
    from urllib.parse import quote_plus
    url = "https://www.google.com/search?q=" + quote_plus(query)
    try:
        webbrowser.open(url)
        return f"Searching the web for '{query}'."
    except Exception as e:  # noqa: BLE001
        return f"Failed to open search: {e}"


@tool(
    name="close_app",
    description="Close/terminate a running application by process name, e.g. 'notepad.exe'.",
    parameters={
        "process_name": {"type": "string", "description": "Process image name."}
    },
    required=["process_name"],
    risk=Risk.INPUT,
)
def close_app(process_name: str) -> str:
    name = process_name if process_name.lower().endswith(".exe") else process_name + ".exe"
    killed = 0
    for p in psutil.process_iter(["name"]):
        if (p.info["name"] or "").lower() == name.lower():
            try:
                p.terminate()
                killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    return f"Terminated {killed} instance(s) of {name}." if killed else f"No running {name}."


@tool(
    name="list_running_apps",
    description="List currently running user applications (visible processes) with memory use.",
    parameters={},
    required=[],
    risk=Risk.READ,
)
def list_running_apps() -> str:
    rows = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            mem = p.info["memory_info"].rss / (1024 * 1024)
            if mem > 20:  # skip tiny background bits
                rows.append((p.info["name"], mem))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    rows.sort(key=lambda r: r[1], reverse=True)
    top = rows[:25]
    return "\n".join(f"{n:<35} {m:>7.0f} MB" for n, m in top)


@tool(
    name="search_software",
    description="Search the winget catalog for installable software (does NOT install). "
                "Use before download_software to find the exact package id.",
    parameters={"query": {"type": "string", "description": "Software name to search."}},
    required=["query"],
    risk=Risk.READ,
)
def search_software(query: str) -> str:
    if not shutil.which("winget"):
        return "winget is not available on this system."
    return run(["winget", "search", "--accept-source-agreements", query], timeout=60)


@tool(
    name="download_software",
    description="Download AND install a program via winget by its package id "
                "(e.g. '7zip.7zip', 'Mozilla.Firefox', 'Valve.Steam'). Requires confirmation.",
    parameters={
        "package_id": {"type": "string", "description": "Exact winget package id."}
    },
    required=["package_id"],
    risk=Risk.DOWNLOAD,
)
def download_software(package_id: str) -> str:
    if not shutil.which("winget"):
        return "winget is not available on this system."
    return run(
        ["winget", "install", "--id", package_id, "-e",
         "--accept-source-agreements", "--accept-package-agreements"],
        timeout=600,
    )
