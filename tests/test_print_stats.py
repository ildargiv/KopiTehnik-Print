import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["APPDATA"] = tempfile.mkdtemp()
import print_stats as ps


class Stats(unittest.TestCase):
    def test_kinds_and_paper(self):
        ps.record("P", 1, "102x152", "crop", "app", 3, ["a.jpg"], kind="photo")
        ps.record("P", 4, "210x297", "crop", "app", 2, ["b.jpg"], kind="photo")
        ps.record("P", 0, "210x297", "document", "app", 5, ["c.pdf"], kind="doc")
        t = ps.today()
        self.assertEqual((t["sheets"], t["photo"], t["doc"]), (10, 5, 5))
        s = ps.summary()
        self.assertEqual(dict(s["paper_photo"]), {"10x15 (102x152 мм)": 3, "A4 (210x297 мм)": 2})
        self.assertEqual(dict(s["paper_doc"]), {"A4 (210x297 мм)": 5})
        self.assertTrue(ps.verify()[0])

    def test_by_printer(self):
        import time
        now = time.time()
        mk = lambda pr, mode, paper, n, kind: {"ts": now, "t": time.strftime("%Y-%m-%d %H:%M:%S"), "printer": pr, "mode": mode,
                                               "paper": paper, "sheets": n, "kind": kind}
        recs = [mk("Canon", "crop", "102x152", 4, "photo"), mk("HP", "document", "210x297", 2, "doc"),
                mk("Canon", "crop", "102x152", 1, "photo")]
        self.assertEqual(ps.printer_names(recs), ["Canon", "HP"])
        d = dict(ps.by_printer(recs, "today"))
        self.assertEqual((d["Canon"]["photo"], d["Canon"]["doc"]), (5, 0))
        self.assertEqual(d["HP"]["rows"], [("doc", "A4 (210x297 мм)", 2)])
        self.assertEqual([n for n, _ in ps.by_printer(recs, "all", "HP")], ["HP"])
        out = os.path.join(tempfile.mkdtemp(), "p.csv")
        self.assertEqual(ps.export_printers_csv(out, "all", "HP", recs), 1)

    def test_old_record_without_kind(self):
        self.assertEqual(ps.rkind({"mode": "document"}), "doc")
        self.assertEqual(ps.rkind({"mode": "crop"}), "photo")
        self.assertEqual(ps.paper_label("123x456"), "123x456 мм")


if __name__ == "__main__":
    unittest.main()
