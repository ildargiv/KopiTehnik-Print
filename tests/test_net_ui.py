import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication  # noqa: E402

import net_service as ns  # noqa: E402
import net_ui  # noqa: E402

THEME = dict(bg="#1b1c1f", surface="#232529", raised="#2d3035", hover="#383c42", border="#3a3e45", text="#eceef1",
             muted="#9aa0aa", accent="#ff7a1a", select="#2ec4e6", ok="#3ccf7a", warn="#f0a030", bad="#ff5a5a")


def svc(name):
    st = {"net": {"name": name, "user": name}}
    return ns.NetService(lambda: st, lambda: None, port=0, udp_port=0, host="127.0.0.1"), st


def pump(app, cond, t=5.0):
    end = time.time() + t
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.03)
    return False


def test_chat_between_two_panels():
    app = QApplication.instance() or QApplication([])
    a, sa = svc("Аня")
    b, sb = svc("Борис")
    pa, pb = net_ui.ChatPanel(a, THEME), net_ui.ChatPanel(b, THEME)
    a.start()
    code = b.open_pairing()
    a.pair("127.0.0.1", code, b.node.port)
    assert pump(app, lambda: a.node.online(b.node.id) and b.node.online(a.node.id))
    pa.toggle(True)
    pa.send("Жду фото")
    assert pump(app, lambda: "Жду фото" in pb.view.toPlainText() or pb.svc.unread() == 1)
    assert pb.svc.unread() == 1 and "(1)" in pb.head.text()       # сообщение получено, на закрытой панели счётчик
    pb.toggle(True)
    assert "Жду фото" in pb.view.toPlainText() and "Аня" in pb.view.toPlainText() and b.unread() == 0
    pb.send("Принято")
    assert pump(app, lambda: "Принято" in pa.view.toPlainText())
    # личный диалог отделён от общего
    pa.who.setCurrentIndex(1)
    assert "Принято" not in pa.view.toPlainText()
    pa.send("лично")
    assert pump(app, lambda: any(m["text"] == "лично" and m["chan"] == a.node.id for m in sb["net"]["chat"]))
    a.stop(); b.stop()
    app.processEvents()
