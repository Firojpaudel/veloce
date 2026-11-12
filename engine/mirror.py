"""
Fast download mirror for files that never change (ffmpeg, Deno) and for release downloads.

GitHub's release-file server is very slow from some networks (well under 1 MB/s here), while
Hugging Face's CDN measured ~8 MB/s from the same machine. Every file is verified against a pinned
SHA-256 no matter which server it came from, so a mirror can't serve anything else; if the mirror
is unreachable, downloads fall back to the original GitHub URL.

Set VELOCE_MIRROR to use a different mirror, or VELOCE_MIRROR=off to always use GitHub.
"""
import os

DEFAULT = "https://huggingface.co/datasets/Firoj112/veloce-downloads/resolve/main"


def base() -> str:
    value = os.environ.get("VELOCE_MIRROR", DEFAULT).strip().rstrip("/")
    return "" if value.lower() in ("", "off", "0", "none") else value


def candidates(path: str, original: str) -> list:
    """URLs to try in order: the fast mirror, then the original."""
    b = base()
    return [f"{b}/{path}", original] if b else [original]
