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
        self.assertEqual(len(s), pq.MAX_SLOTS)
        self.assertEqual(pq.MAX_SLOTS, 8)
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
        # очередь переименована: модель берётся из драйвера
        self.assertTrue(pq.driver_compatible({"printer": "Цех", "model": "L8050", "state": {}}, "Принтер 2", ep.model_of, "L8050"))
        self.assertFalse(pq.driver_compatible({"printer": "Цех", "model": "L8050", "state": {}}, "Принтер 2", ep.model_of, "L18050"))


class StoreTests(unittest.TestCase):
    def test_slots_per_printer(self):
        st = pq.norm_store(None, "P1")
        self.assertEqual(list(st), ["P1"])
        st["P1"][0] = {"name": "a", "bound": True, "printer": "P1", "model": "", "state": {"x": 1}}
        st = pq.norm_store(st, "P2")
        self.assertEqual(sorted(st), ["P1", "P2"])
        self.assertFalse(st["P1"][0].get("empty"))
        self.assertTrue(all(x.get("empty") for x in st["P2"]))

    def test_legacy_list_migrates(self):
        old = [{"name": "a", "bound": True, "printer": "P1", "state": {}},
               {"name": "b", "bound": False, "printer": "P1", "state": {}}, {"empty": True}]
        st = pq.norm_store(old, "P2")
        self.assertEqual(st["P1"][0]["name"], "a")
        self.assertEqual(st["P2"][1]["name"], "b")
        self.assertTrue(st["P2"][1]["bound"] and st["P2"][1]["printer"] == "P2")


if __name__ == "__main__":
    unittest.main()
