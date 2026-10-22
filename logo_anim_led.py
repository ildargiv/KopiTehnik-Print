"""Вариант 2 «LED-табло / плёночная дата».

Название и «К» в знаке — светодиодное табло: видны все погашенные светодиоды матриц 5×7 (тёмные точки).
Интро: табло «включается» буква за буквой, в каждой ячейке тускло-янтарно перебираются случайные символы,
затем буквы слева направо «защёлкиваются» на свои — с бело-золотой вспышкой; «ПРИНТ» фиксируется последним
и вспыхивает целиком. «К» в знаке перебирается и фиксируется так же.
Покой (таймер работает только во время события): строчная развёртка — яркость пробегает по строкам сверху вниз
(раз в 6 с); пара светодиодов мерцает, как на старом табло; раз в 13 с — короткий глитч: полоса строк дёргается
вбок с красно-голубым расслоением, одна-две буквы на миг перебираются.
Наведение: от курсора расходится кольцо — загораются и погашенные светодиоды; знак подпрыгивает и
«перещёлкивает» букву. Клик: «тест табло» — на миг загораются все светодиоды и гаснут.
"""
import math
from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QRectF, QPointF, QSize
from PySide6.QtGui import QPainter, QColor, QRadialGradient, QLinearGradient, QPixmap, QPen, QBrush, QPainterPath
from PySide6.QtWidgets import QWidget, QSizePolicy

import brand_datestamp as bd

ANIM_ON = [True]            # в проекте: подменить на общий ANIM_ON из photo_crop_qt (см. отчёт)
FRAME_MS = 30               # ~33 кадр/с, только пока идёт эффект

PREVIEW = {
    "intro": [0.08, 0.2, 0.35, 0.5, 0.65, 0.8, 1.0, 1.2, 1.45, 1.75, 2.05, 3.0],
    "idle": [("развёртка строк", 4.2), ("развёртка +0.2", 4.4), ("мерцание", 6.78), ("глитч", 9.25), ("глитч +0.15", 9.4)],
    "act": [("наведение +0.2", 20.2, ("hover", 140, 22, 20.0)), ("наведение +0.6", 20.6, ("hover", 140, 22, 20.0)),
            ("клик +0.05", 20.05, ("click", 150, 22, 20.0)), ("клик по знаку +0.08", 20.08, ("click", 22, 22, 20.0))],
}

INK, HOT, GOLD = QColor("#f4f4f6"), QColor("#ff8a1e"), QColor("#ffd21f")
WHITE_HOT, BASE = QColor("#fff7e2"), QColor("#22242b")


# ---------------------------------------------------------------- помощники
def _mix(a, b, t):
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


def _hash(*v):
    x = 2166136261
    for n in v:
        x = ((x ^ (int(n) & 0xffffffff)) * 16777619) & 0xffffffff
        x ^= x >> 15
        x = (x * 2246822519) & 0xffffffff
        x ^= x >> 13
    return x / 4294967296.0


def _out_back(u, s=1.7):
    u = min(1.0, max(0.0, u)) - 1
    return 1 + u * u * ((s + 1) * u + s)


_SPR = {}


def _glow_pm(col):
    """Готовое пятно свечения (радиальный градиент) — рисуется drawPixmap'ом, без градиента на каждую точку."""
    key = (col.red() >> 3, col.green() >> 3, col.blue() >> 3)
    pm = _SPR.get(key)
    if pm is None:
        if len(_SPR) > 300:
            _SPR.clear()
        n = 48
        pm = QPixmap(n, n)
        pm.fill(Qt.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.Antialiasing)
        g = QRadialGradient(n / 2, n / 2, n / 2)
        c0 = QColor(col)
        for pos, a in ((0, 255), (0.35, 150), (0.7, 45), (1, 0)):
            c0.setAlpha(a)
            g.setColorAt(pos, c0)
        q.setPen(Qt.NoPen)
        q.setBrush(QBrush(g))
        q.drawEllipse(QRectF(0, 0, n, n))
        q.end()
        _SPR[key] = pm
    return pm


