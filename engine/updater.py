"""
Self-updating yt-dlp.

Video sites change their pages often, and a yt-dlp that is a few months old starts failing.
Instead of requiring users to update by hand (or re-download Veloce), the engine:

  1. checks PyPI for a newer yt-dlp once a day (and shortly after start-up),
  2. downloads the pure-Python wheel, verifies its SHA-256 against PyPI's published digest,
  3. unpacks it into ~/.veloce/lib/yt_dlp-<version>/,
  4. switches to it immediately when no media download is running (otherwise on the next idle check),
     and on every later start-up.

This works for the PyInstaller binaries too: a meta-path hook makes `import yt_dlp` resolve to the
newer copy on disk ahead of the copy frozen into the executable.

Set VELOCE_NO_AUTO_UPDATE=1 to disable.
"""

import hashlib
import importlib.machinery
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from typing import Callable, Optional, Tuple

logger = logging.getLogger("VeloceUpdater")

PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"
CHECK_INTERVAL = 24 * 3600
FIRST_CHECK_DELAY = 20
_DIR_RE = re.compile(r"^yt_dlp-(\d+(?:\.\d+)*)$")

_lock = threading.Lock()
_hook: Optional["_PreferDirectory"] = None


def _home() -> str:
    return os.path.abspath(os.path.expanduser(os.environ.get("VELOCE_HOME", os.path.join("~", ".veloce"))))


def lib_dir() -> str:
    return os.path.join(_home(), "lib")


def parse_version(v: str) -> Tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", v or "0"))


def python_supported(requires_python: str) -> bool:
    """Evaluates simple PEP 440 specifiers like '>=3.10' or '>=3.9,<4' against the running interpreter."""
    here = sys.version_info[:3]
    for spec in filter(None, (s.strip() for s in requires_python.split(","))):
        m = re.match(r"(>=|<=|==|!=|>|<|~=)\s*([\d.]+)", spec)
        if not m:
            continue
        op, ver = m.group(1), parse_version(m.group(2))
        cur = here[:len(ver)]
        ok = {">=": cur >= ver, ">": cur > ver, "<=": cur <= ver, "<": cur < ver,
              "==": cur == ver, "!=": cur != ver, "~=": cur >= ver}[op]
        if not ok:
            return False
    return True


def deactivate():
    """Drops the update hook (used when an update fails to import) so the bundled yt-dlp is used."""
    global _hook
    with _lock:
        if _hook is not None and _hook in sys.meta_path:
            sys.meta_path.remove(_hook)
        _hook = None
        _purge_loaded_modules()


def enabled() -> bool:
    return os.environ.get("VELOCE_NO_AUTO_UPDATE", "").strip() not in ("1", "true", "yes")


class _PreferDirectory:
    """meta_path finder resolving yt_dlp (and its submodules) from an unpacked directory first."""

    def __init__(self, root: str):
        self.root = root

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "yt_dlp":
            return importlib.machinery.PathFinder.find_spec(fullname, [self.root])
        if fullname.startswith("yt_dlp."):
            return importlib.machinery.PathFinder.find_spec(fullname, path)
        return None


def installed_updates() -> list:
    """[(version_tuple, path)] of unpacked updates, newest first."""
    root = lib_dir()
    if not os.path.isdir(root):
        return []
    found = []
    for name in os.listdir(root):
        m = _DIR_RE.match(name)
        if m and os.path.isfile(os.path.join(root, name, "yt_dlp", "__init__.py")):
            found.append((parse_version(m.group(1)), os.path.join(root, name)))
    return sorted(found, reverse=True)


def bundled_version() -> Tuple[int, ...]:
    """Version of the yt-dlp shipped with this install (ignoring our own updates)."""
    try:
        from importlib.metadata import version
        return parse_version(version("yt-dlp"))
    except Exception:
        pass
    try:
        spec = importlib.machinery.PathFinder.find_spec("yt_dlp")
        if spec and spec.submodule_search_locations:
            path = os.path.join(list(spec.submodule_search_locations)[0], "version.py")
            with open(path, encoding="utf-8") as fh:
                m = re.search(r"__version__\s*=\s*['\"]([\d.]+)", fh.read())
            if m:
                return parse_version(m.group(1))
    except Exception:
        pass
    return ()


def _purge_loaded_modules():
    for name in [n for n in sys.modules if n == "yt_dlp" or n.startswith("yt_dlp.")]:
        del sys.modules[name]


