"""
Veloce Engine Local API Server & Native Bridge
Runs a lightweight REST & WebSocket service to bridge browser extension, CLI, and desktop UI.
Uses standard library components for zero-dependency execution.
"""

import os
import sys
import json
import uuid
import time
import logging
import threading
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict

from .segmenter import DownloadTask
from .media import MediaEngine

logger = logging.getLogger("VeloceServer")
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~/Downloads"), "veloce")
os.makedirs(DEFAULT_DOWNLOAD_DIR, exist_ok=True)


def reveal_in_explorer(file_path: str) -> bool:
    """Opens File Explorer / Finder / file manager and selects or opens the file/folder."""
    if not file_path:
        file_path = DEFAULT_DOWNLOAD_DIR

    norm_path = os.path.normpath(file_path)
    if not os.path.exists(norm_path):
        parent = os.path.dirname(norm_path)
        norm_path = parent if (parent and os.path.exists(parent)) else DEFAULT_DOWNLOAD_DIR

    try:
        if sys.platform == "win32":
            if os.path.isfile(norm_path):
                subprocess.Popen(f'explorer /select,"{norm_path}"')
            else:
                subprocess.Popen(f'explorer "{norm_path}"')
        elif sys.platform == "darwin":
            if os.path.isfile(norm_path):
                subprocess.Popen(["open", "-R", norm_path])
            else:
                subprocess.Popen(["open", norm_path])
        else:
            target = os.path.dirname(norm_path) if os.path.isfile(norm_path) else norm_path
            subprocess.Popen(["xdg-open", target])
        return True
    except Exception as e:
        logger.error(f"Failed to open explorer for {norm_path}: {e}")
        return False

class TaskStore:
    def __init__(self):
        self.tasks: Dict[str, DownloadTask] = {}
        self.task_metadata: Dict[str, dict] = {}
        self.lock = threading.Lock()

    def create_task(self, url: str, output_path: str = None, connections: int = 16, headers: dict = None) -> str:
        task_id = str(uuid.uuid4())[:8]
        if not output_path:
            output_path = DEFAULT_DOWNLOAD_DIR

        def on_progress(info):
            with self.lock:
                self.task_metadata[task_id] = {
                    "id": task_id,
                    "url": url,
                    "file_path": task.output_path,
                    **info
                }

        task = DownloadTask(
            url=url,
            output_path=output_path,
            num_connections=connections,
            headers=headers or {},
            progress_callback=on_progress
        )

        with self.lock:
            self.tasks[task_id] = task
            self.task_metadata[task_id] = {
                "id": task_id,
                "url": url,
                "status": "INITIALIZING",
                "filename": os.path.basename(output_path) if output_path else "file",
                "percent": 0.0,
                "speed": 0.0,
                "downloaded": 0,
                "total_size": 0,
                "eta": 0,
                "segments": []
            }

        t = threading.Thread(target=task.start, daemon=True)
        t.start()
        return task_id

    def list_tasks(self) -> list:
        with self.lock:
            # Sync with physical filesystem: if user deleted file, reflect it
            for tid, meta in self.task_metadata.items():
                fpath = meta.get("file_path")
                if meta.get("status") == "COMPLETED" and fpath:
                    if not os.path.exists(fpath):
                        meta["status"] = "FILE_REMOVED"
                        meta["file_missing"] = True
            return list(self.task_metadata.values())

    def clear_completed(self) -> int:
        with self.lock:
            to_remove = [tid for tid, m in self.task_metadata.items() if m.get("status") in ["COMPLETED", "FILE_REMOVED", "ERROR"]]
            for tid in to_remove:
                self.tasks.pop(tid, None)
                self.task_metadata.pop(tid, None)
            return len(to_remove)

    def pause_task(self, task_id: str) -> bool:
        with self.lock:
            task = self.tasks.get(task_id)
            if task:
                task.pause()
                return True
        return False

    def cancel_task(self, task_id: str) -> bool:
        with self.lock:
            task = self.tasks.get(task_id)
            if task:
                task.cancel()
                self.tasks.pop(task_id, None)
                self.task_metadata.pop(task_id, None)
                return True
        return False


STORE = TaskStore()


