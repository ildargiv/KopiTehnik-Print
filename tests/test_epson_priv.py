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
        self.assertFalse(e.supported("border"))
        self.assertEqual(e.set(b, "border", True), b)
        self.assertIsNone(e.get(b, "border"))

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
            self.assertTrue(e.supported("border"))


if __name__ == "__main__":
    unittest.main()
