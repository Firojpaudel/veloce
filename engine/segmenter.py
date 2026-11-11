"""
Veloce - High-Performance Dynamic Segmentation Download Engine
Implements dynamic byte-range partitioning, atomic pwrite disk writes,
and thread-safe work-stealing bisection.
"""

import os
import sys
import time
import math
import json
import logging
import threading
from typing import List, Dict, Optional, Callable
from urllib.parse import urlparse, unquote
import urllib.request
import urllib.error

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("VeloceEngine")

MIN_SPLIT_SIZE = 1 * 1024 * 1024  # 1 MB threshold for dynamic segment bisection
CHUNK_BUFFER_SIZE = 64 * 1024     # 64 KB per read buffer


class Segment:
    def __init__(self, segment_id: int, start: int, end: int, current: int = None):
        self.segment_id = segment_id
        self.start = start
        self.end = end
        self.current = current if current is not None else start
        self.completed = False
        self.active = False
        self.error: Optional[str] = None

    @property
    def remaining(self) -> int:
        if self.completed:
            return 0
        rem = self.end - self.current + 1
        return max(0, rem)

    @property
    def total_bytes(self) -> int:
        return self.end - self.start + 1

    @property
    def downloaded_bytes(self) -> int:
        return max(0, self.current - self.start)

    def to_dict(self) -> dict:
        return {
            "id": self.segment_id,
            "start": self.start,
            "end": self.end,
            "current": self.current,
            "remaining": self.remaining,
            "total": self.total_bytes,
            "downloaded": self.downloaded_bytes,
            "completed": self.completed,
            "active": self.active,
        }


