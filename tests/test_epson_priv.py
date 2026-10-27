# -*- coding: utf-8 -*-
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import epson_priv as ep


def blob(extra=8000, size=220):
    b = bytearray(size + extra)
    struct.pack_into("<HH", b, 68, size, extra)
    return bytes(b)


class EpsonPrivTests(unittest.TestCase):
    def test_model(self):
        self.assertEqual(ep.model_of("EPSON L8050 Series (копия 1)"), "L8050")
        self.assertEqual(ep.model_of("EPSON L18050 Series"), "L18050")
        self.assertIsNone(ep.model_of("HP LaserJet 1020"))

    def test_renamed_queue_uses_model_from_driver(self):
        e = ep.EpsonPriv("Принтер в цехе", driver_name="EPSON L8050 Series")
        self.assertEqual(e.model, "L8050")
        self.assertTrue(e.supported("border") and e.supported("quality") and e.supported("maint"))
        self.assertIsNone(ep.EpsonPriv("Принтер в цехе").model)
        self.assertIsNone(ep.EpsonPriv("Принтер в цехе", driver_name="HP Universal").model)

    def test_unknown_model_changes_nothing(self):
        e = ep.EpsonPriv("EPSON L18050 Series")
        b = blob()
        self.assertTrue(e.supported("quality"))
        self.assertTrue(e.supported("border"))
        self.assertTrue(e.supported("maint"))
        e2 = ep.EpsonPriv("EPSON L3250 Series")
        self.assertFalse(e2.supported("border"))
        self.assertEqual(e2.set(b, "border", True), b)
        self.assertIsNone(e2.get(b, "border"))

    def test_border_roundtrip(self):
        e = ep.EpsonPriv("EPSON L8050 Series")
        b = e.set(blob(), "border", True)
        self.assertTrue(e.get(b, "border"))
        self.assertEqual(struct.unpack_from("<H", b, 88)[0], ep.SRC_BORDERLESS)
        b = e.set(b, "border", False)
        self.assertFalse(e.get(b, "border"))
        self.assertEqual(struct.unpack_from("<H", b, 88)[0], ep.SRC_NORMAL)

    def test_ccor(self):
        e = ep.EpsonPriv("EPSON L8050 Series")
        b = e.set_color_correction_off(blob())
        self.assertTrue(e.color_correction_off(b))
        self.assertFalse(e.color_correction_off(e.set_color_correction_off(b, False)))

    def test_quality(self):
        e = ep.EpsonPriv("EPSON L18050 Series")
        b = blob()
        for v in (2, 1, 0):
            b = e.set(b, "quality", v)
            self.assertEqual(e.get(b, "quality"), v)
        self.assertEqual(b[220 + 7788], 0)

    def test_quality_sets_plain_and_photo(self):
        e = ep.EpsonPriv("EPSON L8050 Series")
        b = bytearray(blob())
        struct.pack_into("<I", b, 196, 1)
        b = e.set(bytes(b), "quality", 2)
        self.assertEqual((b[220 + 124], b[220 + 150], b[220 + 154], b[220 + 7788]), (3, 4, 0x22, 2))
        b = bytearray(b)
        struct.pack_into("<I", b, 196, 396)
        b[220 + 2088] = 0x10
        b = e.set(bytes(b), "quality", 1)
        self.assertEqual((b[220 + 124], b[220 + 154], b[220 + 7788]), (3, 0x20, 1))
        d = ep.EpsonPriv("EPSON L18050 Series").set(blob(), "quality", 0)
        self.assertEqual((d[220 + 124], d[220 + 7765], d[90], d[91]), (2, 0x40, 0x68, 1))

    def test_plain_a5_uses_plain_set_despite_2088(self):
        b = bytearray(blob())
        struct.pack_into("<I", b, 196, 1)
        b[220 + 2088] = 0x10                      # A5: драйвер ставит 0x10 и на простой бумаге
        b = ep.EpsonPriv("EPSON L8050 Series").set(bytes(b), "quality", 2)
        self.assertEqual((b[220 + 124], b[220 + 154]), (3, 0x22))

    def test_l18050_draft_only_on_photo(self):
        e = ep.EpsonPriv("EPSON L18050 Series")
        b = bytearray(blob())
        struct.pack_into("<I", b, 196, 1)
        self.assertEqual([v for v, _ in e.quality_modes(bytes(b))], [1, 2])
        struct.pack_into("<I", b, 196, 396)
        self.assertEqual([v for v, _ in e.quality_modes(bytes(b))], [0, 1, 2])
        self.assertEqual(e.set(bytes(b), "quality", 2)[220 + 124], 5)
        struct.pack_into("<I", b, 196, 1)
        self.assertEqual(e.set(bytes(b), "quality", 2)[220 + 124], 3)

    def test_l8050_high_hidden_on_unsupported_media(self):
        e = ep.EpsonPriv("EPSON L8050 Series")
        b = bytearray(blob())
        for media, want in ((1, [1, 2]), (396, [1, 2]), (326, [1, 2]), (828, [1]), (318, [1]), (338, [1]), (353, [1])):
            struct.pack_into("<I", b, 196, media)
            self.assertEqual([v for v, _ in e.quality_modes(bytes(b))], want, media)

    def test_quality_modes_per_model(self):
        self.assertEqual([v for v, _ in ep.EpsonPriv("EPSON L8050 Series").quality_modes()], [1, 2])
        self.assertEqual([v for v, _ in ep.EpsonPriv("EPSON L18050 Series").quality_modes()], [0, 1, 2])
        self.assertEqual(ep.EpsonPriv("EPSON L3250 Series").quality_modes(), [])

    def test_maintenance_job(self):
        j = ep.maintenance_job("nozzle_check")
        self.assertTrue(j.startswith(b"\x1b@\x1b(R") and j.endswith(b"\x1b@"))
        self.assertIn(b"REMOTE1NC", j)
        self.assertIn(b"REMOTE1CH", ep.maintenance_job("clean"))
        with self.assertRaises(ValueError):
            ep.EpsonPriv("EPSON L3250 Series").maintenance("EPSON L3250 Series", "clean")

    def test_short_devmode_raises(self):
        e = ep.EpsonPriv("EPSON L8050 Series")
        with self.assertRaises(ValueError):
            e.get(blob(extra=10), "border")

    def test_extra_profiles(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.json")
            json.dump({"L18050": {"border": 100, "ccor": 50}}, open(p, "w"))
            e = ep.EpsonPriv("EPSON L18050 Series", ep.load_profiles(p))
            self.assertTrue(e.supported("quality"))
            self.assertTrue(e.supported("border"))




class RecipeModelTests(unittest.TestCase):
    def blob(self, model):
        extra = 3704 if model.startswith("L") and model != "1410" else 796
        b = bytearray(220 + extra)
        struct.pack_into("<HH", b, 68, 220, extra)
        struct.pack_into("<H", b, 90, 360)
        struct.pack_into("<H", b, 88, 261 if extra == 3704 else 7)
        struct.pack_into("<I", b, 196, 1)
        return bytes(b)

    def test_model_names(self):
        for name, m in (("EPSON Stylus Photo 1410 Series", "1410"), ("EPSON Stylus Photo R290 Series", "R290"),
                        ("EPSON TX650 Series", "TX650"), ("EPSON L805 Series", "L805"), ("EPSON PX660 Series", "PX660")):
            self.assertEqual(ep.model_of(name), m)

    def test_quality_and_border_roundtrip(self):
        for m in ep.RECIPES:
            e = ep.EpsonPriv("EPSON %s Series" % m)
            self.assertTrue(e.supported("quality") and e.supported("border"), m)
            self.assertFalse(e.supported("ccor"), m)
            self.assertTrue(e.supported("maint"), m)
            b = self.blob(m)
            self.assertEqual(e.get(b, "quality"), 1)
            b = e.set(b, "quality", 2)
            self.assertEqual(e.get(b, "quality"), 2)
            b = e.set(b, "border", True)
            self.assertTrue(e.get(b, "border"))
            b = e.set(b, "border", False)
            self.assertFalse(e.get(b, "border"))

    def test_1410_borderless_switches_to_photo_media(self):
        e = ep.EpsonPriv("EPSON Stylus Photo 1410 Series")
        b = e.set(self.blob("1410"), "border", True)
        self.assertEqual(struct.unpack_from("<I", b, 196)[0], 359)


class MediaMirrorTests(unittest.TestCase):
    def test_media_written_in_both_places(self):
        e = ep.EpsonPriv("EPSON T50 Series")
        b = bytearray(220 + 796)
        struct.pack_into("<HH", b, 68, 220, 796)
        b = e.set_media(bytes(b), 271)
        self.assertEqual(struct.unpack_from("<I", b, 196)[0], 271)
        self.assertEqual(struct.unpack_from("<H", b, 220 + 116)[0], 271)

    def test_old_family_photo_media_only_high_quality(self):
        e = ep.EpsonPriv("EPSON T50 Series")
        b = bytearray(220 + 796)
        struct.pack_into("<HH", b, 68, 220, 796)
        struct.pack_into("<I", b, 196, 1)
        self.assertGreater(len(e.quality_modes(bytes(b))), 1)
        b = e.set_media(bytes(b), 272)
        self.assertEqual([k for k, _ in e.quality_modes(b)], [2])


if __name__ == "__main__":
    unittest.main()
