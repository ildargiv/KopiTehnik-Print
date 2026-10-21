# -*- coding: utf-8 -*-
"""Уровни, кривые и выборочный цвет: расчёт без Qt.

Значения коррекции хранятся неизменяемыми кортежами: они входят в ключ кэша плиток и без потерь проходят через JSON
(там они становятся списками, а normalize возвращает кортежи). Пустой кортеж — «ничего не меняется».
"""
import math

CHANNELS = ("rgb", "r", "g", "b")                        # порядок строк в levels и curves
LEVELS_NEUTRAL = (0.0, 1.0, 255.0, 0.0, 255.0)           # чёрная точка, гамма, белая точка, выход от, выход до
CURVE_NEUTRAL = ((0, 0), (255, 255))
SEL_COLORS = ("R", "Y", "G", "C", "B", "M")              # красный, жёлтый, зелёный, голубой, синий, пурпурный
SEL_HUE_DEG = {"R": 0, "Y": 60, "G": 120, "C": 180, "B": 240, "M": 300}
SEL_NEUTRAL = (0.0, 0.0, 0.0)                            # сдвиг оттенка, насыщенности, яркости (-100..100)
HUE_SPAN_DEG = 30.0                                      # оттенок ±100 = ±30°
IDENT = list(range(256))


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _num(v, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


# ---------------------------------------------------------------- нормализация значений

def norm_levels_row(row):
    try:
        b, g, w, ob, ow = (_num(x, d) for x, d in zip(row, LEVELS_NEUTRAL))
    except (TypeError, ValueError):
        return LEVELS_NEUTRAL
    b = _clamp(b, 0, 254)
    w = _clamp(w, b + 1, 255)
    ob = _clamp(ob, 0, 254)
    ow = _clamp(ow, ob + 1, 255)
    return (round(b, 1), round(_clamp(g, 0.1, 10.0), 2), round(w, 1), round(ob, 1), round(ow, 1))


def norm_levels(v):
    try:
        rows = list(v)
    except TypeError:
        return ()
    out = tuple(norm_levels_row(rows[i] if i < len(rows) else LEVELS_NEUTRAL) for i in range(4))
    return () if all(r == LEVELS_NEUTRAL for r in out) else out


def _norm_points(pts):
    seen = {}
    try:
        for p in pts:
            x, y = _num(p[0], None), _num(p[1], None)
            if x is not None and y is not None:
                seen[int(round(_clamp(x, 0, 255)))] = int(round(_clamp(y, 0, 255)))
    except (TypeError, IndexError):
        pass
    if len(seen) < 2:
        return CURVE_NEUTRAL
    return tuple(sorted(seen.items()))


def norm_curves(v):
    try:
        rows = list(v)
    except TypeError:
        return ()
    out = tuple(_norm_points(rows[i]) if i < len(rows) else CURVE_NEUTRAL for i in range(4))
    return () if all(r == CURVE_NEUTRAL for r in out) else out


def norm_selcol(v):
    try:
        rows = list(v)
    except TypeError:
        return ()
    out = []
    for i in range(len(SEL_COLORS)):
        try:
            h, s, l = (round(_clamp(_num(x, 0.0), -100, 100), 1) for x in rows[i])
        except (IndexError, TypeError, ValueError):
            h, s, l = SEL_NEUTRAL
        out.append((h, s, l))
    out = tuple(out)
    return () if all(r == SEL_NEUTRAL for r in out) else out


NORMALIZE = {"levels": norm_levels, "curves": norm_curves, "selcol": norm_selcol}


def levels_full(v):
    """Четыре строки (общий, R, G, B); недостающее нейтрально."""
    return norm_levels(v) or (LEVELS_NEUTRAL,) * 4


def curves_full(v):
    return norm_curves(v) or (CURVE_NEUTRAL,) * 4


def selcol_full(v):
    return norm_selcol(v) or (SEL_NEUTRAL,) * len(SEL_COLORS)


# ---------------------------------------------------------------- таблицы по 256 значений

def levels_lut(row):
    b, g, w, ob, ow = row
    inv = 1.0 / g
    tab = []
    for i in range(256):
        x = _clamp((i - b) / (w - b), 0.0, 1.0)
        tab.append(int(round(_clamp(ob + (x ** inv) * (ow - ob), 0, 255))))
    return tab


def curve_lut(points):
    """Монотонный кубический сплайн (Fritsch-Carlson): кривая не «звенит» между точками. Левее первой и правее
    последней точки она идёт горизонтально."""
    pts = list(points)
    xs, ys = [float(p[0]) for p in pts], [float(p[1]) for p in pts]
    n = len(xs)
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = [d[0]] + [0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2.0 for i in range(1, n - 1)] + [d[-1]]
    for i in range(n - 1):
        if d[i] == 0:
            m[i] = m[i + 1] = 0.0
        else:
            a, b = m[i] / d[i], m[i + 1] / d[i]
            s = a * a + b * b
            if s > 9:
                t = 3.0 / math.sqrt(s)
                m[i], m[i + 1] = t * a * d[i], t * b * d[i]
    tab, k = [], 0
    for i in range(256):
        if i <= xs[0]:
            y = ys[0]
        elif i >= xs[-1]:
            y = ys[-1]
        else:
            while xs[k + 1] < i:
                k += 1
            h = xs[k + 1] - xs[k]
            t = (i - xs[k]) / h
            t2, t3 = t * t, t * t * t
            y = ((2 * t3 - 3 * t2 + 1) * ys[k] + (t3 - 2 * t2 + t) * h * m[k]
                 + (-2 * t3 + 3 * t2) * ys[k + 1] + (t3 - t2) * h * m[k + 1])
        tab.append(int(round(_clamp(y, 0, 255))))
    return tab


def _compose(first, second):
    return [second[v] for v in first]


def _channel_luts(rows, make, neutral):
    """Таблицы R, G, B: сначала канал, потом общая строка. None — всё нейтрально."""
    if not rows:
        return None
    master = make(rows[0]) if rows[0] != neutral else IDENT
    out = [_compose(make(rows[1 + c]) if rows[1 + c] != neutral else IDENT, master) for c in range(3)]
    return None if all(t == IDENT for t in out) else out


def extra_luts(a):
    """Уровни, затем кривые — тремя таблицами для R, G, B. None, если ни то ни другое не задано."""
    lv = _channel_luts(norm_levels(a.get("levels")), levels_lut, LEVELS_NEUTRAL)
    cv = _channel_luts(norm_curves(a.get("curves")), curve_lut, CURVE_NEUTRAL)
    if lv and cv:
        return [_compose(lv[c], cv[c]) for c in range(3)]
    return lv or cv


def auto_levels_rows(lo, hi):
    """Строки уровней по границам растяжения гистограммы: общий — нейтральный, каналы R, G, B — свои."""
    rows = [LEVELS_NEUTRAL]
    for c in range(3):
        rows.append((float(lo[c]), 1.0, float(hi[c]), 0.0, 255.0))
    return norm_levels(rows)


# ---------------------------------------------------------------- выборочный цвет

def _hue_weights(deg):
    """Вес каждого из шести цветов для оттенка deg: треугольно-косинусные «колпаки» шириной 120°, сумма весов 1."""
    out = []
    for name in SEL_COLORS:
        d = abs((deg - SEL_HUE_DEG[name] + 180.0) % 360.0 - 180.0)
        out.append(0.5 * (1.0 + math.cos(math.pi * d / 60.0)) if d < 60.0 else 0.0)
    return out


def selective_color(img, sel):
    """Для каждого из шести цветов сдвиг оттенка, насыщенности и яркости. Серые пиксели не затрагиваются."""
    sel = norm_selcol(sel)
    if not sel:
        return img
    import numpy as np
    from PIL import Image
    dh, ds, dv = np.zeros(256), np.zeros(256), np.zeros(256)
    for hb in range(256):
        w = _hue_weights(hb * 360.0 / 256.0)
        dh[hb] = sum(wk * s[0] for wk, s in zip(w, sel)) / 100.0 * HUE_SPAN_DEG * 256.0 / 360.0
        ds[hb] = sum(wk * s[1] for wk, s in zip(w, sel)) / 100.0
        dv[hb] = sum(wk * s[2] for wk, s in zip(w, sel)) / 100.0
    hsv = np.asarray(img.convert("HSV")).astype(np.float32)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    hi = h.astype(np.int32)
    colorful = np.sqrt(s / 255.0)                              # нейтральные пиксели почти не меняются
    new_h = np.mod(h + dh[hi] * colorful, 256.0)
    new_s = np.clip(s * (1.0 + ds[hi]), 0, 255)
    new_v = np.clip(v * (1.0 + 0.6 * dv[hi] * colorful), 0, 255)
    out = np.stack([new_h, new_s, new_v], axis=-1).round().astype(np.uint8)
    return Image.fromarray(out, "HSV").convert("RGB")
