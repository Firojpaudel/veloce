"""
Veloce - High-Performance Dynamic Segmentation Download Engine
Implements dynamic byte-range partitioning, positional (pwrite) disk writes,
thread-safe work-stealing bisection, and pause/resume.
"""

import os
import re
import json
import time
import logging
import mimetypes
import threading
import http.client
from email.message import Message
from typing import List, Dict, Optional, Callable
from urllib.parse import urlparse, unquote, parse_qs, urljoin
import urllib.request
import urllib.error

logger = logging.getLogger("VeloceEngine")

MIN_SPLIT_SIZE = 1 * 1024 * 1024  # 1 MB threshold for dynamic segment bisection
CHUNK_BUFFER_SIZE = 256 * 1024    # 256 KB per read: fewer Python-level iterations at high throughput
MAX_SEGMENT_RETRIES = 5           # consecutive failures of one segment before the task is failed
MAX_CONNECTIONS = 32

# Adaptive ramp-up: start small, add connections only while they keep raising total throughput.
# Avoids paying 16 TLS handshakes on fast edge CDNs where one or two sockets already saturate the link.
INITIAL_CONNECTIONS = 8
BYTES_PER_INITIAL_CONNECTION = 1024 * 1024
RAMP_INTERVAL = 0.6               # seconds between ramp decisions
RAMP_STEP = 4                     # connections added per step
RAMP_MIN_GAIN = 1.10              # keep ramping only if throughput grew ≥10% since the last step
# "Single stream first": the probe connection streams the file immediately; after FANOUT_DELAY we
# measure it and only open more connections if one stream would still need > SINGLE_STREAM_ETA seconds.
FANOUT_DELAY = 0.4
SINGLE_STREAM_ETA = 1.0

# Slow-connection shedding: a connection far slower than the best one is dropped and its work
# re-requested on a fresh socket (often lands on a faster CDN node / less congested path).
SHED_GRACE = 2.0                  # seconds a connection gets before it can be judged
SHED_RATIO = 4                    # shed if slower than best / SHED_RATIO
SHED_MIN_ETA = 2.0                # ...and it still needs more than this many seconds at its pace
SHED_MAX_PER_SEGMENT = 3

REDIRECT_CODES = (301, 302, 303, 307, 308)

# Statuses in which no transfer is running
TERMINAL_STATUSES = ("COMPLETED", "ERROR", "CANCELLED", "PAUSED")

# Query parameters commonly used by CDNs / file hosts to carry the real filename
FILENAME_QUERY_KEYS = ("response-content-disposition", "filename", "file_name", "file", "name", "fn", "title", "dl")

# mimetypes.guess_extension picks odd defaults for some common types
PREFERRED_EXTENSIONS = {
    "application/octet-stream": "",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
    "application/pdf": ".pdf",
    "application/gzip": ".gz",
    "application/x-gzip": ".gz",
    "application/x-7z-compressed": ".7z",
    "application/vnd.rar": ".rar",
    "application/x-rar-compressed": ".rar",
    "application/x-msdownload": ".exe",
    "application/x-msdos-program": ".exe",
    "application/vnd.android.package-archive": ".apk",
    "application/x-iso9660-image": ".iso",
    "image/jpeg": ".jpg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
    "text/plain": ".txt",
    "text/html": ".html",
}

INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def friendly_error(e: BaseException) -> str:
    """Turns network exceptions into short, actionable messages for the UI."""
    import socket
    import ssl
    if isinstance(e, urllib.error.HTTPError):
        hints = {
            401: "the server wants you to sign in",
            403: "access denied — the link may have expired or need you to be logged in",
            404: "file not found — the link may be broken or removed",
            410: "this file was removed from the server",
            416: "the server rejected the requested range",
            429: "the server is rate-limiting downloads — try again in a few minutes",
        }
        return f"HTTP {e.code}: {hints.get(e.code, 'the server is having problems' if e.code >= 500 else e.reason or 'request rejected')}"
    reason = getattr(e, "reason", e)
    if isinstance(reason, socket.gaierror):
        return "Couldn't find the server — check the link and your internet connection"
    if isinstance(reason, ConnectionRefusedError):
        return "The server refused the connection — it may be down"
    if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(reason).lower():
        return "The server stopped responding (timed out)"
    if isinstance(reason, ssl.SSLError):
        return "Secure connection failed (SSL) — the site's certificate may be invalid"
    if isinstance(reason, (ConnectionResetError, http.client.RemoteDisconnected)):
        return "The server dropped the connection"
    if isinstance(e, PermissionError):
        return "Veloce can't write to the download folder (permission denied)"
    if isinstance(e, OSError) and getattr(e, "errno", None) == 28:
        return "Your disk is full"
    return str(e).strip() or e.__class__.__name__


