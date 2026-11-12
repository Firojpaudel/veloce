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

from engine.server import RequestHandler


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

    def test_extension_origin_allowed(self):
        req = urllib.request.Request(
            f"{self.base_url}/api/status",
            headers={"Origin": "chrome-extension://abcdefghijklmnop"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "chrome-extension://abcdefghijklmnop")

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


if __name__ == "__main__":
    unittest.main()
