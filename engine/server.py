"""
Veloce Engine Local API Server
Runs a lightweight loopback REST service that bridges the browser extension and CLI to the engine.
Uses standard library components for zero-dependency execution.
"""

import os
import re
import sys
import json
import time
import uuid
import atexit
import logging
import threading
import subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from typing import Dict, Optional

from .version import __version__
from .segmenter import DownloadTask, MAX_CONNECTIONS, TERMINAL_STATUSES, sanitize_filename
from .media import MediaEngine, disambiguate_media_title
from .media_worker import run_job, MediaJobCancelled, WarmProbe

logger = logging.getLogger("VeloceServer")

VELOCE_HOME = os.path.abspath(os.path.expanduser(os.environ.get("VELOCE_HOME", os.path.join("~", ".veloce"))))
DEFAULT_DOWNLOAD_DIR = os.path.abspath(
    os.path.expanduser(os.environ.get("VELOCE_DOWNLOAD_DIR", os.path.join("~", "Downloads", "veloce")))
)
HISTORY_FILE = os.path.join(VELOCE_HOME, "history.json")
HISTORY_LIMIT = 200

# Pinned unpacked extension ID (derived from extension/manifest.json "key") and CWS placeholder
DEFAULT_EXTENSION_IDS = {
    "faaebjnfegkfoehnbilkajcdkjjngeap",  # pinned unpacked extension ID from extension/manifest.json key
    "velocecwsplaceholder00000000000",   # reserved placeholder for future Chrome Web Store ID
}
# Extension IDs allow-list: defaults to pinned extension ID + placeholder.
# Set VELOCE_EXTENSION_IDS to override (comma-separated, or empty to allow any extension).
ALLOWED_EXTENSION_IDS = (
    {i.strip() for i in os.environ["VELOCE_EXTENSION_IDS"].split(",") if i.strip()}
    if "VELOCE_EXTENSION_IDS" in os.environ
    else set(DEFAULT_EXTENSION_IDS)
)
EXTENSION_SCHEMES = ("chrome-extension", "moz-extension")
ALLOWED_HOSTS = ("127.0.0.1", "localhost", "[::1]")
MAX_BODY_BYTES = 4 * 1024 * 1024  # playlists + cookies can be sizeable
MAX_PARALLEL_MEDIA = 3


class BadRequest(Exception):
    pass


UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
UI_FILES = {
    "index.html": "text/html; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "theme.js": "text/javascript; charset=utf-8",
    "logo.png": "image/png",
}


_SHARE = None


def share():
    """Home-network sharing of the downloads folder (always starts off)."""
    global _SHARE
    if _SHARE is None:
        from .share import Share
        _SHARE = Share(DEFAULT_DOWNLOAD_DIR)
    return _SHARE


def _update_summary() -> dict:
    """Cheap (no network): what the extension and app window need to offer an update."""
    from . import app_update
    u = app_update.check(fetch=False)
    return {"update_available": u["available"], "latest_version": u["latest"], "updating": u["installing"],
            **app_update.status()}


def settings_payload() -> dict:
    from . import autostart, updater, jsruntime
    try:
        auto = autostart.is_enabled()
    except Exception:
        auto = False
    return {
        "version": __version__,
        "autostart": auto,
        "download_dir": DEFAULT_DOWNLOAD_DIR,
        "auto_update": updater.enabled(),
        "media_support": MediaEngine.available(),
        "max_connections": MAX_CONNECTIONS,
        **_update_summary(),
        **jsruntime.status(),
    }


# --------------------------------------------------------------------------- validation helpers

def is_allowed_origin(origin: str, own_port: Optional[int] = None) -> bool:
    """
    Who may call the API from a browser:
      - the Veloce extension (chrome-extension:// / moz-extension:// origins), and
      - the engine's own dashboard (exactly http://127.0.0.1:<engine port> or http://localhost:<engine port>).
    Every other web page, including other http://localhost:<port> apps, is rejected.
    """
    if own_port and origin in (f"http://127.0.0.1:{own_port}", f"http://localhost:{own_port}"):
        return True
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    if parsed.scheme not in EXTENSION_SCHEMES or not parsed.netloc:
        return False
    return not ALLOWED_EXTENSION_IDS or parsed.netloc in ALLOWED_EXTENSION_IDS


