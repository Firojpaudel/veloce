#!/usr/bin/env python3
"""
Packages the extension directory into a clean zip archive for Chrome Web Store distribution.
Excludes unnecessary files, development artifacts, and hidden directories.
"""

import os
import zipfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_DIR = os.path.join(PROJECT_ROOT, "extension")
OUTPUT_ZIP = os.path.join(PROJECT_ROOT, "dist", "veloce-extension.zip")

EXCLUDED_FILES = {".DS_Store", "Thumbs.db", "jsconfig.json", "chrome.d.ts"}  # dev-only files
EXCLUDED_EXTS = {".map", ".ts"}

def package():
    os.makedirs(os.path.dirname(OUTPUT_ZIP), exist_ok=True)
    
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(EXT_DIR):
            for file in files:
                if file in EXCLUDED_FILES or any(file.endswith(ext) for ext in EXCLUDED_EXTS):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, EXT_DIR)
                zf.write(full_path, rel_path)
                print(f"Added: {rel_path}")

    print(f"\n[OK] Package created: {OUTPUT_ZIP} ({os.path.getsize(OUTPUT_ZIP)} bytes)")

if __name__ == "__main__":
    package()

