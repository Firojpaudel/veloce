"""
Phase 2 Engine Test Coverage:
- split_largest_segment picks the segment that finishes last, not the largest.
- Concurrent splitting never produces overlapping or missing byte ranges under many threads.
- shed_slow_connections drops a connection slower than best / 4 after grace period.
- Server answering 200 to ranged request raises RangeNotSupported, task in ERROR, no corrupt file.
- Server closing segment early is retried, resulting in an intact final file.
- Adaptive mode stays on one connection for small/fast downloads.
"""

import _isolate  # noqa: F401  (must run before engine imports)

import hashlib
import os
import random
import socket
import struct
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from engine.segmenter import (
    DownloadTask,
    SegmentManager,
    Segment,
    RangeNotSupported,
    MIN_SPLIT_SIZE,
    SHED_GRACE,
    SHED_RATIO,
)

PAYLOAD_TEST = os.urandom(3 * 1024 * 1024 + 101)
PAYLOAD_SHA = hashlib.sha256(PAYLOAD_TEST).hexdigest()


class ControlledCoverageServer(BaseHTTPRequestHandler):
    mode = "normal"  # "normal", "drop_early_once", "return_200_on_range"
    dropped_segments = set()
    request_count = 0
    lock = threading.Lock()

    def log_message(self, *args):
        pass

    def do_GET(self):
        with type(self).lock:
            type(self).request_count += 1
            mode = type(self).mode

        rng = self.headers.get("Range")
        total = len(PAYLOAD_TEST)

        if not rng:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(total))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            try:
                self.wfile.write(PAYLOAD_TEST)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        # Ranged request
        start, _, end = rng.replace("bytes=", "").partition("-")
        start = int(start)
        end = min(int(end or total - 1), total - 1)
        chunk = PAYLOAD_TEST[start:end + 1]

        if mode == "return_200_on_range":
            # If start == 0 and end == total - 1, it's probe -> answer 206 so inspect succeeds
            if start == 0 and end == total - 1:
                self.send_response(206)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                try:
                    self.wfile.write(chunk)
                except OSError:
                    pass
                return
            # Subsequent ranged requests get 200 full body (ignoring range)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(total))
            self.end_headers()
            try:
                self.wfile.write(PAYLOAD_TEST)
            except OSError:
                pass
            return

        if mode == "drop_early_once" and start > 0:
            with type(self).lock:
                should_drop = start not in type(self).dropped_segments
                if should_drop:
                    type(self).dropped_segments.add(start)
            if should_drop:
                # Send 206 header and partial chunk, then close connection early
                self.send_response(206)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
                self.send_header("Content-Length", str(len(chunk)))
                self.end_headers()
                try:
                    self.wfile.write(chunk[:8192])
                    self.wfile.flush()
                except OSError:
                    pass
                self.close_connection = True
                # Hard reset (RST) so the client fails fast instead of waiting for a read timeout
                try:
                    self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                    self.connection.close()
                except OSError:
                    pass
                return

        self.send_response(206)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        self.send_header("Content-Length", str(len(chunk)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        try:
            self.wfile.write(chunk)
        except OSError:
            pass


class TestEngineCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ControlledCoverageServer)
        cls.server.daemon_threads = True
        cls.port = cls.server.server_port
        cls.url = f"http://127.0.0.1:{cls.port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        ControlledCoverageServer.mode = "normal"
        ControlledCoverageServer.dropped_segments = set()
        ControlledCoverageServer.request_count = 0

    def test_split_picks_segment_finishing_last_not_largest(self):
        # 50 MB total, 2 segments
        total_size = 50 * 1024 * 1024
        mgr = SegmentManager(total_size, 2)

        seg0 = mgr.get_idle_segment()
        seg1 = mgr.get_idle_segment()
        self.assertIsNotNone(seg0)
        self.assertIsNotNone(seg1)

        now = time.monotonic()
        # Seg0: 10 MB remaining, running fast at 10 MB/s -> finishes in 1.0s
        seg0.current = seg0.start + 15 * 1024 * 1024
        seg0.end = seg0.start + 25 * 1024 * 1024 - 1
        seg0.assigned_at = now - 1.0
        seg0.assigned_from = seg0.current - 10 * 1024 * 1024

        # Seg1: 4 MB remaining, running slow at 0.5 MB/s -> finishes in 8.0s
        seg1.current = seg1.start + 21 * 1024 * 1024
        seg1.end = seg1.start + 25 * 1024 * 1024 - 1
        seg1.assigned_at = now - 2.0
        seg1.assigned_from = seg1.current - 1 * 1024 * 1024

        self.assertGreater(seg0.remaining, seg1.remaining, "Seg0 has more remaining bytes than Seg1")

        # split_largest_segment should pick seg1 because its ETA is 8s vs seg0's 1s
        new_seg = mgr.split_largest_segment()
        self.assertIsNotNone(new_seg)
        # Verify new_seg came from seg1 (range within seg1's initial boundary)
        self.assertGreaterEqual(new_seg.start, seg1.start)
        self.assertLessEqual(new_seg.end, seg1.start + 25 * 1024 * 1024 - 1)

    def test_concurrent_splitting_range_integrity(self):
        total_size = 100 * 1024 * 1024  # 100 MB
        mgr = SegmentManager(total_size, 4)

        # Initially 4 idle segments
        for _ in range(4):
            mgr.get_idle_segment()

        threads = []
        stop_event = threading.Event()

        def worker_churn():
            while not stop_event.is_set():
                action = random.choice(["split", "progress", "idle"])
                if action == "split":
                    mgr.split_largest_segment()
                elif action == "progress":
                    with mgr.lock:
                        for s in mgr.segments:
                            if s.active and not s.completed and s.current < s.end:
                                s.current = min(s.end + 1, s.current + 64 * 1024)
                time.sleep(0.001)

        for _ in range(16):
            t = threading.Thread(target=worker_churn)
            t.daemon = True
            t.start()
            threads.append(t)

        time.sleep(0.5)
        stop_event.set()
        for t in threads:
            t.join()

        # Verify range integrity under mgr.lock
        with mgr.lock:
            sorted_segs = sorted(mgr.segments, key=lambda s: s.start)
            self.assertEqual(sorted_segs[0].start, 0)
            self.assertEqual(sorted_segs[-1].end, total_size - 1)

            total_covered = 0
            for i in range(len(sorted_segs) - 1):
                cur = sorted_segs[i]
                nxt = sorted_segs[i + 1]
                self.assertEqual(
                    cur.end + 1,
                    nxt.start,
                    f"Segment {cur.segment_id} and {nxt.segment_id} must be contiguous with no overlap/gap",
                )
                total_covered += cur.end - cur.start + 1
            total_covered += sorted_segs[-1].end - sorted_segs[-1].start + 1

            self.assertEqual(total_covered, total_size, "Union of segments must exactly match total_size")

    def test_shed_slow_connections(self):
        total_size = 20 * 1024 * 1024
        mgr = SegmentManager(total_size, 2)

        s0 = mgr.get_idle_segment()
        s1 = mgr.get_idle_segment()
        self.assertIsNotNone(s0)
        self.assertIsNotNone(s1)

        now = time.monotonic()
        # s0 is fast: 2 MB/s
        s0.assigned_at = now - (SHED_GRACE + 1.0)
        s0.assigned_from = s0.current - int(2 * 1024 * 1024 * (SHED_GRACE + 1.0))

        # s1 is slow: 50 KB/s (far below best / 4)
        s1.assigned_at = now - (SHED_GRACE + 1.0)
        s1.assigned_from = s1.current - int(50 * 1024 * (SHED_GRACE + 1.0))

        shed_count = mgr.shed_slow_connections()
        self.assertEqual(shed_count, 1)
        self.assertTrue(s1.shed)
        self.assertFalse(s0.shed)

    def test_server_answering_200_to_range_fails_cleanly(self):
        ControlledCoverageServer.mode = "return_200_on_range"
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "bad_server.bin")
            task = DownloadTask(f"{self.url}/test.bin", output_path=out_file, num_connections=4, adaptive=False)

            with self.assertRaises((RangeNotSupported, IOError)):
                task.start()

            self.assertEqual(task.status, "ERROR")
            self.assertFalse(os.path.exists(out_file), "No corrupt file must exist at final path")

    def test_server_closing_segment_early_is_retried(self):
        ControlledCoverageServer.mode = "drop_early_once"
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "retry_test.bin")
            task = DownloadTask(f"{self.url}/test.bin", output_path=out_file, num_connections=4, adaptive=False)
            task.start()

            self.assertEqual(task.status, "COMPLETED")
            self.assertTrue(os.path.exists(out_file))
            with open(out_file, "rb") as f:
                data = f.read()
            self.assertEqual(hashlib.sha256(data).hexdigest(), PAYLOAD_SHA)
            self.assertTrue(len(ControlledCoverageServer.dropped_segments) > 0, "At least one segment was dropped and retried")

    def test_adaptive_mode_stays_on_one_connection_for_fast_file(self):
        # A small 64 KB payload served near instantly
        small_payload = b"X" * (64 * 1024)
        server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        
        class SmallHandler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(small_payload)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.wfile.write(small_payload)

        server.RequestHandlerClass = SmallHandler
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                out = os.path.join(tmpdir, "small.bin")
                task = DownloadTask(f"http://127.0.0.1:{server.server_port}/small.bin", output_path=out, num_connections=8, adaptive=True)
                task.start()

                self.assertEqual(task.status, "COMPLETED")
                # Single-stream probe-stream reuse -> manager is None or has 1 segment
                seg_count = len(task.manager.segments) if task.manager else 1
                self.assertEqual(seg_count, 1, "Small/fast download must remain on 1 connection")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
