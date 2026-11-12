#!/usr/bin/env python3
"""
Generates the winget package manifest for a published Veloce release.

    python3 scripts/winget_manifest.py 1.1.1

Reads the installer's hash from the release's SHA256SUMS.txt and writes the three manifest files to
winget/manifests/f/Firojpaudel/Veloce/<version>/ — the exact layout microsoft/winget-pkgs expects.
Submit them with `wingetcreate submit <that folder>` or as a pull request to microsoft/winget-pkgs.
"""

import os
import sys
import urllib.request

PACKAGE_ID = "Firojpaudel.Veloce"
REPO = "https://github.com/Firojpaudel/veloce"
MANIFEST_VERSION = "1.6.0"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: winget_manifest.py <version>   (e.g. 1.1.1)")
    version = sys.argv[1].lstrip("v")
    url = f"{REPO}/releases/download/v{version}/veloce-setup-windows-x64.exe"

    # The release publishes every asset's hash in SHA256SUMS.txt: read it instead of downloading the installer.
    sums_url = f"{REPO}/releases/download/v{version}/SHA256SUMS.txt"
    print(f"Reading {sums_url}")
    with urllib.request.urlopen(urllib.request.Request(sums_url, headers={"User-Agent": "veloce-winget"}), timeout=60) as r:
        sums = dict(reversed(line.split()) for line in r.read().decode().splitlines() if len(line.split()) == 2)
    sha = sums.get("veloce-setup-windows-x64.exe", "").upper()
    if len(sha) != 64:
        sys.exit("SHA256SUMS.txt has no entry for veloce-setup-windows-x64.exe")

    out = os.path.join(ROOT, "winget", "manifests", "f", "Firojpaudel", "Veloce", version)
    os.makedirs(out, exist_ok=True)
    header = f"# yaml-language-server: $schema=https://aka.ms/winget-manifest.{{kind}}.{MANIFEST_VERSION}.schema.json\n"

    files = {
        f"{PACKAGE_ID}.yaml": header.format(kind="version") + f"""
PackageIdentifier: {PACKAGE_ID}
PackageVersion: {version}
DefaultLocale: en-US
ManifestType: version
ManifestVersion: {MANIFEST_VERSION}
""",
        f"{PACKAGE_ID}.installer.yaml": header.format(kind="installer") + f"""
PackageIdentifier: {PACKAGE_ID}
PackageVersion: {version}
InstallerType: inno
Scope: user
UpgradeBehavior: install
InstallModes:
  - interactive
  - silent
  - silentWithProgress
Installers:
  - Architecture: x64
    InstallerUrl: {url}
    InstallerSha256: {sha}
ManifestType: installer
ManifestVersion: {MANIFEST_VERSION}
""",
        f"{PACKAGE_ID}.locale.en-US.yaml": header.format(kind="defaultLocale") + f"""
PackageIdentifier: {PACKAGE_ID}
PackageVersion: {version}
PackageLocale: en-US
Publisher: Firoj Paudel
PublisherUrl: https://github.com/Firojpaudel
PublisherSupportUrl: {REPO}/issues
PackageName: Veloce
PackageUrl: {REPO}
License: MIT
LicenseUrl: {REPO}/blob/main/LICENSE
ShortDescription: Small, fast download manager with one-click video and audio downloads.
Description: |-
  Veloce speeds up downloads by adding connections only while they help, catches browser
  downloads, and grabs video or audio from YouTube, TikTok, Instagram and 1,800+ other sites.
  It runs quietly in the system tray and can stream your downloads to phones and laptops on your home network.
Moniker: veloce
Tags:
  - download-manager
  - downloader
  - youtube-downloader
  - video-downloader
  - accelerator
ReleaseNotesUrl: {REPO}/releases/tag/v{version}
ManifestType: defaultLocale
ManifestVersion: {MANIFEST_VERSION}
""",
    }
    for name, body in files.items():
        with open(os.path.join(out, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        print("wrote", os.path.relpath(os.path.join(out, name), ROOT))
    print(f"\nInstaller SHA256: {sha}")


if __name__ == "__main__":
    main()
