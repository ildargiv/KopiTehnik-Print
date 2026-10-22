"""Фирменное начертание «КопиТехник Принт»: буквы нарисованы штрихами на сетке (не зависят от установленных шрифтов).
Сетка: верх заглавных 0, верх строчных 4, базовая линия 14, низ выносных 19. Штрих скруглённый, как у метки обрезки."""
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath

STROKE = 2.3        # толщина штриха в единицах сетки
GAP = 3.0           # расстояние между буквами
SPACE = 6.0
HEIGHT = 19.0       # полная высота (с выносными), для расчёта масштаба


def _poly(*pts):
    p = QPainterPath(QPointF(*pts[0]))
    for q in pts[1:]:
        p.lineTo(QPointF(*q))
    return p


def _lines(*segs):
    p = QPainterPath()
    for seg in segs:
        p.moveTo(QPointF(*seg[0]))
        for q in seg[1:]:
            p.lineTo(QPointF(*q))
    return p


def _o():
    p = QPainterPath()
    p.addRoundedRect(QRectF(1, 4, 6.5, 10), 3.2, 3.2)
    return p


def _e():
    p = QPainterPath()
    p.moveTo(7.5, 9)
    p.arcMoveTo(QRectF(1, 4, 6.5, 10), 0)
    p.arcTo(QRectF(1, 4, 6.5, 10), 0, 325)
    p.moveTo(1, 9)
    p.lineTo(7.5, 9)
    return p


def _r():
    p = QPainterPath()
    p.moveTo(1, 4)
    p.lineTo(1, 19)
    b = QPainterPath()
    b.addRoundedRect(QRectF(1, 4, 6.5, 10), 3.2, 3.2)
    p.addPath(b)
    return p


# буква -> (ширина, путь, «акцент» — индекс штриха для подсветки или None)
GLYPHS = {
    "К": (8.5, _lines([(1, 0), (1, 14)], [(8.2, 0), (1.4, 8)], [(3.6, 6.4), (8.5, 14)])),
    "о": (7.5, _o()),
    "п": (7.5, _poly((1, 14), (1, 4), (7, 4), (7, 14))),
    "и": (7.5, _lines([(1, 4), (1, 14)], [(7, 4), (7, 14)], [(7, 4), (1, 14)])),
    "Т": (9, _lines([(0.5, 0), (8.5, 0)], [(4.5, 0), (4.5, 14)])),
    "е": (7.5, _e()),
    "х": (7.5, _lines([(1, 4), (7, 14)], [(7, 4), (1, 14)])),
    "н": (7.5, _lines([(1, 4), (1, 14)], [(7, 4), (7, 14)], [(1, 9), (7, 9)])),
    "к": (7.5, _lines([(1, 4), (1, 14)], [(7.2, 4), (1, 9.2)], [(3.2, 7.7), (7.5, 14)])),
    "П": (8.5, _poly((1, 14), (1, 0), (7.5, 0), (7.5, 14))),
    "р": (7.5, _r()),
    "т": (8, _lines([(0.5, 4), (7.5, 4)], [(4, 4), (4, 14)])),
}


def _arch(top):
    """Арка «n»/«h»: ножка слева и дуга вправо-вниз."""
    p = QPainterPath()
    p.moveTo(1, top)
    p.lineTo(1, 14)
    p.moveTo(1, 8.5)
    p.arcMoveTo(QRectF(1, 4, 6.5, 9), 180)
    p.arcTo(QRectF(1, 4, 6.5, 9), 180, -180)
    p.lineTo(7.5, 14)
    return p


def _P():
    p = QPainterPath()
    p.addRoundedRect(QRectF(1, 0, 7, 8.2), 3.4, 3.4)
    p.moveTo(1, 0)
    p.lineTo(1, 14)
    return p


# латиница (английский интерфейс: «KopiTehnik Print»); совпадающие по виду буквы берём из кириллицы
GLYPHS.update({
    "K": GLYPHS["К"], "T": GLYPHS["Т"], "o": GLYPHS["о"], "e": GLYPHS["е"], "p": GLYPHS["р"],
    "i": (2, _lines([(1, 4), (1, 14)], [(1, 0.6), (1, 0.7)])),
    "h": (7.5, _arch(0)),
    "n": (7.5, _arch(4)),
    "r": (6, _lines([(1, 4), (1, 14)], [(1, 8), (2.5, 5), (5.5, 4)])),
    "t": (7, _lines([(3.5, 1), (3.5, 14)], [(0.8, 4.5), (6.7, 4.5)])),
    "P": (8.5, _P()),
    "k": (7.5, _lines([(1, 0), (1, 14)], [(7.2, 4), (1, 9.2)], [(3.2, 7.7), (7.5, 14)])),
})


def has_glyphs(text):
    return all(ch == " " or ch in GLYPHS for ch in text)


def layout(text):
    """[(символ, путь со сдвигом по x)] и полная ширина в единицах сетки."""
    out, x = [], 0.0
    for ch in text:
        if ch == " ":
            x += SPACE
            continue
        w, path = GLYPHS[ch]
        out.append((ch, path.translated(x, 0)))
        x += w + GAP
    return out, max(0.0, x - GAP)
