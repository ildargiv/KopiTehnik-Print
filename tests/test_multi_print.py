import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import multi_print as mp


def fake(delays, broken=(), log=None):
    def send(printer, sheet):
        if printer in broken:
            raise OSError("офлайн")
        time.sleep(delays.get(printer, 0.0))
        if log is not None:
            log.append((printer, sheet))
    return send


class MultiPrint(unittest.TestCase):
    def test_every_sheet_once(self):
        log = []
        rep = mp.MultiRun(range(30), ["A", "B", "C"], fake({"A": .002, "B": .002, "C": .002}, log=log)).run()
        self.assertEqual(sorted(s for _, s in log), list(range(30)))
        self.assertEqual(rep["failed"], [])

    def test_fast_printer_gets_more(self):
        rep = mp.MultiRun(range(40), ["fast", "slow"], fake({"fast": .002, "slow": .02})).run()
        self.assertGreater(len(rep["sent"]["fast"]), len(rep["sent"]["slow"]) * 2)
        self.assertEqual(len(rep["sent"]["fast"]) + len(rep["sent"]["slow"]), 40)

    def test_broken_printer_excluded_sheets_rerouted(self):
        rep = mp.MultiRun(range(12), ["A", "B"], fake({}, broken=("B",))).run()
        self.assertIn("B", rep["excluded"])
        self.assertEqual(sorted(rep["sent"]["A"]), list(range(12)))
        self.assertEqual(rep["failed"], [])

    def test_all_broken(self):
        rep = mp.MultiRun(range(5), ["A", "B"], fake({}, broken=("A", "B"))).run()
        self.assertEqual(sorted(rep["failed"]), list(range(5)))
        self.assertEqual(rep["sent"], {"A": [], "B": []})

    def test_single_printer_failure_keeps_sheet_failed(self):
        rep = mp.MultiRun([1, 2], ["A"], fake({}, broken=("A",))).run()
        self.assertEqual(sorted(rep["failed"]), [1, 2])

    def test_cancel(self):
        ev = threading.Event()
        log = []

        def send(p, s):
            log.append(s)
            if len(log) == 3:
                ev.set()
            time.sleep(0.005)
        rep = mp.MultiRun(range(50), ["A", "B"], send, cancel=ev).run()
        self.assertTrue(rep["cancelled"])
        self.assertLess(len(log), 50)
        self.assertTrue(rep["not_started"])

    def test_serialize_never_parallel(self):
        active, peak = [0], [0]
        lock = threading.Lock()

        def send(p, s):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.003)
            with lock:
                active[0] -= 1
        mp.MultiRun(range(20), ["A", "B", "C"], send, serialize=True).run()
        self.assertEqual(peak[0], 1)

    def test_flaky_printer_recovers(self):
        calls = {"n": 0}

        def send(p, s):
            calls["n"] += 1
            if p == "A" and calls["n"] == 1:
                raise OSError("разово")
        rep = mp.MultiRun(range(6), ["A", "B"], send).run()
        self.assertEqual(rep["failed"], [])
        self.assertEqual(sum(len(v) for v in rep["sent"].values()), 6)

    def test_order_kept_when_other_printer_fails(self):
        rep = mp.MultiRun(range(5), ["A", "B"], fake({"A": .005}, broken=("B",))).run()
        self.assertEqual(rep["sent"]["A"], [0, 1, 2, 3, 4])

    def test_last_printer_gets_retry(self):
        n = {"c": 0}

        def send(p, s):
            if p == "A" and s == 3 and n["c"] < 1:
                n["c"] += 1
                raise OSError("разово")
        rep = mp.MultiRun(range(5), ["A"], send, max_errors=2).run()
        self.assertEqual(rep["failed"], [])

    def test_cancelled_is_not_an_error(self):
        def send(p, s):
            raise mp.Cancelled()
        rep = mp.MultiRun(range(3), ["A", "B"], send).run()
        self.assertEqual(rep["errors"], {})
        self.assertEqual(rep["excluded"], {})

    def test_base_exception_does_not_hang(self):
        def send(p, s):
            if p == "A":
                raise SystemExit(1)
        rep = mp.MultiRun(range(4), ["A", "B"], send).run()
        self.assertEqual(sorted(rep["sent"]["B"]), [0, 1, 2, 3])
        self.assertIn("A", rep["excluded"])

    def test_tuple_units_and_counter(self):
        counts = []
        units = [(k, r) for k in range(3) for r in range(2)]
        mp.MultiRun(units, ["A", "B"], fake({}), on_event=lambda k, p, u, i: counts.append(i) if k == "sent" else None).run()
        self.assertEqual(sorted(counts), list(range(1, 7)))


if __name__ == "__main__":
    unittest.main()
