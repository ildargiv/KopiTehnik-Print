"""Окна сети: панель чата (слева, сворачивается) и диалог подключения ПК. PySide6; логика в net_service.

ChatPanel(service, theme): theme — словарь цветов программы (photo_crop_qt.T). Сервис вызывает панель из потоков сети,
поэтому событие переправляется сигналом в поток окна.
Возможности: кнопки ПК по именам (больше 4 — остальные в списке), смайлики (обычные и «про печать»), любые файлы
(фото показываются картинкой, у каждого присланного кнопка «Скачать»), анимация появления сообщений, звуки.
Внешний вид рисуется только стилями Qt и QPainter — без картинок и внешних ресурсов, цвета берутся из темы программы.
"""
import html
import math
import os
import socket
import time

from PySide6.QtCore import QEasingCurve, QObject, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QScrollArea, QSizePolicy, QTabWidget, QToolButton, QVBoxLayout, QWidget)

import net_service as ns
import net_sound

MAX_TABS = 4                      # столько ПК показывается кнопками, остальные уходят в список
BUBBLE_W = 196                    # ширина текста в пузыре: панель ~270–290 px, пузырь не должен упираться в края
PEER_COLS = 3                     # кнопки ПК: «Все» + до 4 ПК = две аккуратные строки по три
QWIDGETSIZE_MAX = 16777215
RADIUS = 12                       # скругление панели; пузыри и карточки чуть меньше

# Цвет плашки по типу файла: картинки, документы, таблицы, архивы, PDF.
FILE_KINDS = (
    (("pdf",), "#e5484d"),
    (("jpg", "jpeg", "png", "tif", "tiff", "bmp", "gif", "webp", "heic", "psd"), "#3e8ef7"),
    (("doc", "docx", "rtf", "odt", "txt"), "#4f6bed"),
    (("xls", "xlsx", "csv", "ods"), "#2fa36b"),
    (("zip", "rar", "7z", "gz", "tar"), "#d9a02b"),
    (("cdr", "ai", "eps", "svg", "indd"), "#c25bd6"),
)


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


def _mix(a, b, k):
    """Смесь двух цветов темы: k=0 — a, k=1 — b. Нужна для мягких подложек без прозрачности."""
    a, b = QColor(a), QColor(b)
    return QColor(int(a.red() + (b.red() - a.red()) * k), int(a.green() + (b.green() - a.green()) * k),
                  int(a.blue() + (b.blue() - a.blue()) * k)).name()


def _rgba(c, alpha):
    c = QColor(c)
    return "rgba(%d,%d,%d,%d)" % (c.red(), c.green(), c.blue(), int(alpha * 255))


def _theme(t):
    """Тема с подстраховкой: у старых тем может не быть accent_text."""
    d = dict(t)
    d.setdefault("accent_text", "#ffffff")
    return d


def state_color(t, state):
    return t["ok"] if state == "ok" else t["select"] if state == "printing" else t["warn"] if state in ("attention", "error") else t["bad"]


def state_text(tr, state):
    return {"ok": tr("в сети"), "printing": tr("печатает"), "attention": tr("требует внимания"),
            "error": tr("требует внимания")}.get(state, tr("нет в сети"))


