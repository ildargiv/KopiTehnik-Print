import hashlib
import http.server
import sys
import os
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import updater

PAYLOAD = b"MZ" + bytes(range(256)) * 4000


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.end_headers()
        self.wfile.write(PAYLOAD)

    def log_message(self, *a):
        pass


class UpdaterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = "http://127.0.0.1:%d/KopiTehnikPrint-Setup-9.9.9.exe" % cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def asset(self, **kw):
        a = {"name": "KopiTehnikPrint-Setup-9.9.9.exe", "url": self.url, "size": len(PAYLOAD),
             "sha256": hashlib.sha256(PAYLOAD).hexdigest()}
        a.update(kw)
        return a

    def test_assets_from_release(self):
        rel = {"assets": [
            {"name": "notes.txt", "browser_download_url": "http://x/notes.txt"},
            {"name": "KopiTehnikPrint-Setup-1.4.0.exe", "browser_download_url": "http://x/s.exe", "size": 5, "digest": "sha256:ABCD"},
            {"name": "PhotoCropQt.exe", "browser_download_url": "http://x/p.exe"}]}
        got = updater.assets_from_release(rel)
        self.assertEqual(list(got), ["setup"])
        self.assertEqual((got["setup"]["url"], got["setup"]["size"], got["setup"]["sha256"]), ("http://x/s.exe", 5, "abcd"))
        self.assertEqual(updater.assets_from_release({}), {})
        self.assertEqual(updater.assets_from_release({"assets": [{"name": "KopiTehnikPrint-Setup-1.exe"}]}), {})

    def test_download_ok_with_progress(self):
        seen = []
        with tempfile.TemporaryDirectory() as d:
            p = updater.download(self.asset(), d, progress=lambda a, b: seen.append((a, b)))
            self.assertEqual(p.read_bytes(), PAYLOAD)
            self.assertFalse(list(Path(d).glob("*.part")))
        self.assertEqual(seen[-1], (len(PAYLOAD), len(PAYLOAD)))

    def test_bad_checksum_and_size_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(updater.UpdateError):
                updater.download(self.asset(sha256="0" * 64), d)
            with self.assertRaises(updater.UpdateError):
                updater.download(self.asset(size=len(PAYLOAD) + 1), d)
            self.assertEqual(list(Path(d).iterdir()), [])          # битый файл не остаётся

    def test_cancel(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(updater.UpdateError):
                updater.download(self.asset(), d, cancelled=lambda: True)
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_script(self):
        s = updater.build_script(r"C:\Temp\Setup.exe", r"C:\Users\Я\KopiTehnik Print\PhotoCropQt.exe", 4321)
        self.assertIn("Wait-Process -Id 4321", s)
        self.assertIn("'C:\\Temp\\Setup.exe'", s)
        self.assertLess(s.index("/SILENT"), s.rindex("Start-Process"))      # сначала установка, потом запуск
        self.assertNotIn("RunAs", s)
        self.assertTrue(s.endswith("\r\n"))

    def test_script_elevated_and_quotes(self):
        s = updater.build_script(r"C:\Temp\it's.exe", r"C:\Program Files\KT\PhotoCropQt.exe", 7, elevate=True)
        self.assertIn("-Wait -Verb RunAs", s)
        self.assertIn("'C:\\Temp\\it''s.exe'", s)

    def test_needs_elevation(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(updater.needs_elevation(os.path.join(d, "app.exe")))

    def test_source_run_has_no_self_update(self):
        self.assertIsNone(updater.install_kind())
        self.assertIsNone(updater.pick_asset({"setup": {"name": "x"}}))


if __name__ == "__main__":
    unittest.main()
