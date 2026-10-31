import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication  # noqa: E402

import net_service as ns  # noqa: E402
import net_sound  # noqa: E402
import net_ui  # noqa: E402

THEME = dict(bg="#1b1c1f", surface="#232529", raised="#2d3035", hover="#383c42", border="#3a3e45", text="#eceef1",
             muted="#9aa0aa", accent="#ff7a1a", accent_text="#1a1205", select="#2ec4e6", ok="#3ccf7a", warn="#f0a030", bad="#ff5a5a")


class Mute:
    def __init__(self):
        self.log = []

    def play(self, name):
        self.log.append(name)


def svc(name, tmp=None):
    st = {"net": {"name": name, "user": name, "files_dir": str(tmp / name) if tmp else None}}
    if not tmp:
        st["net"].pop("files_dir")
    return ns.NetService(lambda: st, lambda: None, port=0, udp_port=0, host="127.0.0.1"), st


def pump(app, cond, t=5.0):
    end = time.time() + t
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.03)
    return False


def count(panel):
    return sum(1 for i in range(panel.col.count()) if isinstance(panel.col.itemAt(i).widget(), net_ui.Bubble))


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def connect(app, tmp):
    a, sa = svc("Аня", tmp)
    b, sb = svc("Борис", tmp)
    ma, mb = Mute(), Mute()
    pa, pb = net_ui.ChatPanel(a, THEME, sounds=ma), net_ui.ChatPanel(b, THEME, sounds=mb)
    a.start()
    b.start()
    a.pair("127.0.0.1", b.open_pairing(), b.node.port)
    assert pump(app, lambda: a.node.online(b.node.id) and b.node.online(a.node.id))
    return a, b, sa, sb, pa, pb, ma, mb


def test_chat_text_buttons_and_sounds(app, tmp_path):
    a, b, sa, sb, pa, pb, ma, mb = connect(app, tmp_path)
    pa.toggle(True)
    pa.send("Жду фото")
    assert ma.log == ["send"] and count(pa) == 1
    assert pump(app, lambda: b.unread() == 1)
    assert mb.log == ["recv"] and "(1)" in pb.head.text()
    pb.toggle(True)
    assert count(pb) == 1 and b.unread() == 0
    pb.send("Принято 👍")
    assert pump(app, lambda: count(pa) == 2)
    assert "recv" in ma.log
    # кнопка ПК вместо списка: выбираем Бориса, личный диалог отделён от общего
    assert pa.peers.more is None
    pa.peers.buttons[b.node.id].click()
    assert pa.peers.cur == b.node.id and count(pa) == 0
    pa.send("лично")
    assert pump(app, lambda: any(m["text"] == "лично" and m["chan"] == a.node.id for m in sb["net"]["chat"]))
    a.stop(); b.stop()


def test_more_than_four_peers_use_list(app):
    a, sa = svc("A")
    pa = net_ui.ChatPanel(a, THEME, sounds=Mute())
    sa["net"]["paired"] = {"p%d" % i: {"name": "ПК %d" % i, "key": "k", "addr": "127.0.0.1", "port": 1} for i in range(6)}
    pa.refresh()
    assert pa.peers.more is not None and pa.peers.more.count() == 1 + 2          # заголовок + два «лишних» ПК
    assert len([k for k in pa.peers.buttons if k is not None]) == 4
    sa["net"]["paired"] = {k: v for k, v in list(sa["net"]["paired"].items())[:4]}
    pa.refresh()
    assert pa.peers.more is None


def test_file_and_photo_transfer(app, tmp_path):
    from PIL import Image
    a, b, sa, sb, pa, pb, ma, mb = connect(app, tmp_path)
    img, doc = tmp_path / "фото.png", tmp_path / "заказ.pdf"
    Image.new("RGB", (400, 300), (200, 30, 30)).save(img)
    doc.write_bytes(b"%PDF-1.4 test" * 1000)
    pa.toggle(True)
    pb.toggle(True)
    pa.send_paths([str(img), str(doc)])
    assert pump(app, lambda: count(pb) == 2)
    msgs = sb["net"]["chat"]
    kinds = {m["att"]["name"]: m["att"]["kind"] for m in msgs}
    assert kinds == {"фото.png": "image", "заказ.pdf": "file"}
    assert "file" in mb.log
    for m in msgs:                                                   # файлы лежат в папке получателя, а не рядом с исходниками
        assert str(tmp_path / "Борис") in m["att"]["path"] and os.path.getsize(m["att"]["path"]) == m["att"]["size"]
    dest = tmp_path / "скачано.png"
    ns.NetService.download(msgs[0]["att"], str(dest))
    assert dest.read_bytes() == img.read_bytes()
    pm = pb.col.itemAt(0).widget().findChildren(net_ui.QLabel)
    assert any(l.pixmap() is not None and not l.pixmap().isNull() for l in pm)        # фото показано картинкой
    a.stop(); b.stop()


def test_filename_cannot_escape_folder(app, tmp_path):
    import net_link as nl
    a, b, *_ = connect(app, tmp_path)
    s = a.node.sessions[b.node.id]
    h, _ = s.call("file", {"id": "x1", "name": "..\\..\\evil/../../a.txt", "channel": "all"}, b"hi")
    assert h["ok"]
    saved = b.cfg["chat"][-1]["att"]["path"]
    assert os.path.commonpath([saved, str(tmp_path / "Борис")]) == str(tmp_path / "Борис")
    a.stop(); b.stop()


def test_emoji_popup_and_sounds_generated(app, tmp_path):
    a, sa = svc("A")
    p = net_ui.ChatPanel(a, THEME, sounds=Mute())
    pop = net_ui.EmojiPopup(THEME, lambda s: s)
    got = []
    pop.picked.connect(got.append)
    btns = pop.findChildren(net_ui.QToolButton)
    assert len(btns) == len(ns.EMOJI_COMMON) + len(ns.EMOJI_PRINT) and "🖨️" in [b.text() for b in btns]
    btns[0].click()
    assert got == ["😀"]
    paths = net_sound.write_wavs(str(tmp_path / "snd"))
    assert set(paths) == {"send", "recv", "file", "error"} and all(os.path.getsize(v) > 1000 for v in paths.values())
    off = net_sound.Sounds(str(tmp_path / "snd"), enabled=lambda: False)
    assert off.play("recv") is False
