import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import color_tools as ct
import photo_crop as pc
from PIL import Image, ImageStat


def photo(base, sky=False):
    im = Image.new("RGB", (240, 160), base)
    if sky:
        im.paste((70, 120, 210), (0, 0, 240, 70))
    return im


class EnhanceTest(unittest.TestCase):
    def run_enh(self, im, lvl):
        a = pc.enhance_adj(pc.analyze_image(im), lvl)
        out = pc.adjust_tile(im, pc.merge_adj({}, type("S", (), {"adj": a})()), 100, preview=True)
        return a, out

    def test_dark_photo_gets_lighter_never_darker(self):
        im = photo((60, 70, 80))
        for lvl in (1, 2):
            a, out = self.run_enh(im, lvl)
            self.assertGreater(ImageStat.Stat(out.convert("L")).mean[0], ImageStat.Stat(im.convert("L")).mean[0])

    def test_level2_is_stronger_than_level1(self):
        im = photo((70, 80, 90), sky=True)
        l1 = ImageStat.Stat(self.run_enh(im, 1)[1].convert("L")).mean[0]
        l2 = ImageStat.Stat(self.run_enh(im, 2)[1].convert("L")).mean[0]
        self.assertGreaterEqual(l2, l1)

    def test_sky_gets_selective_colour(self):
        a, _ = self.run_enh(photo((70, 80, 90), sky=True), 2)
        sel = ct.selcol_full(a.get("selcol"))
        self.assertGreater(sel[ct.SEL_COLORS.index("B")][1], 0)

    def test_levels_gamma_replaces_brightness_slider(self):
        a, _ = self.run_enh(photo((70, 80, 90)), 2)
        self.assertEqual(a.get("bright", 0), 0)
        self.assertGreater(ct.levels_full(a["levels"])[0][1], 1.0)

    def test_params_are_valid_and_clean(self):
        a, _ = self.run_enh(photo((120, 120, 120)), 2)
        self.assertEqual(a, pc.clean_adj(a))
        self.assertTrue(set(a) <= set(pc.NEUTRAL_ADJ))

    def test_halve_selcol_sat(self):
        sel = pc.halve_selcol_sat([(0, 0, 0), (0, 0, 0), (0, 10, 0), (0, 0, 0), (0, -6, 0), (0, 0, 0)])
        self.assertEqual(sel[2][1], 5.0)
        self.assertEqual(sel[4][1], -6.0)


if __name__ == "__main__":
    unittest.main()