class RequestHandler(BaseHTTPRequestHandler):
    def _validate_origin(self) -> bool:
        """
        Guards against DNS rebinding and cross-site request forgery (CSRF).
        Rejects requests from web pages; permits only the Veloce extension and local CLI.
        """
        host = self.headers.get("Host", "").split(":")[0]
        if host not in ["127.0.0.1", "localhost"]:
            self._send_json(403, {"error": "Forbidden: invalid Host header (DNS rebinding guard)"})
            return False

        origin = self.headers.get("Origin")
        # CLI tools (curl, local scripts) do not send Origin header; permit loopback
        if not origin:
            return True

        allowed_schemes = ("chrome-extension://", "moz-extension://")
        allowed_hosts = ("http://127.0.0.1", "http://localhost")
        if origin.startswith(allowed_schemes) or any(origin.startswith(h) for h in allowed_hosts):
            return True

        self._send_json(403, {"error": "Forbidden: unauthorized origin. Requests from websites are blocked."})
        return False

    def _send_cors_headers(self):
        origin = self.headers.get("Origin", "")
        allowed_schemes = ("chrome-extension://", "moz-extension://")
        allowed_hosts = ("http://127.0.0.1", "http://localhost")
        if origin.startswith(allowed_schemes) or any(origin.startswith(h) for h in allowed_hosts):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        if not self._validate_origin():
            return
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._validate_origin():
            return
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            self._send_json(200, {
                "status": "ok",
                "name": "Veloce High-Performance Engine",
                "version": "1.0.0",
                "default_download_dir": DEFAULT_DOWNLOAD_DIR
            })
            return

        if path == "/api/tasks":
            tasks = STORE.list_tasks()
            self._send_json(200, {"tasks": tasks})
            return

        self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        if not self._validate_origin():
            return
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            payload = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            self._send_json(400, {"error": "Invalid JSON"})
            return

        if path == "/api/media/probe":
            url = payload.get("url")
            if not url:
                self._send_json(400, {"error": "Missing 'url'"})
                return
            headers = payload.get("headers", {})
            probe_result = MediaEngine.probe_url(url, headers)
            self._send_json(200, {"success": True, "result": probe_result})
            return

        if path == "/api/media/download":
            url = payload.get("url")
            if not url:
                self._send_json(400, {"error": "Missing 'url'"})
                return

            task_id = str(uuid.uuid4())[:8]
            out_dir = payload.get("output_path", DEFAULT_DOWNLOAD_DIR)
            format_id = payload.get("format_id", "bestvideo[height<=720]+bestaudio/best[height<=720]")
            extract_audio = bool(payload.get("extract_audio", False))
            audio_format = payload.get("audio_format", "mp3")
            title = payload.get("title", f"media_{task_id}")
            headers = payload.get("headers", {})

            # Ensure video downloads ALWAYS merge an audio track so sound is never missing
            if not extract_audio:
                if format_id in ["720p", "720"]:
                    format_id = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
                elif format_id in ["1080p", "1080"]:
                    format_id = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
                elif format_id and "+" not in format_id and not format_id.startswith("best"):
                    format_id = f"{format_id}+bestaudio/best"

            # Register in task store
            with STORE.lock:
                STORE.task_metadata[task_id] = {
                    "id": task_id,
                    "url": url,
                    "status": "DOWNLOADING",
                    "filename": f"{title}.{'mp3' if extract_audio else 'mp4'}",
                    "percent": 5.0,
                    "speed": 0.0,
                    "downloaded": 0,
                    "total_size": 0,
                    "eta": 0,
                    "segments": []
                }

            def run_stream():
                try:
                    final_path = MediaEngine.download_stream(
                        url=url,
                        output_dir=out_dir,
                        filename_prefix=title,
                        format_id=format_id,
                        extract_audio=extract_audio,
                        audio_format=audio_format,
                        headers=headers
                    )
                    with STORE.lock:
                        if task_id in STORE.task_metadata:
                            STORE.task_metadata[task_id]["status"] = "COMPLETED"
                            STORE.task_metadata[task_id]["percent"] = 100.0
                            STORE.task_metadata[task_id]["file_path"] = final_path
                            STORE.task_metadata[task_id]["filename"] = os.path.basename(final_path)
                except Exception as e:
                    logger.error(f"Stream download failed: {e}")
                    with STORE.lock:
                        if task_id in STORE.task_metadata:
                            STORE.task_metadata[task_id]["status"] = "ERROR"

            threading.Thread(target=run_stream, daemon=True).start()
            self._send_json(200, {"success": True, "task_id": task_id})
            return

        if path == "/api/download":
            url = payload.get("url")
            if not url:
                self._send_json(400, {"error": "Missing 'url' parameter"})
                return

            out_dir = payload.get("output_path", DEFAULT_DOWNLOAD_DIR)
            connections = int(payload.get("connections", 16))
            headers = payload.get("headers", {})

            task_id = STORE.create_task(
                url=url,
                output_path=out_dir,
                connections=connections,
                headers=headers
            )
            self._send_json(200, {"success": True, "task_id": task_id})
            return

        if path.startswith("/api/tasks/") and path.endswith("/pause"):
            parts = path.split("/")
            task_id = parts[3]
            success = STORE.pause_task(task_id)
            self._send_json(200 if success else 404, {"success": success})
            return

        if path.startswith("/api/tasks/") and path.endswith("/cancel"):
            parts = path.split("/")
            task_id = parts[3]
            success = STORE.cancel_task(task_id)
            self._send_json(200 if success else 404, {"success": success})
            return

        if path.startswith("/api/tasks/") and path.endswith("/open"):
            parts = path.split("/")
            task_id = parts[3]
            with STORE.lock:
                meta = STORE.task_metadata.get(task_id, {})
                fpath = meta.get("file_path") or os.path.join(DEFAULT_DOWNLOAD_DIR, meta.get("filename", ""))
            success = reveal_in_explorer(fpath)
            self._send_json(200, {"success": success})
            return

        if path == "/api/tasks/clear-completed":
            count = STORE.clear_completed()
            self._send_json(200, {"success": True, "cleared": count})
            return

        if path == "/api/open-folder":
            folder = payload.get("path", DEFAULT_DOWNLOAD_DIR)
            success = reveal_in_explorer(folder)
            self._send_json(200, {"success": success})
            return

        self._send_json(404, {"error": "Endpoint not found"})

    def log_message(self, format, *args):
        # Quiet standard logging to avoid terminal clutter
        pass


def run_server(port: int = 9229, host: str = "127.0.0.1"):
    server_address = (host, port)
    httpd = HTTPServer(server_address, RequestHandler)
    print(f"[OK] Veloce Engine listening at http://{host}:{port}/api", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Stopping Veloce engine...", flush=True)
        httpd.server_close()


if __name__ == "__main__":
    run_server()
