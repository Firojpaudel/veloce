#!/usr/bin/env python3
"""
Writes the Homebrew formula for a published Veloce release (macOS and Linux).

    python3 scripts/homebrew_formula.py 1.1.1

Reads the hashes from the release's SHA256SUMS.txt and writes homebrew/Formula/veloce.rb.
Copy that file into your tap repository (github.com/Firojpaudel/homebrew-tap, folder Formula/).
Then anyone can run:   brew install firojpaudel/tap/veloce

Why Homebrew: it downloads the binary itself, so macOS never marks it as quarantined and
Gatekeeper doesn't block it — no paid Apple notarization needed.
"""

import os
import sys
import urllib.request

REPO = "https://github.com/Firojpaudel/veloce"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = {"mac_arm": "veloce-macos-arm64", "mac_intel": "veloce-macos-x86_64", "linux_intel": "veloce-linux-x86_64"}


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: homebrew_formula.py <version>   (e.g. 1.1.1)")
    version = sys.argv[1].lstrip("v")
    base = f"{REPO}/releases/download/v{version}"
    with urllib.request.urlopen(urllib.request.Request(f"{base}/SHA256SUMS.txt", headers={"User-Agent": "veloce-brew"}), timeout=60) as r:
        sums = {}
        for line in r.read().decode().splitlines():
            parts = line.split()
            if len(parts) == 2:
                sums[parts[1].lstrip("*")] = parts[0]
    missing = [a for a in ASSETS.values() if a not in sums]
    if missing:
        sys.exit(f"SHA256SUMS.txt has no entry for: {', '.join(missing)}")

    def block(key):
        name = ASSETS[key]
        return f'url "{base}/{name}"\n      sha256 "{sums[name]}"'

    formula = f'''class Veloce < Formula
  desc "Small, fast download manager with one-click video and audio downloads"
  homepage "{REPO}"
  version "{version}"
  license "MIT"

  on_macos do
    on_arm do
      {block("mac_arm")}
    end
    on_intel do
      {block("mac_intel")}
    end
  end

  on_linux do
    on_intel do
      {block("linux_intel")}
    end
  end

  def install
    bin.install Dir["veloce-*"].first => "veloce"
  end

  def caveats
    <<~EOS
      Start Veloce:            veloce
      Start it at every login: veloce autostart enable
      For HD video and MP3:    brew install ffmpeg
    EOS
  end

  test do
    system bin/"veloce", "--help"
  end
end
'''
    out = os.path.join(ROOT, "homebrew", "Formula")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "veloce.rb")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(formula)
    print("wrote", os.path.relpath(path, ROOT))


if __name__ == "__main__":
    main()
