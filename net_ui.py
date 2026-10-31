"""Окна сети: панель чата (слева, сворачивается) и диалог подключения ПК. PySide6; логика в net_service.

ChatPanel(service, theme): theme — словарь цветов программы (photo_crop_qt.T). Сервис вызывает панель из потоков сети,
поэтому событие переправляется сигналом в поток окна.
Возможности: кнопки ПК по именам (больше 4 — остальные в списке), смайлики (обычные и «про печать»), любые файлы
(фото показываются картинкой, у каждого присланного кнопка «Скачать»), анимация появления сообщений, звуки.
"""
import html
import os
import socket
import time

from PySide6.QtCore import QEasingCurve, QObject, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QScrollArea, QTabWidget, QToolButton, QVBoxLayout, QWidget)

import net_service as ns
import net_sound

MAX_TABS = 4                      # столько ПК показывается кнопками, остальные уходят в список
BUBBLE_W = 220


def _local_addrs():
    out = []
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith("127."):
                out.append(ip)
    except OSError:
        pass
    return out or ["127.0.0.1"]


def human_size(n):
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024 or unit == "ГБ":
            return ("%d %s" % (n, unit)) if unit == "Б" else ("%.1f %s" % (n, unit))
        n /= 1024.0


def dot_icon(color, size=12):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pm)


class _Bridge(QObject):
    event = Signal(str, object)


class Bubble(QWidget):
    """Одно сообщение. Появляется с анимацией: выезжает с края, проявляется и слегка «пружинит»."""

    def __init__(self, panel, m, animate=False):
        super().__init__()
        self.panel, self.m = panel, m
        t = panel.T
        me = m["me"]
        self._me = me
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 2, 0, 2)
        card = QFrame()
        card.setObjectName("mine" if me else "theirs")
        card.setMaximumWidth(BUBBLE_W + 24)
        col = QVBoxLayout(card)
        col.setContentsMargins(10, 6, 10, 6)
        col.setSpacing(3)
        when = time.strftime("%H:%M", time.localtime(m["ts"]))
        on_acc = t.get("accent_text", "#ffffff")
        head = QLabel('<b style="color:%s">%s</b> <span style="color:%s">%s</span>'
                      % (on_acc if me else t["select"], html.escape(panel.tr("Вы") if me else (m["user"] or "?")), on_acc if me else t["muted"], when))
        col.addWidget(head)
        att = m.get("att")
        if att:
            col.addWidget(self._attachment(att, me))
        if m.get("text"):
            txt = QLabel(html.escape(m["text"]).replace("\n", "<br>"))
            txt.setWordWrap(True)
            txt.setTextInteractionFlags(Qt.TextSelectableByMouse)
            txt.setMaximumWidth(BUBBLE_W)
            col.addWidget(txt)
        if me:
            self.lay.addStretch(1)
            self.lay.addWidget(card)
        else:
            self.lay.addWidget(card)
            self.lay.addStretch(1)
        self.card = card
        if animate:
            self._pop_in()

    def _attachment(self, att, me):
        t = self.panel.T
        box = QFrame()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3)
        pm = None
        if att.get("kind") == "image" and os.path.isfile(att.get("path", "")):
            pm = QPixmap(att["path"])
        if pm is not None and not pm.isNull():
            pic = QLabel()
            pic.setPixmap(pm.scaledToWidth(min(BUBBLE_W, pm.width()), Qt.SmoothTransformation) if pm.width() > BUBBLE_W else pm)
            pic.setAlignment(Qt.AlignCenter)
            pic.setObjectName("pic")
            v.addWidget(pic)
            cap = "%s · %s" % (att["name"], human_size(att.get("size", 0)))
        else:
            cap = "📄 %s · %s" % (att["name"], human_size(att.get("size", 0)))
        c = QLabel(cap)
        c.setWordWrap(True)
        c.setMaximumWidth(BUBBLE_W)
        c.setStyleSheet("font-size: 11px;")
        v.addWidget(c)
        if not me:
            b = QPushButton("⬇ " + self.panel.tr("Скачать"))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda: self.panel.download(att))
            v.addWidget(b)
        return box

    def _pop_in(self):
        eff = QGraphicsOpacityEffect(self)
        eff.setOpacity(0.0)
        self.setGraphicsEffect(eff)
        a = QVariantAnimation(self)
        a.setDuration(420)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutBack)
        shift = 60

        def step(v):
            eff.setOpacity(max(0.0, min(1.0, v * 1.4)))
            off = int((1.0 - v) * shift)                      # от края к месту; пружина за счёт OutBack
            if self._me:
                self.lay.setContentsMargins(0, 2, -off, 2)
            else:
                self.lay.setContentsMargins(-off, 2, 0, 2)

        def done():
            self.setGraphicsEffect(None)
            self.lay.setContentsMargins(0, 2, 0, 2)
        a.valueChanged.connect(step)
        a.finished.connect(done)
        self._anim = a
        a.start()


