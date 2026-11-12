#!/usr/bin/env python3
"""
Checks that version numbers match across engine/version.py, package.json, and extension/manifest.json.
Exits with 0 if all match, or 1 with an error message if there is a mismatch.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_engine_version() -> str:
    path = os.path.join(ROOT, "engine", "version.py")
    with open(path, "r", encoding="utf-8") as f:
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', f.read())
        if not m:
            raise RuntimeError(f"Could not parse __version__ from {path}")
        return m.group(1)


def get_package_version() -> str:
    path = os.path.join(ROOT, "package.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["version"]


def get_manifest_version() -> str:
    path = os.path.join(ROOT, "extension", "manifest.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["version"]


def main():
    engine_ver = get_engine_version()
    pkg_ver = get_package_version()
    ext_ver = get_manifest_version()

    print(f"engine/version.py:       {engine_ver}")
    print(f"package.json:            {pkg_ver}")
    print(f"extension/manifest.json: {ext_ver}")

    if not (engine_ver == pkg_ver == ext_ver):
        print("\nERROR: Version mismatch detected across project files!", file=sys.stderr)
        sys.exit(1)

    print("\nOK: All versions match.")


if __name__ == "__main__":
    main()
