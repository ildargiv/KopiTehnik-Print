"""Фирменное начертание «Дата-штамп»: моноширинная точечная матрица 5×7, как оранжевая дата, которую плёночные
мыльницы впечатывали в угол кадра. «КОПИТЕХНИК» — ровные точки цвета текста, «ПРИНТ» — светящиеся оранжевые.
Под словом — кромка плёнки: перфорация и номер кадра.
Знак: тёмная плитка-«кадр» со светящейся точечной «К» и номером кадра; на 16–32 px точки становятся пикселями."""
import math
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QRadialGradient, QBrush, QPen, QPainterPath



class c:                                            # мелкие помощники (раньше в общем модуле набросков)
    DARK_BG, LIGHT_BG = "#17181c", "#f4f4f6"

    @staticmethod
    def ink(dark):
        return QColor("#f4f4f6") if dark else QColor("#1c1d22")

    @staticmethod
    def mix(a, b, t):
        a, b = QColor(a), QColor(b)
        return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                      round(a.blue() + (b.blue() - a.blue()) * t), round(a.alpha() + (b.alpha() - a.alpha()) * t))

    @staticmethod
    def rounded(rect, r):
        p = QPainterPath()
        p.addRoundedRect(QRectF(rect), r, r)
        return p

FONT = {
    # кириллица и латиница; совпадающие по виду буквы (К О Т Е Н Р Х) общие
    "К": ["1...1", "1..1.", "1.1..", "11...", "1.1..", "1..1.", "1...1"],
    "О": [".111.", "1...1", "1...1", "1...1", "1...1", "1...1", ".111."],
    "П": ["11111", "1...1", "1...1", "1...1", "1...1", "1...1", "1...1"],
    "И": ["1...1", "1...1", "1..11", "1.1.1", "11..1", "1...1", "1...1"],
    "Т": ["11111", "..1..", "..1..", "..1..", "..1..", "..1..", "..1.."],
    "Е": ["11111", "1....", "1....", "1111.", "1....", "1....", "11111"],
    "Х": ["1...1", "1...1", ".1.1.", "..1..", ".1.1.", "1...1", "1...1"],
    "Н": ["1...1", "1...1", "1...1", "11111", "1...1", "1...1", "1...1"],
    "Р": ["1111.", "1...1", "1...1", "1111.", "1....", "1....", "1...."],
    "K": ["1...1", "1..1.", "1.1..", "11...", "1.1..", "1..1.", "1...1"],
    "I": ["11111", "..1..", "..1..", "..1..", "..1..", "..1..", "11111"],
    "N": ["1...1", "11..1", "11..1", "1.1.1", "1..11", "1..11", "1...1"],
    "R": ["1111.", "1...1", "1...1", "1111.", "1.1..", "1..1.", "1...1"],
    "2": [".111.", "1...1", "....1", "...1.", "..1..", ".1...", "11111"],
    "7": ["11111", "....1", "...1.", "..1..", ".1...", ".1...", ".1..."],
    "6": ["..11.", ".1...", "1....", "1111.", "1...1", "1...1", ".111."],
    "'": ["..1..", "..1..", ".1...", ".....", ".....", ".....", "....."],
    "▸": ["1....", "11...", "111..", "1111.", "111..", "11...", "1...."],
}
FONT.update({"O": FONT["О"], "T": FONT["Т"], "E": FONT["Е"], "H": FONT["Н"], "P": FONT["Р"]})
CELL = 6          # 5 точек + 1 шаг
SPACE = 4
DOT = 0.78        # диаметр точки в шагах сетки
WORD_A, WORD_B = "КОПИТЕХНИК", "ПРИНТ"
TOTAL_W = 0.0
EDGE = 3.2        # высота кромки плёнки под словом (в шагах)
UNIT_H = 7 + 1.3 + EDGE


def _text_w(t):
    return sum(SPACE if ch == " " else CELL for ch in t) - 1




def _dots(text, x0=0.0):
    out, x = [], x0
    for ch in text:
        if ch == " ":
            x += SPACE
            continue
        for r, row in enumerate(FONT[ch]):
            for col, v in enumerate(row):
                if v == "1":
                    out.append((x + col, r))
        x += CELL
    return out


def _glow_dot(p, cx, cy, d, color, glow):
    if glow:
        g = QRadialGradient(QPointF(cx, cy), d * 1.25)
        col = QColor(color)
        col.setAlpha(glow)
        g.setColorAt(0, col)
        col2 = QColor(color)
        col2.setAlpha(0)
        g.setColorAt(1, col2)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), d * 1.25, d * 1.25)
    p.setBrush(QColor(color))
    p.drawEllipse(QPointF(cx, cy), d / 2, d / 2)


def set_name(text):
    """Название «Слово1 Слово2» (кириллица или латиница); возвращает False, если в нём есть незнакомые буквы."""
    global WORD_A, WORD_B, TOTAL_W
    a, _, b = text.upper().partition(" ")
    if not all(ch in FONT for ch in a + b):
        return False
    WORD_A, WORD_B = a, b
    TOTAL_W = _text_w(a) + SPACE + 1 + _text_w(b)
    return True


set_name("КопиТехник Принт")


def _unit_h(h):
    return UNIT_H if h >= 40 else 7.0             # мелко (в шапке) — без кромки плёнки


