#!/usr/bin/env python3
"""
Uploads files to the fast download mirror (a public Hugging Face dataset repo). Runs in CI.

    python scripts/mirror_upload.py <version> <release-assets-dir>

  * tools/   — ffmpeg and Deno builds the app downloads (fetched from GitHub, verified against the
               pinned hashes, uploaded once: they never change)
  * latest/  — the newest release's installer, binaries and extension (stable links for the README).
               Older versions are removed here — they stay on GitHub Releases.

Needs HF_TOKEN (a write token from the account that owns the repo) and pip install huggingface_hub.
"""
import hashlib
import os
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
REPO_ID = os.environ.get("VELOCE_MIRROR_REPO", "Firoj112/veloce-downloads")


def fetch_verified(url, sha):
    path = os.path.join(tempfile.mkdtemp(), os.path.basename(url))
    digest = hashlib.sha256()
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "veloce-mirror"}), timeout=600) as r, \
            open(path, "wb") as f:
        for chunk in iter(lambda: r.read(1 << 20), b""):
            digest.update(chunk)
            f.write(chunk)
    if digest.hexdigest() != sha.lower():
        raise SystemExit(f"checksum mismatch for {url}")
    return path


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: mirror_upload.py <version> <release-assets-dir>")
    version, assets = sys.argv[1].lstrip("v"), sys.argv[2]
    from huggingface_hub import HfApi
    from engine import ffmpeg_setup, jsruntime
    api = HfApi(token=os.environ["HF_TOKEN"])
    api.create_repo(REPO_ID, repo_type="dataset", exist_ok=True, private=False)
    existing = set(api.list_repo_files(REPO_ID, repo_type="dataset"))

    tools = [(ffmpeg_setup.RELEASE + a, a, sha) for a, sha in ffmpeg_setup.PINNED.values()]
    tools += [(f"https://github.com/denoland/deno/releases/download/v{jsruntime.DENO_VERSION}/{a}", a, sha)
              for a, sha in jsruntime.DENO_SHA256.items()]
    for url, name, sha in tools:
        if f"tools/{name}" in existing:
            continue
        api.upload_file(path_or_fileobj=fetch_verified(url, sha), path_in_repo=f"tools/{name}",
                        repo_id=REPO_ID, repo_type="dataset", commit_message=f"tools: {name}")
        print("uploaded tools/" + name)

    # Only the newest release lives here; older versions stay on GitHub Releases.
    api.upload_folder(folder_path=assets, path_in_repo="latest", repo_id=REPO_ID, repo_type="dataset",
                      commit_message=f"Veloce {version}", delete_patterns=["*"])
    print("uploaded release files to latest/")
    old = sorted({f.split("/")[0] for f in existing if f.split("/")[0] not in ("latest", "tools", ".gitattributes")
                  and "/" in f})
    for folder in old:
        api.delete_folder(path_in_repo=folder, repo_id=REPO_ID, repo_type="dataset", commit_message=f"remove {folder}")
        print(f"removed old {folder}/")
    # Deleted files would otherwise stay in the repo's git history and keep using storage
    api.super_squash_history(repo_id=REPO_ID, repo_type="dataset", commit_message=f"Veloce {version} (latest only)")
    print("squashed history: only the current files are stored")


if __name__ == "__main__":
    main()