def dot_icon(color, size=12, ring=None):
    """Точка статуса; ring — мягкий ореол вокруг (у ПК в сети)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    if ring:
        c = QColor(color)
        c.setAlphaF(0.28)
        p.setBrush(c)
        p.drawEllipse(0, 0, size, size)
        p.setBrush(QColor(color))
        p.drawEllipse(QRectF(size * 0.25, size * 0.25, size * 0.5, size * 0.5))
    else:
        p.setBrush(QColor(color))
        p.drawEllipse(QRectF(size * 0.2, size * 0.2, size * 0.6, size * 0.6))
    p.end()
    return QIcon(pm)


def file_tile(name, size=(34, 40)):
    """Иконка файла: листок с загнутым углом и расширением, цвет по типу."""
    ext = os.path.splitext(name)[1].lstrip(".").lower()
    color = next((c for exts, c in FILE_KINDS if ext in exts), "#7b8494")
    w, h = size
    pm = QPixmap(w * 2, h * 2)                      # двойная плотность — ровные края на HiDPI и без него
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    fold = 10
    path = QPainterPath()
    path.moveTo(4, 1)
    path.lineTo(w - fold - 1, 1)
    path.lineTo(w - 1, fold + 1)
    path.lineTo(w - 1, h - 4)
    path.quadTo(w - 1, h - 1, w - 4, h - 1)
    path.lineTo(4, h - 1)
    path.quadTo(1, h - 1, 1, h - 4)
    path.lineTo(1, 4)
    path.quadTo(1, 1, 4, 1)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(path)
    corner = QPainterPath()
    corner.moveTo(w - fold - 1, 1)
    corner.lineTo(w - fold - 1, fold - 1)
    corner.quadTo(w - fold - 1, fold + 1, w - fold + 1, fold + 1)
    corner.lineTo(w - 1, fold + 1)
    corner.closeSubpath()
    p.setBrush(QColor(255, 255, 255, 90))
    p.drawPath(corner)
    f = QFont()
    f.setPixelSize(9 if len(ext) <= 4 else 7)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#ffffff"))
    p.drawText(QRectF(0, h * 0.45, w, h * 0.45), Qt.AlignCenter, (ext or "file").upper()[:5])
    p.end()
    return pm


def rounded_pixmap(pm, radius=9):
    out = QPixmap(pm.size())
    out.setDevicePixelRatio(pm.devicePixelRatio())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, pm.width() / pm.devicePixelRatio(), pm.height() / pm.devicePixelRatio()), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.end()
    return out


def _elide(widget, text, width, mode=Qt.ElideMiddle):
    return QFontMetrics(widget.font()).elidedText(text, mode, width)


class _Bridge(QObject):
    event = Signal(str, object)


class Bubble(QWidget):
    """Одно сообщение. Появляется с анимацией: строка плавно раздвигает историю, пузырь выезжает со своего края,
    проявляется и чуть «пружинит» на месте."""

    def __init__(self, panel, m, animate=False, delay=0):
        super().__init__()
        self.panel, self.m = panel, m
        t = panel.T
        me = m["me"]
        self._me = me
        self.setObjectName("row")
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 3, 0, 3)
        card = QFrame()
        card.setObjectName("mine" if me else "theirs")
        card.setMaximumWidth(BUBBLE_W + 22)
        col = QVBoxLayout(card)
        col.setContentsMargins(11, 7, 11, 6)
        col.setSpacing(4)
        if not me:
            head = QLabel(html.escape(m["user"] or "?"))
            head.setObjectName("who")
            col.addWidget(head)
        att = m.get("att")
        if att:
            col.addWidget(self._attachment(att, me))
        if m.get("text"):
            txt = QLabel(html.escape(m["text"]).replace("\n", "<br>"))
            txt.setObjectName("msg")
            txt.setWordWrap(True)
            txt.setTextInteractionFlags(Qt.TextSelectableByMouse)
            txt.setMaximumWidth(BUBBLE_W)
            f = QFont(txt.font())
            f.setPixelSize(13)
            fm = QFontMetrics(f)
            longest = max(fm.horizontalAdvance(line) for line in m["text"].split("\n"))
            txt.setMinimumWidth(min(BUBBLE_W, longest + 8))         # короткие фразы не переносятся по слову
            col.addWidget(txt)
        when = time.strftime("%H:%M", time.localtime(m["ts"]))
        foot = QLabel(when + ("  ✓" if me else ""))
        foot.setObjectName("when")
        foot.setAlignment(Qt.AlignRight)
        col.addWidget(foot)
        if me:
            self.lay.addStretch(1)
            self.lay.addWidget(card)
        else:
            self.lay.addWidget(card)
            self.lay.addStretch(1)
        self.card = card
        if animate:
            self._pop_in(delay)

    def _attachment(self, att, me):
        box = QFrame()
        box.setObjectName("att")
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        pm = None
        if att.get("kind") == "image" and os.path.isfile(att.get("path", "")):
            pm = QPixmap(att["path"])
        size = human_size(att.get("size", 0))
        if pm is not None and not pm.isNull():
            pic = QLabel()
            if pm.width() > BUBBLE_W:
                pm = pm.scaledToWidth(BUBBLE_W, Qt.SmoothTransformation)
            if pm.height() > 240:                                   # высокие фото не растягивают ленту
                pm = pm.scaledToHeight(240, Qt.SmoothTransformation)
            pic.setPixmap(rounded_pixmap(pm))
            pic.setAlignment(Qt.AlignCenter)
            pic.setObjectName("pic")
            pic.setToolTip(att["name"])
            v.addWidget(pic)
            cap = QLabel()
            cap.setObjectName("cap")
            cap.setText(_elide(cap, att["name"], BUBBLE_W - 64) + "  ·  " + size)
            v.addWidget(cap)
        else:
            row = QFrame()
            row.setObjectName("fileCard")
            h = QHBoxLayout(row)
            h.setContentsMargins(8, 8, 10, 8)
            h.setSpacing(10)
            ico = QLabel()
            ico.setPixmap(file_tile(att["name"]))
            ico.setFixedSize(34, 40)
            h.addWidget(ico, 0, Qt.AlignVCenter)
            info = QVBoxLayout()
            info.setSpacing(1)
            nm = QLabel()
            nm.setObjectName("fname")
            nm.setWordWrap(True)
            nm.setMaximumWidth(BUBBLE_W - 66)
            name = att["name"] if len(att["name"]) <= 48 else att["name"][:30] + "…" + att["name"][-16:]
            nm.setText(html.escape(name).replace("_", "_\u200b").replace("-", "-\u200b"))
            nm.setToolTip(att["name"])
            sz = QLabel(size)
            sz.setObjectName("cap")
            info.addWidget(nm)
            info.addWidget(sz)
            h.addLayout(info, 1)
            v.addWidget(row)
        if not me:
            b = QPushButton("⬇  " + self.panel.tr("Скачать"))
            b.setObjectName("dl")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda: self.panel.download(att))
            v.addWidget(b)
        return box

    def _pop_in(self, delay=0):
        eff = QGraphicsOpacityEffect(self)
        eff.setOpacity(0.0)
        self.setGraphicsEffect(eff)
        vw = self.panel.scroll.viewport().width() - 8
        self.adjustSize()
        target = max(self.sizeHint().height(), self.heightForWidth(vw) if vw > 0 and self.hasHeightForWidth() else 0, 24)
        cw = self.card.sizeHint().width()
        ch = self.card.heightForWidth(cw) if self.card.hasHeightForWidth() else -1
        self.card.setMinimumHeight(max(ch, self.card.sizeHint().height()))   # пузырь не сплющивается, а «выдвигается»
        self.lay.setAlignment(self.card, Qt.AlignTop)
        self.setMaximumHeight(0)
        grow = QEasingCurve(QEasingCurve.OutCubic)                   # строка раздвигает историю
        slide = QEasingCurve(QEasingCurve.OutBack)                   # пузырь выезжает и пружинит
        slide.setOvershoot(1.9)
        a = QVariantAnimation(self)
        a.setDuration(520)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        shift = 56

        def step(v):
            self.setMaximumHeight(max(0, int(target * grow.valueForProgress(min(1.0, v / 0.42)))))
            s = slide.valueForProgress(max(0.0, min(1.0, (v - 0.06) / 0.94)))
            eff.setOpacity(max(0.0, min(1.0, v * 2.4)))
            off = int((1.0 - s) * shift)                              # от края к месту; пружина за счёт OutBack
            if self._me:
                self.lay.setContentsMargins(0, 3, -off, 3)
            else:
                self.lay.setContentsMargins(-off, 3, 0, 3)

        def done():
            self.setGraphicsEffect(None)
            self.setMaximumHeight(QWIDGETSIZE_MAX)
            self.card.setMinimumHeight(0)
            self.lay.setContentsMargins(0, 3, 0, 3)
        a.valueChanged.connect(step)
        a.finished.connect(done)
        self._anim = a
        step(0.0)
        if delay:
            QTimer.singleShot(delay, a.start)                        # несколько сообщений сразу — появляются «лесенкой»
        else:
            a.start()


class EmojiPopup(QFrame):
    picked = Signal(str)

    def __init__(self, theme, tr):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        t = _theme(theme)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.T = t
        self.setStyleSheet("QToolButton { background: transparent; border: none; font-size: 19px; border-radius: 8px;"
                           " min-width: 30px; min-height: 30px; max-width: 30px; max-height: 30px; }"
                           "QToolButton:hover { background: %(hover)s; }"
                           "QToolButton:pressed { background: %(raised)s; }"
                           "QLabel { color: %(muted)s; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
                           " background: transparent; padding: 4px 4px 2px 4px; }"
                           "QWidget#sep { background: %(border)s; }" % t)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(2)
        for k, (title, items) in enumerate(((tr("Смайлики"), ns.EMOJI_COMMON), (tr("Печать и работа"), ns.EMOJI_PRINT))):
            if k:
                sep = QWidget()
                sep.setObjectName("sep")
                sep.setAttribute(Qt.WA_StyledBackground)
                sep.setFixedHeight(1)
                lay.addSpacing(4)
                lay.addWidget(sep)
            lay.addWidget(QLabel(title.upper()))
            g = QGridLayout()
            g.setSpacing(1)
            for i, e in enumerate(items):
                b = QToolButton()
                b.setText(e)
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, x=e: (self.picked.emit(x), self.close()))
                g.addWidget(b, i // 8, i % 8)
            lay.addLayout(g)

    def paintEvent(self, e):
        """Фон рисуем сами: у прозрачного всплывающего окна стиль Qt подложку не рисует, а нужны скруглённые углы."""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(self.T["border"]), 1))
        p.setBrush(QColor(self.T["surface"]))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        p.end()

    def showEvent(self, e):
        super().showEvent(e)
        a = QVariantAnimation(self)                                  # мягкое проявление, без тяжёлых эффектов
        a.setDuration(140)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.valueChanged.connect(lambda v: self.setWindowOpacity(v))
        self._fade = a
        a.start()


class PeerBar(QWidget):
    """Кому писать: кнопки «Все» и по одной на ПК (до 4); если ПК больше, остальные в выпадающем списке."""
    chosen = Signal(object)

    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.cur = None
        self.setObjectName("peerBar")
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(5)
        self.grid.setVerticalSpacing(5)
        for c in range(PEER_COLS):
            self.grid.setColumnStretch(c, 1)
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
        tr = self.panel.tr
        svc = self.panel.svc
        entries = [(None, tr("Все"), "ok", False)] + [(p["id"], p["name"], p["state"], not p["online"]) for p in peers[:MAX_TABS]]
        width = max(60, (self.width() or 250) // PEER_COLS - 34)
        for i, (pid, name, state, off) in enumerate(entries):
            n = svc.unread(pid) if pid else sum(1 for m in svc.cfg.get("chat", []) if m["chan"] == "all" and not m["me"] and not m.get("read"))
            b = QToolButton()
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setChecked(pid == self.cur)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setMinimumWidth(0)
            b.setFixedHeight(27)
            tail = (" (%d)" % n) if n else ""
            b.setText(_elide(b, name, width - (QFontMetrics(b.font()).horizontalAdvance(tail) if n else 0), Qt.ElideRight) + tail)
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("off", off)
            b.setProperty("unread", bool(n))
            if pid is not None:
                b.setIcon(dot_icon(state_color(t, state), 12, ring=not off))
                b.setIconSize(QSize(10, 10))
                b.setToolTip("%s — %s" % (name, state_text(tr, state)))
            else:
                b.setToolTip(tr("Сообщение всем подключённым ПК"))
            b.clicked.connect(lambda _=False, x=pid: self.select(x))
            self.buttons[pid] = b
            self.grid.addWidget(b, i // PEER_COLS, i % PEER_COLS)
        rest = peers[MAX_TABS:]
        if rest:
            self.more = QComboBox()
            self.more.setObjectName("more")
            self.more.setCursor(Qt.PointingHandCursor)
            self.more.addItem(tr("Ещё") + " +%d  ▾" % len(rest), "__none__")
            self.more.setToolTip(tr("Ещё ПК") + ": %d" % len(rest))
            self.more.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.more.setMinimumWidth(0)
            self.more.view().setMinimumWidth(170)
            for p in rest:
                self.more.addItem(dot_icon(state_color(t, p["state"]), 12, ring=p["online"]), p["name"], p["id"])
            i = self.more.findData(self.cur)
            self.more.setCurrentIndex(max(0, i))
            self.more.setProperty("active", i > 0)
            self.more.activated.connect(lambda _=0: self.select(self.more.currentData()) if self.more.currentData() != "__none__" else None)
            n = len(entries)                                 # «Ещё» — такая же ячейка, как кнопки ПК (5 + 1 = две строки по три)
            self.grid.addWidget(self.more, n // PEER_COLS, n % PEER_COLS)

    def select(self, pid):
        self.cur = pid
        self.rebuild(self.panel.svc.peers())
        self.chosen.emit(pid)


class ChatHead(QPushButton):
    """Шапка панели: стрелка, значок, «Чат», счётчик непрочитанных и индикатор «в сети». Рисуется сама;
    text() хранит то же самое строкой (для доступности и проверок)."""

    def __init__(self, theme):
        super().__init__()
        self.T = theme
        self.opened = False
        self.unread = 0
        self.online = 0
        self.total = 0
        self.flash = 0.0
        self.rot = 0.0
        self._hover = False
        self.title = "Чат"
        self.reserve = 0                     # место справа под кнопки шапки
        self.sub = ""
        self.setFixedHeight(42)
        self.setFlat(True)
        self._rot_anim = None

    def set_state(self, opened, unread, online, total, title, sub):
        if opened != self.opened:
            a = QVariantAnimation(self)
            a.setDuration(180)
            a.setStartValue(self.rot)
            a.setEndValue(1.0 if opened else 0.0)
            a.setEasingCurve(QEasingCurve.OutCubic)
            a.valueChanged.connect(lambda v: (setattr(self, "rot", v), self.update()))
            self._rot_anim = a
            a.start()
        self.opened, self.unread, self.online, self.total, self.title, self.sub = opened, unread, online, total, title, sub
        self.setText("%s %s%s    %s" % ("▾" if opened else "▸", title, ("  (%d)" % unread) if unread else "",
                                        "● %d/%d" % (online, total) if total else ""))
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, e):
        t = self.T
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        bg = None
        if self._hover:
            bg = QColor(t["hover"])
            bg.setAlphaF(0.55)
        if self.flash > 0:
            bg = QColor(_mix(t["surface"], t["accent"], 0.45 * self.flash))
        if bg is not None:
            path = QPainterPath()
            path.addRoundedRect(r, RADIUS - 1, RADIUS - 1)
            p.fillPath(path, bg)
        if self.opened:
            p.setPen(QPen(QColor(t["border"]), 1))
            p.drawLine(QPointF(10, r.bottom()), QPointF(r.right() - 9, r.bottom()))
        cy = r.center().y()
        # стрелка (поворачивается при раскрытии)
        p.save()
        p.translate(17, cy)
        p.rotate(90 * self.rot)
        p.setPen(QPen(QColor(t["muted"]), 1.7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline([QPointF(-2, -4), QPointF(2.5, 0), QPointF(-2, 4)])
        p.restore()
        # значок-облачко
        bub = QPainterPath()
        bub.addRoundedRect(QRectF(31, cy - 7.5, 17, 13), 4.5, 4.5)
        tail = QPainterPath()
        tail.moveTo(34, cy + 3)
        tail.lineTo(33, cy + 9)
        tail.lineTo(39.5, cy + 4.5)
        tail.closeSubpath()
        p.fillPath(bub.united(tail), QColor(t["accent"]))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["accent_text"]))
        for k in range(3):
            p.drawEllipse(QPointF(35.5 + k * 4, cy - 1), 1.15, 1.15)
        # заголовок
        f = QFont(self.font())
        f.setBold(True)
        f.setPixelSize(13)
        p.setFont(f)
        p.setPen(QColor(t["text"]))
        fm = QFontMetrics(f)
        x = 56
        p.drawText(QRectF(x, r.top(), 120, r.height()), Qt.AlignVCenter | Qt.AlignLeft, self.title)
        x += fm.horizontalAdvance(self.title) + 8
        # счётчик непрочитанных — «пилюля» цвета акцента
        if self.unread:
            fb = QFont(f)
            fb.setPixelSize(11)
            p.setFont(fb)
            s = str(self.unread) if self.unread < 100 else "99+"
            w = max(20, QFontMetrics(fb).horizontalAdvance(s) + 12)
            pill = QRectF(x, cy - 9, w, 18)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["accent"]))
            p.drawRoundedRect(pill, 9, 9)
            p.setPen(QColor(t["accent_text"]))
            p.drawText(pill, Qt.AlignCenter, s)
        # индикатор сети справа
        fs = QFont(self.font())
        fs.setPixelSize(11)
        p.setFont(fs)
        fm = QFontMetrics(fs)
        right = r.right() - 8 - self.reserve
        sub = self.sub
        if right - fm.horizontalAdvance(sub) - 18 < x + (34 if self.unread else 0):
            sub = sub.split(" ")[0]                                   # узко — оставляем только «1/5»
        sw = fm.horizontalAdvance(sub)
        p.setPen(QColor(t["muted"]))
        p.drawText(QRectF(right - sw, r.top(), sw + 2, r.height()), Qt.AlignVCenter | Qt.AlignLeft, sub)
        dx = right - sw - 10
        col = QColor(t["ok"] if self.online else (t["muted"] if not self.total else t["bad"]))
        halo = QColor(col)
        halo.setAlphaF(0.25)
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QPointF(dx, cy), 6, 6)
        p.setBrush(col)
        p.drawEllipse(QPointF(dx, cy), 3.2, 3.2)
        p.end()


class ChatPanel(QFrame):
    def __init__(self, service, theme, tr=lambda s: s, parent=None, sounds=None):
        super().__init__(parent)
        self.svc, self.T, self.tr = service, _theme(theme), tr
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

        self.head = ChatHead(self.T)
        self.head.setObjectName("chatHead")
        self.head.setCursor(Qt.PointingHandCursor)
        self.head.clicked.connect(lambda: self.toggle())
        root.addWidget(self.head)

        self.body = QWidget()
        self.body.setObjectName("chatBody")
        b = QVBoxLayout(self.body)
        b.setContentsMargins(10, 8, 10, 10)
        b.setSpacing(8)

        self.b_add = QToolButton()
        self.b_add.setObjectName("icon")
        self.b_add.setText("＋")
        self.b_add.setToolTip(tr("Подключить ПК"))
        self.b_add.setCursor(Qt.PointingHandCursor)
        self.b_add.clicked.connect(self.pair_dialog)
        self.b_snd = QToolButton()
        self.b_snd.setObjectName("icon")
        self.b_snd.setCursor(Qt.PointingHandCursor)
        self.b_snd.clicked.connect(self._toggle_sound)
        hl = QHBoxLayout(self.head)                    # звук и «подключить ПК» живут в шапке — экономим строку для ленты
        hl.setContentsMargins(0, 0, 9, 0)
        hl.setSpacing(2)
        hl.addStretch(1)
        hl.addWidget(self.b_snd)
        hl.addWidget(self.b_add)
        self.head.reserve = 58
        self.peers = PeerBar(self)
        self.peers.chosen.connect(lambda pid: self._render(True))
        b.addWidget(self.peers)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("history")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setMinimumHeight(150)
        self.holder = QWidget()
        self.holder.setObjectName("holder")
        self.col = QVBoxLayout(self.holder)
        self.col.setContentsMargins(8, 8, 6, 8)
        self.col.setSpacing(2)
        self.col.addStretch(1)
        self.scroll.setWidget(self.holder)
        self.scroll.viewport().setObjectName("histView")
        b.addWidget(self.scroll, 1)

        composer = QFrame()
        composer.setObjectName("composer")
        row = QHBoxLayout(composer)
        row.setContentsMargins(4, 3, 3, 3)
        row.setSpacing(0)
        self.b_emoji = QToolButton()
        self.b_emoji.setObjectName("flat")
        self.b_emoji.setText("😊")
        self.b_emoji.setToolTip(tr("Смайлики"))
        self.b_emoji.clicked.connect(self.show_emoji)
        self.b_file = QToolButton()
        self.b_file.setObjectName("flat")
        self.b_file.setText("📎")
        self.b_file.setToolTip(tr("Отправить файл или фото"))
        self.b_file.clicked.connect(self.pick_files)
        self.edit = QLineEdit()
        self.edit.setObjectName("input")
        self.edit.setPlaceholderText(tr("Сообщение…"))
        self.edit.returnPressed.connect(lambda: self.send(self.edit.text()))
        self.b_send = QToolButton()
        self.b_send.setObjectName("send")
        self.b_send.setText("➤")
        self.b_send.setToolTip(tr("Отправить"))
        self.b_send.clicked.connect(lambda: self.send(self.edit.text()))
        for w in (self.b_emoji, self.b_file, self.b_send):
            w.setCursor(Qt.PointingHandCursor)
        for w, st in ((self.b_emoji, 0), (self.b_file, 0), (self.edit, 1), (self.b_send, 0)):
            row.addWidget(w, st)
        b.addWidget(composer)
        root.addWidget(self.body, 1)
        self.body.setVisible(False)
        self.refresh()

    def _qss(self):
        t = self.T
        c = dict(t,
                 hist=_mix(t["bg"], t["surface"], 0.35),               # лента чуть глубже панели
                 theirs=t["raised"],
                 theirs_b=_mix(t["raised"], t["border"], 0.6),
                 mine_when=_mix(t["accent"], t["accent_text"], 0.6),
                 file_bg=_rgba(t["bg"], 0.35),
                 file_mine=_rgba(t["accent_text"], 0.12),
                 dl_bg=_mix(t["raised"], t["accent"], 0.14),
                 dl_b=_mix(t["raised"], t["accent"], 0.6),
                 chip_on=_mix(t["surface"], t["accent"], 0.18),
                 chip_unread=_mix(t["border"], t["accent"], 0.6),
                 handle=_mix(t["border"], t["muted"], 0.3),
                 r=RADIUS)
        return ("#chatPanel { background: %(surface)s; border: 1px solid %(border)s; border-radius: %(r)spx; }"
                "#chatPanel QToolTip { background: %(raised)s; color: %(text)s; border: 1px solid %(border)s; }"
                "#chatBody, QWidget#peerBar, QWidget#row, QWidget#empty { background: transparent; }"
                "QLabel#caption { color: %(muted)s; font-size: 10px; font-weight: 700; letter-spacing: 1px; background: transparent; }"
                # кнопки-иконки в строке «Кому»
                "QToolButton#icon { background: transparent; color: %(muted)s; border: 1px solid transparent; border-radius: 7px;"
                " min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px; padding: 0; font-size: 13px; }"
                "QToolButton#icon:hover { background: %(hover)s; color: %(text)s; border-color: %(border)s; }"
                # чипы ПК
                "QToolButton#chip { background: %(raised)s; color: %(text)s; border: 1px solid %(border)s; border-radius: 13px;"
                " padding: 0 8px; font-size: 12px; }"
                "QToolButton#chip:hover { background: %(hover)s; }"
                "QToolButton#chip[off=\"true\"] { color: %(muted)s; }"
                "QToolButton#chip[unread=\"true\"] { border-color: %(chip_unread)s; font-weight: 700; }"
                "QToolButton#chip:checked { background: %(accent)s; color: %(accent_text)s; border-color: %(accent)s; font-weight: 600; }"
                "QComboBox#more { background: transparent; color: %(text)s; border: 1px solid %(border)s; border-radius: 13px;"
                " padding: 0 10px; min-height: 25px; max-height: 25px; font-size: 12px; }"
                "QComboBox#more[active=\"true\"] { background: %(chip_on)s; color: %(text)s; border: 1px solid %(accent)s; }"
                "QComboBox#more:hover { background: %(hover)s; }"
                "QComboBox#more::drop-down { border: none; width: 0; }"
                "QComboBox#more::down-arrow { image: none; width: 0; height: 0; }"
                "QComboBox#more QAbstractItemView { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s;"
                " selection-background-color: %(hover)s; outline: none; padding: 4px; }"
                # лента сообщений
                "QScrollArea#history { background: %(hist)s; border: 1px solid %(border)s; border-radius: 10px; }"
                "#holder, #histView { background: %(hist)s; border: none; }"
                "QScrollArea#history QScrollBar:vertical { background: transparent; width: 8px; margin: 6px 2px 6px 0; }"
                "QScrollArea#history QScrollBar::handle:vertical { background: %(handle)s; border-radius: 3px; min-height: 28px; }"
                "QScrollArea#history QScrollBar::handle:vertical:hover { background: %(muted)s; }"
                "QScrollArea#history QScrollBar::add-line, QScrollArea#history QScrollBar::sub-line { height: 0; border: none; }"
                "QScrollArea#history QScrollBar::add-page, QScrollArea#history QScrollBar::sub-page { background: transparent; }"
                # пузыри: свой — цвет акцента, хвостик справа внизу; чужой — приподнятый, хвостик слева
                "#mine { background: %(accent)s; border: none; border-radius: 14px; border-bottom-right-radius: 4px; }"
                "#theirs { background: %(theirs)s; border: 1px solid %(theirs_b)s; border-radius: 14px; border-bottom-left-radius: 4px; }"
                "#mine QLabel { color: %(accent_text)s; background: transparent; }"
                "#theirs QLabel { color: %(text)s; background: transparent; }"
                "QLabel#msg { font-size: 13px; }"
                "QLabel#who { color: %(select)s; font-weight: 700; font-size: 12px; }"
                "#theirs QLabel#when, #theirs QLabel#cap { color: %(muted)s; font-size: 10px; }"
                "#mine QLabel#when, #mine QLabel#cap { color: %(mine_when)s; font-size: 10px; }"
                "QLabel#cap { font-size: 11px; }"
                "QLabel#fname { font-size: 12px; font-weight: 600; }"
                "#att { background: transparent; border: none; }"
                "#theirs QFrame#fileCard { background: %(file_bg)s; border: 1px solid %(border)s; border-radius: 10px; }"
                "#mine QFrame#fileCard { background: %(file_mine)s; border: none; border-radius: 10px; }"
                "QPushButton#dl { background: transparent; color: %(accent)s; border: 1px solid %(dl_b)s; border-radius: 9px;"
                " padding: 5px 10px; font-weight: 600; font-size: 12px; }"
                "QPushButton#dl:hover { background: %(accent)s; color: %(accent_text)s; border-color: %(accent)s; }"
                "QPushButton#dl:pressed { background: %(dl_b)s; }"
                # поле ввода
                "QFrame#composer { background: %(raised)s; border: 1px solid %(border)s; border-radius: 19px; }"
                "QLineEdit#input { background: transparent; color: %(text)s; border: none; padding: 4px 4px; font-size: 13px;"
                " selection-background-color: %(select)s; }"
                "QToolButton#flat { background: transparent; border: none; border-radius: 15px; font-size: 15px;"
                " min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; padding: 0; }"
                "QToolButton#flat:hover { background: %(hover)s; }"
                "QToolButton#send { background: %(accent)s; color: %(accent_text)s; border: none; border-radius: 15px;"
                " min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; padding: 0 0 0 2px; font-size: 14px; }"
                "QToolButton#send:hover { background: %(select)s; }"
                "QToolButton#send:disabled { background: %(hover)s; color: %(muted)s; }"
                # пустая лента
                "QLabel#emptyIcon { font-size: 30px; background: transparent; }"
                "QLabel#emptyTitle { color: %(text)s; font-size: 13px; font-weight: 600; background: transparent; }"
                "QLabel#emptyHint { color: %(muted)s; font-size: 11px; background: transparent; }") % c

    # ---- состояние ----
    def toggle(self, on=None):
        self.open = (not self.open) if on is None else bool(on)
        self.body.setVisible(self.open)
        self.setMinimumHeight(440 if self.open else 0)
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
        sub = ("%d/%d %s" % (online, len(peers), self.tr("в сети"))) if peers else self.tr("нет ПК")
        self.head.set_state(self.open, unread, online, len(peers), self.tr("Чат"), sub)

    def _toggle_sound(self):
        self.svc.set_sound(not self.svc.sound_on())
        self.refresh()

    # ---- сообщения ----
    def _clear(self):
        while self.col.count() > 1:
            it = self.col.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _empty(self):
        """Понятное «пусто»: что здесь будет и что сделать дальше."""
        w = QWidget()
        w.setObjectName("empty")
        w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(4)
        paired = bool(self.svc.cfg.get("paired"))
        icon = QLabel("💬" if paired else "🔌")
        icon.setObjectName("emptyIcon")
        title = QLabel(self.tr("Сообщений пока нет.") if paired else self.tr("Нет подключённых ПК"))
        title.setObjectName("emptyTitle")
        hint = QLabel(self.tr("Напишите первым или перетащите сюда фото и файлы.") if paired
                      else self.tr("Нажмите ＋ вверху, чтобы подключить другой ПК."))
        hint.setObjectName("emptyHint")
        hint.setWordWrap(True)
        v.addStretch(1)
        for x in (icon, title, hint):
            x.setAlignment(Qt.AlignCenter)
            v.addWidget(x)
        v.addStretch(1)
        return w

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
            self.col.insertWidget(0, self._empty(), 10)
        self._scroll_end(False)
        self.refresh()

    def _append_new(self):
        peer = self._peer()
        h = self.svc.history(peer)
        if (peer or "all") != self._shown_key or len(h) < self._shown:
            return self._render()
        if self._shown == 0 and self.col.count() > 1:            # убрать надпись «Сообщений пока нет»
            self.col.takeAt(0).widget().deleteLater()
        new = h[self._shown:]
        for k, m in enumerate(new):
            self.col.insertWidget(self.col.count() - 1, Bubble(self, m, animate=True, delay=min(k, 5) * 90))
        self._shown = len(h)
        self._scroll_end(True, len(new))
        self.refresh()

    def _scroll_end(self, animate, n=1):
        bar = self.scroll.verticalScrollBar()
        if not animate:
            bar.setValue(bar.maximum())
            QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))   # после раскладки лента точно внизу
            return
        start = bar.value()
        a = QVariantAnimation(self)                    # догоняем низ, пока новые пузыри раздвигают ленту
        a.setDuration(560 + min(max(n, 1) - 1, 5) * 90)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.valueChanged.connect(lambda v: bar.setValue(int(start + (bar.maximum() - start) * v)))
        a.finished.connect(lambda: bar.setValue(bar.maximum()))
        self._scroll_anim = a
        a.start()

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
        """Шапка дважды мягко вспыхивает цветом акцента, когда пришло сообщение в свёрнутый чат."""
        a = QVariantAnimation(self)
        a.setDuration(1300)
        a.setStartValue(0.0)
        a.setEndValue(1.0)

        def step(v):
            self.head.flash = abs(math.sin(v * math.pi * 2)) * (1.0 - 0.5 * v)
            self.head.update()

        def done():
            self.head.flash = 0.0
            self.head.update()
        a.valueChanged.connect(step)
        a.finished.connect(done)
        self._pulse_anim = a
        a.start()

    def pair_dialog(self):
        PairDialog(self.svc, self.T, self.tr, self).exec()
        self.refresh()


class PairDialog(QDialog):
    def __init__(self, service, theme, tr, parent=None):
        super().__init__(parent)
        self.svc, self.tr = service, tr
        t = _theme(theme)
        self.setWindowTitle(tr("Подключить ПК"))
        self.setMinimumWidth(400)
        self.setObjectName("pairDlg")
        self.setStyleSheet(
            ("#pairDlg { background: %(surface)s; }"
             "#pairDlg QLabel { color: %(text)s; background: transparent; }"
             "#pairDlg QLabel#title { font-size: 16px; font-weight: 700; }"
             "#pairDlg QLabel#hint, #pairDlg QLabel#addr { color: %(muted)s; font-size: 12px; }"
             "#pairDlg QLabel#caption { color: %(muted)s; font-size: 10px; font-weight: 700; letter-spacing: 1px; }"
             "#pairDlg QTabWidget::pane { border: 1px solid %(border)s; border-radius: 10px; background: %(raised)s; top: -1px; }"
             "#pairDlg QTabBar::tab { background: transparent; color: %(muted)s; padding: 7px 14px; border: none;"
             " border-bottom: 2px solid transparent; margin-right: 4px; }"
             "#pairDlg QTabBar::tab:selected { color: %(text)s; border-bottom-color: %(accent)s; }"
             "#pairDlg QTabBar::tab:hover { color: %(text)s; }"
             "#pairDlg QTabWidget > QWidget > QWidget { background: %(raised)s; }"
             "#pairDlg QLineEdit, #pairDlg QComboBox { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s;"
             " border-radius: 8px; padding: 6px 8px; selection-background-color: %(select)s; }"
             "#pairDlg QLineEdit:focus, #pairDlg QComboBox:focus { border-color: %(accent)s; }"
             "#pairDlg QLineEdit#code { font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 17px; font-weight: 700;"
             " letter-spacing: 1px; color: %(accent)s; padding: 10px; }"
             "#pairDlg QComboBox QAbstractItemView { background: %(surface)s; color: %(text)s; selection-background-color: %(hover)s; }"
             "#pairDlg QPushButton { background: %(raised)s; color: %(text)s; border: 1px solid %(border)s; border-radius: 8px;"
             " padding: 7px 14px; }"
             "#pairDlg QPushButton:hover { background: %(hover)s; }"
             "#pairDlg QPushButton#primary { background: %(accent)s; color: %(accent_text)s; border-color: %(accent)s; font-weight: 700; }"
             "#pairDlg QPushButton#primary:hover { background: %(select)s; border-color: %(select)s; }") % t)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        ttl = QLabel("🔗  " + tr("Подключить ПК"))
        ttl.setObjectName("title")
        lay.addWidget(ttl)
        tabs = QTabWidget()
        lay.addWidget(tabs)
        # вкладка 1: на этом ПК показать код
        w1 = QWidget()
        l1 = QVBoxLayout(w1)
        l1.setContentsMargins(14, 14, 14, 14)
        l1.setSpacing(8)
        hint1 = QLabel(tr("На другом ПК выберите «Ввести код» и введите адрес и код ниже. Код действует 5 минут."))
        hint1.setObjectName("hint")
        hint1.setWordWrap(True)
        l1.addWidget(hint1)
        self.code = QLineEdit()
        self.code.setObjectName("code")
        self.code.setReadOnly(True)
        self.code.setAlignment(Qt.AlignCenter)
        self.code.setPlaceholderText("— — — — — —")
        self.addr = QLabel(tr("Адрес этого ПК") + ": " + ", ".join(_local_addrs()))
        self.addr.setObjectName("addr")
        self.addr.setWordWrap(True)
        self.addr.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b_show = QPushButton(tr("Показать код"))
        b_show.setObjectName("primary")
        b_show.setCursor(Qt.PointingHandCursor)
        b_show.clicked.connect(self._show_code)
        l1.addWidget(b_show)
        l1.addWidget(self.code)
        l1.addWidget(self.addr)
        l1.addStretch(1)
        tabs.addTab(w1, tr("Показать код"))
        # вкладка 2: ввести код другого ПК
        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        l2.setContentsMargins(14, 14, 14, 14)
        l2.setSpacing(8)
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
        self.msg.setObjectName("hint")
        self.msg.setWordWrap(True)
        b_pair = QPushButton(tr("Подключить"))
        b_pair.setObjectName("primary")
        b_pair.setCursor(Qt.PointingHandCursor)
        b_pair.clicked.connect(self._pair)
        for x in (self.found, self.e_addr, self.e_code, b_pair, self.msg):
            l2.addWidget(x)
        l2.addStretch(1)
        tabs.addTab(w2, tr("Ввести код"))
        self.name = QLineEdit(service.user())
        self.name.setPlaceholderText(tr("Моё имя в чате"))
        self.name.editingFinished.connect(lambda: service.set_user(self.name.text()))
        cap = QLabel(tr("Моё имя в чате").upper())
        cap.setObjectName("caption")
        lay.addWidget(cap)
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
