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
        opts = {"quiet": True, "no_warnings": True, **extra}
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
                try:
                    opts = MediaEngine._ydl_opts(http_headers, cookiefile, skip_download=True,
                                                 noplaylist=True, extract_flat="in_playlist",
                                                 playlistend=PLAYLIST_ENTRY_LIMIT)
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        data = ydl.extract_info(url, download=False)
                except Exception as e:
                    logger.warning(f"yt_dlp module probe failed: {e}")

                if data and data.get("_type") in ("playlist", "multi_video"):
                    # The URL *is* a playlist / channel / album page
                    playlist, data = MediaEngine._playlist_summary(data), None
                elif looks_like_playlist(url):
                    # A single video opened from inside a playlist: offer both
                    try:
                        # "in_playlist", not True: True would return an unresolved link to the playlist
                        # (_type "url") instead of the playlist itself; entries still stay flat (fast).
                        opts = MediaEngine._ydl_opts(http_headers, cookiefile, skip_download=True,
                                                     noplaylist=False, extract_flat="in_playlist",
                                                     playlistend=PLAYLIST_ENTRY_LIMIT)
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            pl = ydl.extract_info(url, download=False)
                        if pl and pl.get("_type") == "playlist":
                            playlist = MediaEngine._playlist_summary(pl)
                    except Exception as e:
                        logger.info(f"Playlist expansion failed: {e}")

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
        """Finds ffmpeg in PATH, next to the executable, or in ~/.veloce/bin."""
        if shutil.which("ffmpeg"):
            return True
        exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        exe_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
        for directory in (exe_dir, os.path.expanduser("~/.veloce/bin")):
            if os.path.exists(os.path.join(directory, exe)):
                os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")
                return True
        return False

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
    ) -> str:
        """
        Downloads a media stream with yt-dlp (16 concurrent fragments for HLS/DASH),
        merging audio+video or extracting audio with ffmpeg when available.
        Returns the final file path. Raises on failure or MediaCancelled when stopped.
        """
        with cookie_file(cookies) as cookiefile:
            return MediaEngine._download_impl(url, output_dir, filename_prefix, format_id, extract_audio,
                                              audio_format, headers, progress_callback, should_stop, cookiefile)

    @staticmethod
    def _download_impl(url, output_dir, filename_prefix, format_id, extract_audio, audio_format,
                       headers, progress_callback, should_stop, cookiefile) -> str:
        os.makedirs(output_dir, exist_ok=True)
        out_template = os.path.join(output_dir, f"{filename_prefix}.%(ext)s")
        has_ffmpeg = MediaEngine._locate_ffmpeg()
        http_headers = MediaEngine._filter_headers(headers)
        preferred_ext = audio_format if (extract_audio and has_ffmpeg) else ("mp4" if has_ffmpeg else None)

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
                "outtmpl": out_template,
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
            else:
                primary["format"] = "best[ext=mp4]/best"

            fallback = dict(base_opts, format="bestaudio/best" if extract_audio else "best[ext=mp4]/best")

            last_error = None
            for opts in (primary, fallback):
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
                raise RuntimeError(f"Media download failed: {last_error}")

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
