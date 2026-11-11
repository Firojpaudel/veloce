"""
Veloce Engine Local API Server & Native Bridge
Runs a lightweight REST & WebSocket service to bridge browser extension, CLI, and desktop UI.
Uses standard library components for zero-dependency execution.
"""

import os
import json
import uuid
import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict

from .segmenter import DownloadTask
from .media import MediaEngine

logger = logging.getLogger("VeloceServer")
DEFAULT_DOWNLOAD_DIR = os.path.expanduser("~/Downloads")

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
            return list(self.task_metadata.values())

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
    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
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
                    MediaEngine.download_stream(
                        url=url,
                        output_dir=out_dir,
                        filename_prefix=title,
                        format_id=format_id,
                        extract_audio=extract_audio,
                        audio_format=audio_format
                    )
                    with STORE.lock:
                        if task_id in STORE.task_metadata:
                            STORE.task_metadata[task_id]["status"] = "COMPLETED"
                            STORE.task_metadata[task_id]["percent"] = 100.0
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

        self._send_json(404, {"error": "Endpoint not found"})

    def log_message(self, format, *args):
        # Quiet standard logging to avoid terminal clutter
        pass


def run_server(port: int = 9229, host: str = "127.0.0.1"):
    server_address = (host, port)
    httpd = HTTPServer(server_address, RequestHandler)
    logger.info("Veloce Core Engine listening on http://%s:%d", host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping server...")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
