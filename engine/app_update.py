"""
Self-update for the Veloce app and its browser extension.

  * check()   — asks GitHub for the latest release (a tiny JSON request, at most every 6 hours).
  * install() — downloads the new build from the fast mirror (GitHub as fallback), verifies it against
                the release's SHA256SUMS.txt (fetched from GitHub over HTTPS), then:
                  Windows installer build → runs the installer silently; it closes Veloce, replaces the
                                            old files (nothing left behind) and starts the new version
                  macOS / Linux binary    → replaces the program file in place and restarts
  * Extension — the app keeps an exact copy of its matching extension in ~/.veloce/extension.
                Load that folder in Chrome once; after each update the extension reloads itself.
"""

import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from typing import Optional

from .version import __version__

logger = logging.getLogger("VeloceUpdate")

REPO = "Firojpaudel/veloce"
CHECK_EVERY = 6 * 3600
_state = {"checked": 0.0, "latest": None, "error": None, "installing": False}
_lock = threading.Lock()


def _home() -> str:
    return os.path.abspath(os.path.expanduser(os.environ.get("VELOCE_HOME", os.path.join("~", ".veloce"))))


def _ver(v: str):
    return tuple(int(x) for x in (v or "0").lstrip("v").split(".") if x.isdigit())


def _get(url: str, timeout: float = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"veloce/{__version__}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def asset_name() -> Optional[str]:
    """Which release file updates this install (None when running from source)."""
    if not frozen():
        return None
    if sys.platform == "win32":
        return "veloce-setup-windows-x64.exe"
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"
    if sys.platform == "darwin":
        return f"veloce-macos-{arch}"
    return "veloce-linux-x86_64"


def check(force: bool = False, fetch: bool = True) -> dict:
    """Latest release info: {current, latest, available, can_install, notes_url}. fetch=False never touches the network."""
    with _lock:
        stale = fetch and (force or time.time() - _state["checked"] > CHECK_EVERY)
    if stale:
        try:
            data = json.loads(_get(f"https://api.github.com/repos/{REPO}/releases/latest"))
            latest = {
                "version": data.get("tag_name", "").lstrip("v"),
                "notes_url": data.get("html_url"),
                "assets": {a["name"]: a["browser_download_url"] for a in data.get("assets", [])},
            }
            with _lock:
                _state.update(checked=time.time(), latest=latest, error=None)
        except Exception as e:
            with _lock:
                _state.update(checked=time.time(), error=str(e))
    with _lock:
        latest = _state["latest"] or {}
        available = bool(latest) and _ver(latest.get("version")) > _ver(__version__)
        return {
            "current": __version__,
            "latest": latest.get("version") or None,
            "available": available,
            "can_install": available and asset_name() in latest.get("assets", {}),
            "installing": _state["installing"],
            "notes_url": latest.get("notes_url"),
            "error": _state["error"],
        }


def _download_verified(name: str, assets: dict) -> str:
    sums_url = assets.get("SHA256SUMS.txt")
    if not sums_url:
        raise IOError("This release has no checksum list")
    sums = {}
    for line in _get(sums_url, timeout=30).decode().splitlines():
        parts = line.split()
        if len(parts) == 2:
            sums[parts[1].lstrip("*")] = parts[0].lower()
    expected = sums.get(name)
    if not expected:
        raise IOError(f"{name} isn't in the release's checksum list")

    from . import mirror
    target_dir = os.path.join(_home(), "tmp")
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, name)
    last = None
    for url in mirror.candidates(f"latest/{name}", assets[name]):
        try:
            digest = hashlib.sha256()
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "veloce-update"}), timeout=120) as r, \
                    open(path, "wb") as f:
                for chunk in iter(lambda: r.read(1 << 20), b""):
                    digest.update(chunk)
                    f.write(chunk)
            if digest.hexdigest() == expected:
                return path
            last = IOError(f"checksum mismatch from {url}")  # e.g. the mirror already has a newer release
        except Exception as e:
            last = e
        logger.info(f"Update download from {url} failed ({last}); trying the next source")
    raise IOError(f"Couldn't download the update: {last}")