def host_without_port(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):  # IPv6 literal, e.g. [::1]:9229
        return host.split("]")[0] + "]"
    return host.split(":")[0]


def _within(path: str, root: str) -> bool:
    path, root = os.path.realpath(path), os.path.realpath(root)
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:  # different drives on Windows
        return False


def resolve_output_dir(requested: Optional[str]) -> str:
    """Downloads requested over the API are confined to the download directory."""
    if not requested:
        return DEFAULT_DOWNLOAD_DIR
    if not isinstance(requested, str):
        raise BadRequest("'output_path' must be a string")
    candidate = requested if os.path.isabs(requested) else os.path.join(DEFAULT_DOWNLOAD_DIR, requested)
    candidate = os.path.abspath(os.path.expanduser(candidate))
    if not _within(candidate, DEFAULT_DOWNLOAD_DIR):
        raise BadRequest(f"output_path must be inside {DEFAULT_DOWNLOAD_DIR}")
    os.makedirs(candidate, exist_ok=True)
    return candidate


def require_http_url(url) -> str:
    if not isinstance(url, str) or urlparse(url.strip()).scheme not in ("http", "https"):
        raise BadRequest("'url' must be an http(s) URL")
    return url.strip()


def parse_cookies(value) -> list:
    """Validates the browser cookie list sent by the extension (never persisted to history)."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 500:
        raise BadRequest("'cookies' must be a list of at most 500 cookies")
    keys = ("name", "value", "domain", "path", "secure", "httpOnly", "expirationDate")
    return [{k: c.get(k) for k in keys} for c in value if isinstance(c, dict)]


def remove_media_partials(directory: str, prefix: str):
    """Deletes yt-dlp's leftovers (.part / .ytdl / fragment files) after a cancelled media job."""
    try:
        for name in os.listdir(directory):
            if name.startswith(prefix + ".") and (name.endswith((".part", ".ytdl", ".temp")) or ".part-Frag" in name):
                os.remove(os.path.join(directory, name))
    except OSError:
        pass


def media_title(name: str, fallback: str) -> str:
    # '%' is stripped too: yt-dlp would interpret it as an output-template field
    name = re.sub(r"%", "_", sanitize_filename(name or ""))
    return name[:150] or fallback


def open_extension_folder() -> bool:
    """Opens the folder to pick in Chrome's "Load unpacked" (the app keeps it up to date)."""
    from . import app_update
    folder = app_update.status().get("extension_dir")
    if not folder or not os.path.isdir(folder):
        return False
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", folder])
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", folder])
        return True
    except Exception as e:
        logger.error(f"Failed to open the extension folder: {e}")
        return False


def reveal_in_explorer(file_path: Optional[str]) -> bool:
    """Opens the platform file manager at a file (selected) or folder inside the download directory."""
    norm_path = os.path.normpath(file_path or DEFAULT_DOWNLOAD_DIR)
    if not _within(norm_path, DEFAULT_DOWNLOAD_DIR) or not os.path.exists(norm_path):
        parent = os.path.dirname(norm_path)
        norm_path = parent if (parent and os.path.isdir(parent) and _within(parent, DEFAULT_DOWNLOAD_DIR)) \
            else DEFAULT_DOWNLOAD_DIR
    os.makedirs(DEFAULT_DOWNLOAD_DIR, exist_ok=True)

    try:
        if sys.platform == "win32":
            if os.path.isfile(norm_path):
                subprocess.Popen(["explorer", f"/select,{norm_path}"])
            else:
                subprocess.Popen(["explorer", norm_path])
        elif sys.platform == "darwin":
            # Always reveal (-R): `open` on a directory ending in .app would *launch* it.
            subprocess.Popen(["open", "-R", norm_path])
        else:
            target = os.path.dirname(norm_path) if os.path.isfile(norm_path) else norm_path
            subprocess.Popen(["xdg-open", target])
        return True
    except Exception as e:
        logger.error(f"Failed to open file manager for {norm_path}: {e}")
        return False


# --------------------------------------------------------------------------- task store

