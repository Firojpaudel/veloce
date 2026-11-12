"""
Out-of-process media jobs.

yt-dlp is large (~30 MB resident once imported) and only needed while a video job runs. The engine
therefore never imports it: each probe/download runs in a short-lived child process
(`veloce media-worker`), which exits when the job ends and returns all of that memory to the OS.
It also makes cancelling reliable (terminate the child), isolates extractor crashes from the engine,
and means every new job automatically uses the latest auto-updated yt-dlp.

Protocol: the parent writes one JSON job to the child's stdin (cookies travel here, never in argv).
The child writes JSON lines to stdout: {"event": "progress", ...}, then exactly one
{"event": "result", "data": ...} or {"event": "error", "message": ...}.
"""

import json
import os
import subprocess
import sys
import threading
from typing import Callable, Optional


def _worker_command() -> list:
    if getattr(sys, "frozen", False):  # PyInstaller binary: re-invoke ourselves
        return [sys.executable, "media-worker"]
    main_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    return [sys.executable, main_py, "media-worker"]


class MediaJobError(Exception):
    pass


class MediaJobCancelled(Exception):
    pass


def run_job(job: dict, on_progress: Optional[Callable[[dict], None]] = None,
            stop: Optional[threading.Event] = None, timeout: Optional[float] = None):
    """Runs a media job in a child process and returns its result (raises MediaJobError / MediaJobCancelled)."""
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW: no console flash for the child
    proc = subprocess.Popen(_worker_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", **kwargs)
    proc.stdin.write(json.dumps(job))
    proc.stdin.close()

    cancelled = threading.Event()

    def watchdog():
        if stop is not None:
            while proc.poll() is None:
                if stop.wait(0.25):
                    cancelled.set()
                    proc.terminate()
                    try:
                        proc.wait(3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    return

    threading.Thread(target=watchdog, daemon=True).start()
    timer = None
    if timeout:
        timer = threading.Timer(timeout, proc.kill)
        timer.daemon = True
        timer.start()

    result, error = None, None
    try:
        for line in proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            event = msg.get("event")
            if event == "progress" and on_progress:
                on_progress(msg)
            elif event == "result":
                result = msg.get("data")
            elif event == "error":
                error = msg.get("message") or "Media job failed"
        proc.wait()
    finally:
        if timer:
            timer.cancel()

    if cancelled.is_set():
        raise MediaJobCancelled("Cancelled by user")
    if error:
        raise MediaJobError(error)
    if result is None:
        raise MediaJobError("The media helper stopped unexpectedly" if proc.returncode else "No result from media helper")
    return result


def _run_one(job: dict, emit) -> object:
    from .media import MediaEngine
    op = job.get("op")
    if op == "probe":
        return MediaEngine.probe_url(job["url"], job.get("headers"), job.get("cookies"))
    if op == "download":
        return MediaEngine.download_stream(
            url=job["url"],
            output_dir=job["output_dir"],
            filename_prefix=job["filename_prefix"],
            format_id=job["format_id"],
            extract_audio=job.get("extract_audio", False),
            audio_format=job.get("audio_format", "mp3"),
            headers=job.get("headers"),
            cookies=job.get("cookies"),
            referers=job.get("referers"),
            subtitle_urls=job.get("subtitle_urls"),
            progress_callback=lambda p: emit({"event": "progress", **p}),
        )
    raise ValueError(f"unknown op {op!r}")


def worker_main():
    """Entry point of the child process: `veloce media-worker` (one job) or `veloce media-worker --serve`."""
    out = sys.stdout

    def emit(obj):
        out.write(json.dumps(obj) + "\n")
        out.flush()

    if "--serve" in sys.argv:
        return _serve(emit)
    try:
        emit({"event": "result", "data": _run_one(json.loads(sys.stdin.read()), emit)})
    except Exception as e:  # report every failure as a message the UI can show
        emit({"event": "error", "message": str(e).strip()[:400] or e.__class__.__name__})


SERVE_IDLE_SECONDS = 120


def _serve(emit):
    """Warm helper: handles lookups one per line, keeping yt-dlp loaded; exits after 2 idle minutes."""
    import queue
    lines: "queue.Queue[str]" = queue.Queue()

    def reader():
        for line in sys.stdin:
            lines.put(line)
        lines.put("")  # parent closed the pipe

    threading.Thread(target=reader, daemon=True).start()
    from . import media  # import yt-dlp now, while idle, so the first lookup doesn't pay for it
    media.ytdlp()
    while True:
        try:
            line = lines.get(timeout=SERVE_IDLE_SECONDS)
        except queue.Empty:
            return  # idle: exit and give the memory back
        if not line:
            return
        try:
            job = json.loads(line)
        except ValueError:
            continue
        try:
            emit({"id": job.get("id"), "event": "result", "data": _run_one(job, emit)})
        except Exception as e:
            emit({"id": job.get("id"), "event": "error", "message": str(e).strip()[:400] or e.__class__.__name__})


class WarmProbe:
    """
    Keeps one `media-worker --serve` process for format lookups, so a lookup skips process start-up and
    the yt-dlp import (1-2 s on Windows). Busy or broken → callers fall back to a one-shot worker.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._seq = 0

    def _spawn(self):
        kwargs = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
        self._proc = subprocess.Popen(_worker_command() + ["--serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1, **kwargs)

    def warm(self):
        """Start the helper ahead of time (e.g. when the user hovers a video)."""
        if self._lock.acquire(blocking=False):
            try:
                if self._proc is None or self._proc.poll() is not None:
                    self._spawn()
            finally:
                self._lock.release()

    def probe(self, job: dict, timeout: float = 120):
        if not self._lock.acquire(timeout=0.05):
            return run_job(job, timeout=timeout)  # someone else is using the warm helper
        try:
            for attempt in (1, 2):
                if self._proc is None or self._proc.poll() is not None:
                    self._spawn()
                self._seq += 1
                job_id = self._seq
                timer = threading.Timer(timeout, self._proc.kill)
                timer.daemon = True
                timer.start()
                try:
                    self._proc.stdin.write(json.dumps({**job, "id": job_id}) + "\n")
                    self._proc.stdin.flush()
                    for line in self._proc.stdout:
                        try:
                            msg = json.loads(line)
                        except ValueError:
                            continue
                        if msg.get("id") != job_id:
                            continue
                        if msg.get("event") == "result":
                            return msg.get("data")
                        if msg.get("event") == "error":
                            raise MediaJobError(msg.get("message") or "Lookup failed")
                except (BrokenPipeError, OSError):
                    pass
                finally:
                    timer.cancel()
                self._proc = None  # helper exited (idle timeout or crash): start a fresh one and retry once
            raise MediaJobError("The media helper stopped unexpectedly")
        finally:
            self._lock.release()
