"""Home-network sharing: only the downloads folder, only with the code, read-only."""

import http.client
import json
import os
import tempfile
import unittest

from engine.share import FREE_TRIES, Share


class ShareTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "Show"))
        with open(os.path.join(self.root, "Show", "Ep 1.mp4"), "wb") as f:
            f.write(b"v" * 1000)
        with open(os.path.join(self.root, "Show", "Ep 1.en.srt"), "w") as f:
            f.write("1\n00:00:01,000 --> 00:00:02,000\nHi\n")
        with open(os.path.join(self.root, "page.html"), "w") as f:
            f.write("<script>alert(1)</script>")
        for name in (".env", "half.iso.part"):
            with open(os.path.join(self.root, name), "w") as f:
                f.write("x")
        self.outside = tempfile.mkdtemp()
        with open(os.path.join(self.outside, "secret.txt"), "w") as f:
            f.write("secret")
        try:
            os.symlink(self.outside, os.path.join(self.root, "link"))
        except (OSError, NotImplementedError):
            pass
        self.share = Share(self.root)
        self.addCleanup(self.share.stop)

    def request(self, path, cookie=None, method="GET", headers=None):
        bind_host = self.share._server.server_address[0]
        host = "127.0.0.1" if bind_host in ("0.0.0.0", "") else bind_host
        conn = http.client.HTTPConnection(host, self.share._server.server_address[1], timeout=5)
        h = {"Host": host}
        if cookie:
            h["Cookie"] = cookie
        h.update(headers or {})
        conn.request(method, path, headers=h)
        resp = conn.getresponse()
        return resp, resp.read()

    def login(self):
        resp, _ = self.request(f"/auth?code={self.share.code}")
        self.assertEqual(resp.status, 200)
        return resp.getheader("Set-Cookie").split(";")[0]

    def test_off_until_started(self):
        self.assertEqual(self.share.status(), {"enabled": False})

    def test_paths_never_leave_the_folder(self):
        for rel in ("../etc/passwd", "link/secret.txt", ".env", "half.iso.part", "Show/../page.html", "/etc/passwd"):
            self.assertIsNone(self.share.resolve(rel), rel)
        self.assertTrue(self.share.resolve("Show/Ep 1.mp4"))

    def test_listing_hides_private_files_and_attaches_captions(self):
        names = [e["name"] for e in self.share.listing(self.share.root)]
        self.assertEqual(sorted(names), ["Show", "page.html"])
        video = self.share.listing(os.path.join(self.share.root, "Show"))
        self.assertEqual([e["name"] for e in video], ["Ep 1.mp4"])
        self.assertEqual(video[0]["captions"][0]["label"], "en")

    def test_code_required_and_read_only(self):
        self.share.start()
        resp, _ = self.request("/api/list")
        self.assertEqual(resp.status, 401)
        cookie = self.login()
        resp, body = self.request("/api/list", cookie)
        self.assertEqual(resp.status, 200)
        self.assertIn("Show", [e["name"] for e in json.loads(body)["entries"]])
        resp, _ = self.request("/f/page.html", cookie, method="POST")
        self.assertEqual(resp.status, 405)

    def test_streaming_ranges_and_safe_types(self):
        self.share.start()
        cookie = self.login()
        resp, body = self.request("/f/Show/Ep%201.mp4", cookie, headers={"Range": "bytes=10-19"})
        self.assertEqual((resp.status, len(body)), (206, 10))
        resp, _ = self.request("/f/page.html", cookie)
        self.assertEqual(resp.getheader("Content-Type"), "application/octet-stream")
        self.assertTrue(resp.getheader("Content-Disposition").startswith("attachment"))
        resp, body = self.request("/vtt/Show/Ep%201.en.srt", cookie)
        self.assertTrue(body.startswith(b"WEBVTT") and b"00:00:01.000" in body)

    def test_foreign_host_rejected(self):
        self.share.start()
        cookie = self.login()
        resp, _ = self.request("/api/list", cookie, headers={"Host": "evil.example"})
        self.assertEqual(resp.status, 421)

    def test_lockout_grows_and_new_code_signs_everyone_out(self):
        self.share.start()
        cookie = self.login()
        for _ in range(FREE_TRIES):
            self.assertIsNone(self.share.check_code("10.0.0.9", "WRONG1"))
        self.assertEqual(self.share.wait_left("10.0.0.9"), 0)
        self.share.check_code("10.0.0.9", "WRONG1")
        self.assertGreater(self.share.wait_left("10.0.0.9"), 0)
        self.assertIsNone(self.share.check_code("10.0.0.9", self.share.code))  # locked even with the right code
        old = self.share.code
        self.share.new_code()
        self.assertNotEqual(self.share.code, old)
        resp, _ = self.request("/api/list", cookie)
        self.assertEqual(resp.status, 401)

    def test_devices_are_listed_and_can_be_disconnected(self):
        self.share.start()
        iphone = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
        resp, _ = self.request(f"/auth?code={self.share.code}", headers={"User-Agent": iphone})
        cookie = resp.getheader("Set-Cookie").split(";")[0]
        self.request("/f/Show/Ep%201.mp4", cookie, headers={"Range": "bytes=0-99"})
        [device] = self.share.status()["devices"]
        self.assertEqual((device["name"], device["browser"], device["kind"]), ("iPhone", "Safari", "phone"))
        self.assertEqual(device["playing"]["name"], "Ep 1.mp4")
        self.assertEqual(device["bytes"], 100)
        self.share.disconnect(device["id"])
        self.assertEqual(self.share.status()["devices"], [])
        resp, _ = self.request("/api/list", cookie)
        self.assertEqual(resp.status, 401)

    def test_stop_ends_sessions(self):
        self.share.start()
        self.login()
        self.share.stop()
        self.assertEqual(self.share.sessions, {})
        self.assertFalse(self.share.status()["enabled"])


if __name__ == "__main__":
    unittest.main()
