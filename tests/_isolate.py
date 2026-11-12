"""
Imported first by every test module: points the engine at a throwaway home/download directory
so tests never read or write the real ~/.veloce history or ~/Downloads/veloce.
"""
import atexit
import os
import shutil
import sys
import tempfile

_ROOT = tempfile.mkdtemp(prefix="veloce-tests-")
for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
os.environ.setdefault("VELOCE_HOME", os.path.join(_ROOT, "home"))
os.environ.setdefault("VELOCE_DOWNLOAD_DIR", os.path.join(_ROOT, "downloads"))
os.makedirs(os.environ["VELOCE_DOWNLOAD_DIR"], exist_ok=True)
atexit.register(shutil.rmtree, _ROOT, True)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DOWNLOAD_DIR = os.environ["VELOCE_DOWNLOAD_DIR"]