def set_theme(bg, text):
    """Цвета логотипа под тему окна: на светлом фоне буквы тёмные, «ПРИНТ» насыщенно-оранжевое, свечение слабее."""
    global INK, HOT, GOLD, WHITE_HOT, UNLIT, DIM_BG, GLOW_K
    bgc, tc = QColor(bg), QColor(text)
    light = (0.299 * bgc.red() + 0.587 * bgc.green() + 0.114 * bgc.blue()) > 140
    DIM_BG = bgc
    UNLIT = _mix(bgc, tc, 0.11 if light else 0.09)
    if light:
        INK, HOT, GOLD, WHITE_HOT, GLOW_K = tc, QColor("#f06a00"), QColor("#e09a00"), QColor("#ff5a00"), 0.3
    else:
        INK, HOT, GOLD, WHITE_HOT, GLOW_K = QColor("#f4f4f6") if tc.lightness() > 200 else tc, QColor("#ff8a1e"), QColor("#ffd21f"), QColor("#fff7e2"), 1.0


DIM_BG, GLOW_K = QColor("#17181c"), 1.0


def _dot(p, x, y, d, col, glow):
    """Точка диаметром d с ореолом (glow 0..1)."""
    if glow > 0.01:
        r = d * 1.35
        p.setOpacity(min(1.0, glow * GLOW_K))
        p.drawPixmap(QRectF(x - r, y - r, 2 * r, 2 * r), _glow_pm(col), QRectF(0, 0, 48, 48))
        p.setOpacity(1.0)
    p.setBrush(col)
    p.drawEllipse(QPointF(x, y), d / 2, d / 2)


def _heat_col(final, h, white=True):
    col = _mix(final, GOLD, h * 1.4)
    return _mix(col, WHITE_HOT, h * h) if white else col


class _Anim(QWidget):
    """Общая механика: свой «часовой» отсчёт, таймер только пока виден и пока что-то движется."""
    INTRO_END = 2.0

    def __init__(self):
        super().__init__()
        self._clock, self._off, self._frozen = QElapsedTimer(), 0.0, None
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)
        self._wake = QTimer(self)
        self._wake.setSingleShot(True)
        self._wake.timeout.connect(self._kick)
        self._hover_t0 = self._click_t0 = self._leave_t0 = -1e9
        self._hover_pos = self._click_pos = QPointF()
        self._hovered = False

    # время эффекта, с; None — статичный кадр (анимация выключена)
    def now(self):
        if self._frozen is not None:
            return self._frozen
        if not ANIM_ON[0] or not self._clock.isValid():
            return None
        return self._clock.elapsed() / 1000.0 + self._off

    def freeze(self, t):
        """Для превью и тестов: показать кадр в момент t (None — статичный)."""
        self._frozen = t
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        if ANIM_ON[0] and self._frozen is None:
            if not self._clock.isValid():
                self._clock.start()
            self._timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()
        self._wake.stop()

    def _kick(self):
        if not (ANIM_ON[0] and self.isVisible() and self._frozen is None):
            return
        if not self._clock.isValid():           # анимацию включили уже после показа — без интро
            self._clock.start()
            self._off = self.INTRO_END + 0.5
        self._wake.stop()
        if not self._timer.isActive():
            self._timer.start()

    def _tick(self):
        self.update()
        t = self.now()
        if t is None:
            self._timer.stop()
        elif not self._busy(t):
            self._timer.stop()
            nxt = self._next_event(t)
            if nxt is not None:
                self._wake.start(max(40, int((nxt - t) * 1000)))

    @staticmethod
    def _idle(t, start, period, dur):
        """Доля 0..1 текущего периодического события покоя или None."""
        if t is None or t < start:
            return None
        r = (t - start) % period
        return r / dur if r < dur else None

    @staticmethod
    def _idle_next(t, start, period):
        return start if t < start else start + (math.floor((t - start) / period) + 1) * period

    def enterEvent(self, e):
        super().enterEvent(e)
        t = self.now()
        self._hovered = True
        if t is not None:
            self._hover_t0 = t
            self._hover_pos = e.position()
            self._on_enter(t)
            self._kick()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        t = self.now()
        self._hovered = False
        if t is not None:
            self._leave_t0 = t
            self._on_leave(t)
            self._kick()

    def mousePressEvent(self, e):
        t = self.now()
        if t is not None:
            self._click_t0, self._click_pos = t, e.position()
            self._kick()
        super().mousePressEvent(e)

    def _on_enter(self, t):
        pass

    def _on_leave(self, t):
        pass