class EmojiPopup(QFrame):
    picked = Signal(str)

    def __init__(self, theme, tr):
        super().__init__(None, Qt.Popup)
        self.setStyleSheet("EmojiPopup { background: %(surface)s; border: 1px solid %(border)s; border-radius: 8px; }"
                           "QToolButton { background: transparent; border: none; font-size: 18px; padding: 2px; }"
                           "QToolButton:hover { background: %(hover)s; border-radius: 6px; }"
                           "QLabel { color: %(muted)s; font-size: 11px; }" % theme)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        for title, items in ((tr("Смайлики"), ns.EMOJI_COMMON), (tr("Печать и работа"), ns.EMOJI_PRINT)):
            lay.addWidget(QLabel(title))
            g = QGridLayout()
            g.setSpacing(0)
            for i, e in enumerate(items):
                b = QToolButton()
                b.setText(e)
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, x=e: (self.picked.emit(x), self.close()))
                g.addWidget(b, i // 8, i % 8)
            lay.addLayout(g)


class PeerBar(QWidget):
    """Кому писать: кнопки «Все» и по одной на ПК (до 4); если ПК больше, остальные в выпадающем списке."""
    chosen = Signal(object)

    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.cur = None
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(4)
        self.buttons = {}
        self.more = None

    def rebuild(self, peers):
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().hide()                      # deleteLater работает позже: без hide старые кнопки висят под новыми
                it.widget().setParent(None)
                it.widget().deleteLater()
        self.buttons = {}
        self.more = None
        t = self.panel.T
        svc = self.panel.svc
        entries = [(None, self.panel.tr("Все"), "ok", False)] + [(p["id"], p["name"], p["state"], not p["online"]) for p in peers[:MAX_TABS]]
        for i, (pid, name, state, off) in enumerate(entries):
            n = svc.unread(pid) if pid else sum(1 for m in svc.cfg.get("chat", []) if m["chan"] == "all" and not m["me"] and not m.get("read"))
            b = QToolButton()
            b.setCheckable(True)
            b.setChecked(pid == self.cur)
            b.setText(name + (" (%d)" % n if n else ""))
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setCursor(Qt.PointingHandCursor)
            if pid is not None:
                b.setIcon(dot_icon(t["ok"] if state == "ok" else t["select"] if state == "printing" else t["warn"] if state == "attention" else t["bad"]))
                b.setIconSize(QSize(10, 10))
            b.setStyleSheet("QToolButton:checked { background: %s; color: %s; }" % (t["accent"], t.get("accent_text", "#ffffff")) +
                            (" QToolButton { color: %s; }" % t["muted"] if off else ""))
            b.clicked.connect(lambda _=False, x=pid: self.select(x))
            self.buttons[pid] = b
            self.grid.addWidget(b, i // 2, i % 2)
        rest = peers[MAX_TABS:]
        if rest:
            self.more = QComboBox()
            self.more.addItem(self.panel.tr("Ещё ПК") + " (%d)" % len(rest), "__none__")
            for p in rest:
                self.more.addItem(("● " if p["online"] else "○ ") + p["name"], p["id"])
            i = self.more.findData(self.cur)
            self.more.setCurrentIndex(max(0, i))
            self.more.activated.connect(lambda _=0: self.select(self.more.currentData()) if self.more.currentData() != "__none__" else None)
            self.grid.addWidget(self.more, (len(entries) + 1) // 2, 0, 1, 2)

    def select(self, pid):
        self.cur = pid
        self.rebuild(self.panel.svc.peers())
        self.chosen.emit(pid)


class ChatPanel(QFrame):
    def __init__(self, service, theme, tr=lambda s: s, parent=None, sounds=None):
        super().__init__(parent)
        self.svc, self.T, self.tr = service, theme, tr
        self.sounds = sounds if sounds is not None else net_sound.Sounds(enabled=service.sound_on)
        self._bridge = _Bridge()
        self._bridge.event.connect(self._on_event)
        service.on_ui = lambda kind, info: self._bridge.event.emit(kind, info)
        self.open = False
        self._shown = 0
        self._shown_key = "all"
        self.setObjectName("chatPanel")
        self.setAcceptDrops(True)
        self.setStyleSheet(self._qss())
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.head = QPushButton()
        self.head.setObjectName("chatHead")
        self.head.setCursor(Qt.PointingHandCursor)
        self.head.clicked.connect(lambda: self.toggle())
        root.addWidget(self.head)

        self.body = QWidget()
        b = QVBoxLayout(self.body)
        b.setContentsMargins(8, 6, 8, 8)
        b.setSpacing(6)
        top = QHBoxLayout()
        self.peers = PeerBar(self)
        self.peers.chosen.connect(lambda pid: self._render(True))
        self.b_add = QToolButton()
        self.b_add.setText("＋")
        self.b_add.setToolTip(tr("Подключить ПК"))
        self.b_add.clicked.connect(self.pair_dialog)
        self.b_snd = QToolButton()
        self.b_snd.clicked.connect(self._toggle_sound)
        side = QVBoxLayout()
        side.addWidget(self.b_add)
        side.addWidget(self.b_snd)
        side.addStretch(1)
        top.addWidget(self.peers, 1)
        top.addLayout(side)
        b.addLayout(top)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.holder = QWidget()
        self.col = QVBoxLayout(self.holder)
        self.col.setContentsMargins(4, 4, 4, 4)
        self.col.setSpacing(2)
        self.col.addStretch(1)
        self.scroll.setWidget(self.holder)
        b.addWidget(self.scroll, 1)

        row = QHBoxLayout()
        self.b_emoji = QToolButton()
        self.b_emoji.setText("😊")
        self.b_emoji.setToolTip(tr("Смайлики"))
        self.b_emoji.clicked.connect(self.show_emoji)
        self.b_file = QToolButton()
        self.b_file.setText("📎")
        self.b_file.setToolTip(tr("Отправить файл или фото"))
        self.b_file.clicked.connect(self.pick_files)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(tr("Сообщение…"))
        self.edit.returnPressed.connect(lambda: self.send(self.edit.text()))
        self.b_send = QToolButton()
        self.b_send.setText("➤")
        self.b_send.setToolTip(tr("Отправить"))
        self.b_send.clicked.connect(lambda: self.send(self.edit.text()))
        for w, st in ((self.b_emoji, 0), (self.b_file, 0), (self.edit, 1), (self.b_send, 0)):
            row.addWidget(w, st)
        b.addLayout(row)
        root.addWidget(self.body, 1)
        self.body.setVisible(False)
        self.refresh()

    def _qss(self):
        t = self.T
        return ("#chatPanel { background: %(surface)s; border: 1px solid %(border)s; border-radius: 10px; }"
                "#chatHead { background: transparent; color: %(text)s; border: none; text-align: left; padding: 8px 10px; font-weight: 600; }"
                "#chatHead:hover { background: %(hover)s; }"
                "#chatPanel QScrollArea { background: %(raised)s; border: 1px solid %(border)s; border-radius: 6px; }"
                "#chatPanel QScrollArea > QWidget > QWidget { background: %(raised)s; }"
                "#chatPanel QLineEdit, #chatPanel QComboBox { background: %(raised)s; color: %(text)s;"
                " border: 1px solid %(border)s; border-radius: 6px; padding: 4px; }"
                "#chatPanel QPushButton, #chatPanel QToolButton { background: %(raised)s; color: %(text)s; border: 1px solid %(border)s;"
                " border-radius: 6px; padding: 4px 8px; }"
                "#chatPanel QPushButton:hover, #chatPanel QToolButton:hover { background: %(hover)s; }"
                "#mine { background: %(accent)s; border-radius: 10px; }"
                "#mine QLabel { color: %(accent_text)s; background: transparent; }"
                "#theirs { background: %(surface)s; border: 1px solid %(border)s; border-radius: 10px; }"
                "#theirs QLabel { color: %(text)s; background: transparent; }"
                "#pic { border-radius: 6px; }") % dict(t, accent_text=t.get("accent_text", "#ffffff"))

    # ---- состояние ----
    def toggle(self, on=None):
        self.open = (not self.open) if on is None else bool(on)
        self.body.setVisible(self.open)
        self.setMinimumHeight(420 if self.open else 0)
        if self.open:
            self.svc.mark_read(self.peers.cur)
            self._render(True)
            self.edit.setFocus()
        self.refresh()
        self.updateGeometry()

    def _peer(self):
        return self.peers.cur

    def refresh(self):
        peers = self.svc.peers()
        self.peers.rebuild(peers)
        self.b_snd.setText("🔔" if self.svc.sound_on() else "🔕")
        self.b_snd.setToolTip(self.tr("Звук сообщений: включён") if self.svc.sound_on() else self.tr("Звук сообщений: выключен"))
        online = sum(1 for p in peers if p["online"])
        unread = self.svc.unread()
        arrow = "▾" if self.open else "▸"
        self.head.setText("%s  💬 %s%s    %s" % (arrow, self.tr("Чат"), ("  (%d)" % unread) if unread else "",
                                                "● %d/%d" % (online, len(peers)) if peers else ""))

    def _toggle_sound(self):
        self.svc.set_sound(not self.svc.sound_on())
        self.refresh()

    # ---- сообщения ----
    def _clear(self):
        while self.col.count() > 1:
            it = self.col.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _render(self, mark=False):
        peer = self._peer()
        if mark and self.open:
            self.svc.mark_read(peer)
        self._clear()
        h = self.svc.history(peer)
        for m in h:
            self.col.insertWidget(self.col.count() - 1, Bubble(self, m))
        self._shown, self._shown_key = len(h), peer or "all"
        if not h:
            ph = QLabel(self.tr("Сообщений пока нет."))
            ph.setStyleSheet("color: %s;" % self.T["muted"])
            ph.setAlignment(Qt.AlignCenter)
            self.col.insertWidget(0, ph)
        self._scroll_end(False)
        self.refresh()

    def _append_new(self):
        peer = self._peer()
        h = self.svc.history(peer)
        if (peer or "all") != self._shown_key or len(h) < self._shown:
            return self._render()
        if self._shown == 0 and self.col.count() > 1:            # убрать надпись «Сообщений пока нет»
            self.col.takeAt(0).widget().deleteLater()
        for m in h[self._shown:]:
            self.col.insertWidget(self.col.count() - 1, Bubble(self, m, animate=True))
        self._shown = len(h)
        self._scroll_end(True)
        self.refresh()

    def _scroll_end(self, animate):
        bar = self.scroll.verticalScrollBar()
        if not animate:
            bar.setValue(bar.maximum())
            return
        from PySide6.QtCore import QTimer

        def go():
            a = QVariantAnimation(self)
            a.setDuration(260)
            a.setStartValue(bar.value())
            a.setEndValue(bar.maximum())
            a.setEasingCurve(QEasingCurve.OutCubic)
            a.valueChanged.connect(lambda v: bar.setValue(int(v)))
            self._scroll_anim = a
            a.start()
        QTimer.singleShot(30, go)

    # ---- действия ----
    def send(self, text):
        text = (text or "").strip()
        if not text:
            return
        if not self.svc.cfg.get("paired"):
            self.pair_dialog()
            return
        self.svc.send_chat(text, self._peer())
        self.edit.clear()
        self.sounds.play("send")
        self._append_new()

    def send_paths(self, paths):
        if not self.svc.cfg.get("paired"):
            self.pair_dialog()
            return
        for p in paths:
            try:
                self.svc.send_file(p, self._peer())
                self.sounds.play("send")
            except (OSError, ValueError) as e:
                self.sounds.play("error")
                self.edit.setPlaceholderText(str(e))
        self._append_new()

    def pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, self.tr("Отправить файл или фото"))
        if paths:
            self.send_paths(paths)

    def show_emoji(self):
        pop = EmojiPopup(self.T, self.tr)
        pop.picked.connect(lambda e: (self.edit.insert(e), self.edit.setFocus()))
        pop.adjustSize()
        pop.move(self.b_emoji.mapToGlobal(self.b_emoji.rect().topLeft()) - pop.rect().bottomLeft() + self.b_emoji.rect().topLeft())
        self._emoji = pop
        pop.show()

    def download(self, att):
        default = os.path.join(os.path.expanduser("~"), "Downloads", att["name"])
        dest, _ = QFileDialog.getSaveFileName(self, self.tr("Скачать"), default)
        if dest:
            self.svc.download(att, dest)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile() and os.path.isfile(u.toLocalFile())]
        if paths:
            self.send_paths(paths)

    def _on_event(self, kind, info):
        if kind == "chat":
            self.sounds.play("file" if info.get("att") else "recv")
            if self.open:
                self.svc.mark_read(self._peer()) if self._is_current(info) else None
                self._append_new()
            else:
                self.refresh()
                self._pulse()
        elif kind in ("presence", "paired"):
            self.refresh()

    def _is_current(self, info):
        return (info.get("channel") == "all" and self._peer() is None) or info.get("from") == self._peer()

    def _pulse(self):
        """Заголовок мигает цветом акцента, пока человек не откроет чат."""
        a = QVariantAnimation(self)
        a.setDuration(1100)
        a.setStartValue(1.0)
        a.setEndValue(0.0)
        a.setEasingCurve(QEasingCurve.OutQuad)
        t = self.T
        base, acc = QColor(t["surface"]), QColor(t["accent"])

        def step(v):
            c = QColor(int(base.red() + (acc.red() - base.red()) * v), int(base.green() + (acc.green() - base.green()) * v),
                       int(base.blue() + (acc.blue() - base.blue()) * v))
            self.head.setStyleSheet("background: %s;" % c.name())
        a.valueChanged.connect(step)
        a.finished.connect(lambda: self.head.setStyleSheet(""))
        self._pulse_anim = a
        a.start()

    def pair_dialog(self):
        PairDialog(self.svc, self.T, self.tr, self).exec()
        self.refresh()


class PairDialog(QDialog):
    def __init__(self, service, theme, tr, parent=None):
        super().__init__(parent)
        self.svc, self.tr = service, tr
        self.setWindowTitle(tr("Подключить ПК"))
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)
        # вкладка 1: на этом ПК показать код
        w1 = QWidget()
        l1 = QVBoxLayout(w1)
        l1.addWidget(QLabel(tr("На другом ПК выберите «Ввести код» и введите адрес и код ниже. Код действует 5 минут.")))
        self.code = QLineEdit()
        self.code.setReadOnly(True)
        self.addr = QLabel(tr("Адрес этого ПК") + ": " + ", ".join(_local_addrs()))
        self.addr.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b_show = QPushButton(tr("Показать код"))
        b_show.clicked.connect(self._show_code)
        l1.addWidget(b_show)
        l1.addWidget(self.code)
        l1.addWidget(self.addr)
        l1.addStretch(1)
        tabs.addTab(w1, tr("Показать код"))
        # вкладка 2: ввести код другого ПК
        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        self.found = QComboBox()
        self.found.addItem(tr("— найденные в сети —"), None)
        for f in service.found():
            self.found.addItem("%s  %s" % (f["name"], f["addr"]), f)
        self.found.currentIndexChanged.connect(self._pick)
        self.e_addr = QLineEdit()
        self.e_addr.setPlaceholderText(tr("Адрес ПК (например 192.168.1.20 или имя Tailscale)"))
        self.e_code = QLineEdit()
        self.e_code.setPlaceholderText(tr("Код с другого ПК"))
        self.msg = QLabel("")
        self.msg.setWordWrap(True)
        b_pair = QPushButton(tr("Подключить"))
        b_pair.clicked.connect(self._pair)
        for x in (self.found, self.e_addr, self.e_code, b_pair, self.msg):
            l2.addWidget(x)
        l2.addStretch(1)
        tabs.addTab(w2, tr("Ввести код"))
        self.name = QLineEdit(service.user())
        self.name.setPlaceholderText(tr("Моё имя в чате"))
        self.name.editingFinished.connect(lambda: service.set_user(self.name.text()))
        lay.addWidget(QLabel(tr("Моё имя в чате")))
        lay.addWidget(self.name)

    def _show_code(self):
        self.code.setText(self.svc.open_pairing())

    def _pick(self):
        f = self.found.currentData()
        if f:
            self.e_addr.setText(f["addr"])

    def _pair(self):
        try:
            self.svc.pair(self.e_addr.text(), self.e_code.text())
            self.msg.setText(self.tr("Подключено."))
            self.accept()
        except Exception as e:
            self.msg.setText("%s: %s" % (self.tr("Не удалось подключить"), e))
