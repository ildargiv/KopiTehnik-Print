# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import print_quick as pq
import epson_priv as ep


class PrintQuickTests(unittest.TestCase):
    def test_norm_pads_and_cleans(self):
        s = pq.norm_slots(None)
        self.assertEqual(len(s), 3)
        self.assertTrue(all(x.get("empty") for x in s))
        s = pq.norm_slots([{"name": "  Матовая   высокое ", "bound": 1, "printer": "P", "state": {"a": 1}}, "junk", {"state": 5}])
        self.assertEqual(s[0]["name"], "Матовая высокое")
        self.assertTrue(s[0]["bound"])
        self.assertTrue(s[1]["empty"] and s[2]["empty"])

    def test_status_colors(self):
        slot = pq.norm_slots([{"name": "a", "bound": True, "printer": "P1", "state": {}}])[0]
        self.assertEqual(pq.status(slot, ["P1"]), pq.GREEN)
        self.assertEqual(pq.status(slot, ["P2"]), pq.RED)
        slot["bound"] = False
        self.assertEqual(pq.status(slot, ["P2"]), pq.ORANGE)
        self.assertEqual(pq.status(pq.empty_slot(0), []), pq.GRAY)

    def test_driver_compatible(self):
        slot = {"printer": "EPSON L8050 Series (копия 1)", "state": {}}
        self.assertTrue(pq.driver_compatible(slot, "EPSON L8050 Series", ep.model_of))
        self.assertTrue(pq.driver_compatible(slot, "EPSON L8050 Series (копия 1)", ep.model_of))
        self.assertFalse(pq.driver_compatible(slot, "EPSON L18050 Series", ep.model_of))
        self.assertFalse(pq.driver_compatible(slot, "", ep.model_of))


if __name__ == "__main__":
    unittest.main()
