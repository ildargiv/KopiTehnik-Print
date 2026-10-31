import base64
import io
import os
import sys
import types

import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import net_print as npr


class FakeJob:
    log = []

    def __init__(self, name, blob, title):
        self.name, self.blob, self.title, self.pages = name, blob, title, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        FakeJob.log.append((self.name, self.blob, self.title, self.pages))

    def page(self, img):
        self.pages.append(img.size)

    def finish(self):
        pass


def fake_pc():
    pc = types.SimpleNamespace()
    pc.PAPER_DRIVER = "drv"
    pc.PrinterJob = FakeJob
    pc.list_printers = lambda: ["Epson", "HP", "Secret"]
    pc.devmode_valid = lambda b: b.startswith(b"DM")
    pc.prepare_blob = lambda p, b, o, kw: b
    pc.printer_geometry = lambda p, b, o: {"paper": (102.0, 152.0), "dpi": (720, 720)}
    pc.resolve_ppi = lambda o, g: 360
    pc.cm_build = lambda *a: {"profile": b"x"}
    pc.apply_printer_profile = lambda img, src, cm: img.point(lambda v: 255 - v)
    return pc


def fake_pcr():
    return types.SimpleNamespace(norm=lambda x: x, active=lambda x: bool(x and x.get("on")),
                                 apply=lambda img, c: img.point(lambda v: min(255, v + 10)))


def png(w, h, color=(100, 100, 100)):
    b = io.BytesIO()
    Image.new("RGB", (w, h), color).save(b, "PNG")
    return b.getvalue()


@pytest.fixture
def np_():
    FakeJob.log.clear()
    st = {"print_devmodes": {"Epson": base64.b64encode(b"DMepson").decode()},
          "print_profiles": {"Epson | 10x15 | Glossy | ": {"blob": base64.b64encode(b"DMprof").decode(), "cm_on": True,
                                                         "icc": "p.icc", "intent": "perc", "bpc": False, "embed": False,
                                                         "pcorr": {"on": True}}},
          "net_shared": ["Epson", "HP"]}
    return npr.NetPrinting(fake_pc(), fake_pcr(), lambda: st), st


def test_shared_and_listing(np_):
    n, st = np_
    assert n.shared_printers() == ["Epson", "HP"]
    st["net_shared"] = None
    assert n.shared_printers() == ["Epson", "HP", "Secret"]
    r = n.handler_printers({}, b"", "p")
    assert r["printers"][0]["profiles"][0]["key"].startswith("Epson")


def test_print_applies_executor_profile(np_):
    n, st = np_
    n.print_sheet({"printer": "Epson", "format": "10x15", "from": "PC1"}, png(1020, 1520, (100, 100, 100)))
    name, blob, title, pages = FakeJob.log[0]
    assert (name, blob, pages) == ("Epson", b"DMprof", [(1020, 1520)])      # блоб из профиля, не из общих настроек
    assert "PC1" in title


def test_color_applied_inverted_then_corr(np_):
    n, st = np_
    seen = {}
    n.pcr.apply = lambda img, c: seen.setdefault("px", img.getpixel((0, 0))) and img
    n.print_sheet({"printer": "Epson"}, png(1020, 1520, (100, 100, 100)))
    assert seen["px"] == (155, 155, 155)           # сначала ICC (инверсия-заглушка), потом поправка


def test_refusals(np_):
    n, st = np_
    with pytest.raises(npr.PrintRefused, match="недоступен"):
        n.print_sheet({"printer": "Secret"}, png(10, 15))
    with pytest.raises(npr.PrintRefused, match="Пропорции"):
        n.print_sheet({"printer": "Epson"}, png(1000, 1000))
    with pytest.raises(npr.PrintRefused, match="нет сохранённых"):
        n.print_sheet({"printer": "HP"}, png(1020, 1520))
    with pytest.raises(Exception):
        n.print_sheet({"printer": "Epson"}, b"not an image")
    assert not FakeJob.log


def test_revision_mismatch_and_snapshot(np_):
    n, st = np_
    snap = n.handler_snapshot({"printer": "Epson", "format": "10x15"}, b"", "p")
    assert snap["paper_mm"] == [102.0, 152.0] and snap["ppi"] == 360 and snap["color"] and snap["pcorr"]
    n.print_sheet({"printer": "Epson", "rev": snap["rev"]}, png(1020, 1520))
    key = next(iter(st["print_profiles"]))
    st["print_profiles"][key]["sharp"] = 5                          # профиль поменяли на этом ПК
    with pytest.raises(npr.PrintRefused, match="изменился"):
        n.print_sheet({"printer": "Epson", "rev": snap["rev"]}, png(1020, 1520))


def test_pixel_limit(np_):
    n, st = np_
    npr.MAX_PIXELS, old = 1000, npr.MAX_PIXELS
    try:
        with pytest.raises(Exception):
            n.print_sheet({"printer": "Epson"}, png(1020, 1520))
    finally:
        npr.MAX_PIXELS = old


def test_end_to_end_over_network(np_):
    import net_link as nl
    import time
    n, st = np_
    b = nl.Node("B", host="127.0.0.1", port=0, udp_port=0, print_sheet=n.print_sheet, handlers=n.handlers()).start()
    a = nl.Node("A", host="127.0.0.1", port=0, udp_port=0).start()
    try:
        a.pair("127.0.0.1", b.open_pairing(), b.port)
        for _ in range(100):
            if a.online(b.id):
                break
            time.sleep(0.05)
        s = a.sessions[b.id]
        h, _ = s.call("printer_snapshot", {"printer": "Epson", "format": "10x15"})
        assert h["ok"] and h["paper_mm"] == [102.0, 152.0]
        a.send_sheet(b.id, "Epson", "j", "s1", png(1020, 1520), meta={"rev": h["rev"]})
        assert FakeJob.log and FakeJob.log[0][0] == "Epson"
        with pytest.raises(nl.NetError, match="недоступен"):
            a.send_sheet(b.id, "Secret", "j", "s2", png(1020, 1520))
    finally:
        a.stop(); b.stop()
