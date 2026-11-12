"""
ffmpeg for video downloads.

YouTube (and most big sites) send video and audio as separate streams; ffmpeg joins them into one
file. Without it only audio-only downloads work, which is what happens on a PC that has never
installed ffmpeg. So Veloce makes sure it exists:

  * uses ffmpeg from the system when one is installed;
  * otherwise downloads a single static ffmpeg build once into ~/.veloce/bin.

The build is pinned to one release of github.com/eugeneware/ffmpeg-static and verified against the
SHA-256 hashes below before use, so only these exact files can ever run.

Set VELOCE_NO_AUTO_UPDATE=1 to skip the download (then install ffmpeg yourself).
"""

import gzip
import hashlib
import logging
import os
import platform
import shutil
import stat
import sys
import tempfile
import threading
import urllib.request
from typing import Optional

logger = logging.getLogger("VeloceFFmpeg")

RELEASE = "https://github.com/eugeneware/ffmpeg-static/releases/download/b6.1.1/"
# asset name -> SHA-256 of the .gz file (from the release's published asset digests)
PINNED = {
    ("win32", "x86_64"): ("ffmpeg-win32-x64.gz", "8883a3dffbd0a16cf4ef95206ea05283f78908dbfb118f73c83f4951dcc06d77"),
    ("linux", "x86_64"): ("ffmpeg-linux-x64.gz", "bfe8a8fc511530457b528c48d77b5737527b504a3797a9bc4866aeca69c2dffa"),
    ("linux", "aarch64"): ("ffmpeg-linux-arm64.gz", "754a678672298bc68156adff58aa7385a592c2b30b1d0ae8750c45c915c4bac0"),
    ("darwin", "aarch64"): ("ffmpeg-darwin-arm64.gz", "8923876afa8db5585022d7860ec7e589af192f441c56793971276d450ed3bbfa"),
    ("darwin", "x86_64"): ("ffmpeg-darwin-x64.gz", "929b375c1182d956c51f7ac25e0b2b0411fb01f6f407aa15c9758efeb4242106"),
}
_lock = threading.Lock()


def _home() -> str:
    return os.path.abspath(os.path.expanduser(os.environ.get("VELOCE_HOME", os.path.join("~", ".veloce"))))


def bin_dir() -> str:
    return os.path.join(_home(), "bin")


def own_path() -> str:
    return os.path.join(bin_dir(), "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")


def app_dir() -> str:
    """Folder of the installed app (the Windows installer ships ffmpeg and Deno right next to Veloce.exe)."""
    return os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else ""


def find() -> Optional[str]:
    """Path of a usable ffmpeg: the one bundled with the app, Veloce's downloaded copy, then the system's."""
    bundled = os.path.join(app_dir(), os.path.basename(own_path())) if app_dir() else ""
    for path in (bundled, own_path()):
        if path and os.path.isfile(path):
            return path
    return shutil.which("ffmpeg")


def _platform_key():
    machine = platform.machine().lower()
    arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64" if machine in ("x86_64", "amd64") else machine
    osname = "win32" if sys.platform == "win32" else "darwin" if sys.platform == "darwin" else "linux"
    return osname, arch


def install(timeout: float = 180) -> Optional[str]:
    pinned = PINNED.get(_platform_key())
    if not pinned:
        logger.warning("No ffmpeg build for this platform; install ffmpeg to enable HD video")
        return None
    asset, expected = pinned
    os.makedirs(bin_dir(), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".ffmpeg-", dir=bin_dir())
    try:
        from . import mirror
        gz_path = os.path.join(tmp, asset)
        last = None
        for url in mirror.candidates(f"tools/{asset}", RELEASE + asset):
            try:
                digest = hashlib.sha256()
                req = urllib.request.Request(url, headers={"User-Agent": "veloce-ffmpeg-setup"})
                with urllib.request.urlopen(req, timeout=timeout) as src, open(gz_path, "wb") as dst:
                    for chunk in iter(lambda: src.read(256 * 1024), b""):
                        digest.update(chunk)
                        dst.write(chunk)
                if digest.hexdigest() == expected:
                    break
                last = IOError(f"checksum mismatch from {url}")
            except Exception as e:
                last = e
            logger.info(f"ffmpeg download from {url} failed ({last}); trying the next source")
        else:
            raise IOError(f"ffmpeg download failed: {last}")
        out = os.path.join(tmp, "ffmpeg.bin")
        with gzip.open(gz_path, "rb") as src, open(out, "wb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
        os.chmod(out, os.stat(out).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.replace(out, own_path())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    logger.info(f"Installed ffmpeg for video downloads at {own_path()}")
    return own_path()


def ensure() -> Optional[str]:
    """Returns a usable ffmpeg, downloading Veloce's copy first if needed. Concurrent callers wait for one download."""
    path = find()
    if path:
        return path
    if os.environ.get("VELOCE_NO_AUTO_UPDATE", "").strip() in ("1", "true", "yes"):
        return None
    with _lock:
        path = find()
        if path:
            return path
        try:
            return install()
        except Exception as e:
            logger.warning(f"Couldn't set up ffmpeg: {e}")
            return None
