# -*- coding: utf-8 -*-
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image

import photo_crop as pc

PAPER = (100.0, 150.0)          # 10×15, мм


class PhotoModeTests(unittest.TestCase):
    def test_default_follows_global(self):
        st = pc.CropState()
        self.assertIsNone(st.mode)
        self.assertEqual(pc.photo_mode(st, "crop"), "crop")
        self.assertEqual(pc.photo_mode(st, "fit"), "fit")

    def test_own_mode_wins(self):
        st = pc.CropState()
        st.mode = "fit"
        self.assertEqual(pc.photo_mode(st, "crop"), "fit")
        st.mode = "crop"
        self.assertEqual(pc.photo_mode(st, "fit"), "crop")

    def test_effective_dpi_uses_own_mode_only(self):
        a, b = pc.CropState(), pc.CropState()
        a.scale = b.scale = 0.5                                          # рамка вдвое меньше: в режиме «кадрировать» dpi выше
        b.mode = "fit"
        W, H = 3000, 2000
        crop = pc.effective_dpi(W, H, PAPER, a, "crop")
        fit = pc.effective_dpi(W, H, PAPER, b, "crop")
        self.assertAlmostEqual(pc.effective_dpi(W, H, PAPER, a, "fit"), fit, places=3)     # без личного режима — общий
        self.assertNotAlmostEqual(crop, fit, places=1)

    def test_render_fit_keeps_whole_photo_on_white(self):
        img = Image.new("RGB", (300, 200), (200, 30, 30))
        st = pc.CropState()
        st.mode = "fit"
        out, _ = pc.render(img, PAPER, st, "crop", 100, True)
        self.assertEqual(out.size[0] / out.size[1], PAPER[0] / PAPER[1])
        self.assertEqual(out.getpixel((0, 0)), (255, 255, 255))          # белое поле сверху
        st2 = pc.CropState()
        out2, _ = pc.render(img, PAPER, st2, "crop", 100, True)
        self.assertEqual(out2.getpixel((0, 0)), (200, 30, 30))           # кадрирование: фото до самого края

    def test_copy_and_project_roundtrip(self):
        st = pc.CropState()
        st.mode = "fit"
        self.assertEqual(st.copy().mode, "fit")
        d = json.loads(json.dumps({k: getattr(st, k) for k in pc.CropState.__slots__}))
        self.assertEqual(d["mode"], "fit")

    def test_junk_mode_is_cleaned(self):
        st = pc.CropState()
        st.mode = "bogus"
        pc._sanitize_state(st)
        self.assertIsNone(st.mode)


if __name__ == "__main__":
    unittest.main()