UNLIT = QColor("#2b2d35")
MARK_UNLIT = QColor("#2b2d35")                        # знак всегда на тёмной плитке, независимо от темы окна
RED_G, CYAN_G = QColor(255, 50, 90), QColor(40, 225, 255)
POOL = [g for k, g in bd.FONT.items() if k not in "'▸"]


def _scr_glyph(*key):
    return POOL[int(_hash(*key) * len(POOL)) % len(POOL)]


class _LedSchedule:
    """Три независимых события покоя: развёртка строк, мерцание пары светодиодов, редкий глитч."""
    SCAN = (4.0, 6.0, 0.6)
    FLICK = (6.7, 6.0, 0.3)
    GLITCH = (9.2, 13.0, 0.3)

    def _events_busy(self, t):
        return any(self._idle(t, *ev) is not None for ev in (self.SCAN, self.FLICK, self.GLITCH))

    def _events_next(self, t):
        return min(self._idle_next(t, ev[0], ev[1]) for ev in (self.SCAN, self.FLICK, self.GLITCH))

    def _glitch(self, t):
        """(сдвиг, первая строка, число строк, номер события) или None."""
        g = self._idle(t, *self.GLITCH)
        if g is None:
            return None
        n = int((t - self.GLITCH[0]) // self.GLITCH[1])
        step = int(g * 5)                              # глитч «дёргается» несколько раз
        sh = (1 if _hash(n, step) < 0.5 else -1) * (1 + int(_hash(n, step, 3) * 2))
        if step in (2,):
            sh = 0
        r0 = int(_hash(n, step, 5) * 5)
        return sh, r0, 2 + int(_hash(n, 9) * 2), n

    def _flicker_off(self, t, idx, total):
        f = self._idle(t, *self.FLICK)
        if f is None:
            return False
        n = int((t - self.FLICK[0]) // self.FLICK[1])
        picks = {int(_hash(n, j) * total) for j in range(3)}
        return idx in picks and _hash(n, idx, int(t / 0.045)) < 0.6


def _led(p, x, y, d, col, glow):
    _dot(p, x, y, d, col, glow)


# ---------------------------------------------------------------- знак
class LogoMarkAnim(_LedSchedule, _Anim):
    SIZE = 44
    INTRO_END = 1.6
    LOCK = 0.78

    def __init__(self, letter="К"):
        _Anim.__init__(self)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self._pop_from, self._pop_to, self._pop_t0 = 0.0, 0.0, -1e9
        s = self.SIZE
        self._pitch = s * 0.082
        self._ox = s / 2 - 2.5 * self._pitch
        self._oy = s / 2 - 3.5 * self._pitch - s * 0.03
        self._glyph = bd.FONT.get(letter.upper(), bd.FONT["К"])

    def _pop(self, t):
        u = (t - self._pop_t0) / 0.38
        return self._pop_to if u >= 1 else self._pop_from + (self._pop_to - self._pop_from) * _out_back(u, 2.2)

    def _on_enter(self, t):
        self._pop_from, self._pop_to, self._pop_t0 = self._pop(t), 1.0, t

    def _on_leave(self, t):
        self._pop_from, self._pop_to, self._pop_t0 = self._pop(t), 0.0, t

    def _busy(self, t):
        return (t < self.INTRO_END or self._events_busy(t) or t - self._pop_t0 < 0.45
                or t - self._hover_t0 < 0.7 or t - self._click_t0 < 0.6)

    def _next_event(self, t):
        return self._events_next(t)

    def paintEvent(self, _):
        t = self.now()
        st = t is None
        T = 99.0 if st else t
        s = self.SIZE
        c = QPointF(s / 2, s / 2)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        appear = 1.0 if st else min(1.0, T / 0.25)
        pop = 0.0 if st else self._pop(T)
        lock_flash = 0.0 if st or T < self.LOCK else math.exp(-(T - self.LOCK) / 0.22)
        relock = self._hover_t0 + 0.3
        if not st and relock <= T < relock + 1:
            lock_flash = max(lock_flash, math.exp(-(T - relock) / 0.2))
        ca = T - self._click_t0
        click = 0.0 if st or ca < 0 else math.exp(-ca / 0.18)
        g = QRadialGradient(c, s * 0.62)
        g.setColorAt(0.55, QColor(255, 122, 24, int(min(255, (70 + 130 * lock_flash + 50 * pop + 120 * click) * appear))))
        g.setColorAt(1, QColor(255, 122, 24, 0))
        p.fillRect(self.rect(), g)
        p.translate(c)
        k = 1 + 0.1 * pop
        p.scale(k, k)
        p.translate(-c)
        p.setOpacity(appear)
        tile = QRectF(s * 0.04, s * 0.04, s * 0.92, s * 0.92)
        rad = s * 0.22
        p.fillPath(bd.c.rounded(tile, rad), BASE)
        bc = _mix(QColor(255, 140, 40), WHITE_HOT, lock_flash)
        bc.setAlpha(int(min(255, 120 + 135 * max(lock_flash, click))))
        p.strokePath(bd.c.rounded(tile.adjusted(0.5, 0.5, -0.5, -0.5), rad - 0.5), QPen(bc, 1.0))
        p.setBrush(QColor(255, 255, 255, 38))
        hw, hh, span = s * 0.07, s * 0.045, tile.width() * 0.62
        for i in range(5):
            cx = tile.center().x() - span / 2 + span * i / 4
            p.drawRoundedRect(QRectF(cx - hw / 2, tile.top() + s * 0.07, hw, hh), hh * 0.3, hh * 0.3)
        p.setOpacity(1.0)
        # какой «кадр» показывает табло
        glyph, dim = self._glyph, False
        if not st:
            if T < self.LOCK:
                glyph, dim = (_scr_glyph(77, int(T / 0.06)) if T > 0.18 else None), True
            elif relock - 0.25 <= T < relock:
                glyph, dim = _scr_glyph(78, int(T / 0.05)), True
        gl = None if st else self._glitch(T)
        scan = None if st else self._idle(T, *self.SCAN)
        pitch, ox, oy = self._pitch, self._ox, self._oy
        idx = 0
        for r in range(7):
            shift = gl[0] * 0.5 if gl and gl[1] <= r < gl[1] + gl[2] else 0
            for col in range(5):
                x, y = ox + (col + 0.5 + shift) * pitch, oy + (r + 0.5) * pitch
                lit = glyph is not None and glyph[r][col] == "1"
                off = (not st) and self._flicker_off(T, idx, 35)
                idx += 1
                if not lit or off:
                    u = QColor(MARK_UNLIT)
                    if click > 0.01:
                        u = _mix(u, GOLD, click * 0.9)
                    _led(p, x, y, pitch * 0.62, u, 0.4 * click)
                    continue
                if dim:
                    _led(p, x, y, pitch * 0.72, _mix(HOT, BASE, 0.35), 0.15)
                    continue
                heat = max(lock_flash, click)
                if scan is not None:
                    heat = max(heat, 0.7 * math.exp(-((r - (scan * 9 - 1)) / 0.8) ** 2))
                if shift:
                    _led(p, x - 0.9, y, pitch * 0.7, RED_G, 0.0)
                    _led(p, x + 0.9, y, pitch * 0.7, CYAN_G, 0.0)
                _led(p, x, y, pitch * 0.8 * (1 + 0.2 * heat), _heat_col(HOT, heat, heat > 0.3), 0.47 + 0.5 * heat)
        p.end()


# ---------------------------------------------------------------- название
class BrandTitleAnim(_LedSchedule, _Anim):
    H = 17

    def __init__(self):
        _Anim.__init__(self)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.setText("КопиТехник Принт")

    def setText(self, text):
        self.brand = text if bd.set_name(text) else "КопиТехник Принт"
        bd.set_name(self.brand)
        self._W = bd.TOTAL_W
        self._letters = []                              # (x0, glyph, горячая?, порядковый номер)
        x, n = 0.0, 0
        for word, hot in ((bd.WORD_A, False), (bd.WORD_B, True)):
            for ch in word:
                self._letters.append((x, bd.FONT[ch], hot, n))
                x += bd.CELL
                n += 1
            x += bd.SPACE + 1 - 0                       # пробел между словами (как в brand_datestamp)
        self._xb = bd._text_w(bd.WORD_A) + bd.SPACE + 1
        # пересчёт x второго слова точно как в brand_datestamp
        na = len(bd.WORD_A)
        self._letters = [(lx if i < na else self._xb + (i - na) * bd.CELL, g, h, i)
                         for i, (lx, g, h, _) in enumerate(self._letters)]
        last = self._lock(len(self._letters) - 1, True)
        self.INTRO_END = last + 0.7
        self.updateGeometry()
        self.update()

    def _lock(self, i, hot):
        return 0.55 + 0.085 * i + (0.15 if hot else 0)

    def sizeHint(self):
        return QSize(int(self._W * self.H / 7) + 6, 34)

    def minimumSizeHint(self):
        return self.sizeHint()

    def _busy(self, t):
        return (t < self.INTRO_END or self._events_busy(t) or t - self._hover_t0 < 1.4 or t - self._click_t0 < 0.7)

    def _next_event(self, t):
        return self._events_next(t)

    def paintEvent(self, _):
        t = self.now()
        st = t is None
        T = 99.0 if st else t
        k = self.H / 7.0
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.translate(3, (self.height() - self.H) / 2)
        p.scale(k, k)
        gl = None if st else self._glitch(T)
        scan = None if st else self._idle(T, *self.SCAN)
        ha = T - self._hover_t0
        hov = None
        if not st and 0 <= ha < 1.4:
            hov = ((self._hover_pos.x() - 3) / k, (self._hover_pos.y() - (self.height() - self.H) / 2) / k, 55 * ha, 1 - ha / 1.4)
        ca = T - self._click_t0
        click = 0.0 if st or ca < 0 else math.exp(-ca / 0.2)
        total = len(self._letters) * 35
        for (x0, glyph, hot, i) in self._letters:
            final = HOT if hot else INK
            on_t = 0.08 + 0.022 * i
            lock_t = self._lock(i, hot)
            if not st and T < on_t:
                continue
            power = 1.0 if st else min(1.0, (T - on_t) / 0.12)
            show, dim = glyph, False
            if not st and T < lock_t:
                show = _scr_glyph(i, int(T / 0.065)) if T > on_t + 0.06 else None
                dim = True
            if gl and _hash(gl[3], i) < 0.12 and not dim:          # глитч иногда «перебирает» букву
                show, dim = _scr_glyph(gl[3], i, int(T / 0.05)), True
            lf = 0.0 if st or T < lock_t else math.exp(-(T - lock_t) / 0.2)
            if hot and not st and T >= self.INTRO_END - 0.55:     # общая вспышка «ПРИНТ» после фиксации
                ft = T - (self.INTRO_END - 0.55)
                lf = max(lf, 0.7 * math.exp(-ft / 0.3) * min(1.0, ft / 0.05))
            for r in range(7):
                shift = gl[0] if gl and gl[1] <= r < gl[1] + gl[2] else 0
                for cl in range(5):
                    x, y = x0 + cl + 0.5 + shift, r + 0.5
                    lit = show is not None and show[r][cl] == "1"
                    idx = i * 35 + r * 5 + cl
                    if lit and not st and not dim and self._flicker_off(T, idx, total):
                        lit = False
                    hb = 0.0
                    if hov:
                        dist = math.hypot(x - hov[0], (y - hov[1]) * 1.3)
                        hb = math.exp(-((dist - hov[2]) / 3.0) ** 2) * hov[3]
                    if not lit:
                        u = QColor(UNLIT)
                        e = max(click * 0.85, hb * 0.9)
                        if e > 0.01:
                            u = _mix(u, GOLD if click > hb else HOT, e)
                        p.setOpacity(power)
                        _led(p, x, y, bd.DOT * (0.7 + 0.15 * e), u, 0.5 * e)
                        p.setOpacity(1.0)
                        continue
                    if dim:
                        _led(p, x, y, bd.DOT * 0.85, _mix(HOT, DIM_BG, 0.38), 0.12)
                        continue
                    heat = max(lf, click, 0.85 * hb)
                    if scan is not None:
                        heat = max(heat, (0.8 if hot else 0.6) * math.exp(-((r - (scan * 9.5 - 1.2)) / 0.8) ** 2))
                    white = lf > 0.25 or click > 0.25
                    if shift:
                        _led(p, x - 0.45, y, bd.DOT * 0.9, RED_G, 0.0)
                        _led(p, x + 0.45, y, bd.DOT * 0.9, CYAN_G, 0.0)
                    _led(p, x, y, bd.DOT * (1.02 if hot else 1) * (1 + 0.25 * heat), _heat_col(final, heat, white),
                         (0.43 if hot else 0) + 0.6 * heat)
        p.end()
