# -*- coding: utf-8 -*-
"""Поправка принтера: мягкая подстройка цвета на выходе, для связки «принтер + бумага». Профиль ICC описывает принтер на момент
съёмки, а реальный отпечаток уходит (партия бумаги, чернила, износ головки): розовит, зеленит, красные уходят в оранжевый.
Поправка не меняет фото на экране и профиль, а накладывается на лист перед отправкой на принтер (после профиля, если он включён).
Состав: нейтраль (оттенок серого отдельно для теней, средних тонов и светов), шесть цветов (оттенок, насыщенность, яркость),
общая гамма и насыщенность. Чистые чёрный и белый остаются на месте: белые поля листа не окрашиваются. Модуль без Qt."""
import color_tools as ct

ZONES = ("shadows", "mids", "lights")                   # тени, средние тона, света
ZONE_X = {"shadows": 40, "mids": 128, "lights": 210}    # где на шкале 0..255 стоит опорная точка зоны
TONE_MAX = 100.0                                         # ползунки -100..100
SHIFT_LEVELS = 20.0                                      # 100 на ползунке = сдвиг канала до 20 уровней из 255 (суммарно красный-синий)
GAMMA_SPAN = 0.5                                         # гамма ±100 = степень 1/(1±0,5)
SAT_SPAN = 0.5                                           # насыщенность ±100 = множитель 1±0,5


def _num(v, default=0.0):
    try:
        return max(-TONE_MAX, min(TONE_MAX, float(v)))
    except (TypeError, ValueError):
        return default


def default():
    return {"on": False,
            "tone": {z: [0.0, 0.0] for z in ZONES},          # [тепло↔холод, зелёный↔пурпурный] на зону
            "gamma": 0.0, "sat": 0.0,
            "sel": [[0.0, 0.0, 0.0] for _ in ct.SEL_COLORS]}


def norm(c):
    """Любой входной словарь (из настроек, от агента) -> полный словарь в допустимых пределах."""
    out = default()
    if not isinstance(c, dict):
        return out
    out["on"] = bool(c.get("on", False))
    tone = c.get("tone") if isinstance(c.get("tone"), dict) else {}
    for z in ZONES:
        v = tone.get(z)
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            out["tone"][z] = [_num(v[0]), _num(v[1])]
    out["gamma"], out["sat"] = _num(c.get("gamma")), _num(c.get("sat"))
    sel = c.get("sel")
    if isinstance(sel, (list, tuple)) and len(sel) == len(ct.SEL_COLORS):
        for i, row in enumerate(sel):
            if isinstance(row, (list, tuple)) and len(row) >= 3:
                out["sel"][i] = [_num(row[0]), _num(row[1]), _num(row[2])]
    return out


def is_neutral(c):
    c = norm(c)
    return (all(v == 0 for z in ZONES for v in c["tone"][z]) and c["gamma"] == 0 and c["sat"] == 0
            and all(v == 0 for row in c["sel"] for v in row))


def active(c):
    """Включена ли и есть ли что применять."""
    c = norm(c)
    return c["on"] and not is_neutral(c)


def _channel_shift(temp, tint):
    """Ползунки зоны -> сдвиг уровней (R, G, B). Тепло: красный вверх, синий вниз. Пурпур: зелёный вниз, красный и синий вверх."""
    t, n = temp * SHIFT_LEVELS / TONE_MAX, tint * SHIFT_LEVELS / TONE_MAX
    return (0.5 * t + 0.5 * n, -n, -0.5 * t + 0.5 * n)


def tone_luts(c):
    """Три таблицы по 256 значений (R, G, B). Концы шкалы 0 и 255 закреплены, между ними плавная монотонная кривая."""
    c = norm(c)
    luts = []
    for ch in range(3):
        pts = [(0, 0)]
        for z in ZONES:
            x = ZONE_X[z]
            pts.append((x, x + _channel_shift(*c["tone"][z])[ch]))
        pts.append((255, 255))
        tab = ct.curve_lut(pts)
        if c["gamma"]:
            inv = 1.0 / (1.0 + c["gamma"] / TONE_MAX * GAMMA_SPAN)
            g = [int(round(255.0 * (i / 255.0) ** inv)) for i in range(256)]
            tab = [g[v] for v in tab]
        luts.append(tab)
    return luts


def apply(img, c):
    """Применяет поправку к RGB-картинке листа. Нейтральная или выключенная поправка возвращает картинку как есть."""
    c = norm(c)
    if not active(c):
        return img
    from PIL import ImageEnhance
    im = img if img.mode == "RGB" else img.convert("RGB")
    luts = tone_luts(c)
    if any(t != ct.IDENT for t in luts):
        im = im.point(luts[0] + luts[1] + luts[2])
    if any(v for row in c["sel"] for v in row):
        im = ct.selective_color(im, [tuple(r) for r in c["sel"]])
    if c["sat"]:
        im = ImageEnhance.Color(im).enhance(1.0 + c["sat"] / TONE_MAX * SAT_SPAN)
    return im


# ---------------------------------------------------------------- тестовая страница

HUE_PATCHES = (("R", (255, 0, 0)), ("Y", (255, 255, 0)), ("G", (0, 255, 0)), ("C", (0, 255, 255)), ("B", (0, 0, 255)), ("M", (255, 0, 255)))
LIVE_PATCHES = ((224, 172, 140), (141, 85, 60), (110, 160, 215), (80, 140, 60), (200, 180, 140), (120, 120, 120))   # кожа, небо, трава, песок


def make_test_page(w_mm, h_mm, ppi=300):
    """Страница для подбора поправки: серые ступени, шесть цветов в трёх насыщенностях, «живые» цвета (кожа, небо, трава).
    Печатается с поправкой и без неё, отпечатки сравниваются с экраном."""
    from PIL import Image, ImageDraw
    import photo_crop as pc
    W, H = max(1, round(w_mm / 25.4 * ppi)), max(1, round(h_mm / 25.4 * ppi))
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    px = ppi / 25.4
    m = round(px * max(5.0, min(w_mm, h_mm) * 0.06))
    f_big, f_small = pc._font_bold(max(12, round(px * 4.2))), pc._font_bold(max(10, round(px * 2.6)))
    d.text((m, m), "Printer correction test", fill=(40, 40, 40), font=f_big)
    d.text((m, m + round(px * 5)), "Тест поправки принтера", fill=(40, 40, 40), font=f_big)
    y = m + round(px * 12)
    gw = W - 2 * m

    def row(colors, label, h):
        nonlocal y
        n = len(colors)
        cw = gw / n
        for i, col in enumerate(colors):
            d.rectangle((m + round(i * cw), y, m + round((i + 1) * cw) - 1, y + h), fill=tuple(col), outline=(150, 150, 150))
        d.text((m, y + h + round(px * 0.8)), label, fill=(90, 90, 90), font=f_small)
        y += h + round(px * 5.5)

    ph = max(round(px * 9), min(round(px * 30), round((H - y - m) / 5.0) - round(px * 5.5)))
    row([(v, v, v) for v in (0, 25, 51, 76, 102, 127, 153, 178, 204, 229, 255)], "Gray steps 0…100% / Серые ступени", ph)
    for name, tone in (("full", 1.0), ("medium", 0.6), ("light", 0.3)):
        row([tuple(round(255 - (255 - c) * tone) for c in rgb) for _n, rgb in HUE_PATCHES],
            "R Y G C B M — %s / %s" % (name, {"full": "насыщенные", "medium": "средние", "light": "светлые"}[name]), ph)
    row(LIVE_PATCHES, "Skin, sky, grass, sand, gray / Кожа, небо, трава, песок", ph)
    return im
