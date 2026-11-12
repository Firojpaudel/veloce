"""
Home-network streaming: play and download files from the Veloce downloads folder on other devices.

Safety model
  * Off on every start. Only an explicit switch in the dashboard turns it on; nothing is persisted.
  * Separate, read-only server (GET/HEAD only). The main engine API stays bound to 127.0.0.1.
  * Exposes exactly one folder: the Veloce downloads folder. Every path is resolved (symlinks too) and must
    stay inside it; hidden files, unfinished downloads and temp folders are never listed or served.
  * Each time sharing turns on, a new access code is made. A device enters it once and gets its own session;
    turning sharing off (or making a new code) ends every session. After 5 wrong codes a device must wait,
    longer after each further miss: 1 min, 5 min, 15 min, then 1 hour.
  * Files that a browser could execute (HTML, SVG, XML…) are only ever offered as downloads, never rendered.
"""

import ipaddress
import json
import logging
import mimetypes
import os
import re
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

logger = logging.getLogger("VeloceShare")

PORTS = range(9230, 9240)
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I to misread
CODE_LENGTH = 6
FREE_TRIES = 5
LOCKOUTS = (60, 300, 900, 3600)  # like a phone: each wrong code past the free tries waits longer
UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")

HIDDEN_SUFFIXES = (".part", ".ytdl", ".tmp", ".crdownload", ".download", ".veloce.part", ".veloce.json")
VIDEO = {".mp4", ".m4v", ".webm", ".mov", ".mkv"}
AUDIO = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".oga", ".wav", ".flac", ".weba"}
IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp"}
CAPTIONS = {".srt", ".vtt"}
# Shown in the browser; anything else is sent as a download
INLINE_TYPES = {"application/pdf", "text/plain", "text/vtt"}
EXTRA_TYPES = {".mkv": "video/x-matroska", ".m4a": "audio/mp4", ".opus": "audio/ogg", ".weba": "audio/webm",
               ".vtt": "text/vtt", ".srt": "text/plain", ".flac": "audio/flac", ".avif": "image/avif"}


_lan = {"addr": "", "at": 0.0}