class TaskStore:
    def __init__(self, history_file: Optional[str] = HISTORY_FILE):
        self.tasks: Dict[str, DownloadTask] = {}
        self.media_stops: Dict[str, threading.Event] = {}
        self.media_slots = threading.BoundedSemaphore(MAX_PARALLEL_MEDIA)
        self.task_metadata: Dict[str, dict] = {}
        self.lock = threading.Lock()
        self.history_file = history_file
        self._load_history()

    # ---- persistence (finished/failed tasks survive engine restarts)

    def _load_history(self):
        if not self.history_file or not os.path.exists(self.history_file):
            return
        try:
            with open(self.history_file, "r", encoding="utf-8") as fh:
                for meta in json.load(fh):
                    if meta.get("status") not in ("COMPLETED", "ERROR", "CANCELLED", "FILE_REMOVED"):
                        meta["status"] = "ERROR"
                        meta["error"] = "Interrupted when the engine stopped"
                    meta["speed"] = 0.0
                    fpath = meta.get("file_path")
                    if fpath:
                        sidecar = f"{fpath}.veloce.json"
                        part = f"{fpath}.veloce.part"
                        if os.path.isfile(sidecar) and os.path.isfile(part):
                            meta["sidecar"] = sidecar
                    self.task_metadata[meta["id"]] = meta
        except Exception as e:
            logger.warning(f"Could not load download history: {e}")

    def _save_history_locked(self):
        if not self.history_file:
            return
        try:
            items = sorted(self.task_metadata.values(), key=lambda m: m.get("created_at", 0))[-HISTORY_LIMIT:]
            slim = [{k: v for k, v in m.items() if k != "segments"} for m in items]
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            tmp = self.history_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(slim, fh)
            os.replace(tmp, self.history_file)
        except Exception as e:
            logger.warning(f"Could not save download history: {e}")

    # ---- file downloads

    def create_task(self, url: str, output_path: str = None, connections: int = 16,
                    headers: dict = None, filename: Optional[str] = None, task_id: Optional[str] = None,
                    sidecar_data: Optional[dict] = None) -> str:
        task_id = task_id or uuid.uuid4().hex[:8]
        output_path = output_path or DEFAULT_DOWNLOAD_DIR
        out_dir = output_path if (os.path.isdir(output_path) or output_path.endswith(("/", "\\"))) else os.path.dirname(os.path.abspath(output_path))
        created_at = time.time()

        task = DownloadTask(
            url=url,
            output_path=output_path,
            num_connections=connections,
            headers=headers or {},
            suggested_filename=filename,
            sidecar_data=sidecar_data,
        )

        def on_progress(info):
            with self.lock:
                if task_id not in self.task_metadata:
                    return
                previous = self.task_metadata[task_id].get("status")
                if info["status"] in TERMINAL_STATUSES:
                    info = dict(info, segments=[])  # per-connection detail is only useful while running
                self.task_metadata[task_id] = {
                    "id": task_id,
                    "kind": "file",
                    "url": url,
                    "created_at": created_at,
                    "output_dir": out_dir,
                    "file_path": task.output_path,
                    **info,
                }
                if info["status"] != previous and info["status"] in TERMINAL_STATUSES:
                    self._save_history_locked()

        task.progress_callback = on_progress

        with self.lock:
            self.tasks[task_id] = task
            self.task_metadata[task_id] = {
                "id": task_id,
                "kind": "file",
                "url": url,
                "created_at": created_at,
                "output_dir": out_dir,
                "status": "QUEUED",
                "filename": sanitize_filename(filename or "") or os.path.basename(urlparse(url).path) or "Resolving…",
                "percent": 0.0,
                "speed": 0.0,
                "downloaded": 0,
                "total_size": 0,
                "eta": 0,
                "connections": connections,
                "segments": [],
            }

        self._spawn(task_id, task)
        return task_id

    def _spawn(self, task_id: str, task: DownloadTask):
        def run():
            try:
                task.start()
            except Exception as e:  # status/error are already recorded via the progress callback
                logger.warning(f"Task {task_id} failed: {e}")

        threading.Thread(target=run, daemon=True).start()

    # ---- media (yt-dlp) downloads

    def create_media_task(self, url: str, out_dir: str, title: str, format_id: str,
                          extract_audio: bool, audio_format: str, headers: dict,
                          page_url: Optional[str] = None, task_id: Optional[str] = None,
                          cookies: Optional[list] = None, playlist: Optional[str] = None,
                          referers: Optional[list] = None, subtitle_urls: Optional[list] = None) -> str:
        title = disambiguate_media_title(out_dir, title, url)
        task_id = task_id or uuid.uuid4().hex[:8]
        stop = threading.Event()
        with self.lock:
            self.media_stops[task_id] = stop
            self.task_metadata[task_id] = {
                "id": task_id,
                "kind": "media",
                "url": url,
                "page_url": page_url or url,
                "created_at": time.time(),
                "output_dir": out_dir,
                "title": title,
                "playlist": playlist,
                "format_id": format_id,
                "extract_audio": extract_audio,
                "audio_format": audio_format,
                "status": "QUEUED",
                "filename": f"{title}.{audio_format if extract_audio else 'mp4'}",
                "percent": 0.0,
                "speed": 0.0,
                "downloaded": 0,
                "total_size": 0,
                "eta": 0,
                "segments": [],
            }

        def on_progress(p):
            with self.lock:
                meta = self.task_metadata.get(task_id)
                if not meta or meta["status"] in TERMINAL_STATUSES:
                    return
                total = p.get("total_size") or 0
                p = {k: p.get(k) or 0 for k in ("downloaded", "total_size", "speed", "eta")}
                meta.update(p, status="DOWNLOADING",
                            percent=round(min(p["downloaded"] / total * 100, 99.9), 2) if total else 0.0)

        def run():
            try:
                # Playlists can enqueue hundreds of items; only a few run at once.
                with self.media_slots:
                    if stop.is_set():
                        raise MediaJobCancelled("Cancelled before start")
                    with self.lock:
                        if task_id in self.task_metadata:
                            self.task_metadata[task_id]["status"] = "INITIALIZING"
                    # Video needs ffmpeg (to join video + audio) and YouTube needs a JS runtime. Both are
                    # fetched once in the background at start; a job that arrives first waits for them.
                    from . import ffmpeg_setup, jsruntime
                    if not ffmpeg_setup.find() or not jsruntime.find_runtimes():
                        with self.lock:
                            if task_id in self.task_metadata:
                                self.task_metadata[task_id]["note"] = "Setting up video support (one time)…"
                        ffmpeg_setup.ensure()
                        jsruntime.ensure_runtime()
                        with self.lock:
                            if task_id in self.task_metadata:
                                self.task_metadata[task_id].pop("note", None)
                    if stop.is_set():
                        raise MediaJobCancelled("Cancelled before start")
                    # Runs in a child process: the engine itself never loads yt-dlp (see media_worker.py)
                    final_path = run_job({
                        "op": "download", "url": url, "output_dir": out_dir, "filename_prefix": title,
                        "format_id": format_id, "extract_audio": extract_audio, "audio_format": audio_format,
                        "headers": headers, "cookies": cookies, "referers": referers or [],
                        "subtitle_urls": subtitle_urls or [],
                    }, on_progress=on_progress, stop=stop)
                size = os.path.getsize(final_path) if os.path.exists(final_path) else 0
                update = {"status": "COMPLETED", "percent": 100.0, "speed": 0.0, "eta": 0,
                          "file_path": final_path, "filename": os.path.basename(final_path),
                          "downloaded": size, "total_size": size}
            except MediaJobCancelled:
                update = {"status": "CANCELLED", "speed": 0.0}
                remove_media_partials(out_dir, title)
            except Exception as e:
                logger.error(f"Stream download failed: {e}")
                update = {"status": "ERROR", "error": str(e).strip()[:300], "speed": 0.0}
            with self.lock:
                self.media_stops.pop(task_id, None)
                if task_id in self.task_metadata:
                    self.task_metadata[task_id].update(update)
                    self._save_history_locked()

        threading.Thread(target=run, daemon=True).start()
        return task_id

    # ---- queries & control

    def list_tasks(self) -> list:
        with self.lock:
            for meta in self.task_metadata.values():
                fpath = meta.get("file_path")
                if meta.get("status") == "COMPLETED" and fpath and not os.path.exists(fpath):
                    meta["status"] = "FILE_REMOVED"
                    meta["file_missing"] = True
            # Copies, so JSON serialization outside the lock can't race with progress updates
            items = [dict(m) for m in self.task_metadata.values()]
        return sorted(items, key=lambda m: m.get("created_at", 0), reverse=True)

    def clear_completed(self) -> int:
        with self.lock:
            to_remove = [tid for tid, m in self.task_metadata.items()
                         if m.get("status") in ("COMPLETED", "FILE_REMOVED", "ERROR", "CANCELLED")]
            for tid in to_remove:
                self.tasks.pop(tid, None)
                self.task_metadata.pop(tid, None)
            self._save_history_locked()
            return len(to_remove)

    def pause_task(self, task_id: str) -> bool:
        with self.lock:
            task = self.tasks.get(task_id)
        if not task:
            return False
        task.pause()
        return True

    def resume_task(self, task_id: str) -> bool:
        """Resumes a paused task in place, or retries a failed/interrupted one from scratch."""
        with self.lock:
            task = self.tasks.get(task_id)
            meta = dict(self.task_metadata.get(task_id) or {})
        if task and task.prepare_resume():
            self._spawn(task_id, task)
            return True
        if not meta or meta.get("status") not in ("ERROR", "CANCELLED", "PAUSED", "FILE_REMOVED"):
            return False

        with self.lock:
            self.tasks.pop(task_id, None)
            self.task_metadata.pop(task_id, None)
        out_dir = meta.get("output_dir") or DEFAULT_DOWNLOAD_DIR
        if meta.get("kind") == "media":
            if not _within(out_dir, DEFAULT_DOWNLOAD_DIR):
                out_dir = DEFAULT_DOWNLOAD_DIR
            self.create_media_task(
                url=meta["url"], out_dir=out_dir, title=meta.get("title") or "media",
                format_id=meta.get("format_id") or MediaEngine.normalize_format("720p", False),
                extract_audio=bool(meta.get("extract_audio")), audio_format=meta.get("audio_format") or "mp3",
                headers={}, page_url=meta.get("page_url"), task_id=task_id,
            )
        else:
            fpath = meta.get("file_path")
            sidecar_data = None
            output_target = out_dir
            if fpath:
                sidecar_path = f"{fpath}.veloce.json"
                part_path = f"{fpath}.veloce.part"
                if os.path.isfile(sidecar_path) and os.path.isfile(part_path):
                    try:
                        with open(sidecar_path, "r", encoding="utf-8") as f:
                            sidecar_data = json.load(f)
                        output_target = fpath
                    except Exception as e:
                        logger.warning(f"Failed to read sidecar for {fpath}: {e}")
            self.create_task(url=meta["url"], output_path=output_target, connections=meta.get("connections") or 16,
                             filename=meta.get("filename"), task_id=task_id, sidecar_data=sidecar_data)
        return True

    def shutdown(self):
        with self.lock:
            for task in self.tasks.values():
                if task and getattr(task, "_running", False):
                    try:
                        task._save_sidecar()
                    except Exception:
                        pass

    def remove_task(self, task_id: str) -> bool:
        """Removes a task from the list. Stops it (deleting only the *partial* file) if still running."""
        with self.lock:
            task = self.tasks.pop(task_id, None)
            stop = self.media_stops.get(task_id)
            found = self.task_metadata.pop(task_id, None) is not None
            self._save_history_locked()
        if task:
            task.cancel()
        if stop:
            stop.set()
        return found or task is not None


