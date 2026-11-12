"""
Regression tests for bugs found in review: origin bypass, arbitrary file writes, servers that ignore
Range, "Remove" deleting finished files, filename detection, retry limits, and pause/resume.
"""

import _isolate  # noqa: F401  (must run before engine imports)

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from engine import segmenter
from engine.segmenter import (
    DownloadTask, filename_from_url, parse_content_disposition, sanitize_filename,
)
from engine.server import RequestHandler, TaskStore, is_allowed_origin

PAYLOAD = os.urandom(3 * 1024 * 1024 + 123)


def serve(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


class Quiet(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_body(self, status, body, headers=None):
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


class RangeIgnoringServer(Quiet):
    """Advertises Accept-Ranges but always returns the full body with 200."""
    def do_GET(self):
        self.send_body(200, PAYLOAD, {"Accept-Ranges": "bytes"})


class RangeServer(Quiet):
    delay = 0.0
    fail = False
    content_disposition = None
    content_type = "application/octet-stream"

    def do_GET(self):
        if self.fail:
            self.send_body(503, b"busy")
            return
        headers = {"Content-Type": self.content_type, "Accept-Ranges": "bytes"}
        if self.content_disposition:
            headers["Content-Disposition"] = self.content_disposition
        rng = self.headers.get("Range")
        if not rng:
            self.send_body(200, PAYLOAD, headers)
            return
        start, _, end = rng.replace("bytes=", "").partition("-")
        start, end = int(start), min(int(end or len(PAYLOAD) - 1), len(PAYLOAD) - 1)
        headers["Content-Range"] = f"bytes {start}-{end}/{len(PAYLOAD)}"
        body = PAYLOAD[start:end + 1]
        self.send_response(206)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            for i in range(0, len(body), 32 * 1024):
                self.wfile.write(body[i:i + 32 * 1024])
                if self.delay:
                    time.sleep(self.delay)
        except (BrokenPipeError, ConnectionResetError):
            pass


class TestOriginValidation(unittest.TestCase):
    def test_lookalike_web_origins_rejected(self):
        for origin in ("http://localhost.evil.com", "http://127.0.0.1.attacker.net",
                       "http://localhost:3000", "http://127.0.0.1", "null", "https://example.com"):
            self.assertFalse(is_allowed_origin(origin), origin)

    def test_extension_origins_allowed(self):
        self.assertTrue(is_allowed_origin("chrome-extension://faaebjnfegkfoehnbilkajcdkjjngeap"))
        self.assertTrue(is_allowed_origin("chrome-extension://velocecwsplaceholder00000000000"))
        self.assertFalse(is_allowed_origin("chrome-extension://abcdefghijklmnop"))
        self.assertFalse(is_allowed_origin("chrome-extension://"))


class TestServerHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api, cls.api_url = serve(RequestHandler)
        cls.files, cls.files_url = serve(RangeServer)

    @classmethod
    def tearDownClass(cls):
        for s in (cls.api, cls.files):
            s.shutdown()
            s.server_close()

    def post(self, path, body, origin="chrome-extension://faaebjnfegkfoehnbilkajcdkjjngeap"):
        req = urllib.request.Request(
            f"{self.api_url}{path}", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Origin": origin},
        )
        return urllib.request.urlopen(req)

    def assert_status(self, code, path, body, **kw):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post(path, body, **kw)
        self.assertEqual(ctx.exception.code, code)

    def test_lookalike_origin_cannot_start_download(self):
        self.assert_status(403, "/api/download", {"url": f"{self.files_url}/a.bin"},
                           origin="http://localhost.evil.com")

    def test_output_path_outside_download_dir_rejected(self):
        outside = os.path.join(tempfile.gettempdir(), "veloce-escape")
        self.assert_status(400, "/api/download", {"url": f"{self.files_url}/a.bin", "output_path": outside})
        self.assert_status(400, "/api/download", {"url": f"{self.files_url}/a.bin", "output_path": "../../etc"})
        self.assertFalse(os.path.exists(outside))

    def test_non_http_urls_rejected(self):
        self.assert_status(400, "/api/download", {"url": "file:///etc/passwd"})
        self.assert_status(400, "/api/media/download", {"url": "--exec=touch /tmp/pwned"})

    def test_invalid_connections_rejected(self):
        for value in (0, 1000, "abc"):
            self.assert_status(400, "/api/download", {"url": f"{self.files_url}/a.bin", "connections": value})

    def test_inspect_reports_real_filename(self):
        with self.post("/api/inspect", {"url": f"{self.files_url}/releases/tool-v2.tar.gz?token=abc"}) as resp:
            data = json.loads(resp.read())
        self.assertEqual(data["filename"], "tool-v2.tar.gz")
        self.assertEqual(data["total_size"], len(PAYLOAD))
        self.assertTrue(data["resumable"])


class TestEngineCorrectness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        RangeServer.delay = 0.0
        RangeServer.fail = False
        RangeServer.content_disposition = None
        RangeServer.content_type = "application/octet-stream"

    def test_server_ignoring_range_still_yields_intact_file(self):
        server, url = serve(RangeIgnoringServer)
        try:
            out = os.path.join(self.tmp, "x.bin")
            task = DownloadTask(f"{url}/x.bin", out, num_connections=4)
            task.start()
            self.assertEqual(task.status, "COMPLETED")
            with open(out, "rb") as fh:
                self.assertEqual(fh.read(), PAYLOAD)
        finally:
            server.shutdown()

    def test_filename_from_content_disposition_and_content_type(self):
        server, url = serve(RangeServer)
        try:
            RangeServer.content_disposition = "attachment; filename=\"a.pdf\"; filename*=UTF-8''Report%20%C3%A9.pdf"
            task = DownloadTask(f"{url}/download?id=7", self.tmp)
            task.inspect_url()
            self.assertEqual(task.filename, "Report é.pdf")

            RangeServer.content_disposition = None
            RangeServer.content_type = "application/zip"
            task = DownloadTask(f"{url}/download?id=7", self.tmp)
            task.inspect_url()
            self.assertEqual(task.filename, "download.zip")
        finally:
            server.shutdown()

    def test_existing_file_not_overwritten(self):
        server, url = serve(RangeServer)
        try:
            existing = os.path.join(self.tmp, "data.bin")
            with open(existing, "wb") as fh:
                fh.write(b"keep me")
            task = DownloadTask(f"{url}/data.bin", self.tmp, num_connections=2)
            task.start()
            self.assertEqual(os.path.basename(task.output_path), "data (1).bin")
            with open(existing, "rb") as fh:
                self.assertEqual(fh.read(), b"keep me")
        finally:
            server.shutdown()

    def test_persistent_failure_ends_in_error_instead_of_hanging(self):
        server, url = serve(RangeServer)
        old = segmenter.MAX_SEGMENT_RETRIES
        segmenter.MAX_SEGMENT_RETRIES = 2
        try:
            task = DownloadTask(f"{url}/f.bin", self.tmp, num_connections=2)
            task.inspect_url()
            task.release_probe()  # drop the already-flowing probe stream so every new request fails
            RangeServer.fail = True
            with self.assertRaises(IOError):
                task.start()
            self.assertEqual(task.status, "ERROR")
        finally:
            segmenter.MAX_SEGMENT_RETRIES = old
            server.shutdown()

    def test_pause_then_resume_produces_intact_file(self):
        server, url = serve(RangeServer)
        try:
            RangeServer.delay = 0.05
            task = DownloadTask(f"{url}/big.bin", self.tmp, num_connections=4)
            t = threading.Thread(target=task.start)
            t.start()
            time.sleep(0.5)
            task.pause()
            t.join(20)
            self.assertEqual(task.status, "PAUSED")
            self.assertFalse(os.path.exists(task.output_path))
            self.assertTrue(os.path.exists(task.part_path))
            self.assertTrue(os.path.exists(task.sidecar_path))

            RangeServer.delay = 0.0
            self.assertTrue(task.prepare_resume())
            task.start()
            self.assertEqual(task.status, "COMPLETED")
            with open(task.output_path, "rb") as fh:
                self.assertEqual(fh.read(), PAYLOAD)
        finally:
            server.shutdown()

    def test_remove_keeps_completed_file_but_deletes_partial(self):
        server, url = serve(RangeServer)
        store = TaskStore(history_file=None)
        try:
            tid = store.create_task(f"{url}/done.bin", self.tmp, connections=2)
            for _ in range(100):
                if store.task_metadata[tid]["status"] == "COMPLETED":
                    break
                time.sleep(0.1)
            path = store.task_metadata[tid]["file_path"]
            self.assertTrue(store.remove_task(tid))
            self.assertTrue(os.path.exists(path), "Remove must never delete a finished download")

            RangeServer.delay = 0.02
            tid = store.create_task(f"{url}/partial.bin", self.tmp, connections=2)
            time.sleep(0.8)
            path = store.task_metadata[tid]["file_path"]
            task = store.tasks[tid]
            store.remove_task(tid)
            for _ in range(100):
                if not task._running:
                    break
                time.sleep(0.1)
            self.assertFalse(os.path.exists(path), "Cancelling should clean up the partial file")
        finally:
            server.shutdown()


class TestFilenameHelpers(unittest.TestCase):
    def test_filename_from_url(self):
        self.assertEqual(filename_from_url("https://x.com/a/b/movie%20night.mkv?x=1"), "movie night.mkv")
        self.assertEqual(
            filename_from_url("https://s3.amazonaws.com/b/k?response-content-disposition="
                              "attachment%3B%20filename%3D%22setup.exe%22"),
            "setup.exe")
        self.assertEqual(filename_from_url("https://x.com/get?file=archive.7z"), "archive.7z")
        self.assertEqual(filename_from_url("https://x.com/files/report.pdf/download"), "report.pdf")
        self.assertEqual(filename_from_url("https://x.com/"), "")

    def test_sanitize(self):
        self.assertEqual(sanitize_filename("..\\..\\evil.exe"), "evil.exe")
        self.assertEqual(sanitize_filename('a<b>:"c".txt'), "a_b___c_.txt")
        self.assertEqual(sanitize_filename(".."), "")
        self.assertEqual(parse_content_disposition('attachment; filename="../../etc/passwd"'), "passwd")


if __name__ == "__main__":
    unittest.main()
