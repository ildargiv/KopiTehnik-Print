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

    def test_unknown_model_changes_nothing(self):
        e = ep.EpsonPriv("EPSON L18050 Series")
        b = blob()
        self.assertTrue(e.supported("quality"))
        self.assertTrue(e.supported("border"))
        self.assertFalse(e.supported("maint"))
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
            ep.EpsonPriv("EPSON L18050 Series").maintenance("EPSON L18050 Series", "clean")

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


if __name__ == "__main__":
    unittest.main()