STORE = TaskStore()
atexit.register(STORE.shutdown)


class ProbeCache:
    """
    Format lookups are network-bound (seconds), so Veloce avoids repeating them:
      * results are kept for 10 minutes (reopening the picker or the popup is instant);
      * a lookup already running for a URL is shared, not started twice;
      * lookups run in a warm helper that already has yt-dlp loaded;
      * the extension starts the lookup when you point at a video ("prefetch"), so it's usually
        finished by the time you click Download.
    """
    TTL = 600
    MAX = 64

    def __init__(self):
        self._lock = threading.Lock()
        self._done = {}       # key -> (time, result)
        self._running = {}    # key -> threading.Event
        self._errors = {}     # key -> message
        self.warm = WarmProbe()

    @staticmethod
    def _key(url, cookies):
        return (url, bool(cookies))

    def get(self, url, headers, cookies, wait=True):
        key = self._key(url, cookies)
        with self._lock:
            hit = self._done.get(key)
            if hit and time.time() - hit[0] < self.TTL:
                return hit[1]
            event = self._running.get(key)
            owner = event is None
            if owner:
                event = self._running[key] = threading.Event()
                self._errors.pop(key, None)
        if not owner:
            if not wait:
                return None
            event.wait(130)
            with self._lock:
                if key in self._done:
                    return self._done[key][1]
                raise RuntimeError(self._errors.get(key) or "Lookup failed")
        try:
            result = self.warm.probe({"op": "probe", "url": url, "headers": headers, "cookies": cookies})
            with self._lock:
                self._done[key] = (time.time(), result)
                if len(self._done) > self.MAX:
                    oldest = min(self._done, key=lambda k: self._done[k][0])
                    self._done.pop(oldest, None)
            return result
        except Exception as e:
            with self._lock:
                self._errors[key] = str(e)
            raise
        finally:
            with self._lock:
                self._running.pop(key, None)
            event.set()

    def prefetch(self, url, headers, cookies):
        threading.Thread(target=lambda: self._safe(url, headers, cookies), daemon=True).start()

    def _safe(self, *args):
        try:
            self.get(*args)
        except Exception:
            pass


