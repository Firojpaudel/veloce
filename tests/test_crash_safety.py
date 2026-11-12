"""
Phase 1 Crash-Safe Downloads Test Suite:
1. Kill download midway, resume from TaskStore, verify bit-exact SHA-256.
2. Server changes ETag/file between runs -> fresh restart, correct output.
3. No file exists at final name until download completes.
4. Share server does not list or serve .veloce.part or .veloce.json files.
5. Cancelling deletes both .veloce.part and .veloce.json temp files.
"""

import _isolate  # noqa: F401  (must run before engine imports)

import hashlib
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from engine.segmenter import DownloadTask
from engine.server import TaskStore
from engine.share import Share

PAYLOAD_1 = os.urandom(2 * 1024 * 1024 + 456)
SHA256_1 = hashlib.sha256(PAYLOAD_1).hexdigest()

PAYLOAD_2 = os.urandom(1 * 1024 * 1024 + 789)
SHA256_2 = hashlib.sha256(PAYLOAD_2).hexdigest()


class CrashMockServer(BaseHTTPRequestHandler):
    payload = PAYLOAD_1
    etag = "etag-v1"
    last_modified = "Wed, 21 Oct 2026 07:28:00 GMT"
    delay = 0.0

    def log_message(self, *args):
        pass

    def do_GET(self):
        rng = self.headers.get("Range")
        if_range = self.headers.get("If-Range")

        # If If-Range doesn't match current etag, return 200 full body
        if if_range and if_range != type(self).etag:
            rng = None

        if not rng:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(type(self).payload)))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("ETag", type(self).etag)
            self.send_header("Last-Modified", type(self).last_modified)
            self.end_headers()
            try:
                self.wfile.write(type(self).payload)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        total = len(type(self).payload)
        start, _, end = rng.replace("bytes=", "").partition("-")
        start = int(start)
        end = min(int(end or total - 1), total - 1)
        chunk = type(self).payload[start:end + 1]

        self.send_response(206)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        self.send_header("Content-Length", str(len(chunk)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", type(self).etag)
        self.send_header("Last-Modified", type(self).last_modified)
        self.end_headers()
        try:
            for i in range(0, len(chunk), 16 * 1024):
                self.wfile.write(chunk[i:i + 16 * 1024])
                if type(self).delay:
                    time.sleep(type(self).delay)
        except (BrokenPipeError, ConnectionResetError):
            pass


class TestCrashSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), CrashMockServer)
        cls.server.daemon_threads = True
        cls.port = cls.server.server_port
        cls.url = f"http://127.0.0.1:{cls.port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        CrashMockServer.payload = PAYLOAD_1
        CrashMockServer.etag = "etag-v1"
        CrashMockServer.last_modified = "Wed, 21 Oct 2026 07:28:00 GMT"
        CrashMockServer.delay = 0.0

    def test_midway_kill_and_resume_across_restarts(self):
        CrashMockServer.delay = 0.02
        with tempfile.TemporaryDirectory() as tmpdir:
            hist_file = os.path.join(tmpdir, "history.json")
            dl_dir = os.path.join(tmpdir, "downloads")
            os.makedirs(dl_dir, exist_ok=True)

            store1 = TaskStore(history_file=hist_file)
            tid = store1.create_task(f"{self.url}/archive.bin", output_path=dl_dir, connections=4)
            time.sleep(0.4)

            # Simulate sudden interruption / crash
            task1 = store1.tasks[tid]
            task1.pause()
            # Wait for task1 to stop
            for _ in range(50):
                if not task1._running:
                    break
                time.sleep(0.05)

            final_file = store1.task_metadata[tid]["file_path"]
            self.assertFalse(os.path.exists(final_file), "Final file must not exist mid-download")
            self.assertTrue(os.path.exists(task1.part_path), ".part file must exist mid-download")
            self.assertTrue(os.path.exists(task1.sidecar_path), ".json sidecar must exist mid-download")

            # Persist history as if engine stopped
            with store1.lock:
                store1._save_history_locked()

            # Create brand new TaskStore (engine restart simulation)
            CrashMockServer.delay = 0.0
            store2 = TaskStore(history_file=hist_file)
            self.assertIn(tid, store2.task_metadata)
            self.assertEqual(store2.task_metadata[tid]["status"], "ERROR")

            # Resume task
            resumed = store2.resume_task(tid)
            self.assertTrue(resumed)

            # Wait for completion
            for _ in range(100):
                if store2.task_metadata[tid]["status"] == "COMPLETED":
                    break
                time.sleep(0.1)

            self.assertEqual(store2.task_metadata[tid]["status"], "COMPLETED")
            self.assertTrue(os.path.exists(final_file), "Final file must exist upon completion")
            self.assertFalse(os.path.exists(f"{final_file}.veloce.part"), ".part file must be removed on completion")
            self.assertFalse(os.path.exists(f"{final_file}.veloce.json"), ".json sidecar must be removed on completion")

            with open(final_file, "rb") as f:
                content = f.read()
            self.assertEqual(hashlib.sha256(content).hexdigest(), SHA256_1)

    def test_server_changes_file_triggers_fresh_restart(self):
        CrashMockServer.delay = 0.02
        with tempfile.TemporaryDirectory() as tmpdir:
            hist_file = os.path.join(tmpdir, "history.json")
            dl_dir = os.path.join(tmpdir, "downloads")
            os.makedirs(dl_dir, exist_ok=True)

            store1 = TaskStore(history_file=hist_file)
            tid = store1.create_task(f"{self.url}/dynamic.bin", output_path=dl_dir, connections=4)
            time.sleep(0.4)

            task1 = store1.tasks[tid]
            task1.pause()
            for _ in range(50):
                if not task1._running:
                    break
                time.sleep(0.05)

            final_file = store1.task_metadata[tid]["file_path"]
            with store1.lock:
                store1._save_history_locked()

            # Server updates content and ETag between runs!
            CrashMockServer.payload = PAYLOAD_2
            CrashMockServer.etag = "etag-v2"
            CrashMockServer.delay = 0.0

            store2 = TaskStore(history_file=hist_file)
            self.assertTrue(store2.resume_task(tid))

            for _ in range(100):
                if store2.task_metadata[tid]["status"] == "COMPLETED":
                    break
                time.sleep(0.1)

            self.assertEqual(store2.task_metadata[tid]["status"], "COMPLETED")
            self.assertTrue(os.path.exists(final_file))
            with open(final_file, "rb") as f:
                content = f.read()
            self.assertEqual(hashlib.sha256(content).hexdigest(), SHA256_2)

    def test_no_file_exists_at_final_name_until_completion(self):
        CrashMockServer.delay = 0.03
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "target.bin")
            task = DownloadTask(f"{self.url}/target.bin", output_path=out_file, num_connections=4)
            t = threading.Thread(target=task.start)
            t.start()

            # While downloading, check that final path does not exist
            time.sleep(0.3)
            self.assertFalse(os.path.exists(out_file), "Final target must not exist while downloading")
            self.assertTrue(os.path.exists(task.part_path), ".part path must exist while downloading")

            CrashMockServer.delay = 0.0
            t.join(15)

            self.assertEqual(task.status, "COMPLETED")
            self.assertTrue(os.path.exists(out_file), "Final target must exist after completion")
            self.assertFalse(os.path.exists(task.part_path), ".part path must be replaced on completion")

    def test_share_server_hides_veloce_part_and_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "video.mp4"), "wb") as f:
                f.write(b"data")
            with open(os.path.join(tmpdir, "video.mp4.veloce.part"), "wb") as f:
                f.write(b"partial")
            with open(os.path.join(tmpdir, "video.mp4.veloce.json"), "w") as f:
                f.write("{}")

            share = Share(tmpdir)
            entries = share.listing(tmpdir)
            names = [e["name"] for e in entries]
            self.assertIn("video.mp4", names)
            self.assertNotIn("video.mp4.veloce.part", names)
            self.assertNotIn("video.mp4.veloce.json", names)

            # Direct resolution should be rejected
            self.assertIsNone(share.resolve("video.mp4.veloce.part"))
            self.assertIsNone(share.resolve("video.mp4.veloce.json"))
            self.assertIsNotNone(share.resolve("video.mp4"))

    def test_cancel_removes_both_temp_files(self):
        CrashMockServer.delay = 0.02
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TaskStore(history_file=None)
            tid = store.create_task(f"{self.url}/cancel_test.bin", output_path=tmpdir, connections=4)
            time.sleep(0.4)

            task = store.tasks[tid]
            part = task.part_path
            sidecar = task.sidecar_path
            final_path = store.task_metadata[tid]["file_path"]

            self.assertTrue(os.path.exists(part), ".part should exist before cancel")
            self.assertTrue(os.path.exists(sidecar), ".json should exist before cancel")

            store.remove_task(tid)
            for _ in range(50):
                if not task._running:
                    break
                time.sleep(0.05)

            self.assertFalse(os.path.exists(part), ".part should be removed after cancel")
            self.assertFalse(os.path.exists(sidecar), ".json should be removed after cancel")
            self.assertFalse(os.path.exists(final_path), "Final file should not exist")


if __name__ == "__main__":
    unittest.main()