class SegmentManager:
    """
    Coordinates multi-connection dynamic segment allocation and splitting.
    """
    def __init__(self, total_size: int, num_connections: int = 8):
        self.total_size = total_size
        self.num_connections = num_connections
        self.lock = threading.Lock()
        self.segments: List[Segment] = []
        self._next_id = 0
        self._init_static_segments()

    def _init_static_segments(self):
        if self.total_size <= 0:
            seg = Segment(0, 0, 0)
            self.segments.append(seg)
            self._next_id = 1
            return

        chunk_size = self.total_size // self.num_connections
        for i in range(self.num_connections):
            start = i * chunk_size
            end = (i + 1) * chunk_size - 1 if i < self.num_connections - 1 else self.total_size - 1
            if start <= end:
                self.segments.append(Segment(self._next_id, start, end))
                self._next_id += 1

    def get_idle_segment(self) -> Optional[Segment]:
        with self.lock:
            for seg in self.segments:
                if not seg.completed and not seg.active and seg.remaining > 0:
                    seg.active = True
                    return seg
            return None

    def split_largest_segment(self) -> Optional[Segment]:
        """
        Dynamic Segmentation algorithm:
        Finds active segment with largest unfinished byte slice and bisects it.
        """
        with self.lock:
            candidates = [
                s for s in self.segments
                if s.active and not s.completed and s.remaining >= (MIN_SPLIT_SIZE * 2)
            ]
            if not candidates:
                return None

            target = max(candidates, key=lambda s: s.remaining)
            rem = target.end - target.current + 1
            if rem < (MIN_SPLIT_SIZE * 2):
                return None

            split_point = target.current + (rem // 2)
            old_end = target.end
            target.end = split_point

            new_seg = Segment(
                segment_id=self._next_id,
                start=split_point + 1,
                end=old_end,
                current=split_point + 1
            )
            new_seg.active = True
            self._next_id += 1
            self.segments.append(new_seg)
            return new_seg

    def mark_completed(self, segment: Segment):
        with self.lock:
            segment.completed = True
            segment.active = False

    def is_all_completed(self) -> bool:
        with self.lock:
            return all(s.completed for s in self.segments)

    def total_downloaded(self) -> int:
        with self.lock:
            return sum(s.downloaded_bytes for s in self.segments)

    def get_progress_snapshot(self) -> List[dict]:
        with self.lock:
            return [s.to_dict() for s in self.segments]


class DownloadTask:
    def __init__(
        self,
        url: str,
        output_path: str,
        num_connections: int = 16,
        headers: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ):
        self.url = url
        self.output_path = output_path
        self.num_connections = num_connections
        self.headers = headers or {}
        self.progress_callback = progress_callback

        self.total_size = 0
        self.resumable = False
        self.filename = os.path.basename(output_path) if not os.path.isdir(output_path) else ""
        self.status = "INITIALIZING"
        self.error_message: Optional[str] = None

        self.manager: Optional[SegmentManager] = None
        self._stop_event = threading.Event()
        self._fd: Optional[int] = None

        self.start_time = 0.0
        self.last_bytes = 0
        self.last_time = 0.0
        self.current_speed = 0.0

    def _resolve_headers(self) -> dict:
        default_headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Connection": "keep-alive",
        }
        default_headers.update(self.headers)
        return default_headers

    def inspect_url(self):
        """Probes the remote server to detect Content-Length, filename, and Range support."""
        req = urllib.request.Request(self.url, headers=self._resolve_headers(), method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                headers = dict(resp.headers)
                length = headers.get("Content-Length")
                if length and length.isdigit():
                    self.total_size = int(length)

                accept_ranges = headers.get("Accept-Ranges", "")
                if "bytes" in accept_ranges.lower():
                    self.resumable = True

                cd = headers.get("Content-Disposition", "")
                if "filename=" in cd:
                    raw_name = cd.split("filename=")[-1].strip(' "\'')
                    self.filename = os.path.basename(raw_name)
        except Exception as e:
            logger.debug(f"HEAD probe failed: {e}; attempting byte-range probe")
            test_headers = self._resolve_headers()
            test_headers["Range"] = "bytes=0-0"
            req = urllib.request.Request(self.url, headers=test_headers)
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 206:
                        self.resumable = True
                        cr = resp.headers.get("Content-Range", "")
                        if "/" in cr:
                            total = cr.split("/")[-1].strip()
                            if total.isdigit():
                                self.total_size = int(total)
            except Exception as e2:
                logger.debug(f"Range probe also failed: {e2}")
                self.resumable = False

        if not self.filename:
            parsed = urlparse(self.url)
            sanitized = os.path.basename(unquote(parsed.path))
            self.filename = sanitized or "download.bin"

        if os.path.isdir(self.output_path):
            self.output_path = os.path.join(self.output_path, self.filename)

    def _worker_loop(self):
        while not self._stop_event.is_set():
            seg = self.manager.get_idle_segment()
            if not seg:
                seg = self.manager.split_largest_segment()
                if not seg:
                    break

            success = self._download_segment(seg)
            if success:
                self.manager.mark_completed(seg)
            else:
                seg.active = False
                time.sleep(0.5)

    def _download_segment(self, seg: Segment) -> bool:
        headers = self._resolve_headers()
        headers["Range"] = f"bytes={seg.current}-{seg.end}"
        req = urllib.request.Request(self.url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                while not self._stop_event.is_set():
                    with self.manager.lock:
                        if seg.current > seg.end:
                            break
                        max_to_read = min(CHUNK_BUFFER_SIZE, seg.end - seg.current + 1)

                    if max_to_read <= 0:
                        break

                    data = resp.read(max_to_read)
                    if not data:
                        break

                    # Atomic in-place write at offset using POSIX pwrite
                    os.pwrite(self._fd, data, seg.current)
                    seg.current += len(data)

                return seg.current > seg.end
        except Exception as e:
            logger.debug(f"Segment {seg.segment_id} read error: {e}")
            seg.error = str(e)
            return False

    def _download_single_stream(self):
        req = urllib.request.Request(self.url, headers=self._resolve_headers())
        with urllib.request.urlopen(req, timeout=20) as resp:
            with open(self.output_path, "wb") as f:
                while not self._stop_event.is_set():
                    data = resp.read(CHUNK_BUFFER_SIZE)
                    if not data:
                        break
                    f.write(data)
                    if self.manager and self.manager.segments:
                        self.manager.segments[0].current += len(data)

    def start(self):
        self.inspect_url()
        self.status = "DOWNLOADING"
        self.start_time = time.time()
        self.last_time = self.start_time
        self.last_bytes = 0

        out_dir = os.path.dirname(os.path.abspath(self.output_path))
        os.makedirs(out_dir, exist_ok=True)

        if not self.resumable or self.total_size <= 0:
            self.manager = SegmentManager(0, 1)
            self._download_single_stream()
            self.status = "COMPLETED"
            self._report_progress()
            return

        # Pre-allocate contiguous disk space to avoid filesystem fragmentation
        self._fd = os.open(self.output_path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            os.posix_fallocate(self._fd, 0, self.total_size)
        except (AttributeError, OSError):
            os.ftruncate(self._fd, self.total_size)

        self.manager = SegmentManager(self.total_size, self.num_connections)

        threads = []
        for _ in range(self.num_connections):
            t = threading.Thread(target=self._worker_loop, daemon=True)
            t.start()
            threads.append(t)

        try:
            while not self._stop_event.is_set():
                time.sleep(0.3)
                self._update_speed()
                self._report_progress()

                if self.manager.is_all_completed():
                    self.status = "COMPLETED"
                    self._report_progress()
                    break
        finally:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None

    def _update_speed(self):
        now = time.time()
        dt = now - self.last_time
        if dt >= 0.5:
            current_bytes = self.manager.total_downloaded() if self.manager else 0
            d_bytes = current_bytes - self.last_bytes
            self.current_speed = d_bytes / dt
            self.last_time = now
            self.last_bytes = current_bytes

    def _report_progress(self):
        if not self.progress_callback or not self.manager:
            return

        downloaded = self.manager.total_downloaded()
        percent = (downloaded / self.total_size * 100.0) if self.total_size > 0 else 0.0

        eta = 0.0
        if self.current_speed > 0 and self.total_size > downloaded:
            eta = (self.total_size - downloaded) / self.current_speed

        data = {
            "status": self.status,
            "filename": self.filename,
            "output_path": self.output_path,
            "total_size": self.total_size,
            "downloaded": downloaded,
            "percent": round(percent, 2),
            "speed": self.current_speed,
            "eta": round(eta, 1),
            "segments": self.manager.get_progress_snapshot(),
        }
        self.progress_callback(data)

    def pause(self):
        self._stop_event.set()
        self.status = "PAUSED"

    def cancel(self):
        self._stop_event.set()
        self.status = "CANCELLED"
        if os.path.exists(self.output_path):
            try:
                os.remove(self.output_path)
            except OSError:
                pass