PROBES = ProbeCache()


# --------------------------------------------------------------------------- HTTP handler

class RequestHandler(BaseHTTPRequestHandler):
    def _validate_request(self) -> bool:
        """
        Guards against DNS rebinding (Host check) and cross-site request forgery (Origin check).
        Requests without an Origin header (CLI, curl, local scripts) are allowed.
        """
        if host_without_port(self.headers.get("Host", "")) not in ALLOWED_HOSTS:
            self._send_json(403, {"error": "Forbidden: invalid Host header (DNS rebinding guard)"})
            return False

        origin = self.headers.get("Origin")
        if origin is None or is_allowed_origin(origin, self.server.server_port):
            return True

        self._send_json(403, {"error": "Forbidden: unauthorized origin. Requests from websites are blocked."})
        return False

    def _send_cors_headers(self):
        origin = self.headers.get("Origin", "")
        if origin and is_allowed_origin(origin, self.server.server_port):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Vary", "Origin")

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            raise BadRequest("Invalid Content-Length")
        if length < 0 or length > MAX_BODY_BYTES:
            raise BadRequest("Request body too large")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise BadRequest("Invalid JSON")
        if not isinstance(payload, dict):
            raise BadRequest("JSON body must be an object")
        return payload

    def do_OPTIONS(self):
        if not self._validate_request():
            return
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def _send_static(self, name: str):
        """Serves the dashboard's files. Only names that exist directly in engine/ui are served."""
        if name not in UI_FILES:
            self._send_json(404, {"error": "Not Found"})
            return
        with open(os.path.join(UI_DIR, name), "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", UI_FILES[name])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' https: data:; style-src 'self'; script-src 'self'; "
                         "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._validate_request():
            return
        path = urlparse(self.path).path

        if path in ("/", "/index.html"):
            self._send_static("index.html")
            return
        if path.startswith("/ui/"):
            self._send_static(path[len("/ui/"):])
            return

        if path == "/api/settings":
            self._send_json(200, settings_payload())
            return

        if path == "/api/status":
            from . import app_update
            ext = parse_qs(urlparse(self.path).query).get("ext", [""])[0]
            if ext:
                app_update.saw_extension(ext)
            self._send_json(200, {
                "status": "ok",
                "name": "Veloce Engine",
                "version": __version__,
                "default_download_dir": DEFAULT_DOWNLOAD_DIR,
                "media_support": MediaEngine.available(),
                **_update_summary(),
            })
        elif path == "/api/share":
            self._send_json(200, share().status())
        elif path == "/api/tasks":
            self._send_json(200, {"tasks": STORE.list_tasks()})
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        if not self._validate_request():
            return
        try:
            self._handle_post(urlparse(self.path).path, self._read_json())
        except BadRequest as e:
            self._send_json(400, {"error": str(e)})

    def _handle_post(self, path: str, payload: dict):
        headers = payload.get("headers") or {}
        if not isinstance(headers, dict):
            raise BadRequest("'headers' must be an object")
        headers = {str(k): str(v) for k, v in headers.items()}

        if path == "/api/inspect":
            url = require_http_url(payload.get("url"))
            probe = DownloadTask(url=url, output_path=DEFAULT_DOWNLOAD_DIR, headers=headers,
                                 suggested_filename=payload.get("filename"))
            try:
                probe.inspect_url()
            finally:
                probe.release_probe()
            ctype = probe.content_type.split(";")[0].strip().lower()
            self._send_json(200, {
                "success": True,
                "url": url,
                "final_url": probe.url,
                "filename": probe.filename,
                "total_size": probe.total_size,
                "content_type": ctype,
                "resumable": probe.resumable,
                # An HTML response usually means a web page (video site, share page, login wall), not a file
                "is_page": ctype in ("text/html", "application/xhtml+xml"),
            })
            return

        cookies = parse_cookies(payload.get("cookies"))

        if path == "/api/media/probe":
            url = require_http_url(payload.get("url"))
            try:
                result = PROBES.get(url, headers, cookies)
            except Exception as e:
                raise BadRequest(f"Couldn't read this page: {e}")
            self._send_json(200, {"success": True, "result": result})
            return

        if path == "/api/media/prefetch":
            # Fire-and-forget: start the lookup now so the picker opens instantly later
            PROBES.warm.warm()
            prefetch_url = require_http_url(payload.get("url"))
            logger.info(f"Prefetching formats for {urlparse(prefetch_url).netloc}")
            PROBES.prefetch(prefetch_url, headers, cookies)
            self._send_json(202, {"success": True})
            return

        if path == "/api/media/download":
            extract_audio = bool(payload.get("extract_audio", False))
            audio_format = str(payload.get("audio_format", "mp3"))
            if audio_format not in MediaEngine.AUDIO_FORMATS:
                raise BadRequest(f"audio_format must be one of {', '.join(MediaEngine.AUDIO_FORMATS)}")
            format_id = MediaEngine.normalize_format(str(payload.get("format_id") or "720p"), extract_audio)
            out_dir = resolve_output_dir(payload.get("output_path"))
            referers = [r for r in (payload.get("referers") or []) if isinstance(r, str) and r.startswith(("http://", "https://"))][:4]
            subtitle_urls = [u for u in (payload.get("subtitle_urls") or []) if isinstance(u, str) and u.startswith(("http://", "https://"))][:8]
            common = dict(format_id=format_id, extract_audio=extract_audio, audio_format=audio_format,
                          headers=headers, cookies=cookies, referers=referers, subtitle_urls=subtitle_urls)

            entries = payload.get("entries")
            if entries is not None:
                # Playlist: one queued task per selected entry, saved in a folder named after the playlist
                if not isinstance(entries, list) or not entries:
                    raise BadRequest("'entries' must be a non-empty list")
                pl_title = media_title(str(payload.get("playlist_title") or ""), fallback="Playlist")
                pl_dir = resolve_output_dir(os.path.join(out_dir, pl_title))
                task_ids = []
                for i, entry in enumerate(entries[:500], 1):
                    if not isinstance(entry, dict):
                        continue
                    entry_url = require_http_url(entry.get("url"))
                    title = media_title(f"{i:03d} - {entry.get('title') or 'video'}", fallback=f"{i:03d}")
                    task_ids.append(STORE.create_media_task(url=entry_url, out_dir=pl_dir, title=title,
                                                            page_url=entry_url, playlist=pl_title, **common))
                self._send_json(200, {"success": True, "task_ids": task_ids})
                return

            url = require_http_url(payload.get("url"))
            task_id = STORE.create_media_task(
                url=url,
                out_dir=out_dir,
                title=media_title(str(payload.get("title") or ""), fallback=f"media_{uuid.uuid4().hex[:8]}"),
                page_url=payload.get("page_url") if isinstance(payload.get("page_url"), str) else None,
                **common,
            )
            self._send_json(200, {"success": True, "task_id": task_id})
            return

        if path == "/api/download":
            url = require_http_url(payload.get("url"))
            try:
                connections = int(payload.get("connections", 16))
            except (TypeError, ValueError):
                raise BadRequest("'connections' must be an integer")
            if not 1 <= connections <= MAX_CONNECTIONS:
                raise BadRequest(f"'connections' must be between 1 and {MAX_CONNECTIONS}")
            filename = payload.get("filename")
            task_id = STORE.create_task(
                url=url,
                output_path=resolve_output_dir(payload.get("output_path")),
                connections=connections,
                headers=headers,
                filename=filename if isinstance(filename, str) else None,
            )
            self._send_json(200, {"success": True, "task_id": task_id})
            return

        if path == "/api/settings":
            if "autostart" in payload:
                from . import autostart
                try:
                    autostart.enable() if payload["autostart"] else autostart.disable()
                except Exception as e:
                    raise BadRequest(f"Couldn't change start-at-login: {e}")
            self._send_json(200, settings_payload())
            return

        if path == "/api/update/check":
            from . import app_update
            self._send_json(200, app_update.check(force=True))
            return

        if path == "/api/update/install":
            from . import app_update
            self._send_json(200, app_update.install(on_exit=lambda: None))
            return

        if path == "/api/ytdlp/update":
            from . import updater, media
            try:
                new_version = updater.check_and_update()
            except Exception as e:
                raise BadRequest(f"Update check failed: {e}")
            if new_version and not STORE.media_stops and updater.activate():
                media.reload_ytdlp()
            self._send_json(200, {"success": True, "updated_to": new_version, **settings_payload()})
            return

        if path == "/api/tasks/clear-completed":
            self._send_json(200, {"success": True, "cleared": STORE.clear_completed()})
            return

        if path == "/api/share":
            # Only the dashboard on this computer may turn sharing on or off (not extensions or web pages)
            origin = (self.headers.get("Origin") or "").lower()
            port = self.server.server_address[1]
            if origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                self._send_json(403, {"error": "Sharing can only be changed from the Veloce app"})
                return
            try:
                if payload.get("new_code"):
                    status = share().new_code()
                elif payload.get("disconnect"):
                    status = share().disconnect(str(payload["disconnect"]))
                else:
                    status = share().start() if payload.get("enabled") else share().stop()
            except OSError as e:
                raise BadRequest(f"Couldn't start sharing: {e}")
            self._send_json(200, status)
            return

        if path == "/api/extension/open-folder":
            self._send_json(200, {"success": open_extension_folder()})
            return

        if path == "/api/open-folder":
            self._send_json(200, {"success": reveal_in_explorer(DEFAULT_DOWNLOAD_DIR)})
            return

        parts = path.strip("/").split("/")  # api / tasks / <id> / <action>
        if len(parts) == 4 and parts[:2] == ["api", "tasks"]:
            task_id, action = parts[2], parts[3]
            handlers = {
                "pause": STORE.pause_task,
                "resume": STORE.resume_task,
                "cancel": STORE.remove_task,
                "remove": STORE.remove_task,
            }
            if action in handlers:
                ok = handlers[action](task_id)
                self._send_json(200 if ok else 404, {"success": ok})
                return
            if action == "open":
                with STORE.lock:
                    meta = dict(STORE.task_metadata.get(task_id) or {})
                if not meta:
                    self._send_json(404, {"success": False})
                    return
                self._send_json(200, {"success": reveal_in_explorer(meta.get("file_path"))})
                return

        self._send_json(404, {"error": "Endpoint not found"})

    def log_message(self, format, *args):
        # Quiet standard logging to avoid terminal clutter
        pass


