# -*- coding: utf-8 -*-
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image

import printer_corr as pcr


def px(img, xy=(0, 0)):
    return img.getpixel(xy)


class PrinterCorrTests(unittest.TestCase):
    def test_default_is_neutral_and_json_safe(self):
        c = pcr.default()
        self.assertTrue(pcr.is_neutral(c))
        self.assertFalse(pcr.active(c))
        self.assertEqual(pcr.norm(json.loads(json.dumps(c))), c)

    def test_norm_clamps_and_ignores_junk(self):
        c = pcr.norm({"on": 1, "tone": {"mids": [500, "x"], "bogus": [1, 1]}, "gamma": "abc", "sel": [[1, 2]], "sat": -999})
        self.assertTrue(c["on"])
        self.assertEqual(c["tone"]["mids"], [100.0, 0.0])
        self.assertEqual(c["gamma"], 0.0)
        self.assertEqual(c["sat"], -100.0)
        self.assertEqual(c["sel"], pcr.default()["sel"])
        self.assertEqual(pcr.norm("junk"), pcr.default())

    def test_off_or_neutral_returns_same_image(self):
        im = Image.new("RGB", (4, 4), (120, 130, 140))
        self.assertIs(pcr.apply(im, pcr.default()), im)
        c = pcr.default()
        c["tone"]["mids"] = [50, 0]
        self.assertIs(pcr.apply(im, c), im)          # выключена
        c["on"] = True
        self.assertIsNot(pcr.apply(im, c), im)

    def test_white_and_black_stay_put(self):
        c = pcr.norm({"on": True, "tone": {z: [100, -100] for z in pcr.ZONES}, "gamma": 80, "sat": 60,
                      "sel": [[100, 100, 100]] * 6})
        im = Image.new("RGB", (2, 1))
        im.putpixel((0, 0), (255, 255, 255))
        im.putpixel((1, 0), (0, 0, 0))
        out = pcr.apply(im, c)
        self.assertEqual(px(out, (0, 0)), (255, 255, 255))
        self.assertEqual(px(out, (1, 0)), (0, 0, 0))

    def test_warm_shift_moves_grey_toward_red(self):
        c = pcr.default()
        c["on"] = True
        c["tone"]["mids"] = [100, 0]
        out = px(pcr.apply(Image.new("RGB", (1, 1), (128, 128, 128)), c))
        self.assertGreater(out[0], 128)
        self.assertLess(out[2], 128)
        self.assertEqual(out[1], 128)

    def test_tint_magenta_lowers_green(self):
        c = pcr.default()
        c["on"] = True
        c["tone"]["mids"] = [0, 100]
        out = px(pcr.apply(Image.new("RGB", (1, 1), (128, 128, 128)), c))
        self.assertLess(out[1], 128)
        self.assertGreater(out[0], 128)

    def test_zone_changes_stay_local(self):
        c = pcr.default()
        c["on"] = True
        c["tone"]["lights"] = [100, 0]
        shadow = px(pcr.apply(Image.new("RGB", (1, 1), (30, 30, 30)), c))
        light = px(pcr.apply(Image.new("RGB", (1, 1), (210, 210, 210)), c))
        self.assertLessEqual(abs(shadow[0] - 30), 3)
        self.assertGreater(light[0] - 210, 6)

    def test_curves_are_monotonic(self):
        c = pcr.norm({"on": True, "tone": {"shadows": [100, 100], "mids": [-100, -100], "lights": [100, -100]}, "gamma": -100})
        for tab in pcr.tone_luts(c):
            self.assertEqual(tab[0], 0)
            self.assertEqual(tab[255], 255)
            self.assertTrue(all(b >= a for a, b in zip(tab, tab[1:])))

    def test_selective_hue_only_touches_that_colour(self):
        c = pcr.default()
        c["on"] = True
        c["sel"][5] = [0, -100, 0]                   # пурпурный: насыщенность вниз
        magenta = px(pcr.apply(Image.new("RGB", (1, 1), (200, 60, 200)), c))
        green = px(pcr.apply(Image.new("RGB", (1, 1), (60, 200, 60)), c))
        self.assertLess(max(magenta) - min(magenta), 200 - 60)
        self.assertEqual(green, (60, 200, 60))

    def test_test_page_size_and_content(self):
        im = pcr.make_test_page(100, 150, 100)
        self.assertEqual(im.size, (394, 591))
        self.assertGreater(len(im.getcolors(100000) or []), 20)


if __name__ == "__main__":
    unittest.main()
