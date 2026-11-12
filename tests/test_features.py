"""
Tests for features added in 1.1: probe-stream reuse, credential stripping on cross-host redirects,
keep-alive connection reuse, playlist summaries, cookies.txt generation, format presets,
and the yt-dlp updater's safety checks.
"""

import _isolate  # noqa: F401  (must run before engine imports)

import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from engine.media import MediaEngine, cookie_file, looks_like_playlist
from engine.segmenter import DownloadTask
from engine import updater

PAYLOAD = os.urandom(2 * 1024 * 1024 + 7)


def serve(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_port


class Recorder(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive capable
    requests = []
    connections = set()
    redirect_to = None
    honor_range = True

    def log_message(self, *a):
        pass

    def do_GET(self):
        type(self).requests.append({k: v for k, v in self.headers.items()})
        type(self).connections.add(self.client_address)
        if self.redirect_to and self.path.startswith("/start"):
            self.send_response(302)
            self.send_header("Location", self.redirect_to)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        rng = self.headers.get("Range")
        if rng and self.honor_range:
            start, _, end = rng.replace("bytes=", "").partition("-")
            start, end = int(start), min(int(end or len(PAYLOAD) - 1), len(PAYLOAD) - 1)
            body = PAYLOAD[start:end + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(PAYLOAD)}")
        else:
            body = PAYLOAD
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


def fresh_recorder(**attrs):
    return type("R", (Recorder,), {"requests": [], "connections": set(), **attrs})


class TestTransfer(unittest.TestCase):
    def test_non_range_server_is_fetched_with_a_single_request(self):
        handler = fresh_recorder(honor_range=False)
        server, port = serve(handler)
        try:
            task = DownloadTask(f"http://127.0.0.1:{port}/f.bin", tempfile.mkdtemp(), num_connections=8)
            task.start()
            with open(task.output_path, "rb") as fh:
                self.assertEqual(fh.read(), PAYLOAD)
            self.assertEqual(len(handler.requests), 1, "probe response should be reused as the download stream")
        finally:
            server.shutdown()

    def test_ranged_download_reuses_probe_and_is_intact(self):
        handler = fresh_recorder()
        server, port = serve(handler)
        try:
            task = DownloadTask(f"http://127.0.0.1:{port}/f.bin", tempfile.mkdtemp(), num_connections=4)
            task.start()
            with open(task.output_path, "rb") as fh:
                self.assertEqual(fh.read(), PAYLOAD)
            self.assertEqual(handler.requests[0].get("Range"), "bytes=0-")
            # 1 probe (reused for segment 0) + at most one request per other initial segment
            self.assertLessEqual(len(handler.requests), task.manager.num_connections + 2)
        finally:
            server.shutdown()

    def test_cookies_not_forwarded_to_other_host_after_redirect(self):
        target = fresh_recorder()
        target_server, target_port = serve(target)
        origin = fresh_recorder(redirect_to=f"http://localhost:{target_port}/file.bin")
        origin_server, origin_port = serve(origin)
        try:
            task = DownloadTask(f"http://127.0.0.1:{origin_port}/start", tempfile.mkdtemp(), num_connections=2,
                                headers={"Cookie": "session=secret", "Authorization": "Bearer x"})
            task.start()
            self.assertEqual(origin.requests[0].get("Cookie"), "session=secret")
            self.assertTrue(target.requests)
            for req in target.requests:
                self.assertNotIn("Cookie", req)
                self.assertNotIn("Authorization", req)
        finally:
            target_server.shutdown()
            origin_server.shutdown()


class TestMediaHelpers(unittest.TestCase):
    def test_playlist_detection(self):
        self.assertTrue(looks_like_playlist("https://www.youtube.com/watch?v=abc&list=PL123"))
        self.assertTrue(looks_like_playlist("https://www.youtube.com/playlist?list=PL123"))
        self.assertFalse(looks_like_playlist("https://www.youtube.com/shorts/abc"))
        self.assertFalse(looks_like_playlist("https://www.tiktok.com/@u/video/123"))
        self.assertTrue(looks_like_playlist("https://soundcloud.com/artist/sets/album"))

    def test_playlist_summary(self):
        summary = MediaEngine._playlist_summary({
            "title": "Mix", "uploader": "Me", "playlist_count": 3,
            "entries": [
                {"url": "https://www.youtube.com/watch?v=a", "title": "A", "duration": 61},
                {"id": "b", "ie_key": "Youtube", "url": "b", "title": "B"},
                None,
                {"url": "relative-only", "title": "skip me"},
            ],
        })
        self.assertEqual(summary["count"], 3)
        self.assertEqual([e["url"] for e in summary["entries"]],
                         ["https://www.youtube.com/watch?v=a", "https://www.youtube.com/watch?v=b"])

    def test_cookie_file_is_private_and_removed(self):
        cookies = [{"name": "sid", "value": "v", "domain": ".instagram.com", "path": "/", "secure": True,
                    "httpOnly": True, "expirationDate": 2000000000},
                   {"name": "bad\tname", "value": "x", "domain": "a.com"}]
        with cookie_file(cookies) as path:
            with open(path) as fh:
                text = fh.read()
            self.assertIn("#HttpOnly_.instagram.com\tTRUE\t/\tTRUE\t2000000000\tsid\tv", text)
            self.assertNotIn("bad", text)
            if os.name == "posix":
                self.assertEqual(os.stat(path).st_mode & 0o077, 0)
        self.assertFalse(os.path.exists(path))
        with cookie_file([]) as none:
            self.assertIsNone(none)

    def test_format_presets_always_include_audio(self):
        self.assertIn("+bestaudio", MediaEngine.normalize_format("1080p", False))
        self.assertIn("+bestaudio", MediaEngine.normalize_format("137", False))
        self.assertEqual(MediaEngine.normalize_format("1080p", True), "bestaudio/best")


class TestMediaRobustness(unittest.TestCase):
    def test_streams_without_resolution_still_offer_a_video_option(self):
        info = {"title": "index", "duration": 10, "formats": [
            {"format_id": "hls-1", "url": "https://x/1.m3u8", "protocol": "m3u8_native"},
            {"format_id": "hls-2", "url": "https://x/2.m3u8", "protocol": "m3u8_native"}]}
        summary = MediaEngine._summarize(info)
        self.assertEqual([v["format_id"] for v in summary["video_formats"]], ["best"])

    def test_storyboard_only_results_count_as_no_media(self):
        from engine.media import _has_media_formats
        self.assertFalse(_has_media_formats({"formats": [{"format_id": "sb0", "vcodec": "none", "acodec": "none"}]}))
        self.assertTrue(_has_media_formats({"formats": [{"format_id": "251", "vcodec": "none", "acodec": "opus"}]}))

    def test_plain_language_errors(self):
        from engine.media import friendly_media_error
        self.assertIn("didn't offer", friendly_media_error("ERROR: [youtube] x: Requested format is not available"))
        self.assertIn("403", friendly_media_error("ERROR: unable to download video data: HTTP Error 403: Forbidden"))

    def test_ffmpeg_pins_cover_every_release_platform(self):
        from engine import ffmpeg_setup
        for key in [("win32", "x86_64"), ("linux", "x86_64"), ("darwin", "aarch64"), ("darwin", "x86_64")]:
            asset, sha = ffmpeg_setup.PINNED[key]
            self.assertEqual(len(sha), 64)


class TestUpdaterSafety(unittest.TestCase):
    def test_python_requirement_parsing(self):
        self.assertTrue(updater.python_supported(">=3.0"))
        self.assertFalse(updater.python_supported(">=99.0"))
        self.assertTrue(updater.python_supported(""))
        self.assertFalse(updater.python_supported(">=3.0,<3.1"))

    def test_version_ordering(self):
        self.assertGreater(updater.parse_version("2026.10.26"), updater.parse_version("2026.8.19"))
        self.assertGreater(updater.parse_version("2026.10.26.1"), updater.parse_version("2026.10.26"))

    def test_verify_checksum_signature_graceful_fallback(self):
        from engine.app_update import verify_checksum_signature
        sums_data = b"abcdef1234567890 *veloce-setup.exe\n"
        # When no signature assets exist, falls back gracefully returning False
        res = verify_checksum_signature(sums_data, {})
        self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
