"""
Integration test for Veloce engine against a local byte-range HTTP server.
Validates dynamic segmentation, in-place pwrite assembly, and checksum integrity.
"""

import _isolate  # noqa: F401  (must run before engine imports)

import os
import time
import hashlib
import tempfile
import threading
import unittest
from http.server import HTTPServer, BaseHTTPRequestHandler

from engine.segmenter import DownloadTask

# Generate a reproducible pseudo-random 5 MB test payload
TEST_PAYLOAD = os.urandom(5 * 1024 * 1024)
TEST_SHA256 = hashlib.sha256(TEST_PAYLOAD).hexdigest()

class MockRangeServer(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(TEST_PAYLOAD)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        range_header = self.headers.get("Range")
        total_len = len(TEST_PAYLOAD)

        if not range_header:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(total_len))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(TEST_PAYLOAD)
            return

        # Parse 'bytes=start-end'
        try:
            byte_range = range_header.replace("bytes=", "").strip()
            parts = byte_range.split("-")
            start = int(parts[0])
            end = int(parts[1]) if parts[1] else total_len - 1
            end = min(end, total_len - 1)

            chunk = TEST_PAYLOAD[start:end + 1]
            self.send_response(206)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Range", f"bytes {start}-{end}/{total_len}")
            self.send_header("Content-Length", str(len(chunk)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(chunk)
        except Exception:
            self.send_response(416)
            self.end_headers()

    def log_message(self, format, *args):
        pass


class TestDynamicDownloadEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), MockRangeServer)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_accelerated_download_checksum(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "downloaded.bin")
            url = f"http://127.0.0.1:{self.port}/test_file.bin"

            # 8 concurrent connections downloading 5MB with dynamic bisection
            task = DownloadTask(url=url, output_path=out_file, num_connections=8)
            task.start()

            self.assertEqual(task.status, "COMPLETED")
            self.assertTrue(os.path.exists(out_file))
            self.assertEqual(os.path.getsize(out_file), len(TEST_PAYLOAD))

            with open(out_file, "rb") as fh:
                data = fh.read()
            downloaded_sha256 = hashlib.sha256(data).hexdigest()

            # Bit-exact hash verification
            self.assertEqual(downloaded_sha256, TEST_SHA256)


if __name__ == "__main__":
    unittest.main()
