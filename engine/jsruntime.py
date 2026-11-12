"""
JavaScript runtime for yt-dlp.

YouTube increasingly only hands out downloadable formats after a JavaScript challenge is solved.
yt-dlp solves it with an external runtime (Deno ≥ 2.3, Node ≥ 22 or Bun ≥ 1.2.11) plus its EJS
solver scripts. Without one, videos can fail with "Requested format is not available" — which is
exactly what happens on a typical Windows PC, where none of these is installed.

So Veloce makes sure one exists:
  * uses Deno / Bun / Node from the system when a supported version is installed;
  * otherwise downloads the official Deno release once into ~/.veloce/bin, verified against the
    SHA-256 that Deno publishes next to every release asset.

Set VELOCE_NO_AUTO_UPDATE=1 to skip the download (then install Deno yourself).
"""

import hashlib
import logging
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from typing import Dict, Optional, Tuple

logger = logging.getLogger("VeloceJS")

MIN_VERSIONS = {"deno": (2, 3, 0), "node": (22, 0, 0), "bun": (1, 2, 11)}
DENO_RELEASE = "https://github.com/denoland/deno/releases/latest/download/"
_lock = threading.Lock()
_cache: Optional[Dict[str, dict]] = None


def _home() -> str:
    return os.path.abspath(os.path.expanduser(os.environ.get("VELOCE_HOME", os.path.join("~", ".veloce"))))


def bin_dir() -> str:
    return os.path.join(_home(), "bin")


def _exe(name: str) -> str:
    return name + (".exe" if sys.platform == "win32" else "")


def _version(path: str, pattern: str) -> Tuple[int, ...]:
    try:
        kwargs = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10, **kwargs).stdout
        m = re.search(pattern, out, re.MULTILINE)
        return tuple(int(x) for x in re.findall(r"\d+", m.group(1))[:3]) if m else ()
    except Exception:
        return ()


def find_runtimes(refresh: bool = False) -> Dict[str, dict]:
    """Supported runtimes available right now, as yt-dlp's `js_runtimes` option ({name: {"path": ...}})."""
    global _cache
    with _lock:
        if _cache is not None and not refresh:
            return dict(_cache)
        found: Dict[str, dict] = {}
        own = os.path.join(bin_dir(), _exe("deno"))
        candidates = [("deno", own if os.path.isfile(own) else shutil.which("deno"), r"^deno (\S+)"),
                      ("bun", shutil.which("bun"), r"^(\S+)"),
                      ("node", shutil.which("node"), r"^v(\S+)")]
        for name, path, pattern in candidates:
            if path and _version(path, pattern) >= MIN_VERSIONS[name]:
                found[name] = {"path": path}
        _cache = found
        return dict(found)


def _deno_asset() -> Optional[str]:
    machine = platform.machine().lower()
    arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64" if machine in ("x86_64", "amd64") else None
    if not arch:
        return None
    if sys.platform == "win32":
        return f"deno-{arch}-pc-windows-msvc.zip" if arch == "x86_64" else None
    if sys.platform == "darwin":
        return f"deno-{arch}-apple-darwin.zip"
    if sys.platform.startswith("linux"):
        return f"deno-{arch}-unknown-linux-gnu.zip"
    return None


def install_deno(timeout: float = 180) -> Optional[str]:
    """Downloads the official Deno binary into ~/.veloce/bin after verifying its SHA-256. Returns its path."""
    asset = _deno_asset()
    if not asset:
        logger.warning("No Deno build for this platform; install Deno, Node 22+ or Bun to enable YouTube")
        return None
    os.makedirs(bin_dir(), exist_ok=True)
    headers = {"User-Agent": "veloce-runtime-setup"}
    with urllib.request.urlopen(urllib.request.Request(DENO_RELEASE + asset + ".sha256sum", headers=headers), timeout=30) as r:
        expected = re.search(r"\b([0-9a-fA-F]{64})\b", r.read().decode("utf-8", "replace"))
    if not expected:
        raise IOError("Deno checksum file was unreadable")

    tmp = tempfile.mkdtemp(prefix=".deno-", dir=bin_dir())
    try:
        zpath = os.path.join(tmp, asset)
        digest = hashlib.sha256()
        with urllib.request.urlopen(urllib.request.Request(DENO_RELEASE + asset, headers=headers), timeout=timeout) as src, \
                open(zpath, "wb") as dst:
            for chunk in iter(lambda: src.read(256 * 1024), b""):
                digest.update(chunk)
                dst.write(chunk)
        if digest.hexdigest().lower() != expected.group(1).lower():
            raise IOError("Deno download failed checksum verification")
        with zipfile.ZipFile(zpath) as zf:
            member = next(n for n in zf.namelist() if os.path.basename(n) == _exe("deno"))
            zf.extract(member, tmp)
        final = os.path.join(bin_dir(), _exe("deno"))
        os.replace(os.path.join(tmp, member), final)
        os.chmod(final, os.stat(final).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    find_runtimes(refresh=True)
    logger.info(f"Installed Deno for YouTube support at {final}")
    return final


def ensure_in_background():
    """Called once when the app starts: makes sure YouTube support is ready before anyone needs it."""
    threading.Thread(target=ensure_runtime, name="js-runtime-setup", daemon=True).start()


def status() -> dict:
    found = find_runtimes()
    name = next(iter(found), None)
    return {"js_runtime": name, "js_runtime_path": found[name]["path"] if name else None}


def ensure_runtime() -> Dict[str, dict]:
    """Returns available runtimes, downloading Deno once if none is installed (unless updates are disabled)."""
    found = find_runtimes()
    if found:
        return found
    if os.environ.get("VELOCE_NO_AUTO_UPDATE", "").strip() in ("1", "true", "yes"):
        return found
    try:
        install_deno()
    except Exception as e:
        logger.warning(f"Couldn't set up a JavaScript runtime for YouTube: {e}")
    return find_runtimes()


def ytdlp_options() -> dict:
    """yt-dlp options that let it solve YouTube's JavaScript challenges."""
    # Never downloads here (this runs inside video jobs); the app sets Deno up in the background at start.
    opts = {"js_runtimes": find_runtimes() or {"deno": {}}}
    # yt-dlp's solver scripts: the bundled yt-dlp-ejs package when it matches, otherwise fetched from
    # yt-dlp's own GitHub releases (needed after yt-dlp self-updates past the bundled solver version).
    opts["remote_components"] = ["ejs:github"]
    return opts
