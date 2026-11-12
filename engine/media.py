"""
Veloce Media Engine
Universal media stream probing, format selection, HLS/DASH handling,
and audio extraction via yt-dlp & ffmpeg.
"""

import os
import sys
import json
import shutil
import logging
import tempfile
import threading
import subprocess
import contextlib
from typing import Callable, Dict, Iterator, List, Optional
from urllib.parse import urlparse, parse_qs

from . import updater

_yt_module = None


def ytdlp():
    """The yt-dlp module (lazily imported so an auto-update can be swapped in), or None if unavailable."""
    global _yt_module
    if _yt_module is None:
        try:
            if updater.activate():
                try:
                    import yt_dlp
                    _yt_module = yt_dlp
                    return _yt_module
                except Exception as e:  # a broken/incompatible update must never take media support down
                    logger.warning(f"Auto-updated yt-dlp failed to load ({e}); using the bundled one")
                    updater.deactivate()
            import yt_dlp
            _yt_module = yt_dlp
        except ImportError:
            return None
    return _yt_module


def reload_ytdlp():
    """Called by the updater after a new yt-dlp has been activated; next use re-imports it."""
    global _yt_module
    _yt_module = None

logger = logging.getLogger("VeloceMedia")

# Cookies are deliberately not forwarded as a raw header (it would follow redirects to other hosts);
# they go through a domain-scoped cookies.txt instead, see cookie_file().
FORWARDED_HEADERS = ("referer", "user-agent", "origin")
OUTPUT_EXTENSIONS = ("mp4", "mkv", "webm", "m4a", "mp3", "opus", "ogg", "flac", "wav", "aac")


class MediaCancelled(Exception):
    pass


PLAYLIST_ENTRY_LIMIT = 500


PREFERRED_LANGS = ("en", "en-US", "en-GB", "en-orig")


def organize_captions(video_path: str) -> str:
    """
    For a video that has captions:
      * moves the video and its .srt files into their own folder (<title>/), so they stay together;
      * gives the main caption file the video's exact name (<title>.srt) — every player loads that
        automatically — preferring English; other languages keep their tag (<title>.de.srt);
      * marks that caption track "on by default" inside the file, so it shows without pressing CC.
    Returns the video's new path.
    """
    folder, name = os.path.split(video_path)
    root, ext = os.path.splitext(name)
    subs = sorted(f for f in os.listdir(folder) if f.startswith(root + ".") and f.endswith(".srt"))
    if not subs:
        return video_path

    def lang_of(f):
        middle = f[len(root) + 1:-4]
        return middle or "und"

    langs = [lang_of(f) for f in subs]
    main = next((i for i, l in enumerate(langs) if l in PREFERRED_LANGS or l.startswith("en")), 0)

    target = os.path.join(folder, root)
    if os.path.exists(target) and not os.path.isdir(target):
        target += " (captions)"
    os.makedirs(target, exist_ok=True)
    new_video = os.path.join(target, name)
    os.replace(video_path, new_video)
    for i, f in enumerate(subs):
        dest = f"{root}.srt" if i == main else f
        os.replace(os.path.join(folder, f), os.path.join(target, dest))

    # Make the main caption track the default inside the file (players then show it right away)
    if MediaEngine._locate_ffmpeg() and ext.lower() in (".mp4", ".m4v", ".mkv"):
        probe = subprocess.run(["ffmpeg", "-hide_banner", "-i", new_video], capture_output=True, text=True)
        tracks = probe.stderr.count("Subtitle:")
        if tracks:
            out = os.path.join(target, f".{root}.tmp{ext}")
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", new_video, "-map", "0", "-c", "copy"]
            for t in range(tracks):
                cmd += [f"-disposition:s:{t}", "default" if t == min(main, tracks - 1) else "0"]
            if subprocess.run(cmd + [out], capture_output=True).returncode == 0:
                os.replace(out, new_video)
            elif os.path.exists(out):
                os.remove(out)
    return new_video