def install(on_exit) -> dict:
    """Downloads, verifies and applies the update. `on_exit` stops the engine before the restart."""
    info = check(force=True)
    if not info["available"]:
        return {"started": False, "message": "Veloce is up to date"}
    name = asset_name()
    if not name:
        return {"started": False, "message": "Running from source: update with `git pull`"}
    with _lock:
        if _state["installing"]:
            return {"started": True, "message": "Already updating"}
        _state["installing"] = True
        assets = (_state["latest"] or {}).get("assets", {})

    def run():
        try:
            path = _download_verified(name, assets)
            if sys.platform == "win32":
                # The installer closes Veloce, removes the old program files, installs, and starts the new one
                flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                subprocess.Popen([path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                                 creationflags=flags, close_fds=True)
                time.sleep(1)
                on_exit()
                os._exit(0)
            else:
                os.chmod(path, 0o755)
                os.replace(path, sys.executable)  # atomic swap; the running process keeps its old copy open
                on_exit()
                os.execv(sys.executable, [sys.executable, "app", "--background"])
        except Exception as e:
            logger.error(f"Update failed: {e}")
            with _lock:
                _state.update(installing=False, error=str(e))

    threading.Thread(target=run, name="app-update", daemon=True).start()
    return {"started": True, "message": f"Updating to {info['latest']}…"}


# ------------------------------------------------------------------ extension kept in sync with the app

def extension_dir() -> str:
    return os.path.join(_home(), "extension")


def bundled_extension_dir() -> Optional[str]:
    """The extension shipped inside this app build (or the repo's folder when running from source)."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "extension")
    return path if os.path.isfile(os.path.join(path, "manifest.json")) else None


def _manifest_version(folder: str) -> str:
    try:
        with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
            return json.load(f).get("version", "")
    except Exception:
        return ""


def sync_extension() -> Optional[str]:
    """Replaces ~/.veloce/extension with this app's extension when it differs (clean copy, nothing stale)."""
    src = bundled_extension_dir()
    if not src or not frozen():
        return None  # from source, load the repo's extension/ folder directly
    dst = extension_dir()
    if _manifest_version(dst) == _manifest_version(src):
        return dst
    tmp = dst + ".new"
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(src, tmp, ignore=shutil.ignore_patterns("*.d.ts", "jsconfig.json"))
    shutil.rmtree(dst, ignore_errors=True)
    os.replace(tmp, dst)
    logger.info(f"Extension folder updated to {_manifest_version(dst)} at {dst}")
    return dst


def start_background():
    """Checks for a new release shortly after start, then every 6 hours (a tiny request to GitHub)."""
    def loop():
        time.sleep(30)
        while True:
            check(force=True)
            time.sleep(CHECK_EVERY)
    threading.Thread(target=loop, name="app-update-check", daemon=True).start()


def cleanup_leftovers():
    """Start-up housekeeping: temp folders from interrupted downloads or updates."""
    shutil.rmtree(os.path.join(_home(), "tmp"), ignore_errors=True)
    shutil.rmtree(extension_dir() + ".new", ignore_errors=True)


_seen = {"extension": None}


def saw_extension(version: str):
    """The browser extension reports its version with each status call."""
    if version and len(version) < 32:
        _seen["extension"] = version


def status() -> dict:
    ext = extension_dir() if os.path.isfile(os.path.join(extension_dir(), "manifest.json")) else bundled_extension_dir()
    available = _manifest_version(ext) if ext else None
    running = _seen["extension"]
    return {"extension_dir": ext, "extension_version": available, "extension_running": running,
            "extension_outdated": bool(running and available and _ver(running) < _ver(available))}