def create_server(port: int = 9229, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """Binds the engine (raises OSError if the port is taken) and starts the yt-dlp auto-updater."""
    if host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning(f"Binding to {host} exposes the download API beyond this machine.")
    os.makedirs(DEFAULT_DOWNLOAD_DIR, exist_ok=True)
    httpd = ThreadingHTTPServer((host, port), RequestHandler)
    httpd.daemon_threads = True
    from . import updater, media, jsruntime, app_update
    app_update.cleanup_leftovers()
    try:
        app_update.sync_extension()
    except Exception as e:
        logger.warning(f"Couldn't refresh the extension folder: {e}")
    app_update.start_background()
    updater.start_background(is_idle=lambda: not STORE.media_stops, on_swap=media.reload_ytdlp)
    jsruntime.ensure_in_background()
    logger.info(f"Veloce Engine {__version__} listening at http://{host}:{port}/ — saving to {DEFAULT_DOWNLOAD_DIR}")
    return httpd


def run_server(port: int = 9229, host: str = "127.0.0.1"):
    httpd = create_server(port, host)
    print(f"[OK] Veloce Engine {__version__} running — dashboard at http://{host}:{port}/", flush=True)
    print(f"[OK] Saving downloads to {DEFAULT_DOWNLOAD_DIR}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Stopping Veloce engine...", flush=True)
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_server()
