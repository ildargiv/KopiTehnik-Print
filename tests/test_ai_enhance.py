import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from PIL import Image

import ai_enhance as ae


def _nearest(t, s=4):
    return t.repeat(s, axis=2).repeat(s, axis=3)


class Tiled(unittest.TestCase):
    def test_tiles_equal_whole(self):
        rng = np.random.default_rng(1)
        arr = rng.random((37, 53, 3), dtype=np.float32)
        out = ae.run_tiled(_nearest, arr, 4, tile=16, pad=3)
        self.assertEqual(out.shape, (148, 212, 3))
        np.testing.assert_array_equal(out, arr.repeat(4, 0).repeat(4, 1))

    def test_progress_and_cancel(self):
        arr = np.zeros((40, 40, 3), np.float32)
        seen = []
        ae.run_tiled(_nearest, arr, 4, tile=16, progress=seen.append)
        self.assertEqual(seen[-1], 1.0)
        with self.assertRaises(ae.Cancelled):
            ae.run_tiled(_nearest, arr, 4, tile=16, cancel=lambda: True)


class Fallback(unittest.TestCase):
    def test_no_model_falls_back_to_lanczos(self):
        img = Image.new("RGB", (30, 20), (10, 200, 30))
        with tempfile.TemporaryDirectory() as d:
            out, used = ae.enhance(img, models_dir=d)
        self.assertFalse(used)
        self.assertEqual(out.size, (120, 80))

    def test_target_size(self):
        img = Image.new("RGB", (30, 20))
        with tempfile.TemporaryDirectory() as d:
            out, _ = ae.enhance(img, models_dir=d, target_size=(100, 70))
        self.assertEqual(out.size, (100, 70))


class Download(unittest.TestCase):
    def test_requires_license_and_manifest(self):
        with self.assertRaises(PermissionError):
            ae.download_model(ae.DEFAULT_MODEL)       # без принятия лицензии

    def test_sha256(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x"
            p.write_bytes(b"abc")
            self.assertEqual(ae.sha256_file(p), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_needed_factor(self):
        self.assertAlmostEqual(ae.needed_factor((640, 480), (2480, 3508)), 7.31, places=1)


if __name__ == "__main__":
    unittest.main()