def wordmark_size(h):
    k = h / _unit_h(h)
    return TOTAL_W * k, h


def draw_wordmark(p, x, y, h, dark, phase=None, reveal=1.0):
    k = h / _unit_h(h)
    p.save()
    p.translate(x, y)
    p.scale(k, k)
    p.setPen(Qt.NoPen)
    fg = c.ink(dark)
    shown = reveal * (TOTAL_W + 6)
    for (dx, dy) in _dots(WORD_A):
        if dx > shown:
            continue
        _glow_dot(p, dx + 0.5, dy + 0.5, DOT, fg, 0)
    xb = _text_w(WORD_A) + SPACE + 1
    hot = QColor("#ff8a1e") if dark else QColor("#f06a00")
    for (dx, dy) in _dots(WORD_B, xb):
        if dx > shown:
            continue
        if phase is None:
            _glow_dot(p, dx + 0.5, dy + 0.5, DOT * 1.02, hot, 110 if dark else 0)
        else:                                       # бегущая волна яркости по оранжевым точкам
            w = 0.5 + 0.5 * math.sin((phase - (dx - xb) / 30.0) * 2 * math.pi)
            col = c.mix(hot, QColor("#ffe08a"), 0.85 * w ** 3)
            _glow_dot(p, dx + 0.5, dy + 0.5, DOT * 1.02, col, int(70 + 110 * w) if dark else 0)
    if h < 40:
        p.restore()
        return
    # кромка плёнки: перфорация и номер кадра «▸27»
    ey = 7 + 1.3
    edge_col = c.mix(fg, QColor(c.DARK_BG if dark else c.LIGHT_BG), 0.72)
    p.setBrush(edge_col)
    hole_w, hole_h, step = 1.5, 1.05, 3.0
    xs = 0.0
    tag_x = xb                                     # номер кадра — под «ПРИНТ»
    while xs + hole_w <= TOTAL_W + 0.01:
        if not (tag_x - 1 <= xs + hole_w and xs <= tag_x + 6.2):
            p.drawRoundedRect(QRectF(xs, ey + 0.6, hole_w, hole_h), 0.35, 0.35)
        xs += step
    # номер кадра мелкой матрицей (шаг 0.33)
    p.save()
    p.translate(tag_x + 0.2, ey + 0.1)
    p.scale(0.3, 0.3)
    for (dx, dy) in _dots("▸27"):
        _glow_dot(p, dx + 0.5, dy + 0.5, 0.9, hot, 0)
    p.restore()
    p.restore()


def draw_mark(p, rect, dark=True):
    s = rect.width()
    tile = QRectF(rect.left() + s * 0.04, rect.top() + s * 0.04, s * 0.92, s * 0.92)
    p.save()
    p.setPen(Qt.NoPen)
    path = c.rounded(tile, s * 0.22)
    base = QColor("#22242b")
    p.fillPath(path, base)
    if True:                         # тонкий оранжевый ободок-«кадр»
        pen = QPen(QColor(255, 140, 40, 120 if dark else 200), max(1.0, s * 0.012))
        p.strokePath(c.rounded(tile.adjusted(pen.widthF() / 2, pen.widthF() / 2, -pen.widthF() / 2, -pen.widthF() / 2),
                               s * 0.22 - pen.widthF() / 2), pen)
    hot = QColor("#ff8a1e")
    glyph = FONT["К"]
    if s <= 40:
        # пиксельная сетка: точки — квадраты, ровно по пикселям
        pitch = max(2, round(s * 0.62 / 7))
        dot = pitch - 1 if pitch >= 3 else pitch
        gw, gh = 5 * pitch - (pitch - dot), 7 * pitch - (pitch - dot)
        ox = round(rect.left() + (s - gw) / 2)
        oy = round(rect.top() + (s - gh) / 2)
        hot2 = QColor("#ff9a2e")
        for r, row in enumerate(glyph):
            for col, v in enumerate(row):
                if v == "1":
                    p.fillRect(QRectF(ox + col * pitch, oy + r * pitch, dot, dot), hot2)
    else:
        pitch = s * 0.082
        gw, gh = 5 * pitch, 7 * pitch
        ox = tile.center().x() - gw / 2
        oy = tile.center().y() - gh / 2 - s * 0.03
        for r, row in enumerate(glyph):
            for col, v in enumerate(row):
                if v == "1":
                    _glow_dot(p, ox + (col + 0.5) * pitch, oy + (r + 0.5) * pitch, pitch * 0.8, hot, 120)
        # номер кадра внизу справа и перфорация сверху
        q = s * 0.0105
        p.save()
        p.translate(tile.right() - 17 * q - s * 0.1, tile.bottom() - 7 * q - s * 0.075)
        p.scale(q, q)
        for (dx, dy) in (_dots("'27") if s >= 128 else []):
            _glow_dot(p, dx + 0.5, dy + 0.5, 0.85, hot, 90)
        p.restore()
        p.setBrush(QColor(255, 255, 255, 38))
        hw, hh = s * 0.07, s * 0.045
        n = 5
        span = tile.width() * 0.62
        for i in range(n):
            cx = tile.center().x() - span / 2 + span * i / (n - 1)
            p.drawRoundedRect(QRectF(cx - hw / 2, tile.top() + s * 0.07, hw, hh), hh * 0.3, hh * 0.3)
    p.restore()
