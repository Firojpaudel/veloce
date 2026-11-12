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


def worker_main():
    """Entry point of the child process (`veloce media-worker`)."""
    out = sys.stdout

    def emit(obj):
        out.write(json.dumps(obj) + "\n")
        out.flush()

    try:
        job = json.loads(sys.stdin.read())
        from .media import MediaEngine
        op = job.get("op")
        if op == "probe":
            data = MediaEngine.probe_url(job["url"], job.get("headers"), job.get("cookies"))
        elif op == "download":
            data = MediaEngine.download_stream(
                url=job["url"],
                output_dir=job["output_dir"],
                filename_prefix=job["filename_prefix"],
                format_id=job["format_id"],
                extract_audio=job.get("extract_audio", False),
                audio_format=job.get("audio_format", "mp3"),
                headers=job.get("headers"),
                cookies=job.get("cookies"),
                progress_callback=lambda p: emit({"event": "progress", **p}),
            )
        else:
            raise ValueError(f"unknown op {op!r}")
        emit({"event": "result", "data": data})
    except Exception as e:  # report every failure as a message the UI can show
        emit({"event": "error", "message": str(e).strip()[:400] or e.__class__.__name__})
