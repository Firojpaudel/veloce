#!/usr/bin/env python3
"""
Puts ffmpeg and Deno next to the built app so the installer ships them (no first-run download).

    python scripts/bundle_tools.py dist/Veloce

Uses the same verified downloads as the app itself: ffmpeg pinned by SHA-256, Deno checked against
the SHA-256 Deno publishes. Run in CI, where GitHub downloads are fast.
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: bundle_tools.py <app folder>")
    target = os.path.abspath(sys.argv[1])
    home = tempfile.mkdtemp(prefix="veloce-tools-")
    os.environ["VELOCE_HOME"] = home
    from engine import ffmpeg_setup, jsruntime
    ffmpeg = ffmpeg_setup.install(timeout=600)
    deno = jsruntime.install_deno(timeout=600)
    if not ffmpeg or not deno:
        sys.exit("could not fetch ffmpeg and Deno")
    for path in (ffmpeg, deno):
        shutil.copy2(path, os.path.join(target, os.path.basename(path)))
        print("bundled", os.path.basename(path))
    shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    main()
