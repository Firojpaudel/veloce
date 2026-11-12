"""
Unit tests for Veloce Dynamic Segmenter Engine.
"""

import _isolate  # noqa: F401  (must run before engine imports)

import os
import tempfile
import unittest
from engine.segmenter import SegmentManager, Segment

class TestVeloceSegmenter(unittest.TestCase):
    def test_segment_initialization(self):
        total_size = 100 * 1024 * 1024  # 100 MB
        connections = 8
        mgr = SegmentManager(total_size, connections)
        
        self.assertEqual(len(mgr.segments), 8)
        self.assertEqual(mgr.segments[0].start, 0)
        self.assertEqual(mgr.segments[-1].end, total_size - 1)

    def test_dynamic_segment_splitting(self):
        # 50 MB total, 2 initial connections
        total_size = 50 * 1024 * 1024
        mgr = SegmentManager(total_size, 2)

        # Worker 1 takes segment 0
        seg1 = mgr.get_idle_segment()
        self.assertIsNotNone(seg1)
        self.assertEqual(seg1.segment_id, 0)

        # Worker 2 takes segment 1
        seg2 = mgr.get_idle_segment()
        self.assertIsNotNone(seg2)
        self.assertEqual(seg2.segment_id, 1)

        # Simulate Worker 1 finishing early
        seg1.current = seg1.end + 1
        mgr.mark_completed(seg1)

        # Worker 1 is now idle and tries to split Worker 2's unfinished segment
        new_seg = mgr.split_largest_segment()
        self.assertIsNotNone(new_seg)
        # Verify new segment took the upper half of seg2
        self.assertEqual(new_seg.segment_id, 2)
        self.assertEqual(new_seg.start, seg2.end + 1)
        self.assertTrue(new_seg.active)

if __name__ == "__main__":
    unittest.main()