def activate() -> Optional[str]:
    """Points `import yt_dlp` at the newest downloaded update if it beats the bundled one."""
    global _hook
    updates = installed_updates()
    if not updates:
        return None
    version, path = updates[0]
    if version <= bundled_version():
        # The app update shipped a yt-dlp at least as new: downloaded copies are dead weight
        for _, old in updates:
            shutil.rmtree(old, ignore_errors=True)
        return None
    for _, old in updates[1:]:
        shutil.rmtree(old, ignore_errors=True)
    with _lock:
        if _hook is not None and _hook.root == path:
            return path
        if _hook is not None and _hook in sys.meta_path:
            sys.meta_path.remove(_hook)
        _hook = _PreferDirectory(path)
        sys.meta_path.insert(0, _hook)
        _purge_loaded_modules()
    logger.info(f"Using auto-updated yt-dlp {'.'.join(map(str, version))}")
    return path


def current_version() -> Tuple[int, ...]:
    updates = installed_updates()
    return max(updates[0][0] if updates else (), bundled_version())


def check_and_update(timeout: float = 30) -> Optional[str]:
    """Downloads and unpacks a newer yt-dlp if PyPI has one. Returns the new version string or None."""
    req = urllib.request.Request(PYPI_URL, headers={"User-Agent": "veloce-updater", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        meta = json.load(resp)

    latest = meta["info"]["version"]
    if parse_version(latest) <= current_version():
        return None
    if not python_supported(meta["info"].get("requires_python") or ""):
        logger.warning(f"yt-dlp {latest} needs Python {meta['info'].get('requires_python')}; "
                       f"this engine runs {sys.version.split()[0]}. Staying on the current version.")
        return None

    wheel = next((f for f in meta.get("urls", [])
                  if f.get("packagetype") == "bdist_wheel" and f["filename"].endswith("py3-none-any.whl")), None)
    if not wheel or not wheel.get("digests", {}).get("sha256"):
        logger.warning("No verifiable pure-Python wheel published for yt-dlp %s", latest)
        return None
    if not wheel["url"].startswith("https://files.pythonhosted.org/"):
        logger.warning("Unexpected download host for yt-dlp wheel: %s", wheel["url"])
        return None

    root = lib_dir()
    os.makedirs(root, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix=".yt_dlp-", dir=root)
    try:
        whl_path = os.path.join(tmp_dir, "update.whl")
        digest = hashlib.sha256()
        with urllib.request.urlopen(wheel["url"], timeout=timeout) as src, open(whl_path, "wb") as dst:
            for chunk in iter(lambda: src.read(256 * 1024), b""):
                digest.update(chunk)
                dst.write(chunk)
        if digest.hexdigest() != wheel["digests"]["sha256"]:
            raise IOError("yt-dlp update failed checksum verification")

        unpack = os.path.join(tmp_dir, "pkg")
        with zipfile.ZipFile(whl_path) as zf:
            for member in zf.namelist():
                # Only the package itself; refuse anything that would escape the target directory
                if not member.startswith("yt_dlp/") or ".." in member.split("/"):
                    continue
                zf.extract(member, unpack)
        if not os.path.isfile(os.path.join(unpack, "yt_dlp", "__init__.py")):
            raise IOError("yt-dlp wheel did not contain the package")

        final = os.path.join(root, f"yt_dlp-{latest}")
        if os.path.exists(final):
            shutil.rmtree(final, ignore_errors=True)
        os.replace(unpack, final)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Keep only the newest; the bundled yt-dlp is always there to fall back on
    for _, old in installed_updates()[1:]:
        shutil.rmtree(old, ignore_errors=True)
    logger.info(f"Downloaded yt-dlp {latest}")
    return latest


def start_background(is_idle: Callable[[], bool], on_swap: Callable[[], None]):
    """Daily update loop. Swaps the live module only when `is_idle()` (no media download running)."""
    if not enabled():
        logger.info("yt-dlp auto-update disabled (VELOCE_NO_AUTO_UPDATE)")
        return

    def loop():
        time.sleep(FIRST_CHECK_DELAY)
        pending_swap = False
        next_check = 0.0
        while True:
            if time.time() >= next_check:
                try:
                    if check_and_update():
                        pending_swap = True
                except Exception as e:
                    logger.warning(f"yt-dlp update check failed: {e}")
                next_check = time.time() + CHECK_INTERVAL
            if pending_swap and is_idle():
                if activate():
                    on_swap()
                pending_swap = False
            time.sleep(60)

    threading.Thread(target=loop, name="yt-dlp-updater", daemon=True).start()
