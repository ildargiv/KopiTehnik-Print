# -*- coding: utf-8 -*-
"""Тестовый лист для проверки печати: серый клин, тени и света, цвета, оттенки кожи, портреты, градиенты, резкость, поля.

Раскладка считается в миллиметрах от размера листа и переводится в пиксели по dpi. Цвета — обычные sRGB 0–255,
профили не встраиваются и на выходе ничего не корректируется. Без Qt: только Pillow и numpy.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

# ---------------------------------------------------------------- цвета

PRIMARIES = (("R", (255, 0, 0)), ("G", (0, 255, 0)), ("B", (0, 0, 255)),
             ("C", (0, 255, 255)), ("M", (255, 0, 255)), ("Y", (255, 255, 0)))
GRAY18 = (118, 118, 118)        # серая карта 18 %: отражение 0,18 в sRGB ≈ 118 (L* ≈ 50)
NEUTRALS = (("100 %", (255, 255, 255)), ("96 %", (245, 245, 245)), ("50 %", (128, 128, 128)),
            ("18 % (gray card)", GRAY18), ("0 %", (0, 0, 0)))
SHADOW_PCT = (0, 1, 2, 3, 4, 5)
LIGHT_PCT = (95, 96, 97, 98, 99, 100)
SAT_STEPS = (100, 80, 60, 40, 20, 0)

# Оттенки кожи: типовые значения sRGB по шкале Фицпатрика I–VI, не стандарт и не измерение.
# На каждый тип две плашки — светлее и темнее; яркость убывает от I к VI.
SKIN = (("I", (250, 228, 214), (243, 213, 195)),
        ("II", (238, 203, 179), (229, 188, 160)),
        ("III", (222, 178, 148), (208, 160, 125)),
        ("IV", (196, 143, 106), (176, 124, 88)),
        ("V", (150, 100, 68), (122, 80, 54)),
        ("VI", (96, 62, 44), (68, 44, 32)))

TEXT = (40, 40, 40)
MUTED = (100, 100, 100)
FRAME = (160, 160, 160)

# ---------------------------------------------------------------- шрифт

FONT_FILES = ("segoeui.ttf", "arial.ttf", r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf",
              "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
              "/Library/Fonts/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf")
_FONTS = {}


def _font(px):
    """Шрифт с кириллицей нужного размера; если ни одного нет — встроенный шрифт Pillow."""
    px = max(6, int(px))
    if px not in _FONTS:
        f = None
        for name in FONT_FILES:
            try:
                f = ImageFont.truetype(name, px)
                break
            except Exception:
                continue
        for fallback in (lambda: ImageFont.load_default(px), getattr(ImageFont, "load_default_imagefont", None),
                         ImageFont.load_default):
            if f is not None or fallback is None:
                continue
            try:
                f = fallback()
            except Exception:
                f = None
        _FONTS[px] = f
    return _FONTS[px]


def _text(d, xy, s, font, fill=TEXT, anchor="la"):
    """Подпись; встроенный шрифт без кириллицы не должен ронять лист."""
    try:
        d.text(xy, s, fill=fill, font=font, anchor=anchor)
    except Exception:
        s = s.encode("ascii", "replace").decode("ascii")
        try:
            d.text(xy, s, fill=fill, font=font, anchor=anchor)
        except Exception:
            d.text(xy, s, fill=fill, font=font)


def _tw(d, s, font):
    try:
        b = d.textbbox((0, 0), s, font=font)
    except Exception:
        b = d.textbbox((0, 0), s.encode("ascii", "replace").decode("ascii"), font=font)
    return b[2] - b[0]


def _fit_font(d, s, pt, max_w, k):
    """Шрифт pt, уменьшенный (не меньше 4 pt), чтобы строка влезла в max_w пикселей."""
    while True:
        f = _font(pt * k.pt)
        if pt <= 4 or _tw(d, s, f) <= max_w:
            return f
        pt -= 0.5


class _K:
    """Перевод мм и пунктов в пиксели."""
    def __init__(self, dpi):
        self.mm = dpi / 25.4
        self.pt = dpi / 72.0

    def __call__(self, mm):
        return int(round(mm * self.mm))


# ---------------------------------------------------------------- раскладка (в мм, потом в пиксели)

LABEL = 3.6      # строка подписи под плашками, мм
CAPTION = 4.0    # заголовок блока, мм
GAP = 2.6        # промежуток между блоками, мм


def _mm_layout(w, h):
    """Блоки листа в мм: {имя: (x, y, ширина, высота)}. Компактная версия — для листов меньше A5."""
    compact = min(w, h) < 130
    m = 6.0 if compact else 8.0                       # от края до содержимого (рамка полей — в 3 мм)
    cw = w - 2 * m
    head, foot = (5.0, 4.0) if compact else (9.0, 5.5)
    avail = h - 2 * m - head - foot
    # (имя, масштабируемая высота, постоянная высота: заголовок и подписи)
    if compact:
        blocks = [("wedge", 7, CAPTION + LABEL), ("shadows", 6, LABEL), ("colors", 6, CAPTION + LABEL),
                  ("skin", 14, CAPTION + LABEL), ("portraits", None, LABEL + 1), ("gradients", 7 * 3.6, CAPTION)]
    else:
        blocks = [("wedge", 11, CAPTION + LABEL), ("shadows", 9, LABEL), ("colors", 6 * 5.5, CAPTION + LABEL),
                  ("neutrals", 14, CAPTION + 12), ("skin", 30, CAPTION + LABEL), ("portraits", None, LABEL + 1),
                  ("gradients", 7 * 7.0, CAPTION)]
    fixed = sum(b[2] for b in blocks) + GAP * (len(blocks) - 1)
    scal = sum(b[1] for b in blocks if b[1])
    want_p = avail * (0.33 if compact else 0.27)       # окна портретов забирают остаток, не меньше этой доли
    f = max(0.4, min(1.4, (avail - fixed - want_p) / scal))
    port_h = max(8.0, avail - fixed - f * scal)
    out = {"compact": compact, "margin": m, "head": (m, m, cw, head), "foot": (m, h - m - foot, cw, foot)}
    y = m + head
    for name, s, fx in blocks:
        bh = (port_h if s is None else s * f) + fx
        out[name] = (m, y, cw, bh)
        y += bh + GAP
    return out


def _windows(x, y, w, h, n_max, gap):
    """Окна портретов (вертикальные, примерно 3:4) в полосе x, y, w, h; количество — по наибольшей площади."""
    best = None
    for n in range(1, n_max + 1):
        ww = min((w - (n - 1) * gap) / n, h * 0.8)
        wh = min(h, ww / 0.66)
        area = n * ww * wh
        if best is None or area >= best[0] * 0.98:
            best = (area, n, ww, wh)
    _a, n, ww, wh = best
    x0 = x + (w - n * ww - (n - 1) * gap) / 2
    return [(x0 + i * (ww + gap), y, ww, wh) for i in range(n)]


def _rotated(w, h):
    """Маленький альбомный лист (10×15 лёжа) раскладывается как книжный и поворачивается: в высоту блоки не влезают."""
    return w > h and min(w, h) < 130


def layout(width_mm, height_mm, dpi=300):
    """Раскладка листа в пикселях: {имя блока: (x0, y0, x1, y1)}, плюс клетки клина, кожи и окна портретов.
    Для маленького альбомного листа (rotated=True) координаты даны в книжной ориентации, до поворота."""
    if _rotated(width_mm, height_mm):
        out = layout(height_mm, width_mm, dpi)
        out["rotated"] = True
        return out
    k = _K(dpi)
    W, H = max(1, k(width_mm)), max(1, k(height_mm))
    L = _mm_layout(width_mm, height_mm)

    def box(x, y, w, h):
        return (k(x), k(y), k(x + w), k(y + h))

    out = {"size": (W, H), "compact": L["compact"], "rotated": False}
    for name in ("head", "foot", "wedge", "shadows", "colors", "skin", "portraits", "gradients", "neutrals"):
        if name in L:
            out[name] = box(*L[name])
    # клин: 21 ступень под заголовком
    x, y, w, h = L["wedge"]
    y0, y1 = y + CAPTION, y + h - LABEL
    out["wedge_cells"] = [box(x + w * i / 21, y0, w / 21, y1 - y0) for i in range(21)]
    # кожа: 6 типов × 2 плашки, справа серая 18 %
    x, y, w, h = L["skin"]
    lab = 9.0 if not L["compact"] else 6.5
    gw = max(8.0, w * 0.09)
    cw = (w - lab - gw - 1.5) / 6
    y0, ch = y + CAPTION, (h - CAPTION - LABEL) / 2
    out["skin_cells"] = [box(x + lab + i * cw, y0 + j * ch, cw, ch) for i in range(6) for j in range(2)]
    out["skin_gray"] = box(x + w - gw, y0, gw, 2 * ch)
    # портреты; на компактном листе справа от окна колонка с нейтральными плашками и мишенью
    x, y, w, h = L["portraits"]
    ih = h - LABEL - 1
    if L["compact"]:
        win = _windows(x, y, w * 0.56, ih, 1, 3.0)
        wx = win[0][0] + win[0][2] + 4.0
        out["side"] = box(wx, y, x + w - wx, ih)
    else:
        win = _windows(x, y, w, ih, 3, 5.0)
    out["windows"] = [box(*b) for b in win]
    return out


# ---------------------------------------------------------------- блоки

def _rect(d, b, fill, outline=None):
    x0, y0, x1, y1 = b
    if x1 > x0 and y1 > y0:
        d.rectangle((x0, y0, x1 - 1, y1 - 1), fill=fill, outline=outline)


def _bar(d, x0, y0, x1, y1, fill=(0, 0, 0)):
    """Прямоугольник с включёнными краями; пустой не рисуется (на малых листах блоки бывают нулевыми)."""
    if x1 >= x0 and y1 >= y0:
        d.rectangle((x0, y0, x1, y1), fill=fill)


def _caption(d, b, s, k):
    _text(d, (b[0], b[1]), s, _fit_font(d, s, 7.5, b[2] - b[0], k), fill=TEXT)


def _outline(d, x0, y0, x1, y1):
    """Тонкий контур вокруг ряда плашек снаружи: видна граница белых ступеней."""
    d.rectangle((x0 - 1, y0 - 1, x1, y1), outline=(190, 190, 190), width=1)


def _cells_row(d, x0, x1, y0, y1, colors, labels, k, lab_font=None):
    """Плашки встык по ширине x0..x1, подписи под ними."""
    n = len(colors)
    f = lab_font or _font(6 * k.pt)
    for i, col in enumerate(colors):
        a, b = x0 + round((x1 - x0) * i / n), x0 + round((x1 - x0) * (i + 1) / n)
        _rect(d, (a, y0, b, y1), tuple(col))
        if labels and labels[i]:
            _text(d, ((a + b) // 2, y1 + k(0.6)), labels[i], f, fill=MUTED, anchor="ma")


def _wedge(d, L, k):
    _caption(d, L["wedge"], "Gray wedge: 21 steps, 0–100 % (5 % each)", k)
    cells = L["wedge_cells"]
    cw = cells[0][2] - cells[0][0]
    f = _fit_font(d, "100", 6, cw * 0.8, k)
    every = 1 if _tw(d, "100", f) <= cw * 0.9 else 2           # узкий клин — подпись через ступень
    for i, b in enumerate(cells):
        v = round(i * 255 / 20)
        _rect(d, b, (v, v, v))
        if i % every == 0:
            _text(d, ((b[0] + b[2]) // 2, b[3] + k(0.6)), str(i * 5), f, fill=MUTED, anchor="ma")
    _outline(d, cells[0][0], cells[0][1], cells[-1][2], cells[-1][3])


def _shadows(d, L, k):
    """Тени 0–5 % и света 95–100 % встык, между ними серая 18 %."""
    x0, y0, x1, y1 = L["shadows"]
    y1 -= k(LABEL)
    w = x1 - x0
    gw = max(k(8), w // 10)
    left, right = x0 + (w - gw) // 2 - k(2), x0 + (w + gw) // 2 + k(2)
    lf = _fit_font(d, "100 %", 6, (x1 - right) / 6 * 0.9, k)
    _cells_row(d, x0, left, y0, y1, [(round(p * 2.55),) * 3 for p in SHADOW_PCT],
               ["%d %%" % p for p in SHADOW_PCT], k, lf)
    _cells_row(d, right, x1, y0, y1, [(round(p * 2.55),) * 3 for p in LIGHT_PCT],
               ["%d %%" % p for p in LIGHT_PCT], k, lf)
    _outline(d, x0, y0, left, y1)
    _outline(d, right, y0, x1, y1)
    g = (x0 + (w - gw) // 2, y0, x0 + (w + gw) // 2, y1)
    _rect(d, g, GRAY18)
    _text(d, ((g[0] + g[2]) // 2, y1 + k(0.6)), "18 %", lf, fill=MUTED, anchor="ma")
    f = _font(5.5 * k.pt)
    _text(d, (x0 + k(1), y0 + k(0.8)), "shadows", f, fill=(150, 150, 150))
    _text(d, (x1 - k(1), y0 + k(0.8)), "highlights", f, fill=(140, 140, 140), anchor="ra")


def _tint(c, p):
    """Цвет в p % к белому (как в тестовой странице поправки)."""
    return tuple(round(255 - (255 - v) * p / 100.0) for v in c)


def _desat(c, p):
    """Насыщенность p %: смесь цвета с серым той же яркости."""
    y = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    return tuple(round(y + (v - y) * p / 100.0) for v in c)


def _colors(d, L, k, compact):
    x0, y0, x1, y1 = L["colors"]
    if compact:
        _caption(d, L["colors"], "Colors R G B C M Y: 100 % and 50 %, gray 18 %", k)
        cy0, cy1 = y0 + k(CAPTION), y1 - k(LABEL)
        gx = x1 - max(k(6), (x1 - x0) // 13)
        cols = [c for _n, c in PRIMARIES] + [_tint(c, 50) for _n, c in PRIMARIES]
        labs = [n for n, _c in PRIMARIES] + [n + "50" for n, _c in PRIMARIES]
        _cells_row(d, x0, gx - k(1), cy0, cy1, cols, labs, k, _font(5 * k.pt))
        _rect(d, (gx, cy0, x1, cy1), GRAY18)
        _text(d, ((gx + x1) // 2, cy1 + k(0.6)), "18 %", _font(5 * k.pt), fill=MUTED, anchor="ma")
        return
    _caption(d, L["colors"], "Primary and secondary colors: 100 %, 50 % and saturation 100 → 0 % (toward gray of equal brightness)", k)
    cy0, cy1 = y0 + k(CAPTION), y1 - k(LABEL)
    lab = k(6)
    gap = k(2.5)
    w = x1 - x0 - lab - 2 * gap
    cell = w / 9.0
    xa = x0 + lab                    # 100 % и 50 %
    xs = xa + 2 * cell + gap         # шесть ступеней насыщенности
    xg = xs + 6 * cell + gap         # серая 18 %
    rh = (cy1 - cy0) / 6.0
    f = _font(7 * k.pt)
    for j, (name, c) in enumerate(PRIMARIES):
        ra, rb = cy0 + round(j * rh), cy0 + round((j + 1) * rh)
        _text(d, (x0, (ra + rb) // 2), name, f, anchor="lm")
        _rect(d, (round(xa), ra, round(xa + cell), rb), c)
        _rect(d, (round(xa + cell), ra, round(xa + 2 * cell), rb), _tint(c, 50))
        for i, p in enumerate(SAT_STEPS):
            _rect(d, (round(xs + i * cell), ra, round(xs + (i + 1) * cell), rb), _desat(c, p))
    _rect(d, (round(xg), cy0, x1, cy1), GRAY18)
    fl = _font(6 * k.pt)
    ly = cy1 + k(0.6)
    for i, s in enumerate(("100 %", "50 %")):
        _text(d, (round(xa + (i + 0.5) * cell), ly), s, fl, fill=MUTED, anchor="ma")
    for i, p in enumerate(SAT_STEPS):
        _text(d, (round(xs + (i + 0.5) * cell), ly), "sat %d" % p if i == 0 else str(p), fl, fill=MUTED, anchor="ma")
    _text(d, (round((xg + x1) / 2), ly), "18 %", fl, fill=MUTED, anchor="ma")


def _skin(d, L, k, compact):
    x0, y0, x1, y1 = L["skin"]
    _caption(d, L["skin"], "Skin tones, Fitzpatrick I–VI (typical values, not a standard): lighter above, darker below"
             if not compact else "Skin I–VI (typical values): lighter / darker", k)
    cells = L["skin_cells"]
    for i, (_n, light, dark) in enumerate(SKIN):
        _rect(d, cells[2 * i], light)
        _rect(d, cells[2 * i + 1], dark)
    f = _font((8 if not compact else 6.5) * k.pt)
    for i, (n, _l, _d) in enumerate(SKIN):
        b = cells[2 * i + 1]
        _text(d, ((b[0] + b[2]) // 2, b[3] + k(0.6)), n, f, anchor="ma")
    fs = _font((6 if not compact else 5) * k.pt)
    lx = x0
    _text(d, (lx, (cells[0][1] + cells[0][3]) // 2), "light", fs, fill=MUTED, anchor="lm")
    _text(d, (lx, (cells[1][1] + cells[1][3]) // 2), "dark", fs, fill=MUTED, anchor="lm")
    g = L["skin_gray"]
    _rect(d, g, GRAY18)
    _text(d, ((g[0] + g[2]) // 2, g[3] + k(0.6)), "18 %", fs, fill=MUTED, anchor="ma")


def _fit_portrait(img, size):
    """Портрет в окно: по центру с обрезкой, без искажения пропорций; прозрачность — на белом."""
    img = ImageOps.exif_transpose(img) if hasattr(img, "getexif") else img
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
    return ImageOps.fit(img.convert("RGB"), size, Image.LANCZOS, centering=(0.5, 0.5))


def _portraits(d, im, L, k, portraits):
    portraits = [p for p in (portraits or []) if p is not None]
    f = _font(7 * k.pt)
    for i, b in enumerate(L["windows"]):
        x0, y0, x1, y1 = b
        if i < len(portraits):
            im.paste(_fit_portrait(portraits[i], (x1 - x0, y1 - y0)), (x0, y0))
        else:
            d.rectangle((x0, y0, x1 - 1, y1 - 1), fill=(236, 236, 236), outline=FRAME, width=max(1, k(0.5)))
            _text(d, ((x0 + x1) // 2, (y0 + y1) // 2), "Your portrait here",
                  _fit_font(d, "Your portrait here", 8, (x1 - x0) * 0.85, k), fill=(120, 120, 120), anchor="mm")
        _text(d, ((x0 + x1) // 2, y1 + k(0.8)), "Portrait %d" % (i + 1), f, anchor="ma")


def _gradients(im, d, L, k, compact):
    """Плавные полосы на всю ширину: серый 0→100 % яркости, цвета от белого (0 %) до чистого (100 %)."""
    x0, y0, x1, y1 = L["gradients"]
    _caption(d, L["gradients"], "Gradients 0 → 100 % (banding and smoothness)", k)
    gy0 = y0 + k(CAPTION)
    lab = k(5)
    gx0 = x0 + lab
    n = 7
    t = np.linspace(0.0, 1.0, max(1, x1 - gx0))[None, :, None]
    f = _font((6 if not compact else 4.5) * k.pt)
    rows = [("K", (0, 0, 0), (255, 255, 255))] + [(nm, (255, 255, 255), c) for nm, c in PRIMARIES]
    for j, (name, a, b) in enumerate(rows):
        ra, rb = gy0 + round((y1 - gy0) * j / n), gy0 + round((y1 - gy0) * (j + 1) / n)
        if rb - ra < 1:
            continue
        a, b = np.array(a, np.float32), np.array(b, np.float32)
        line = np.rint(a + (b - a) * t).astype(np.uint8)
        im.paste(Image.fromarray(np.repeat(line, rb - ra, axis=0), "RGB"), (gx0, ra))
        _text(d, (x0, (ra + rb) // 2), name, f, anchor="lm")


def _neutrals(d, b, k, vertical=False):
    """Крупные нейтральные плашки с подписью внутри."""
    x0, y0, x1, y1 = b
    n = len(NEUTRALS)
    for i, (name, c) in enumerate(NEUTRALS):
        if vertical:
            cb = (x0, y0 + round((y1 - y0) * i / n), x1, y0 + round((y1 - y0) * (i + 1) / n))
        else:
            cb = (x0 + round((x1 - x0) * i / n), y0, x0 + round((x1 - x0) * (i + 1) / n), y1)
        _rect(d, cb, c, outline=(200, 200, 200) if c[0] > 240 else None)
        s = name.split(" (")[0] if vertical else name
        fc = (60, 60, 60) if c[0] > 140 else (210, 210, 210)
        _text(d, (cb[0] + k(1.2), cb[3] - k(1)), s, _fit_font(d, s, 6, cb[2] - cb[0] - k(2), k), fill=fc, anchor="ld")


def _star(d, cx, cy, r, spokes=36):
    """Звезда Сименса: чередующиеся чёрные и белые секторы."""
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255))
    step = 360.0 / spokes
    for i in range(0, spokes, 2):
        d.pieslice((cx - r, cy - r, cx + r, cy + r), i * step, (i + 1) * step, fill=(0, 0, 0))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(0, 0, 0), width=1)


def _lines(d, b, k):
    """Мишень из тонких линий 1, 2, 3 px при 300 dpi (0,08 / 0,17 / 0,25 мм): горизонтальные и вертикальные пары."""
    x0, y0, x1, y1 = b
    groups = (("0.08", 0.085), ("0.17", 0.17), ("0.25", 0.254))
    gw = (x1 - x0) / 3.0
    f = _fit_font(d, "0.08 mm", 5, gw - k(1.5), k)
    lab = k(2.6)
    for i, (name, mm) in enumerate(groups):
        t = max(1, k(mm))
        a, bnd = round(x0 + i * gw), round(x0 + (i + 1) * gw) - k(1)
        hh = (y1 - y0 - lab) // 2
        y = y0
        while y + t <= y0 + hh:                                         # горизонтальные
            _bar(d, a, y, bnd - 1, y + t - 1)
            y += 2 * t
        x = a
        while x + t <= bnd:                                             # вертикальные
            _bar(d, x, y0 + hh + k(0.5), x + t - 1, y0 + 2 * hh - 1)
            x += 2 * t
        _text(d, ((a + bnd) // 2, y1 - lab + k(0.4)), name + " mm", f, fill=MUTED, anchor="ma")


def _hatch(im, b, k):
    """Штриховки: диагональ 45° слева и мелкая сетка справа (numpy, без вылета за блок)."""
    x0, y0, x1, y1 = b
    w, h = x1 - x0, y1 - y0
    if w < 2 or h < 2:
        return
    t = max(1, k(0.085))
    step = max(3, k(0.5))
    yy, xx = np.mgrid[0:h, 0:w]
    diag = (xx + yy) % step < t
    grid = (xx % step < t) | (yy % step < t)
    ink = np.where(xx < w // 2 - k(0.5), diag, np.where(xx >= w // 2, grid, False))
    im.paste(Image.fromarray(np.where(ink, 0, 255).astype(np.uint8), "L").convert("RGB"), (x0, y0))


def _small_text(im, b, k):
    """Мелкий текст 4, 5, 6 pt: сверху чёрный на белом, снизу белый на чёрном (обрезается по блоку)."""
    x0, y0, x1, y1 = b
    w, h = x1 - x0, y1 - y0
    if w < 2 or h < 2:
        return
    tile = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(tile)
    _bar(d, 0, h // 2, w, h, (0, 0, 0))
    rh = h / 6.0
    for j, fill in enumerate(((0, 0, 0), (255, 255, 255))):
        for i, pt in enumerate((4, 5, 6)):
            _text(d, (k(0.8), round(rh * (3 * j + i + 0.5))), "%d pt The quick brown fox 0123" % pt, _font(pt * k.pt),
                  fill=fill, anchor="lm")
    im.paste(tile, (x0, y0))


def _sharpness(im, d, b, k, compact):
    """Блок резкости: звезда Сименса, линии, штриховка, мелкий текст."""
    x0, y0, x1, y1 = b
    h = y1 - y0
    if compact:                       # колонка: звезда, линии, текст столбиком
        r = min((x1 - x0) // 2, h // 6)
        _star(d, x0 + r, y0 + r, r - 1)
        _lines(d, (x0 + 2 * r + k(1.5), y0, x1, y0 + 2 * r), k)
        ty = y0 + 2 * r + k(1.5)
        _small_text(im, (x0, ty, x1, min(y1, ty + k(14))), k)
        return
    r = min(h // 2, round((x1 - x0) * 0.17))
    _star(d, x0 + r, y0 + h // 2, r - 1)
    rest = x0 + 2 * r + k(3)
    w = x1 - rest
    lw = round(w * 0.42)
    _lines(d, (rest, y0, rest + lw, y1), k)
    tx = rest + lw + k(2)
    th = round(h * 0.68)
    _small_text(im, (tx, y0, x1, y0 + th), k)
    _hatch(im, (tx, y0 + th + k(1.5), x1, y1), k)


def _marks(d, W, H, k, dpi, compact):
    """Рамка по краю листа и в 3 мм от края, угловые метки «L» с номерами углов."""
    d.rectangle((0, 0, W - 1, H - 1), outline=(0, 0, 0), width=1)
    i = k(3)
    d.rectangle((i, i, W - 1 - i, H - 1 - i), outline=(0, 0, 0), width=1)
    arm, off, t = k(5), k(1), max(1, k(0.25))
    f = _font(5 * k.pt)
    corners = ((off, off, 1, 1), (W - 1 - off, off, -1, 1), (W - 1 - off, H - 1 - off, -1, -1), (off, H - 1 - off, 1, -1))
    for n, (cx, cy, sx, sy) in enumerate(corners, 1):
        d.rectangle((min(cx, cx + sx * arm), min(cy, cy + sy * (t - 1)), max(cx, cx + sx * arm), max(cy, cy + sy * (t - 1))), fill=(0, 0, 0))
        d.rectangle((min(cx, cx + sx * (t - 1)), min(cy, cy + sy * arm), max(cx, cx + sx * (t - 1)), max(cy, cy + sy * arm)), fill=(0, 0, 0))
        _text(d, (cx + sx * k(1.0), cy + sy * k(0.9)), str(n), f, fill=(0, 0, 0),
              anchor=("l" if sx > 0 else "r") + ("t" if sy > 0 else "b"))
    # подписи рамок у середины верхнего края
    _text(d, (W // 2, k(0.6)), "sheet edge · frame 3 mm", _font(4.5 * k.pt), fill=MUTED, anchor="ma")


# ---------------------------------------------------------------- лист

def build(width_mm, height_mm, dpi=300, portraits=None, title="", icc_name=""):
    """Тестовый лист width_mm × height_mm при dpi: RGB, sRGB, без профиля и без обработки.
    portraits — до трёх PIL.Image, вписываются в окна с обрезкой по центру; пустые окна — серая рамка с подписью."""
    dpi = max(50, int(round(dpi)))
    width_mm, height_mm = float(width_mm), float(height_mm)
    k = _K(dpi)
    L = layout(width_mm, height_mm, dpi)
    size_mm = (width_mm, height_mm)                   # в шапку — настоящий размер листа, даже если он повёрнут
    W, H = L["size"]
    compact = L["compact"]
    im = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(im)

    # шапка: название и параметры листа
    hx0, hy0, hx1, hy1 = L["head"]
    name = title or "Print test sheet"
    px = (H, W) if L["rotated"] else (W, H)
    info = "%g × %g mm · %d dpi · %d × %d px" % (size_mm + (dpi,) + px)
    if compact:
        _text(d, (hx0, hy0), name, _fit_font(d, name, 8, (hx1 - hx0) * 0.55, k))
        _text(d, (hx1, hy0 + k(0.4)), info, _font(5.5 * k.pt), fill=MUTED, anchor="ra")
    else:
        _text(d, (hx0, hy0), name, _fit_font(d, name, 13, (hx1 - hx0) * 0.6, k))
        _text(d, (hx1, hy0 + k(1.5)), info, _font(7.5 * k.pt), fill=MUTED, anchor="ra")

    _wedge(d, L, k)
    _shadows(d, L, k)
    _colors(d, L, k, compact)
    if not compact:
        x0, y0, x1, y1 = L["neutrals"]
        _caption(d, L["neutrals"], "Neutral patches", k)
        nx = x0 + round((x1 - x0) * 0.5)
        _neutrals(d, (x0, y0 + k(CAPTION), nx - k(3), y1), k)
        _caption(d, (nx, y0, x1, y1), "Sharpness: Siemens star, lines, small text, hatching", k)
        _sharpness(im, d, (nx, y0 + k(CAPTION), x1, y1), k, False)
    _skin(d, L, k, compact)
    _portraits(d, im, L, k, portraits)
    if compact:
        sx0, sy0, sx1, sy1 = L["side"]
        nh = round((sy1 - sy0) * 0.42)
        _neutrals(d, (sx0, sy0, sx1, sy0 + nh), k, vertical=True)
        _sharpness(im, d, (sx0, sy0 + nh + k(2), sx1, sy1), k, True)
    _gradients(im, d, L, k, compact)

    # низ: название программы и профиль
    fx0, fy0, fx1, fy1 = L["foot"]
    foot = "KopiTehnik Print — test sheet"
    if icc_name:
        foot += "  ·  Profile: %s" % icc_name
    _text(d, (fx0, fy1), foot, _fit_font(d, foot, 7 if not compact else 5.5, fx1 - fx0, k), fill=MUTED, anchor="ld")

    _marks(d, W, H, k, dpi, compact)
    if L["rotated"]:
        im = im.transpose(Image.Transpose.ROTATE_90)
    im.info["dpi"] = (dpi, dpi)
    return im


if __name__ == "__main__":
    import sys
    w, h = (float(v) for v in (sys.argv[1:3] if len(sys.argv) > 2 else (210, 297)))
    out = sys.argv[3] if len(sys.argv) > 3 else "test_sheet.png"
    build(w, h).save(out, dpi=(300, 300))
    print(out)
