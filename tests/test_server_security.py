"""
Unit tests for Veloce Local API Server Security.
Validates DNS rebinding protection and Origin authorization guards.
"""

import _isolate  # noqa: F401  (must run before engine imports)

import os
import json
import urllib.request
import urllib.error
import threading
import unittest
from http.server import HTTPServer

from engine.server import RequestHandler, is_allowed_origin, DEFAULT_EXTENSION_IDS
from engine.media import detect_caption_format, disambiguate_media_title


class TestServerSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), RequestHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_pinned_extension_origin_allowed(self):
        # The pinned unpacked extension ID from manifest.json
        pinned_id = "faaebjnfegkfoehnbilkajcdkjjngeap"
        req = urllib.request.Request(
            f"{self.base_url}/api/status",
            headers={"Origin": f"chrome-extension://{pinned_id}"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), f"chrome-extension://{pinned_id}")

    def test_unauthorized_extension_origin_rejected(self):
        # Any extension ID not in ALLOWED_EXTENSION_IDS must receive HTTP 403
        req = urllib.request.Request(
            f"{self.base_url}/api/status",
            headers={"Origin": "chrome-extension://randomunauthorizedextensionid"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

    def test_is_allowed_origin_logic(self):
        pinned_id = "faaebjnfegkfoehnbilkajcdkjjngeap"
        self.assertTrue(is_allowed_origin(f"chrome-extension://{pinned_id}"))
        self.assertFalse(is_allowed_origin("chrome-extension://unauthorizedid"))
        self.assertFalse(is_allowed_origin("https://example.com"))
        # Dashboard on own port is allowed
        self.assertTrue(is_allowed_origin(f"http://127.0.0.1:{self.port}", own_port=self.port))
        # Another port is rejected
        self.assertFalse(is_allowed_origin("http://127.0.0.1:9999", own_port=self.port))

    def test_malicious_website_origin_rejected(self):
        req = urllib.request.Request(
            f"{self.base_url}/api/status",
            headers={"Origin": "https://malicious-website.com"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

    def test_dns_rebinding_rejected(self):
        req = urllib.request.Request(
            f"{self.base_url}/api/status",
            headers={"Host": "attacker-controlled-domain.com"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

    def test_local_cli_allowed(self):
        # CLI requests do not send an Origin header
        req = urllib.request.Request(f"{self.base_url}/api/status")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)

    def test_media_filename_collision_disambiguation(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            # When no file exists, title is returned as-is
            t1 = disambiguate_media_title(td, "My Video", "https://youtube.com/watch?v=dQw4w9WgXcQ")
            self.assertEqual(t1, "My Video")

            # Create an existing file
            with open(os.path.join(td, "My Video.mp4"), "wb") as f:
                f.write(b"existing video content")

            # With collision, should append video ID or hash
            t2 = disambiguate_media_title(td, "My Video", "https://youtube.com/watch?v=dQw4w9WgXcQ")
            self.assertEqual(t2, "My Video [dQw4w9WgXcQ]")

            # Non-youtube URL falls back to 6-char SHA256
            t3 = disambiguate_media_title(td, "My Video", "https://example.com/stream.m3u8")
            self.assertTrue(t3.startswith("My Video ["))
            self.assertTrue(t3.endswith("]"))
            self.assertNotEqual(t3, "My Video")

    def test_detect_caption_format(self):
        # WebVTT
        vtt_data = b"WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHello"
        self.assertEqual(detect_caption_format("text/vtt", vtt_data), "webvtt")
        self.assertEqual(detect_caption_format("application/octet-stream", vtt_data), "webvtt")

        # SRT
        srt_data = b"1\n00:00:01,000 --> 00:00:04,000\nHello"
        self.assertEqual(detect_caption_format("application/x-subrip", srt_data), "srt")
        self.assertEqual(detect_caption_format("text/plain", srt_data), "srt")

        # ASS
        ass_data = b"[Script Info]\nTitle: Test\nScriptType: v4.00+"
        self.assertEqual(detect_caption_format("text/x-ssa", ass_data), "ass")

        # Reject dangerous/invalid inputs
        self.assertIsNone(detect_caption_format("text/html", b"<html><body>Not a sub</body></html>"))
        self.assertIsNone(detect_caption_format("application/x-sh", b"#!/bin/bash\nrm -rf /"))
        self.assertIsNone(detect_caption_format("application/octet-stream", b"\x7fELF\x02\x01\x01"))


if __name__ == "__main__":
    unittest.main()