class RangeNotSupported(Exception):
    """Server answered a ranged request with a full (200) body."""


SENSITIVE_HEADERS = ("Cookie", "Authorization")


class _StripCredentialsOnCrossHostRedirect(urllib.request.HTTPRedirectHandler):
    """Browser cookies sent with a download must never be forwarded to a different host via a redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urlparse(newurl).hostname != urlparse(req.full_url).hostname:
            for name in SENSITIVE_HEADERS:
                new.remove_header(name)
                new.remove_header(name.capitalize())
        return new


_opener = urllib.request.build_opener(_StripCredentialsOnCrossHostRedirect)


def _urlopen(req, timeout):
    return _opener.open(req, timeout=timeout)


def _make_pwrite():
    """os.pwrite is POSIX-only; on Windows emulate it with a locked seek+write."""
    if hasattr(os, "pwrite"):
        return os.pwrite
    lock = threading.Lock()

    def _pwrite(fd: int, data: bytes, offset: int) -> int:
        with lock:
            os.lseek(fd, offset, os.SEEK_SET)
            return os.write(fd, data)

    return _pwrite


_pwrite = _make_pwrite()


def sanitize_filename(name: str) -> str:
    """Makes a name safe to use as a single path component on every OS. Returns "" if nothing usable is left."""
    name = unquote(name or "")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = INVALID_FILENAME_CHARS.sub("_", name).strip(" .")
    if len(name) > 200:
        root, ext = os.path.splitext(name)
        name = root[: 200 - len(ext)] + ext
    return name


def parse_content_disposition(value: str) -> str:
    """Returns the filename from a Content-Disposition header value, honoring RFC 6266 `filename*`."""
    if not value:
        return ""
    # RFC 6266: filename* (RFC 5987 encoded) takes precedence over plain filename
    ext = re.search(r"filename\*\s*=\s*([\w!#$&+.^`|~-]*)'[^']*'([^;\s]+)", value, re.IGNORECASE)
    if ext:
        try:
            name = unquote(ext.group(2).strip('"'), encoding=ext.group(1) or "utf-8", errors="replace")
            name = sanitize_filename(name.replace("%", "%25"))  # already decoded; don't decode twice
            if name:
                return name.replace("%25", "%")
        except LookupError:
            pass
    msg = Message()
    msg["Content-Disposition"] = value
    try:
        name = msg.get_filename() or ""
    except Exception:
        name = ""
    return sanitize_filename(name)


def filename_from_url(url: str) -> str:
    """Best-effort filename from a URL: well-known query parameters first, then the last path segment."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in FILENAME_QUERY_KEYS:
        for value in query.get(key, []):
            if key == "response-content-disposition":
                name = parse_content_disposition(value)
            else:
                name = sanitize_filename(value)
            if name and "." in name:
                return name

    segments = [s for s in unquote(parsed.path).split("/") if s]
    # Skip generic endpoint names like /download or /get when a more specific segment precedes them
    for seg in reversed(segments):
        name = sanitize_filename(seg)
        if name and "." in name:
            return name
    return sanitize_filename(segments[-1]) if segments else ""


def extension_for_content_type(content_type: str) -> str:
    mime = (content_type or "").split(";")[0].strip().lower()
    if not mime:
        return ""
    if mime in PREFERRED_EXTENSIONS:
        return PREFERRED_EXTENSIONS[mime]
    return mimetypes.guess_extension(mime) or ""


def unique_path(path: str) -> str:
    """Returns `path`, or `name (1).ext`, `name (2).ext`, ... if it or its part file already exists."""
    def _in_use(p: str) -> bool:
        return os.path.exists(p) or os.path.exists(f"{p}.veloce.part")

    if not _in_use(path):
        return path
    root, ext = os.path.splitext(path)
    n = 1
    while _in_use(f"{root} ({n}){ext}"):
        n += 1
    return f"{root} ({n}){ext}"