def lan_address() -> str:
    """This machine's address on the home network. No packets are sent and no DNS lookups are made
    (resolving the hostname can stall for seconds on some Macs); cached for 30 s."""
    if time.time() - _lan["at"] < 30 and _lan["addr"]:
        return _lan["addr"]
    addr = "127.0.0.1"
    for probe in ("10.255.255.255", "192.168.255.255", "8.8.8.8"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((probe, 1))  # UDP connect only picks a route; nothing is sent
                found = s.getsockname()[0]
            if found and not found.startswith("0."):
                addr = found
                break
        except OSError:
            continue
    _lan.update(addr=addr, at=time.time())
    return addr


def kind_of(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    return "video" if ext in VIDEO else "audio" if ext in AUDIO else "image" if ext in IMAGE else "file"


ACTIVE_FOR = 600   # a device counts as connected while it was seen in the last 10 minutes
PLAYING_FOR = 90   # and as watching/listening while it fetched part of a file in the last 90 s


def describe_device(user_agent: str) -> dict:
    """A readable name for a browser's device, e.g. {"name": "iPhone", "browser": "Safari", "kind": "phone"}."""
    ua = user_agent or ""
    if "iPhone" in ua or "iPod" in ua:
        name, kind = "iPhone", "phone"
    elif "iPad" in ua or ("Macintosh" in ua and "Mobile" in ua):
        name, kind = "iPad", "tablet"
    elif "Android" in ua:
        name, kind = ("Android phone", "phone") if "Mobile" in ua else ("Android tablet", "tablet")
    elif "CrOS" in ua:
        name, kind = "Chromebook", "laptop"
    elif "Windows" in ua:
        name, kind = "Windows PC", "laptop"
    elif "Macintosh" in ua or "Mac OS X" in ua:
        name, kind = "Mac", "laptop"
    elif "Linux" in ua:
        name, kind = "Linux PC", "laptop"
    elif any(t in ua for t in ("SMART-TV", "SmartTV", "Tizen", "Web0S", "BRAVIA")):
        name, kind = "Smart TV", "tv"
    else:
        name, kind = "Device", "laptop"
    browser = next((b for key, b in (("Edg/", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser", "Samsung Internet"),
                                     ("Firefox/", "Firefox"), ("FxiOS", "Firefox"), ("CriOS", "Chrome"),
                                     ("Chrome/", "Chrome"), ("Safari/", "Safari")) if key in ua), "Browser")
    return {"name": name, "browser": browser, "kind": kind}


def srt_to_vtt(text: str) -> str:
    body = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", text.replace("\r\n", "\n").lstrip("﻿"))
    return "WEBVTT\n\n" + body


class Share:
    def __init__(self, root: str):
        self.root = os.path.realpath(root)
        self._lock = threading.Lock()
        self._server: Optional[ThreadingHTTPServer] = None
        self.code = ""
        self.sessions: dict = {}  # token -> device info (see _session_info)
        self.fails: dict = {}     # ip -> (count, locked_until)

    # ------------------------------------------------------------------ control
    def start(self) -> dict:
        with self._lock:
            if self._server:
                return self.status()
            os.makedirs(self.root, exist_ok=True)
            handler = type("ShareHandler", (_Handler,), {"share": self})
            bind_addr = lan_address()
            last = None
            server = None
            # Bind to detected LAN address first; fall back to 0.0.0.0 if binding fails or no LAN route exists
            if bind_addr and bind_addr not in ("0.0.0.0", "127.0.0.1"):
                for port in PORTS:
                    try:
                        server = ThreadingHTTPServer((bind_addr, port), handler)
                        break
                    except OSError as e:
                        last = e
            if server is None:
                for port in PORTS:
                    try:
                        server = ThreadingHTTPServer(("0.0.0.0", port), handler)
                        break
                    except OSError as e:
                        last = e
                else:
                    raise OSError(f"No free port for sharing ({last})")
            server.daemon_threads = True
            self._new_code()
            self._server = server
            threading.Thread(target=server.serve_forever, name="share", daemon=True).start()
            logger.info(f"Sharing {self.root} on the home network at port {port}")
            return self.status()

    def _new_code(self):
        self.code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        self.sessions, self.fails = {}, {}

    def new_code(self) -> dict:
        """Fresh code (e.g. it was seen by someone): every connected device has to enter the new one."""
        with self._lock:
            if self._server:
                self._new_code()
        return self.status()

    def stop(self) -> dict:
        with self._lock:
            server, self._server = self._server, None
            self.code, self.sessions = "", {}
        if server:
            server.shutdown()
            server.server_close()
            logger.info("Home-network sharing turned off")
        return self.status()

    def status(self) -> dict:
        server = self._server
        if not server:
            return {"enabled": False}
        port = server.server_address[1]
        address = lan_address()
        now = time.time()
        return {
            "enabled": True,
            "url": f"http://{address}:{port}/",
            "link": f"http://{address}:{port}/?code={self.code}",
            "code": self.code,
            "folder": self.root,
            "devices": self.devices(now),
        }

    def devices(self, now: Optional[float] = None) -> list:
        """Connected devices, most recently active first."""
        now = now or time.time()
        out = []
        for info in list(self.sessions.values()):
            if now - info["seen"] > ACTIVE_FOR:
                continue
            playing = info.get("playing")
            out.append({
                "id": info["id"], "name": info["name"], "browser": info["browser"], "kind": info["kind"],
                "ip": info["ip"], "connected_at": info["connected"], "last_seen": info["seen"],
                "bytes": info["bytes"],
                "playing": {"name": playing["name"], "kind": playing["kind"]}
                if playing and now - playing["at"] < PLAYING_FOR else None,
            })
        out.sort(key=lambda d: -d["last_seen"])
        return out

    def disconnect(self, device_id: str) -> dict:
        """Signs one device out; it needs the code again to come back."""
        with self._lock:
            for token, info in list(self.sessions.items()):
                if info["id"] == device_id:
                    del self.sessions[token]
        return self.status()

    # ------------------------------------------------------------------ access
    def check_code(self, ip: str, code: str, user_agent: str = "") -> Optional[str]:
        """A new session token when the code is right; None otherwise (and counts the failure)."""
        now = time.time()
        count, until = self.fails.get(ip, (0, 0))
        if until > now:
            return None
        if self.code and secrets.compare_digest(code.strip().upper().encode(), self.code.encode()):
            self.fails.pop(ip, None)
            token = secrets.token_urlsafe(32)
            self.sessions[token] = {"id": secrets.token_hex(6), "ip": ip, "connected": now, "seen": now,
                                    "bytes": 0, "playing": None, **describe_device(user_agent)}
            return token
        count += 1
        wait = LOCKOUTS[min(count - FREE_TRIES, len(LOCKOUTS)) - 1] if count > FREE_TRIES else 0
        self.fails[ip] = (count, now + wait)
        return None

    def wait_left(self, ip: str) -> int:
        """Seconds this device must wait before trying another code."""
        return max(0, int(self.fails.get(ip, (0, 0))[1] - time.time() + 0.999))

    def tries_left(self, ip: str) -> int:
        return max(0, FREE_TRIES - self.fails.get(ip, (0, 0))[0])

    # ------------------------------------------------------------------ files
    def resolve(self, rel: str) -> Optional[str]:
        """Absolute path for a URL path inside the shared folder, or None when it must not be served."""
        parts = [p for p in rel.replace("\\", "/").split("/") if p]
        if any(p.startswith(".") or p.endswith(HIDDEN_SUFFIXES) for p in parts):
            return None
        path = os.path.realpath(os.path.join(self.root, *parts))
        try:
            if os.path.commonpath([path, self.root]) != self.root:
                return None
        except ValueError:  # different drives on Windows
            return None
        return path if os.path.exists(path) else None

    def listing(self, folder: str) -> list:
        entries = []
        try:
            names = os.listdir(folder)
        except OSError:
            return entries
        video_stems = {os.path.splitext(n)[0] for n in names if os.path.splitext(n)[1].lower() in VIDEO}
        for name in names:
            if name.startswith(".") or name.endswith(HIDDEN_SUFFIXES):
                continue
            full = os.path.join(folder, name)
            if self.resolve(os.path.relpath(full, self.root)) is None:
                continue  # e.g. a link that points outside the folder
            try:
                st = os.stat(full)
            except OSError:
                continue
            rel = os.path.relpath(full, self.root).replace(os.sep, "/")
            if os.path.isdir(full):
                entries.append({"name": name, "path": rel, "type": "folder", "mtime": st.st_mtime})
                continue
            kind = kind_of(name)
            base, ext = os.path.splitext(name)
            if ext.lower() in CAPTIONS and any(base == s or base.startswith(s + ".") for s in video_stems):
                continue  # captions are attached to their video instead of listed
            entry = {"name": name, "path": rel, "type": "file", "kind": kind, "size": st.st_size, "mtime": st.st_mtime}
            if kind == "video":
                entry["captions"] = self._captions_for(folder, name, names)
            entries.append(entry)
        entries.sort(key=lambda e: (e["type"] != "folder", -e["mtime"]))
        return entries

    def _captions_for(self, folder: str, video: str, names: list) -> list:
        stem = os.path.splitext(video)[0]
        found = []
        for n in names:
            base, ext = os.path.splitext(n)
            if ext.lower() not in CAPTIONS or not (base == stem or base.startswith(stem + ".")):
                continue
            lang = base[len(stem) + 1:] if base != stem else ""
            rel = os.path.relpath(os.path.join(folder, n), self.root).replace(os.sep, "/")
            found.append({"label": lang or "Default", "lang": lang.split("-")[0] or "en", "url": "/vtt/" + quote(rel),
                          "default": base == stem})
        found.sort(key=lambda c: not c["default"])
        return found


def _duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = (seconds + 59) // 60
    return f"{minutes} minute{'s' if minutes != 1 else ''}" if minutes < 60 else "1 hour"


class _Handler(BaseHTTPRequestHandler):
    share: Share
    server_version = "Veloce"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        logger.debug("%s - %s", self.client_address[0], fmt % args)

    # ------------------------------------------------------------------ helpers
    def _host_ok(self) -> bool:
        """Only direct addresses or this computer's own name (blocks DNS-rebinding pages)."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            name = socket.gethostname().lower()
            return host in ("localhost", name, name + ".local")

    def _headers(self, status: int, ctype: str, length: int, extra: Optional[dict] = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _send(self, status: int, body: bytes, ctype: str, extra: Optional[dict] = None):
        self._headers(status, ctype, len(body), extra)
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, data):
        self._send(status, json.dumps(data).encode(), "application/json")

    def _session(self) -> Optional[dict]:
        cookie = self.headers.get("Cookie") or ""
        m = re.search(r"(?:^|;\s*)veloce_share=([\w-]+)", cookie)
        return self.share.sessions.get(m.group(1)) if m else None

    # ------------------------------------------------------------------ routes
    def do_POST(self):
        self._send(405, b"Read-only", "text/plain")

    do_PUT = do_DELETE = do_PATCH = do_POST

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._host_ok():
            return self._send(421, b"Use this computer's network address", "text/plain")
        ip = self.client_address[0]
        url = urlparse(self.path)
        path = unquote(url.path)
        query = parse_qs(url.query)

        if path in ("/", "/index.html"):
            code = (query.get("code") or [""])[0]
            if code:  # link with the code: start a session, then drop the code from the address bar
                token = self.share.check_code(ip, code, self.headers.get("User-Agent", ""))
                extra = {"Location": "/"}
                if token:
                    extra["Set-Cookie"] = f"veloce_share={token}; HttpOnly; SameSite=Strict; Path=/"
                return self._send(303, b"", "text/plain", extra)
            return self._static("share.html", "text/html; charset=utf-8", {
                "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                                           "img-src 'self' data:; media-src 'self'; frame-ancestors 'none'"})
        if path == "/logo.png":
            return self._static("logo.png", "image/png")
        if path == "/auth":
            wait = self.share.wait_left(ip)
            if wait:
                return self._json(429, {"error": f"Too many wrong codes. Try again in {_duration(wait)}.", "wait": wait})
            token = self.share.check_code(ip, (query.get("code") or [""])[0], self.headers.get("User-Agent", ""))
            if not token:
                wait, left = self.share.wait_left(ip), self.share.tries_left(ip)
                msg = (f"That code isn't right. Try again in {_duration(wait)}." if wait else
                       f"That code isn't right. {left} more tr{'y' if left == 1 else 'ies'} before a wait." if left <= 2 else
                       "That code isn't right")
                return self._json(429 if wait else 401, {"error": msg, "wait": wait})
            body = json.dumps({"ok": True}).encode()
            return self._send(200, body, "application/json",
                              {"Set-Cookie": f"veloce_share={token}; HttpOnly; SameSite=Strict; Path=/"})

        device = self._session()
        if not device:
            return self._json(401, {"error": "Enter the access code shown in Veloce"})
        device["seen"], device["ip"] = time.time(), ip

        if path == "/api/list":
            rel = (query.get("path") or [""])[0]
            folder = self.share.resolve(rel)
            if not folder or not os.path.isdir(folder):
                return self._json(404, {"error": "Folder not found"})
            return self._json(200, {"path": "" if folder == self.share.root else
                                    os.path.relpath(folder, self.share.root).replace(os.sep, "/"),
                                    "entries": self.share.listing(folder)})
        if path.startswith("/vtt/"):
            full = self.share.resolve(path[len("/vtt/"):])
            if not full or not os.path.isfile(full) or os.path.splitext(full)[1].lower() not in CAPTIONS:
                return self._json(404, {"error": "Not found"})
            with open(full, encoding="utf-8", errors="replace") as f:
                text = f.read(4 * 1024 * 1024)
            body = (text if full.lower().endswith(".vtt") else srt_to_vtt(text)).encode()
            return self._send(200, body, "text/vtt; charset=utf-8")
        if path.startswith("/f/"):
            full = self.share.resolve(path[len("/f/"):])
            if not full or not os.path.isfile(full):
                return self._json(404, {"error": "Not found"})
            device["playing"] = {"name": os.path.basename(full), "kind": kind_of(full), "at": time.time()}
            return self._file(full, download="download" in query, device=device)
        self._json(404, {"error": "Not found"})

    def _static(self, name: str, ctype: str, extra: Optional[dict] = None):
        with open(os.path.join(UI_DIR, name), "rb") as f:
            self._send(200, f.read(), ctype, extra)

    def _file(self, full: str, download: bool, device: Optional[dict] = None):
        size = os.path.getsize(full)
        ext = os.path.splitext(full)[1].lower()
        ctype = EXTRA_TYPES.get(ext) or mimetypes.guess_type(full)[0] or "application/octet-stream"
        name = os.path.basename(full)
        inline = not download and (ctype.split("/")[0] in ("video", "audio") or
                                   (ctype.startswith("image/") and ext in IMAGE) or ctype in INLINE_TYPES)
        if not inline:
            ctype = "application/octet-stream"  # never render HTML/SVG/scripts from this origin
        disposition = f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{quote(name)}"
        extra = {"Accept-Ranges": "bytes", "Content-Disposition": disposition, "Content-Security-Policy": "sandbox"}

        start, end, status = 0, size - 1, 200
        m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", "").strip())
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
            else:  # last N bytes
                start = max(0, size - int(m.group(2)))
            if start > end or start >= size:
                return self._send(416, b"", "text/plain", {"Content-Range": f"bytes */{size}"})
            status = 206
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        self._headers(status, ctype, end - start + 1, extra)
        if self.command == "HEAD":
            return
        try:
            with open(full, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(left, 256 * 1024))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
                    if device is not None:
                        device["bytes"] += len(chunk)
                        device["playing"]["at"] = time.time()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the player seeked or closed: normal while streaming
