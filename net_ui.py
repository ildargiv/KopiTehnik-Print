"""Окна сети: панель чата (слева, сворачивается) и диалог подключения ПК. PySide6; логика в net_service.

ChatPanel(service, theme): theme — словарь цветов программы (photo_crop_qt.T). Сервис вызывает панель из потоков сети,
поэтому событие переправляется сигналом в поток окна.
"""
import html
import socket
import time

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTabWidget, QTextBrowser, QToolButton, QVBoxLayout, QWidget)

import net_service as ns

STATE_COLOR = {"ok": "ok", "printing": "select", "attention": "warn", "error": "bad", "offline": "bad"}


def _local_addrs():
    out = []
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith("127."):
                out.append(ip)
    except OSError:
        pass
    return out or ["127.0.0.1"]


class _Bridge(QObject):
    event = Signal(str, object)


class ChatPanel(QFrame):
    def __init__(self, service, theme, tr=lambda s: s, parent=None):
        super().__init__(parent)
        self.svc, self.T, self.tr = service, theme, tr
        self._bridge = _Bridge()
        self._bridge.event.connect(self._on_event)
        service.on_ui = lambda kind, info: self._bridge.event.emit(kind, info)
        self.open = False
        self.setObjectName("chatPanel")
        self.setStyleSheet(self._qss())
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.head = QPushButton()
        self.head.setObjectName("chatHead")
        self.head.setCursor(Qt.PointingHandCursor)
        self.head.clicked.connect(self.toggle)
        root.addWidget(self.head)

        self.body = QWidget()
        b = QVBoxLayout(self.body)
        b.setContentsMargins(8, 6, 8, 8)
        b.setSpacing(6)
        top = QHBoxLayout()
        self.who = QComboBox()
        self.who.currentIndexChanged.connect(lambda _=0: self._render(True))
        self.b_add = QToolButton()
        self.b_add.setText("＋")
        self.b_add.setToolTip(tr("Подключить ПК"))
        self.b_add.clicked.connect(self.pair_dialog)
        top.addWidget(self.who, 1)
        top.addWidget(self.b_add)
        b.addLayout(top)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        b.addWidget(self.view, 1)
        grid = QGridLayout()
        grid.setSpacing(4)
        for i, ph in enumerate(ns.QUICK_PHRASES):
            btn = QPushButton(tr(ph))
            btn.setObjectName("quick")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, t=ph: self.send(tr(t)))
            grid.addWidget(btn, i // 2, i % 2)
        b.addLayout(grid)
        row = QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(tr("Сообщение…"))
        self.edit.returnPressed.connect(lambda: self.send(self.edit.text()))
        self.b_send = QPushButton(tr("Отправить"))
        self.b_send.clicked.connect(lambda: self.send(self.edit.text()))
        row.addWidget(self.edit, 1)
        row.addWidget(self.b_send)
        b.addLayout(row)
        root.addWidget(self.body, 1)
        self.body.setVisible(False)
        self.refresh()

    def _qss(self):
        t = self.T
        return ("#chatPanel { background: %(surface)s; border: 1px solid %(border)s; border-radius: 10px; }"
                "#chatHead { background: transparent; color: %(text)s; border: none; text-align: left; padding: 8px 10px; font-weight: 600; }"
                "#chatHead:hover { background: %(hover)s; }"
                "#chatPanel QTextBrowser, #chatPanel QLineEdit, #chatPanel QComboBox { background: %(raised)s; color: %(text)s;"
                " border: 1px solid %(border)s; border-radius: 6px; padding: 4px; }"
                "#chatPanel QPushButton, #chatPanel QToolButton { background: %(raised)s; color: %(text)s; border: 1px solid %(border)s;"
                " border-radius: 6px; padding: 4px 8px; }"
                "#chatPanel QPushButton:hover, #chatPanel QToolButton:hover { background: %(hover)s; }"
                "#quick { font-size: 11px; padding: 3px 4px; }") % t

    # ---- состояние ----
    def toggle(self, on=None):
        self.open = (not self.open) if on is None else bool(on)
        self.body.setVisible(self.open)
        self.setMinimumHeight(360 if self.open else 0)
        if self.open:
            self.svc.mark_read(self._peer())
            self._render(True)
            self.edit.setFocus()
        self.refresh()
        self.updateGeometry()

    def _peer(self):
        return self.who.currentData() if self.who.count() else None

    def refresh(self):
        peers = self.svc.peers()
        cur = self._peer()
        self.who.blockSignals(True)
        self.who.clear()
        self.who.addItem(self.tr("Все ПК") + self._badge(None), None)
        for p in peers:
            dot = "●" if p["online"] else "○"
            self.who.addItem("%s %s%s" % (dot, p["name"], self._badge(p["id"])), p["id"])
        i = self.who.findData(cur)
        self.who.setCurrentIndex(max(0, i))
        self.who.blockSignals(False)
        online = sum(1 for p in peers if p["online"])
        unread = self.svc.unread()
        arrow = "▾" if self.open else "▸"
        self.head.setText("%s  💬 %s%s    %s" % (arrow, self.tr("Чат"), ("  (%d)" % unread) if unread else "",
                                                "● %d/%d" % (online, len(peers)) if peers else ""))
        self.head.setStyleSheet("color: %s;" % self.T["select"] if unread else "")

    def _badge(self, pid):
        n = self.svc.unread(pid) if pid else sum(1 for m in self.svc.cfg.get("chat", []) if m["chan"] == "all" and not m["me"] and not m.get("read"))
        return " (%d)" % n if n else ""

    def _render(self, mark=False):
        peer = self._peer()
        if mark and self.open:
            self.svc.mark_read(peer)
        t = self.T
        parts = []
        for m in self.svc.history(peer):
            when = time.strftime("%H:%M", time.localtime(m["ts"]))
            who = self.tr("Вы") if m["me"] else html.escape(m["user"] or "?")
            color = t["accent"] if m["me"] else t["select"]
            parts.append('<p style="margin:2px 0"><span style="color:%s"><b>%s</b></span> <span style="color:%s">%s</span><br>%s</p>'
                         % (color, who, t["muted"], when, html.escape(m["text"]).replace("\n", "<br>")))
        self.view.setHtml("".join(parts) or '<p style="color:%s">%s</p>' % (t["muted"], self.tr("Сообщений пока нет.")))
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())
        self.refresh()

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
        self._render()

    def _on_event(self, kind, info):
        if kind == "chat":
            if self.open and (info.get("channel") == "all" and self._peer() is None or info.get("from") == self._peer()):
                self.svc.mark_read(self._peer())
            self._render()
        elif kind in ("presence", "paired"):
            self.refresh()

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