class Segment:
    def __init__(self, segment_id: int, start: int, end: int, current: int = None):
        self.segment_id = segment_id
        self.start = start
        self.end = end
        self.current = current if current is not None else start
        self.completed = False
        self.active = False
        self.failures = 0
        self.error: Optional[str] = None
        # Per-assignment throughput tracking (used for ETA-aware stealing and slow-connection shedding)
        self.assigned_at = 0.0
        self.assigned_from = self.current
        self.shed = False
        self.shed_count = 0

    def begin_assignment(self):
        self.active = True
        self.shed = False
        self.assigned_at = time.monotonic()
        self.assigned_from = self.current

    def rate(self, now: float) -> float:
        """Bytes/s achieved by the connection currently working this segment (0 if just assigned)."""
        elapsed = now - self.assigned_at
        if not self.active or elapsed < 0.3:
            return 0.0
        return (self.current - self.assigned_from) / elapsed

    @property
    def remaining(self) -> int:
        if self.completed:
            return 0
        return max(0, self.end - self.current + 1)

    @property
    def total_bytes(self) -> int:
        return self.end - self.start + 1

    @property
    def downloaded_bytes(self) -> int:
        return max(0, min(self.current - self.start, self.total_bytes))

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
        self.num_connections = max(1, num_connections)
        self.lock = threading.Lock()
        self.segments: List[Segment] = []
        self._next_id = 0
        self._init_static_segments()

    def _init_static_segments(self):
        if self.total_size <= 0:
            self.segments.append(Segment(0, 0, 0))
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
                    seg.begin_assignment()
                    return seg
            return None

    def split_largest_segment(self) -> Optional[Segment]:
        """
        Dynamic Segmentation (work stealing):
        Picks the active segment that will finish *last* (largest remaining / its connection's speed)
        and bisects it. Pure largest-remaining-bytes picking ignores that a slow connection with less
        left can still be the tail that the whole download waits on.
        Segments whose speed isn't measurable yet fall back to remaining bytes.
        """
        with self.lock:
            candidates = [
                s for s in self.segments
                if s.active and not s.completed and s.remaining >= (MIN_SPLIT_SIZE * 2)
            ]
            if not candidates:
                return None

            now = time.monotonic()
            rated = [(s, s.rate(now)) for s in candidates]
            measured = [(s, r) for s, r in rated if r > 0]
            if measured:
                target = max(measured, key=lambda sr: sr[0].remaining / sr[1])[0]
            else:
                target = max(candidates, key=lambda s: s.remaining)
            rem = target.end - target.current + 1
            split_point = target.current + (rem // 2)
            old_end = target.end
            target.end = split_point

            new_seg = Segment(
                segment_id=self._next_id,
                start=split_point + 1,
                end=old_end,
                current=split_point + 1
            )
            new_seg.begin_assignment()
            self._next_id += 1
            self.segments.append(new_seg)
            return new_seg

    def mark_completed(self, segment: Segment):
        with self.lock:
            segment.completed = True
            segment.active = False

    def release(self, segment: Segment):
        with self.lock:
            segment.active = False

    def active_count(self) -> int:
        with self.lock:
            return sum(1 for s in self.segments if s.active)

    def splittable_bytes(self) -> int:
        with self.lock:
            return sum(s.remaining for s in self.segments if not s.completed and s.remaining >= 2 * MIN_SPLIT_SIZE)

    def shed_slow_connections(self) -> int:
        """Flags connections far slower than the best one; their workers drop and re-request the range."""
        with self.lock:
            now = time.monotonic()
            judged = [(s, s.rate(now)) for s in self.segments
                      if s.active and not s.completed and now - s.assigned_at >= SHED_GRACE]
            if len(judged) < 2:
                return 0
            best = max(r for _, r in judged)
            shed = 0
            for s, r in judged:
                if (s.shed_count < SHED_MAX_PER_SEGMENT and r * SHED_RATIO < best
                        and s.remaining > max(r, 1.0) * SHED_MIN_ETA):
                    s.shed = True
                    s.shed_count += 1
                    shed += 1
            return shed

    @classmethod
    def from_segments(cls, total_size: int, segment_dicts: List[dict], num_connections: int = 8) -> "SegmentManager":
        """Restores a SegmentManager from a persisted sidecar segment list."""
        mgr = cls(total_size, num_connections)
        if not segment_dicts:
            return mgr
        with mgr.lock:
            mgr.segments = []
            for i, d in enumerate(segment_dicts):
                seg = Segment(i, int(d["start"]), int(d["end"]), int(d.get("current", d["start"])))
                if seg.current > seg.end:
                    seg.completed = True
                mgr.segments.append(seg)
            mgr._next_id = len(mgr.segments)
        return mgr

    def reset_for_resume(self):
        with self.lock:
            for s in self.segments:
                s.active = False
                s.failures = 0
                s.error = None
                if s.current > s.end:
                    s.completed = True

    def has_pending_work(self) -> bool:
        with self.lock:
            return any(not s.completed for s in self.segments)

    def is_all_completed(self) -> bool:
        with self.lock:
            for s in self.segments:
                if s.current > s.end:
                    s.completed = True
            return all(s.completed for s in self.segments)

    def total_downloaded(self) -> int:
        with self.lock:
            return sum(s.downloaded_bytes for s in self.segments)

    def get_progress_snapshot(self) -> List[dict]:
        with self.lock:
            return [s.to_dict() for s in self.segments]


class _RangeClient:
    """
    One persistent HTTP/1.1 connection per worker, reused across segments (keep-alive), so a worker
    that steals new work doesn't pay a fresh TCP + TLS handshake each time. Falls back to urllib when
    a proxy is configured or the server redirects.
    """

    def __init__(self, task: "DownloadTask"):
        self.task = task
        self.conn: Optional[http.client.HTTPConnection] = None
        self.key = None
        self.use_urllib = bool(urllib.request.getproxies())

    def close(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
        self.conn = None
        self.key = None

    def _connect(self, parsed):
        key = (parsed.scheme, parsed.hostname, parsed.port)
        if self.conn is None or key != self.key:
            self.close()
            cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
            self.conn = cls(parsed.hostname, parsed.port, timeout=15)
            self.key = key
        return self.conn

    def get(self, url: str, headers: dict):
        """Returns a response object with .status, .read(n) and .getheader()."""
        if self.use_urllib:
            return _urlopen(urllib.request.Request(url, headers=headers), timeout=15)

        parsed = urlparse(url)
        path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
        for attempt in (1, 2):
            conn = self._connect(parsed)
            try:
                conn.request("GET", path, headers=headers)
                resp = conn.getresponse()
                break
            except (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError,
                    http.client.CannotSendRequest, http.client.ResponseNotReady):
                # The server closed an idle keep-alive socket; reconnect once.
                self.close()
                if attempt == 2:
                    raise

        if resp.status in REDIRECT_CODES:
            location = resp.getheader("Location")
            resp.read()
            self.close()
            if not location:
                raise IOError(f"HTTP {resp.status} redirect without Location")
            target = urljoin(url, location)
            if urlparse(target).hostname != parsed.hostname:
                headers = {k: v for k, v in headers.items() if k.title() not in SENSITIVE_HEADERS}
            return _urlopen(urllib.request.Request(target, headers=headers), timeout=15)
        if resp.status >= 400:
            resp.read()
            self.close()
            raise urllib.error.HTTPError(url, resp.status, resp.reason, resp.headers, None)
        resp._veloce_pooled = True
        return resp

    def finish(self, resp, fully_read: bool):
        """Keep the socket for the next segment only if this response was consumed to the end."""
        if resp is None:
            return
        if not getattr(resp, "_veloce_pooled", False):
            try:
                resp.close()
            except Exception:
                pass
            return
        if not fully_read or resp.will_close or not resp.isclosed():
            self.close()


class DownloadTask:
    def __init__(
        self,
        url: str,
        output_path: str,
        num_connections: int = 16,
        headers: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[dict], None]] = None,
        suggested_filename: Optional[str] = None,
        adaptive: bool = True,
        sidecar_data: Optional[dict] = None,
    ):
        # adaptive=True: start with a few connections, ramp up while it helps, shed slow sockets.
        # adaptive=False: open all `num_connections` immediately (classic fixed-N behaviour).
        self.adaptive = adaptive
        self.url = url
        self.source_url = url
        self.output_path = output_path
        self.num_connections = max(1, min(int(num_connections), MAX_CONNECTIONS))
        self.headers = headers or {}
        self.progress_callback = progress_callback
        # A name the caller already knows (e.g. Chrome's own determined filename) wins over guessing
        self.suggested_filename = sanitize_filename(suggested_filename or "")

        self.total_size = 0
        self.resumable = False
        self.content_type = ""
        self.etag = ""
        self.last_modified = ""
        self.created_at = time.time()
        self.filename = "" if os.path.isdir(output_path) else os.path.basename(output_path)
        self.status = "QUEUED"
        self.error_message: Optional[str] = None

        self.manager: Optional[SegmentManager] = None
        self._stop_event = threading.Event()
        self._fd: Optional[int] = None
        self._single_stream_bytes = 0
        self._inspected = False
        self._running = False
        self._primed = None  # open probe response, reused as the first data stream
        self.ttfb = 0.3      # measured time-to-first-byte of the probe (seconds)
        self._primed_lock = threading.Lock()
        self._sidecar_lock = threading.Lock()
        self._last_sidecar_save = 0.0
        self._pending_sidecar = sidecar_data

        self.start_time = 0.0
        self.last_bytes = 0
        self.last_time = 0.0
        self.current_speed = 0.0

    @property
    def part_path(self) -> str:
        return f"{self.output_path}.veloce.part"

    @property
    def sidecar_path(self) -> str:
        return f"{self.output_path}.veloce.json"

    # ------------------------------------------------------------------ probing

    def _resolve_headers(self) -> dict:
        default_headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Connection": "keep-alive",
        }
        default_headers.update(self.headers)
        return default_headers

    def _probe(self, ranged: bool):
        """
        Opens the download itself as the probe: `Range: bytes=0-` (open-ended). The response is kept open
        ("primed") so the first worker, or the single-stream path, continues reading it instead of paying
        another round trip and TLS handshake. On fast/near servers that round trip is a big share of the total.
        """
        headers = self._resolve_headers()
        if ranged:
            headers["Range"] = "bytes=0-"
        return _urlopen(urllib.request.Request(self.url, headers=headers), timeout=12)

    def _take_primed(self, seg: Optional["Segment"] = None):
        """Hands over the probe's open response if it starts exactly where `seg` needs data."""
        with self._primed_lock:
            resp = self._primed
            if resp is None or (seg is not None and (seg.current != 0 or resp.status != 206)):
                return None
            self._primed = None
            return resp

    def release_probe(self):
        """Closes the probe response if nobody consumed it (e.g. inspect-only calls)."""
        resp = self._take_primed()
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass

    def inspect_url(self):
        """Probes the remote server for final URL, total size, content type, filename, and real Range support."""
        resp = None
        t0 = time.monotonic()
        try:
            resp = self._probe(ranged=True)
        except Exception as e:
            # Some servers reject Range requests outright (403/405/416); fall back to a plain GET.
            logger.debug(f"Ranged probe failed ({e}); retrying without Range")
            try:
                resp = self._probe(ranged=False)
            except Exception as e2:
                logger.debug(f"Plain probe failed: {e2}")

        cd_name = ""
        if resp is not None:
            status, final_url, headers = resp.status, resp.geturl(), resp.headers
            self.ttfb = time.monotonic() - t0
            with self._primed_lock:
                self._primed = resp
            # Cache final resolved URL after redirects (e.g. AWS S3 signed URL). If that moved us to another
            # host, the browser's cookies for the original site must not be sent there.
            if urlparse(final_url).hostname != urlparse(self.url).hostname:
                self.headers = {k: v for k, v in self.headers.items() if k.title() not in SENSITIVE_HEADERS}
            self.url = final_url
            self.content_type = headers.get("Content-Type", "")
            self.etag = headers.get("ETag", "").strip()
            self.last_modified = headers.get("Last-Modified", "").strip()

            # Only a 206 with a Content-Range proves the server honors ranges.
            # "200 + Accept-Ranges: bytes" is not enough: many servers advertise it and ignore Range.
            cr = headers.get("Content-Range", "")
            total = cr.rsplit("/", 1)[-1].strip() if "/" in cr else ""
            if status == 206 and total.isdigit():
                self.total_size = int(total)
                self.resumable = True
            elif status == 200:
                cl = headers.get("Content-Length", "")
                if cl.isdigit():
                    self.total_size = int(cl)
            cd_name = parse_content_disposition(headers.get("Content-Disposition", ""))

        self.filename = self._choose_filename(cd_name)

        if os.path.isdir(self.output_path) or self.output_path.endswith(("/", "\\")):
            os.makedirs(self.output_path, exist_ok=True)
            # Never clobber an existing file when we chose the name ourselves
            self.output_path = unique_path(os.path.join(self.output_path, self.filename))
        self._inspected = True

        if self._pending_sidecar:
            exp_etag = (self._pending_sidecar.get("etag") or "").strip()
            exp_mtime = (self._pending_sidecar.get("last_modified") or "").strip()
            exp_size = self._pending_sidecar.get("total_size") or 0

            mismatch = None
            if exp_etag and self.etag and exp_etag != self.etag:
                mismatch = f"ETag changed from {exp_etag} to {self.etag}"
            elif exp_mtime and self.last_modified and exp_mtime != self.last_modified:
                mismatch = f"Last-Modified changed from {exp_mtime} to {self.last_modified}"
            elif exp_size > 0 and self.total_size > 0 and exp_size != self.total_size:
                mismatch = f"total_size changed from {exp_size} to {self.total_size}"

            if mismatch:
                logger.info(f"Server changed file for {self.output_path} ({mismatch}); discarding .part and starting fresh")
                self._remove_partial()
                self._pending_sidecar = None
                self.manager = None
            else:
                logger.info(f"Resuming {self.output_path} from sidecar")
                self.manager = SegmentManager.from_segments(
                    self.total_size,
                    self._pending_sidecar.get("segments", []),
                    num_connections=self.num_connections,
                )
                self._pending_sidecar = None

    def _choose_filename(self, content_disposition_name: str) -> str:
        name = (
            self.filename                           # explicit output file path given by the caller
            or self.suggested_filename
            or content_disposition_name
            or filename_from_url(self.url)          # final URL after redirects
            or filename_from_url(self.source_url)   # what the user pasted
        )
        ext = extension_for_content_type(self.content_type)
        if not name:
            host = urlparse(self.source_url).hostname or "download"
            name = f"{host.replace('.', '_')}_{time.strftime('%Y%m%d_%H%M%S')}"
        if ext and not os.path.splitext(name)[1]:
            name += ext
        return name

    # ------------------------------------------------------------------ transfer

    def _fail(self, message: str):
        if self.status not in TERMINAL_STATUSES:
            self.error_message = message
            self.status = "ERROR"
        self._stop_event.set()
        self._save_sidecar()

    def _worker_loop(self):
        client = _RangeClient(self)
        try:
            while not self._stop_event.is_set():
                seg = self.manager.get_idle_segment() or self.manager.split_largest_segment()
                if not seg:
                    if not self.manager.has_pending_work():
                        break
                    # Remaining work is held by another worker and too small to split; stay available
                    # in case that worker fails and releases its segment.
                    time.sleep(0.2)
                    continue

                try:
                    outcome = self._download_segment(seg, client)
                except RangeNotSupported as e:
                    self.manager.release(seg)
                    self._fail(str(e))
                    return

                if outcome == "done":
                    self.manager.mark_completed(seg)
                    continue
                if outcome == "shed":
                    # Too slow: drop this socket and let the range be re-requested on a fresh one.
                    client.close()
                    self.manager.release(seg)
                    continue

                seg.failures += 1
                self.manager.release(seg)
                if seg.failures >= MAX_SEGMENT_RETRIES:
                    self._fail(seg.error or "The connection kept failing")
                    return
                time.sleep(min(0.5 * (2 ** (seg.failures - 1)), 5.0))
        finally:
            client.close()

    def _download_segment(self, seg: Segment, client: "_RangeClient") -> str:
        """Returns "done", "shed" (dropped for being slow), or "failed"."""
        headers = self._resolve_headers()
        headers["Range"] = f"bytes={seg.current}-{seg.end}"
        if self.etag:
            headers["If-Range"] = self.etag

        resp = None
        fully_read = False
        try:
            resp = self._take_primed(seg) or client.get(self.url, headers)
            if resp.status != 206:
                raise RangeNotSupported(
                    f"Server ignored a Range request (HTTP {resp.status}); stopped to avoid a corrupt file"
                )
            while not self._stop_event.is_set():
                if seg.shed:
                    return "shed"
                with self.manager.lock:
                    max_to_read = min(CHUNK_BUFFER_SIZE, seg.end - seg.current + 1)
                if max_to_read <= 0:
                    break

                data = resp.read(max_to_read)
                if not data:
                    break

                _pwrite(self._fd, data, seg.current)
                with self.manager.lock:
                    seg.current += len(data)
                    seg.failures = 0

            done = seg.current > seg.end
            # Reusable only if the server sent exactly what we asked for (segment not shrunk by a split)
            fully_read = done and resp.read(1) == b""
            return "done" if done else "failed"
        except RangeNotSupported:
            raise
        except Exception as e:
            logger.debug(f"Segment {seg.segment_id} read error: {e}")
            seg.error = friendly_error(e)
            return "failed"
        finally:
            client.finish(resp, fully_read)

    def _download_single_stream(self):
        self._single_stream_bytes = 0
        # Reuse the probe's response when it streams the whole body from byte 0 (200, or an open-ended 206)
        resp = self._take_primed()
        if resp is None:
            resp = _urlopen(urllib.request.Request(self.url, headers=self._resolve_headers()), timeout=20)
        last_report = 0.0
        with resp:
            with open(self.part_path, "wb") as f:
                while not self._stop_event.is_set():
                    data = resp.read(CHUNK_BUFFER_SIZE)
                    if not data:
                        break
                    f.write(data)
                    self._single_stream_bytes += len(data)
                    now = time.time()
                    if now - last_report >= 0.3:
                        last_report = now
                        self._update_speed()
                        self._report_progress()
                    if now - self._last_sidecar_save >= 2.0:
                        self._save_sidecar()

        if self.total_size > 0 and self._single_stream_bytes < self.total_size and not self._stop_event.is_set():
            raise IOError(
                f"Connection closed early: received {self._single_stream_bytes} of {self.total_size} bytes"
            )

    def _downloaded(self) -> int:
        if self.manager is not None:
            return self.manager.total_downloaded()
        return self._single_stream_bytes

    def start(self):
        """Runs (or resumes) the transfer in the calling thread. Raises on failure; status is updated either way."""
        self._running = True
        try:
            self._run()
        except Exception as e:
            self._fail(friendly_error(e))
            self._report_progress()
            raise
        finally:
            self._running = False
            self.release_probe()
            # Deferred until the fd is closed: Windows cannot delete an open file.
            if self.status == "CANCELLED":
                self._remove_partial()

    def _run(self):
        if not self._inspected:
            self.status = "INITIALIZING"
            self._report_progress()
            self.inspect_url()
        if self._stop_event.is_set():
            self._report_progress()
            return

        self.status = "DOWNLOADING"
        self.start_time = time.time()
        self.last_time = self.start_time
        self.last_bytes = self._downloaded()
        self.current_speed = 0.0

        out_dir = os.path.dirname(os.path.abspath(self.output_path))
        os.makedirs(out_dir, exist_ok=True)

        if not self.resumable or self.total_size <= 0:
            self._download_single_stream()
            if not self._stop_event.is_set():
                if self.total_size <= 0 or self._single_stream_bytes == self.total_size:
                    os.replace(self.part_path, self.output_path)
                    self._delete_sidecar()
                    self.status = "COMPLETED"
                else:
                    self.status = "ERROR"
            self._report_progress()
            return

        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
        self._fd = os.open(self.part_path, flags, 0o644)
        if self.manager is None:
            # Pre-allocate disk space to avoid filesystem fragmentation
            try:
                os.posix_fallocate(self._fd, 0, self.total_size)
            except (AttributeError, OSError):
                os.ftruncate(self._fd, self.total_size)
            # Adaptive mode starts as ONE segment streamed over the probe connection; extra connections
            # join later by work-stealing (splitting) it. Fixed mode pre-cuts N static segments.
            self.manager = SegmentManager(self.total_size, 1 if self.adaptive else self.num_connections)
            fresh = True
        else:
            self.manager.reset_for_resume()
            fresh = False

        threads: List[threading.Thread] = []

        def spawn(count: int):
            for _ in range(max(0, min(count, self.num_connections - len(threads)))):
                t = threading.Thread(target=self._worker_loop, daemon=True)
                t.start()
                threads.append(t)

        started = time.monotonic()
        if self.adaptive and fresh:
            spawn(1)
            fanned_out = False
        else:
            pending_segments = sum(1 for s in self.manager.segments if not s.completed)
            spawn(max(self._initial_connections(), min(pending_segments, self.num_connections)))
            fanned_out = True

        ramping = self.adaptive and len(threads) < self.num_connections
        window_start, window_bytes = time.monotonic(), self._downloaded()
        last_window_speed = 0.0
        ramp_misses = 0
        last_report = 0.0

        try:
            while not self._stop_event.is_set():
                # Short tick so completion is noticed promptly (matters for sub-second downloads);
                # progress is still reported at a calmer pace.
                time.sleep(0.05)
                if self.manager.is_all_completed():
                    break
                now = time.monotonic()
                if now - last_report >= 0.3:
                    last_report = now
                    self._update_speed()
                    self._report_progress()

                now_wall = time.time()
                if now_wall - self._last_sidecar_save >= 2.0:
                    self._save_sidecar()

                if not fanned_out:
                    if now - started < FANOUT_DELAY:
                        continue
                    fanned_out = True
                    done = self._downloaded()
                    speed = done / max(now - started, 1e-3)
                    remaining = self.total_size - done
                    eta = remaining / speed if speed > 0 else float("inf")
                    if eta < SINGLE_STREAM_ETA:
                        ramping = False  # one stream finishes this quickly; extra handshakes would only slow it
                    else:
                        # Long transfers fan out wider straight away; short ones gently
                        target = 8 if eta > 4 else INITIAL_CONNECTIONS
                        spawn(min(target, self._initial_connections()) - 1)
                    window_start, window_bytes = now, done
                    continue

                # New connections need ~TTFB before they deliver anything; judge them after that.
                if now - window_start < max(RAMP_INTERVAL, 2.5 * self.ttfb):
                    continue
                window_speed = (self._downloaded() - window_bytes) / (now - window_start)
                window_start, window_bytes = now, self._downloaded()

                if self.adaptive:
                    self.manager.shed_slow_connections()

                if ramping:
                    has_room = self.manager.splittable_bytes() >= 4 * MIN_SPLIT_SIZE
                    if not has_room or len(threads) >= self.num_connections:
                        ramping = False
                    elif last_window_speed == 0.0 or window_speed >= last_window_speed * RAMP_MIN_GAIN:
                        last_window_speed = max(last_window_speed, window_speed)
                        ramp_misses = 0
                        spawn(RAMP_STEP)
                    else:
                        # Throughput is noisy: only conclude "more sockets stopped helping"
                        # (server cap, CDN edge, or the local link) after two flat windows in a row.
                        ramp_misses += 1
                        if ramp_misses >= 2:
                            ramping = False
                            logger.debug(f"Ramp settled at {len(threads)} connections")
        finally:
            # Stop workers and wait for them *before* closing the fd: a worker still inside
            # pwrite() after close() could write into an unrelated file that reused the fd number.
            self._stop_event.set()
            for t in threads:
                t.join()
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            self.release_probe()
            self._report_progress()
            if self.status in ("PAUSED", "ERROR"):
                self._save_sidecar()

        if self.manager.is_all_completed() and self._downloaded() == self.total_size:
            os.replace(self.part_path, self.output_path)
            self._delete_sidecar()
            self.status = "COMPLETED"
            self._report_progress()
        elif not self._stop_event.is_set() and self.status not in TERMINAL_STATUSES:
            self._fail(f"Download incomplete: segment byte count ({self._downloaded()}) does not match total size ({self.total_size})")

        if self.status == "ERROR":
            raise IOError(self.error_message or "Download failed")

    def _initial_connections(self) -> int:
        if not self.adaptive:
            return self.num_connections
        by_size = max(1, self.total_size // BYTES_PER_INITIAL_CONNECTION)
        return int(max(1, min(self.num_connections, INITIAL_CONNECTIONS, by_size)))

    def _update_speed(self):
        now = time.time()
        dt = now - self.last_time
        if dt >= 0.5:
            current_bytes = self._downloaded()
            instant = (current_bytes - self.last_bytes) / dt
            # Light smoothing so the UI number doesn't jitter
            self.current_speed = instant if self.current_speed == 0 else 0.6 * instant + 0.4 * self.current_speed
            self.last_time = now
            self.last_bytes = current_bytes

    def _report_progress(self):
        if not self.progress_callback:
            return

        downloaded = self._downloaded()
        percent = (downloaded / self.total_size * 100.0) if self.total_size > 0 else 0.0
        if self.status == "COMPLETED":
            percent = 100.0
        running = self.status == "DOWNLOADING"

        eta = 0.0
        if running and self.current_speed > 0 and self.total_size > downloaded:
            eta = (self.total_size - downloaded) / self.current_speed

        self.progress_callback({
            "status": self.status,
            # After inspection, report the name actually on disk (it may be "name (1).ext")
            "filename": os.path.basename(self.output_path) if self._inspected else self.filename,
            "output_path": self.output_path,
            "content_type": self.content_type,
            "resumable": self.resumable,
            "total_size": self.total_size,
            "downloaded": downloaded,
            "percent": round(min(percent, 100.0), 2),
            "speed": self.current_speed if running else 0.0,
            "eta": round(eta, 1),
            "error": self.error_message,
            "connections": self.num_connections,
            "segments": self.manager.get_progress_snapshot() if self.manager else [],
        })

    # ------------------------------------------------------------------ control

    def can_resume(self) -> bool:
        return not self._running and self.status in ("PAUSED", "ERROR")

    def prepare_resume(self) -> bool:
        """Arms a paused/failed task to run again; the caller then invokes start() on a thread."""
        if not self.can_resume():
            return False
        self._stop_event = threading.Event()
        self.error_message = None
        self.status = "QUEUED"
        return True

    def pause(self):
        """Stops the transfer and keeps the partial file so it can be resumed."""
        if self.status not in TERMINAL_STATUSES:
            self.status = "PAUSED"
        self._stop_event.set()
        self._save_sidecar()

    def cancel(self):
        """Stops the transfer and deletes the partial and sidecar files."""
        if self.status == "COMPLETED":
            return
        self.status = "CANCELLED"
        self._stop_event.set()
        if not self._running:
            self._remove_partial()

    def _remove_partial(self):
        self._delete_sidecar()
        if os.path.isfile(self.part_path):
            try:
                os.remove(self.part_path)
            except OSError:
                pass

    def _save_sidecar(self):
        """Atomically persists download progress to <final>.veloce.json."""
        if not self._inspected or not self.output_path or not self.resumable or self.total_size <= 0:
            return
        with self._sidecar_lock:
            try:
                segments_data = []
                if self.manager is not None:
                    with self.manager.lock:
                        segments_data = [
                            {"start": s.start, "end": s.end, "current": s.current}
                            for s in self.manager.segments
                        ]
                data = {
                    "version": 1,
                    "source_url": self.source_url,
                    "final_url": self.url,
                    "total_size": self.total_size,
                    "etag": self.etag,
                    "last_modified": self.last_modified,
                    "content_type": self.content_type,
                    "created_at": self.created_at,
                    "segments": segments_data,
                }
                out_dir = os.path.dirname(os.path.abspath(self.sidecar_path))
                os.makedirs(out_dir, exist_ok=True)
                tmp_path = f"{self.sidecar_path}.tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                os.replace(tmp_path, self.sidecar_path)
                self._last_sidecar_save = time.time()
            except Exception as e:
                logger.debug(f"Failed to write sidecar for {self.output_path}: {e}")

    def _delete_sidecar(self):
        with self._sidecar_lock:
            for p in (self.sidecar_path, f"{self.sidecar_path}.tmp"):
                if os.path.isfile(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
