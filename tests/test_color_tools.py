import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import color_tools as ct
import photo_crop as pc
from PIL import Image


class Engine(unittest.TestCase):
    def test_neutral_values_vanish(self):
        self.assertEqual(ct.norm_levels([(0, 1, 255, 0, 255)] * 4), ())
        self.assertEqual(ct.norm_curves([[(0, 0), (255, 255)]] * 4), ())
        self.assertEqual(ct.norm_selcol([(0, 0, 0)] * 6), ())
        self.assertEqual(pc.clean_adj({"levels": [], "curves": None, "selcol": "x"}), {})

    def test_levels_lut(self):
        row = (50.0, 1.0, 200.0, 0.0, 255.0)
        tab = ct.levels_lut(row)
        self.assertEqual((tab[50], tab[200], tab[0], tab[255]), (0, 255, 0, 255))
        self.assertTrue(all(tab[i] <= tab[i + 1] for i in range(255)))
        bright = ct.levels_lut((0.0, 2.0, 255.0, 0.0, 255.0))          # гамма > 1 осветляет средние тона
        self.assertGreater(bright[128], 128)

    def test_curve_lut_is_monotone_and_hits_points(self):
        pts = ((0, 0), (64, 40), (192, 220), (255, 255))
        tab = ct.curve_lut(pts)
        self.assertEqual([tab[0], tab[64], tab[192], tab[255]], [0, 40, 220, 255])
        self.assertTrue(all(tab[i] <= tab[i + 1] for i in range(255)))
        self.assertEqual(ct.curve_lut(ct.CURVE_NEUTRAL), list(range(256)))

    def test_json_roundtrip_and_hashable(self):
        a = pc.clean_adj({"levels": [(10, 1.2, 240, 0, 255), (0, 1, 255, 0, 255), (0, 1, 255, 0, 255), (0, 1, 255, 0, 255)],
                          "curves": [[(0, 0), (100, 80), (255, 255)]] + [[(0, 0), (255, 255)]] * 3,
                          "selcol": [(10, -20, 5)] + [(0, 0, 0)] * 5})
        back = pc.clean_adj(json.loads(json.dumps(a)))
        self.assertEqual(a, back)
        hash(tuple(sorted(pc.adj_full(back).items())))

    def test_pipeline(self):
        img = Image.new("RGB", (8, 8), (100, 100, 100))
        same = pc.adjust_color(img, {})
        self.assertEqual(same.getpixel((0, 0)), (100, 100, 100))
        lv = pc.adjust_color(img, pc.clean_adj({"levels": [(100, 1, 200, 0, 255)] + [(0, 1, 255, 0, 255)] * 3}))
        self.assertEqual(lv.getpixel((0, 0)), (0, 0, 0))                  # чёрная точка = 100
        cv = pc.adjust_color(img, pc.clean_adj({"curves": [[(0, 0), (100, 150), (255, 255)]] + [[(0, 0), (255, 255)]] * 3}))
        self.assertEqual(cv.getpixel((0, 0)), (150, 150, 150))

    def test_selective_color(self):
        red = Image.new("RGB", (4, 4), (200, 60, 60))
        gray = Image.new("RGB", (4, 4), (120, 120, 120))
        more = pc.adjust_color(red, pc.clean_adj({"selcol": [(0, 100, 0)] + [(0, 0, 0)] * 5}))
        r, g, b = more.getpixel((0, 0))
        self.assertGreater(r - g, 200 - 60)                               # красный стал насыщеннее
        same = pc.adjust_color(gray, pc.clean_adj({"selcol": [(0, 100, 50)] * 6}))
        self.assertEqual(same.getpixel((0, 0)), (120, 120, 120))          # серое не затронуто
        green = Image.new("RGB", (4, 4), (60, 200, 60))
        keep = pc.adjust_color(green, pc.clean_adj({"selcol": [(0, -100, 0)] + [(0, 0, 0)] * 5}))
        self.assertLess(abs(keep.getpixel((0, 0))[1] - 200), 6)           # настройка красного не трогает зелёное


if __name__ == "__main__":
    unittest.main()
