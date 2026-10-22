"""Поправка принтера: нормализация, нейтральность, действие на цвет, работа с профилем ICC и без него."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import color_tools as ct
import photo_crop as pc
from PIL import Image


class PrinterCorrectionTest(unittest.TestCase):
    def test_neutral(self):
        self.assertEqual(ct.norm_pcorr({}), {})
        self.assertEqual(ct.norm_pcorr({"tint": 0, "sel": [(0, 0, 0)] * 6}), {})
        self.assertEqual(ct.norm_pcorr("x"), {})
        self.assertEqual(ct.norm_pcorr({"tint": 500}), {"tint": 100.0})
        img = Image.new("RGB", (4, 4), (120, 130, 140))
        self.assertIs(ct.printer_correct(img, {}), img)

    def test_tint_and_warm(self):
        img = Image.new("RGB", (4, 4), (128, 128, 128))
        magenta = ct.printer_correct(img, {"tint": 50}).getpixel((0, 0))
        self.assertLess(magenta[1], 128)                      # меньше зелёного = пурпурнее
        self.assertEqual((magenta[0], magenta[2]), (128, 128))
        warm = ct.printer_correct(img, {"warm": 50}).getpixel((0, 0))
        self.assertGreater(warm[0], 128)
        self.assertLess(warm[2], 128)

    def test_zone_leaves_gray(self):
        gray = Image.new("RGB", (4, 4), (100, 100, 100))
        out = ct.printer_correct(gray, {"sel": [(0, 100, 50)] * 6})
        self.assertEqual(out.getpixel((0, 0)), (100, 100, 100))

    def test_without_icc_profile(self):
        img = Image.new("RGB", (4, 4), (128, 128, 128))
        cm = {"profile": None, "intent": 0, "flags": 0, "embed": False, "name": "x", "corr": {"tint": 50}}
        self.assertLess(pc.apply_printer_profile(img, None, cm).getpixel((0, 0))[1], 128)
        self.assertEqual(pc.apply_printer_profile(img, None, dict(cm, corr={})).getpixel((0, 0)), (128, 128, 128))


if __name__ == "__main__":
    unittest.main()

