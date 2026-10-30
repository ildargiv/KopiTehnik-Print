# -*- coding: utf-8 -*-
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageFont

import test_sheet as ts

SIZES = ((100, 150), (148, 210), (210, 297))


def center(b):
    return ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)


def luma(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


class TestSheetTests(unittest.TestCase):
    def setUp(self):
        ts._FONTS.clear()

    def test_sizes_and_mode(self):
        for w, h in SIZES:
            im = ts.build(w, h)
            self.assertEqual(im.mode, "RGB")
            self.assertEqual(im.size, (round(w / 25.4 * 300), round(h / 25.4 * 300)))
        self.assertEqual(ts.build(210, 297).size, (2480, 3508))
        self.assertEqual(ts.build(150, 100).size, (1772, 1181))     # альбомный 10×15 — повёрнутый книжный

    def test_compact_and_windows(self):
        self.assertTrue(ts.layout(100, 150)["compact"])
        self.assertEqual(len(ts.layout(100, 150)["windows"]), 1)
        self.assertEqual(len(ts.layout(210, 297)["windows"]), 3)
        self.assertIn(len(ts.layout(148, 210)["windows"]), (2, 3))
        for w, h in SIZES:
            for b in ts.layout(w, h)["windows"]:
                self.assertGreater(b[3] - b[1], b[2] - b[0])           # окна вертикальные

    def test_wedge_monotonic(self):
        for w, h in SIZES:
            im = ts.build(w, h)
            vals = [im.getpixel(center(b)) for b in ts.layout(w, h)["wedge_cells"]]
            self.assertEqual(len(vals), 21)
            self.assertTrue(all(v[0] == v[1] == v[2] for v in vals))
            g = [v[0] for v in vals]
            self.assertEqual((g[0], g[-1]), (0, 255))
            self.assertTrue(all(a < b for a, b in zip(g, g[1:])))

    def test_skin_patches_get_darker(self):
        for w, h in SIZES:
            im = ts.build(w, h)
            cells = ts.layout(w, h)["skin_cells"]
            self.assertEqual(len(cells), 12)
            got = [im.getpixel(center(b)) for b in cells]
            want = [c for _n, light, dark in ts.SKIN for c in (light, dark)]
            self.assertEqual(got, want)
            ys = [luma(c) for c in got]                              # I светлее → VI темнее
            self.assertTrue(all(a > b for a, b in zip(ys, ys[1:])))

    def test_portraits_pasted(self):
        blue = Image.new("RGB", (300, 300), (0, 0, 255))
        for w, h in SIZES:
            im = ts.build(w, h, portraits=[blue])
            b = ts.layout(w, h)["windows"][0]
            self.assertEqual(im.getpixel(center(b)), (0, 0, 255))
            self.assertEqual(im.getpixel((b[0] + 2, b[1] + 2)), (0, 0, 255))   # заполнено до края окна

    def test_portrait_crop_keeps_aspect(self):
        wide = Image.new("RGB", (900, 300), (255, 0, 0))
        wide.paste((0, 0, 255), (300, 0, 600, 300))                  # синяя середина, красные края
        im = ts.build(210, 297, portraits=[wide])
        b = ts.layout(210, 297)["windows"][0]
        self.assertEqual(im.getpixel(center(b)), (0, 0, 255))
        self.assertEqual(im.getpixel((b[0] + 1, center(b)[1])), (0, 0, 255))  # края обрезаны, не сжаты

    def test_without_portraits_placeholder(self):
        im = ts.build(148, 210, portraits=None, title="Тест", icc_name="Epson Glossy")
        b = ts.layout(148, 210)["windows"][0]
        self.assertEqual(im.getpixel((b[0] + (b[2] - b[0]) // 4, b[1] + (b[3] - b[1]) // 4)), (236, 236, 236))

    def test_no_font_available(self):
        def boom(*a, **k):
            raise OSError("нет шрифта")
        with mock.patch.object(ts, "FONT_FILES", ("нет-такого.ttf",)), mock.patch.object(ImageFont, "truetype", boom):
            ts._FONTS.clear()
            for w, h in SIZES:
                im = ts.build(w, h, icc_name="Профиль")
                self.assertEqual(im.mode, "RGB")
        ts._FONTS.clear()


if __name__ == "__main__":
    unittest.main()
