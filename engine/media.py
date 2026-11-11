"""
Veloce Media Engine
Universal media stream probing, lightweight format selection,
HLS/DASH manifest handling, and audio extraction via yt-dlp & ffmpeg.
"""

import os
import sys
import json
import logging
import subprocess
from typing import Dict, List, Optional

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

logger = logging.getLogger("VeloceMedia")

class MediaProbeResult:
    def __init__(self, title: str, duration: float, thumbnail: str, formats: List[dict]):
        self.title = title
        self.duration = duration
        self.thumbnail = thumbnail
        self.formats = formats

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "duration": self.duration,
            "thumbnail": self.thumbnail,
            "formats": self.formats,
        }

class MediaEngine:
    @staticmethod
    def probe_url(url: str, headers: Optional[Dict[str, str]] = None) -> Optional[dict]:
        """
        Extracts all stream formats, resolutions, estimated file sizes,
        and audio-only tracks from any web video or stream manifest.
        """
        data = None

        # 1. Try bundled yt_dlp module first (zero external binary dependency)
        if yt_dlp is not None:
            try:
                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "skip_download": True,
                }
                if headers:
                    http_headers = {k: v for k, v in headers.items() if k.lower() in ["user-agent", "referer"]}
                    if http_headers:
                        ydl_opts["http_headers"] = http_headers
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    data = ydl.extract_info(url, download=False)
            except Exception as e:
                logger.warning(f"yt_dlp module probe failed: {e}")

        # 2. Fallback to CLI binary if module failed or not installed
        if data is None:
            cmd = [
                "yt-dlp",
                "--dump-json",
                "--no-playlist",
                "--no-warnings",
                "--ignore-errors",
                url
            ]

            if headers:
                for k, v in headers.items():
                    if k.lower() in ["user-agent", "referer"]:
                        cmd.extend(["--add-header", f"{k}:{v}"])

            try:
                res = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=True
                )
                data = json.loads(res.stdout)
            except Exception as e:
                logger.warning(f"yt-dlp CLI probe failed: {e}")

        if not data:
            # Fallback for direct stream URLs
            return {
                "title": os.path.basename(url).split("?")[0] or "media_stream",
                "duration": 0,
                "thumbnail": "",
                "video_formats": [
                    {
                        "format_id": "direct",
                        "type": "video",
                        "resolution": "Original / Stream",
                        "height": 720,
                        "ext": "mp4",
                        "tag": "Direct Stream",
                        "is_lightweight": True,
                        "filesize": 0,
                    }
                ],
                "audio_formats": [
                    {
                        "format_id": "audio_extract",
                        "type": "audio",
                        "ext": "mp3",
                        "label": "Extracted MP3 Audio",
                        "filesize": 0,
                    }
                ]
            }

        try:
            title = data.get("title", "video")
            duration = data.get("duration", 0)
            thumbnail = data.get("thumbnail", "")

            raw_formats = data.get("formats", [])
            video_options = []
            audio_options = []

            seen_heights = set()

            for f in raw_formats:
                height = f.get("height")
                ext = f.get("ext", "mp4")
                vcodec = f.get("vcodec", "none")
                acodec = f.get("acodec", "none")
                filesize = f.get("filesize") or f.get("filesize_approx") or 0

                # Approximate filesize from tbr and duration if missing
                if not filesize and duration and f.get("tbr"):
                    filesize = int((f["tbr"] * 1024 / 8) * duration)

                # Audio only formats
                if vcodec == "none" and acodec != "none":
                    audio_options.append({
                        "format_id": f.get("format_id"),
                        "type": "audio",
                        "ext": ext,
                        "codec": acodec,
                        "abr": f.get("abr", 128),
                        "label": f"Audio ({f.get('abr', 128)} kbps)",
                        "filesize": filesize,
                    })

                # Video formats
                elif height and height >= 144 and height not in seen_heights and vcodec != "none":
                    seen_heights.add(height)
                    
                    # Highlight lightweight profiles
                    is_lightweight = height in [480, 720]
                    tag = "Balanced" if height == 720 else ("Lightweight" if height <= 480 else "Full HD")

                    video_options.append({
                        "format_id": f.get("format_id"),
                        "type": "video",
                        "resolution": f"{height}p",
                        "height": height,
                        "ext": ext,
                        "fps": f.get("fps"),
                        "tag": tag,
                        "is_lightweight": is_lightweight,
                        "filesize": filesize,
                    })

            # Sort video resolutions descending (1080p, 720p, 480p, 360p)
            video_options.sort(key=lambda x: x["height"], reverse=True)
            # Sort audio descending by bitrate
            audio_options.sort(key=lambda x: x.get("abr", 0), reverse=True)

            return {
                "title": title,
                "duration": duration,
                "thumbnail": thumbnail,
                "video_formats": video_options,
                "audio_formats": audio_options[:3],  # Top 3 clean audio choices
            }

        except Exception as e:
            logger.warning(f"yt-dlp probe failed for {url}: {e}")
            # Fallback for direct stream URLs
            return {
                "title": os.path.basename(url).split("?")[0] or "media_stream",
                "duration": 0,
                "thumbnail": "",
                "video_formats": [
                    {
                        "format_id": "direct",
                        "type": "video",
                        "resolution": "Original / Stream",
                        "height": 720,
                        "ext": "mp4",
                        "tag": "Direct Stream",
                        "is_lightweight": True,
                        "filesize": 0,
                    }
                ],
                "audio_formats": [
                    {
                        "format_id": "audio_extract",
                        "type": "audio",
                        "ext": "mp3",
                        "label": "Extracted MP3 Audio",
                        "filesize": 0,
                    }
                ]
            }

    @staticmethod
    def download_stream(
        url: str,
        output_dir: str,
        filename_prefix: str,
        format_id: str = "bestvideo[height<=720]+bestaudio/best[height<=720]",
        extract_audio: bool = False,
        audio_format: str = "mp3"
    ) -> str:
        """
        Downloads the media stream using ffmpeg muxing and lightweight compression.
        """
        os.makedirs(output_dir, exist_ok=True)
        out_template = os.path.join(output_dir, f"{filename_prefix}.%(ext)s")

        # 1. Try bundled yt_dlp module first
        if yt_dlp is not None:
            try:
                ydl_opts = {
                    "outtmpl": out_template,
                    "format": format_id,
                    "quiet": False,
                    "no_warnings": True,
                }
                if extract_audio:
                    ydl_opts["format"] = "bestaudio/best"
                    ydl_opts["postprocessors"] = [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": audio_format,
                        "preferredquality": "192",
                    }]
                else:
                    ydl_opts["merge_output_format"] = "mp4"

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                return out_template
            except Exception as e:
                logger.warning(f"yt_dlp in-process download failed: {e}, falling back to CLI")

        # 2. Fallback to CLI binary
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--no-warnings",
            "--newline",
            "-o", out_template,
        ]

        if extract_audio:
            cmd.extend([
                "-x",
                "--audio-format", audio_format,
                "--audio-quality", "192K",
            ])
        else:
            # Optimal lightweight video selection with audio merge
            cmd.extend([
                "-f", format_id,
                "--merge-output-format", "mp4"
            ])

        cmd.append(url)
        logger.info(f"Executing stream download: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return out_template