def attach_subtitles(video_path: str, urls: List[str], headers: Dict[str, str]):
    """
    Captions the page's player loaded as separate files (.vtt/.srt/.ass): saves each as .srt next to the
    video (VLC, MPV and Windows' player pick these up automatically) and embeds them in the MP4.
    """
    import urllib.request
    if not MediaEngine._locate_ffmpeg():
        return
    root, ext = os.path.splitext(video_path)
    tmp = tempfile.mkdtemp(prefix="veloce-subs-")
    try:
        srts = []
        for i, url in enumerate(urls[:8]):
            if not str(url).startswith(("http://", "https://")):
                continue
            raw = os.path.join(tmp, f"sub{i}")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", **headers})
            with urllib.request.urlopen(req, timeout=30) as r, open(raw, "wb") as f:
                f.write(r.read(5 * 1024 * 1024))  # caption files are small; cap just in case
            out = f"{root}.{i + 1}.srt" if len(urls) > 1 else f"{root}.srt"
            res = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, out], capture_output=True)
            if res.returncode == 0 and os.path.getsize(out) > 0:
                srts.append(out)
        if not srts or ext.lower() not in (".mp4", ".m4v", ".mkv"):
            return
        embedded = os.path.join(tmp, "with-subs" + ext)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", video_path]
        for srt in srts:
            cmd += ["-i", srt]
        cmd += ["-map", "0"] + sum((["-map", str(i + 1)] for i in range(len(srts))), [])
        cmd += ["-c", "copy", "-c:s", "mov_text" if ext.lower() in (".mp4", ".m4v") else "srt", embedded]
        if subprocess.run(cmd, capture_output=True).returncode == 0:
            os.replace(embedded, video_path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _veloce_home() -> str:
    return os.path.abspath(os.path.expanduser(os.environ.get("VELOCE_HOME", os.path.join("~", ".veloce"))))


class _YdlLog:
    """Routes yt-dlp's own messages into engine.log, so failures on any machine can be diagnosed."""
    _log = logging.getLogger("yt-dlp")

    def debug(self, msg):
        if not msg.startswith("[debug]"):
            self._log.debug(msg)

    def info(self, msg):
        self._log.debug(msg)

    def warning(self, msg):
        self._log.warning(msg)

    def error(self, msg):
        self._log.error(msg)


def _has_media_formats(info: dict) -> bool:
    """True when yt-dlp found at least one real audio/video format (not just storyboard images)."""
    if info.get("url") and not info.get("formats"):
        return True
    return any((f.get("vcodec") or "none") != "none" or (f.get("acodec") or "none") != "none"
               for f in info.get("formats") or [])


def friendly_media_error(err) -> str:
    """Plain-language explanation for the common yt-dlp failures."""
    text = str(err or "").replace("ERROR: ", "").strip()
    low = text.lower()
    if "requested format is not available" in low or "no video formats found" in low:
        return ("The site didn't offer a downloadable version of this video. Veloce retried with other settings; "
                "if it keeps happening, open Settings → Check for update.")
    if "sign in to confirm" in low or "not a bot" in low:
        return "YouTube asked to confirm you're not a bot. Sign in to YouTube in this browser and try again."
    if "private video" in low or "members-only" in low or "join this channel" in low:
        return "This video is private or members-only. Sign in to the site in this browser and try again."
    if "age" in low and ("restricted" in low or "confirm your age" in low):
        return "This video is age-restricted. Sign in to the site in this browser and try again."
    if "unsupported url" in low:
        return "This page isn't a supported video page. Play the video first, then use “Detected streams”."
    if "drm" in low:
        return "This video is DRM-protected, so it can't be downloaded."
    if "http error 403" in low:
        return "The site refused the download (HTTP 403). Reload the page and try again."
    if "unable to download webpage" in low or "timed out" in low or "getaddrinfo" in low:
        return "Couldn't reach the site. Check your internet connection and try again."
    return text[:300] or "The video couldn't be downloaded."


@contextlib.contextmanager
def cookie_file(cookies: Optional[List[dict]]) -> Iterator[Optional[str]]:
    """
    Writes browser cookies (chrome.cookies format) to a temporary Netscape cookies.txt for yt-dlp.
    Needed for Instagram, age-restricted / members-only videos, and some TikTok posts.
    The file is private (0600) and deleted as soon as the download or probe finishes.
    """
    if not cookies:
        yield None
        return
    fd, path = tempfile.mkstemp(prefix="veloce-cookies-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("# Netscape HTTP Cookie File\n")
            for c in cookies:
                name, value, domain = str(c.get("name", "")), str(c.get("value", "")), str(c.get("domain", ""))
                if not name or not domain or any(ch in name + value + domain for ch in "\t\r\n"):
                    continue
                include_sub = "TRUE" if domain.startswith(".") else "FALSE"
                expires = int(c.get("expirationDate") or 0)
                secure = "TRUE" if c.get("secure") else "FALSE"
                prefix = "#HttpOnly_" if c.get("httpOnly") else ""
                fh.write(f"{prefix}{domain}\t{include_sub}\t{c.get('path') or '/'}\t{secure}\t{expires}\t{name}\t{value}\n")
        yield path
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def looks_like_playlist(url: str) -> bool:
    """URLs that carry a playlist besides (or instead of) a single video."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    query = parse_qs(parsed.query)
    if "youtube.com" in host or "youtu.be" in host:
        return "list" in query or parsed.path.startswith("/playlist")
    return any(k in query for k in ("list", "playlist")) or "/playlist" in parsed.path or "/sets/" in parsed.path


def _direct_fallback(url: str) -> dict:
    return {
        "title": os.path.basename(url).split("?")[0] or "media_stream",
        "duration": 0,
        "thumbnail": "",
        "extractor": "direct",
        "video_formats": [{
            "format_id": "best",
            "type": "video",
            "resolution": "Original",
            "height": 0,
            "ext": "mp4",
            "tag": "Direct stream",
            "is_lightweight": False,
            "filesize": 0,
        }],
        "audio_formats": [{
            "format_id": "bestaudio",
            "type": "audio",
            "ext": "mp3",
            "label": "Extracted MP3 audio",
            "filesize": 0,
        }],
    }


class MediaEngine:
    AUDIO_FORMATS = ("mp3", "m4a", "opus", "flac", "wav")

    _available_cache = (0.0, None)

    @staticmethod
    def available() -> dict:
        """Cheap capability check that never imports yt-dlp (the engine stays small; see media_worker).
        Cached for 30 s: the extension polls /api/status every second."""
        import time
        stamp, cached = MediaEngine._available_cache
        if cached is not None and time.monotonic() - stamp < 30:
            return cached
        result = MediaEngine._probe_available()
        MediaEngine._available_cache = (time.monotonic(), result)
        return result

    @staticmethod
    def _probe_available() -> dict:
        import importlib.util
        version = updater.current_version()
        has_module = version != () or importlib.util.find_spec("yt_dlp") is not None
        return {
            "yt_dlp": has_module or shutil.which("yt-dlp") is not None,
            "yt_dlp_version": ".".join(map(str, version)) or None,
            "ffmpeg": MediaEngine._locate_ffmpeg(),
        }

    @staticmethod
    def _filter_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        return {k: v for k, v in (headers or {}).items() if k.lower() in FORWARDED_HEADERS}

    @staticmethod
    def normalize_format(format_id: str, extract_audio: bool) -> str:
        """Maps UI presets to yt-dlp selectors and makes sure video downloads always carry an audio track."""
        if extract_audio:
            return "bestaudio/best"
        presets = {
            "best": "bestvideo+bestaudio/best",
            "2160p": "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
            "1440p": "bestvideo[height<=1440]+bestaudio/best[height<=1440]/best",
            "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
            "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
            "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
        }
        key = format_id.strip().lower()
        if key in presets:
            return presets[key]
        if key.isdigit() and f"{key}p" in presets:
            return presets[f"{key}p"]
        if "+" in format_id or "/" in format_id or format_id.startswith("best"):
            return format_id
        # A specific yt-dlp format id: merge best audio if it is video-only, fall back gracefully otherwise
        return f"{format_id}+bestaudio/{format_id}/best"

    @staticmethod
    def _ydl_opts(http_headers: Dict[str, str], cookiefile: Optional[str], **extra) -> dict:
        from . import jsruntime
        opts = {"quiet": True, "no_warnings": False, "logger": _YdlLog(), **jsruntime.ytdlp_options(), **extra}
        if http_headers:
            opts["http_headers"] = http_headers
        if cookiefile:
            opts["cookiefile"] = cookiefile
        return opts

    @staticmethod
    def probe_url(url: str, headers: Optional[Dict[str, str]] = None,
                  cookies: Optional[List[dict]] = None) -> dict:
        """
        Extracts stream formats, resolutions, estimated sizes and audio-only tracks from a video page
        or stream manifest, and detects playlists (YouTube `list=`, channel/playlist pages, SoundCloud
        sets, ...). The result's "playlist" key is None for single videos.
        """
        http_headers = MediaEngine._filter_headers(headers)
        data = None
        playlist = None

        with cookie_file(cookies) as cookiefile:
            yt_dlp = ytdlp()
            if yt_dlp is not None:
                def extract(cookie_path, **extra):
                    opts = MediaEngine._ydl_opts(http_headers, cookie_path, skip_download=True,
                                                 playlistend=PLAYLIST_ENTRY_LIMIT, extract_flat="in_playlist", **extra)
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(url, download=False)

                # A video opened inside a playlist: look the playlist up at the same time, not afterwards.
                # ("in_playlist", not True: True returns an unresolved link instead of the playlist itself.)
                pl_box = {}
                pl_thread = None
                if looks_like_playlist(url):
                    def expand():
                        try:
                            pl = extract(cookiefile, noplaylist=False)
                            if pl and pl.get("_type") == "playlist":
                                pl_box["v"] = MediaEngine._playlist_summary(pl)
                        except Exception as e:
                            logger.info(f"Playlist expansion failed: {e}")
                    pl_thread = threading.Thread(target=expand, daemon=True)
                    pl_thread.start()

                attempts = [cookiefile, None] if cookiefile else [None]
                for cookie_path in attempts:
                    try:
                        data = extract(cookie_path, noplaylist=True)
                    except Exception as e:
                        logger.warning(f"yt_dlp probe failed{' with cookies' if cookie_path else ''}: {e}")
                        data = None
                        continue
                    if data and (data.get("_type") in ("playlist", "multi_video") or _has_media_formats(data)):
                        break
                    logger.warning("Probe returned no downloadable formats%s" % (" — retrying without cookies" if cookie_path else ""))

                if pl_thread:
                    pl_thread.join(timeout=120)
                if data and data.get("_type") in ("playlist", "multi_video"):
                    # The URL *is* a playlist / channel / album page
                    playlist, data = MediaEngine._playlist_summary(data), None
                elif "v" in pl_box:
                    playlist = pl_box["v"]

            if data is None and playlist is None and shutil.which("yt-dlp"):
                cmd = ["yt-dlp", "--dump-json", "--no-playlist", "--no-warnings"]
                for k, v in http_headers.items():
                    cmd.extend(["--add-header", f"{k}:{v}"])
                if cookiefile:
                    cmd.extend(["--cookies", cookiefile])
                cmd.extend(["--", url])  # "--" so a URL can never be parsed as an option
                try:
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=45, check=True)
                    data = json.loads(res.stdout.splitlines()[0])
                except Exception as e:
                    logger.warning(f"yt-dlp CLI probe failed: {e}")

        if data is None and playlist is None:
            return _direct_fallback(url)

        try:
            result = MediaEngine._summarize(data) if data else {
                "title": playlist["title"], "duration": 0, "thumbnail": playlist.get("thumbnail", ""),
                "uploader": playlist.get("uploader", ""), "extractor": playlist.get("extractor", ""),
                "video_formats": [], "audio_formats": [],
            }
        except Exception as e:
            logger.warning(f"Could not summarize formats for {url}: {e}")
            result = _direct_fallback(url)
        result["playlist"] = playlist
        return result

    @staticmethod
    def _playlist_summary(pl: dict) -> dict:
        entries = []
        for e in pl.get("entries") or []:
            if not e:
                continue
            entry_url = e.get("url") or e.get("webpage_url") or ""
            if not entry_url.startswith(("http://", "https://")):
                if (e.get("ie_key") or "").lower() == "youtube" and e.get("id"):
                    entry_url = f"https://www.youtube.com/watch?v={e['id']}"
                else:
                    continue
            thumbs = e.get("thumbnails") or []
            entries.append({
                "url": entry_url,
                "title": e.get("title") or e.get("id") or "Untitled",
                "duration": e.get("duration") or 0,
                "thumbnail": thumbs[-1].get("url", "") if thumbs else "",
            })
        thumbs = pl.get("thumbnails") or []
        return {
            "id": pl.get("id") or "",
            "title": pl.get("title") or "Playlist",
            "uploader": pl.get("uploader") or pl.get("channel") or "",
            "extractor": pl.get("extractor_key") or "",
            "thumbnail": thumbs[-1].get("url", "") if thumbs else "",
            "count": pl.get("playlist_count") or len(entries),
            "entries": entries,
        }

    @staticmethod
    def _summarize(data: dict) -> dict:
        duration = data.get("duration") or 0
        best_by_height: Dict[int, dict] = {}
        audio_options: List[dict] = []

        def size_of(f: dict) -> int:
            size = f.get("filesize") or f.get("filesize_approx") or 0
            if not size and duration and f.get("tbr"):
                size = int(f["tbr"] * 1000 / 8 * duration)  # tbr is kbit/s
            return int(size)

        for f in data.get("formats") or []:
            vcodec = f.get("vcodec") or "none"
            acodec = f.get("acodec") or "none"
            height = f.get("height")

            if vcodec == "none" and acodec != "none":
                abr = round(f.get("abr") or 0)
                audio_options.append({
                    "format_id": f.get("format_id"),
                    "type": "audio",
                    "ext": f.get("ext", "m4a"),
                    "codec": acodec.split(".")[0],
                    "abr": abr,
                    "label": f"{abr} kbps {acodec.split('.')[0]}" if abr else acodec.split(".")[0],
                    "filesize": size_of(f),
                })
            elif height and height >= 144 and vcodec != "none":
                # yt-dlp lists formats worst → best, so later entries at the same height win
                # unless they are clearly lower bitrate.
                prev = best_by_height.get(height)
                if prev is None or (f.get("tbr") or 0) >= (prev.get("tbr") or 0):
                    best_by_height[height] = f

        video_options = []
        if not best_by_height and any((f.get("vcodec") or "none") != "none" or not f.get("vcodec")
                                      for f in data.get("formats") or [] if (f.get("acodec") or "") != "none" or not f.get("acodec")):
            # Streams that don't declare their resolution or codecs (common with HLS players): still offer them
            video_options.append({"format_id": "best", "type": "video", "resolution": "Best", "height": 0, "ext": "mp4",
                                  "fps": None, "vcodec": "", "tag": "Best available", "is_lightweight": False, "filesize": 0})
        for height, f in sorted(best_by_height.items(), reverse=True):
            tag = "4K" if height >= 2160 else "Quad HD" if height >= 1440 else "Full HD" if height >= 1080 \
                else "HD" if height >= 720 else "SD"
            video_options.append({
                "format_id": f.get("format_id"),
                "type": "video",
                "resolution": f"{height}p",
                "height": height,
                "ext": "mp4",
                "fps": f.get("fps"),
                "vcodec": (f.get("vcodec") or "").split(".")[0],
                "tag": tag,
                "is_lightweight": height in (480, 720),
                "filesize": size_of(f),
            })

        audio_options.sort(key=lambda x: x.get("abr", 0), reverse=True)

        return {
            "title": data.get("title") or "video",
            "duration": duration,
            "thumbnail": data.get("thumbnail") or "",
            "uploader": data.get("uploader") or data.get("channel") or "",
            "extractor": data.get("extractor_key") or data.get("extractor") or "",
            "video_formats": video_options,
            "audio_formats": audio_options[:3],
        }

    @staticmethod
    def _locate_ffmpeg() -> bool:
        """Finds ffmpeg (Veloce's own copy in ~/.veloce/bin, the system's, or one next to the app) and puts it on PATH."""
        from . import ffmpeg_setup
        exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        exe_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
        path = ffmpeg_setup.find() or (os.path.join(exe_dir, exe) if os.path.isfile(os.path.join(exe_dir, exe)) else None)
        if not path:
            return False
        directory = os.path.dirname(path)
        if directory not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")
        return True

    @staticmethod
    def _find_output(output_dir: str, prefix: str, preferred: Optional[str] = None) -> Optional[str]:
        exts = ([preferred] if preferred else []) + [e for e in OUTPUT_EXTENSIONS if e != preferred]
        for ext in exts:
            candidate = os.path.join(output_dir, f"{prefix}.{ext}")
            if os.path.exists(candidate):
                return candidate
        return None

    @staticmethod
    def download_stream(
        url: str,
        output_dir: str,
        filename_prefix: str,
        format_id: str = "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        extract_audio: bool = False,
        audio_format: str = "mp3",
        headers: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[dict], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
        cookies: Optional[List[dict]] = None,
        referers: Optional[List[str]] = None,
        subtitle_urls: Optional[List[str]] = None,
    ) -> str:
        """
        Downloads a media stream with yt-dlp (16 concurrent fragments for HLS/DASH),
        merging audio+video or extracting audio with ffmpeg when available.
        Returns the final file path. Raises on failure or MediaCancelled when stopped.
        """
        with cookie_file(cookies) as cookiefile:
            path = MediaEngine._download_impl(url, output_dir, filename_prefix, format_id, extract_audio,
                                              audio_format, headers, progress_callback, should_stop, cookiefile,
                                              referers or [])
        if subtitle_urls and not extract_audio:
            try:
                attach_subtitles(path, subtitle_urls, MediaEngine._filter_headers(headers))
            except Exception as e:  # captions are a bonus; never fail the video over them
                logger.warning(f"Couldn't attach captions: {e}")
        if not extract_audio:
            try:
                path = organize_captions(path)
            except Exception as e:
                logger.warning(f"Couldn't organise captions: {e}")
        return path

    @staticmethod
    def _download_impl(url, output_dir, filename_prefix, format_id, extract_audio, audio_format,
                       headers, progress_callback, should_stop, cookiefile, referers=()) -> str:
        os.makedirs(output_dir, exist_ok=True)
        out_template = os.path.join(output_dir, f"{filename_prefix}.%(ext)s")
        has_ffmpeg = MediaEngine._locate_ffmpeg()
        http_headers = MediaEngine._filter_headers(headers)
        preferred_ext = audio_format if (extract_audio and has_ffmpeg) else ("mp4" if has_ffmpeg else None)

        # Fragment downloads write hundreds of "*.part-FragN" files; keep them in a private temp folder
        # (deleted afterwards, even on failure) instead of the user's downloads folder.
        work_dir = os.path.join(_veloce_home(), "tmp", f"{os.getpid()}-{abs(hash((url, filename_prefix))) % 10**8}")
        os.makedirs(work_dir, exist_ok=True)
        try:
            return MediaEngine._run_download(url, output_dir, filename_prefix, format_id, extract_audio, audio_format,
                                             headers, progress_callback, should_stop, cookiefile, referers,
                                             out_template, has_ffmpeg, http_headers, preferred_ext, work_dir)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    @staticmethod
    def _run_download(url, output_dir, filename_prefix, format_id, extract_audio, audio_format, headers,
                      progress_callback, should_stop, cookiefile, referers, out_template, has_ffmpeg,
                      http_headers, preferred_ext, work_dir) -> str:
        yt_dlp = ytdlp()
        if yt_dlp is not None:
            def hook(d):
                if should_stop and should_stop():
                    raise MediaCancelled("Cancelled by user")
                if progress_callback and d.get("status") == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    progress_callback({
                        "downloaded": d.get("downloaded_bytes") or 0,
                        "total_size": int(total),
                        "speed": d.get("speed") or 0.0,
                        "eta": d.get("eta") or 0,
                    })

            base_opts = {
                "outtmpl": f"{filename_prefix}.%(ext)s",
                "paths": {"home": output_dir, "temp": work_dir},
                "noplaylist": True,
                "concurrent_fragment_downloads": 16,
                "buffersize": 1024 * 1024,
                "quiet": True,
                "no_warnings": True,
                "progress_hooks": [hook],
            }
            if http_headers:
                base_opts["http_headers"] = http_headers
            if cookiefile:
                base_opts["cookiefile"] = cookiefile

            from . import jsruntime
            base_opts.update(jsruntime.ytdlp_options())
            base_opts.update({"no_warnings": False, "logger": _YdlLog()})
            primary = dict(base_opts)
            if extract_audio:
                primary["format"] = "bestaudio/best"
                if has_ffmpeg:
                    primary["postprocessors"] = [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": audio_format,
                        "preferredquality": "192",
                    }]
            elif has_ffmpeg:
                primary["format"] = format_id
                primary["merge_output_format"] = "mp4"
                # Same resolution, but prefer H.264 + AAC: MP4s that play everywhere (Windows' player, iPhone,
                # QuickTime), not AV1/Opus that only browsers and VLC handle.
                primary["format_sort"] = ["res", "vcodec:h264", "acodec:aac"]
                # Captions: saved as .srt next to the video (players pick these up) and embedded in the MP4.
                primary.update({
                    "writesubtitles": True,
                    "subtitleslangs": ["all", "-live_chat"],
                    "subtitlesformat": "srt/vtt/ass/best",
                })
                primary["postprocessors"] = [
                    {"key": "FFmpegSubtitlesConvertor", "format": "srt"},
                    {"key": "FFmpegEmbedSubtitle", "already_have_subtitle": True},
                ]
            else:
                primary["format"] = "best[ext=mp4]/best"

            basic = "bestaudio/best" if extract_audio else ("bv*+ba/b" if has_ffmpeg else "best[ext=mp4]/best")
            attempts = [primary]
            if primary.get("writesubtitles"):
                # A broken caption file must never cost the video: same download, without captions
                attempts.append({k: v for k, v in primary.items()
                                 if k not in ("writesubtitles", "subtitleslangs", "subtitlesformat", "postprocessors")})
            if cookiefile:
                # Signed-in sessions make YouTube use stricter clients; the same video often works without them.
                attempts.append({k: v for k, v in primary.items() if k != "cookiefile"})
            attempts.append({**{k: v for k, v in primary.items() if k != "cookiefile"}, "format": basic})
            # A stream server that answers 403 usually checks which page is asking. Try the other pages we
            # know about (the embedding page, the player's own site), with a matching Origin.
            for ref in referers:
                if not ref or ref == (http_headers or {}).get("Referer"):
                    continue
                try:
                    origin = "{0.scheme}://{0.netloc}".format(urlparse(ref))
                except ValueError:
                    continue
                attempts.append({**primary, "http_headers": {**(http_headers or {}), "Referer": ref, "Origin": origin}})

            last_error = None
            standard = len(attempts) - sum(1 for r in referers if r and r != (http_headers or {}).get("Referer"))
            for i, opts in enumerate(attempts):
                if i >= standard and last_error is not None and "403" not in str(last_error):
                    break
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([url])
                    found = MediaEngine._find_output(output_dir, filename_prefix, preferred_ext)
                    if found:
                        return found
                    last_error = RuntimeError("yt-dlp finished but no output file was found")
                except MediaCancelled:
                    raise
                except Exception as e:
                    if should_stop and should_stop():
                        raise MediaCancelled("Cancelled by user")
                    last_error = e
                    logger.warning(f"yt_dlp download attempt failed: {e}")
            if not shutil.which("yt-dlp"):
                if not has_ffmpeg and not extract_audio and "format" in str(last_error).lower():
                    raise RuntimeError("Video needs ffmpeg to join the picture and sound, and Veloce couldn't set it up. "
                                       "Check your internet connection and try again, or install ffmpeg yourself.")
                raise RuntimeError(friendly_media_error(last_error))

        if not shutil.which("yt-dlp"):
            raise RuntimeError("yt-dlp is not installed. Install it with: pip install yt-dlp")

        cmd = ["yt-dlp", "--no-playlist", "--no-warnings", "--newline",
               "--concurrent-fragments", "16", "-o", out_template]
        for k, v in http_headers.items():
            cmd.extend(["--add-header", f"{k}:{v}"])
        if cookiefile:
            cmd.extend(["--cookies", cookiefile])
        if extract_audio:
            if has_ffmpeg:
                cmd.extend(["-x", "--audio-format", audio_format, "--audio-quality", "192K"])
            else:
                cmd.extend(["-f", "bestaudio/best"])
        elif has_ffmpeg:
            cmd.extend(["-f", format_id, "--merge-output-format", "mp4"])
        else:
            cmd.extend(["-f", "best[ext=mp4]/best"])
        cmd.extend(["--", url])  # "--" so a URL can never be parsed as an option

        logger.info("Executing yt-dlp CLI stream download")
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        found = MediaEngine._find_output(output_dir, filename_prefix, preferred_ext)
        if not found:
            raise RuntimeError("yt-dlp finished but no output file was found")
        return found
