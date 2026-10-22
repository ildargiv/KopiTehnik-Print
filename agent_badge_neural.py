"""Плашка «ИИ-агент работает», вариант «Нейросеть»: мысль бежит по нейронам.

Слева — крошечная нейросеть 3-4-3-1: по связям слоями бегут светящиеся импульсы-«кометы», нейроны
вспыхивают, когда до них доходит сигнал. Когда импульс добирается до выходного нейрона, тот вспыхивает
золотом, от него расходится кольцо и вылетает горстка искр, а текст коротко «теплеет». Фоном по всей плашке
медленно дрейфует едва заметное «созвездие» — узлы, соединённые тающими линиями. Всё считается из времени
детерминированно (без накопленного состояния), поэтому кадр для выключенной анимации — просто момент t.

Подключение: тот же интерфейс, что у AgentBadge. Тема и флаг анимации — глобальные T и ANIM_ON модуля:
    import agent_badge_neural as abn; abn.T = T; abn.ANIM_ON = ANIM_ON
"""
import math

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, QTimer, QElapsedTimer
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QBrush, QLinearGradient,
                           QConicalGradient, QRadialGradient)
from PySide6.QtWidgets import QWidget

T = {"accent": "#ff7a1a", "text": "#eceef1", "muted": "#9aa0aa"}   # заменяется темой программы
ANIM_ON = [True]                                                    # заменяется общим флагом «Анимация»
GOLD = "#ffd21f"

LAYERS = (3, 4, 3, 1)            # нейронов в слоях
LAYER_DX = 13.0                  # шаг между слоями, px
NET_W = LAYER_DX * (len(LAYERS) - 1)
PULSE_EVERY, HOP = 0.30, 0.20    # импульс рождается раз в 0.3 с (часть пропускается), переход по связи 0.2 с
N_STARS, LINK = 14, 40.0         # узлов фонового «созвездия» и длина связи между ними


def _mix(a, b, k):
    a, b = QColor(a), QColor(b)
    return QColor(round(a.red() + (b.red() - a.red()) * k), round(a.green() + (b.green() - a.green()) * k),
                  round(a.blue() + (b.blue() - a.blue()) * k), round(a.alpha() + (b.alpha() - a.alpha()) * k))


def _alpha(col, a):
    c = QColor(col)
    c.setAlpha(max(0, min(255, int(a))))
    return c


def _h(*xs):
    """Дешёвый детерминированный хеш → [0, 1)."""
    v = 2166136261
    for x in xs:
        v = ((v ^ (int(x) & 0xffffffff)) * 16777619) & 0xffffffff
    v ^= v >> 13
    v = (v * 1274126177) & 0xffffffff
    return (v ^ (v >> 16)) / 4294967296.0


def _pulse(k):
    """Импульс № k: None (пропуск) или путь — номер нейрона в каждом слое."""
    if _h(k, 99) < 0.34:
        return None
    return [int(_h(k, i) * n) for i, n in enumerate(LAYERS)]


class AgentBadgeNeural(QWidget):
    """Мини-нейросеть с бегущими импульсами + фоновое созвездие + искры на выходе."""
    FRAME_MS = 33
    STATIC_T = 2.47

    def __init__(self, text):
        super().__init__()
        self.text, self._t, self._live = text, self.STATIC_T, False
        self.setFixedHeight(32)
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(self.FRAME_MS)
        self._timer.setTimerType(Qt.PreciseTimer)               # ровные ~30 кадров/с на Windows
        self._timer.timeout.connect(self._tick)

    # --- интерфейс AgentBadge ---
    def setText(self, text):
        self.text = text
        self.updateGeometry()
        self.update()

    def _fm(self):
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setBold(True)
        return f, QFontMetricsF(f)

    def sizeHint(self):
        _, fm = self._fm()
        return QSize(int(math.ceil(fm.horizontalAdvance(self.text) + NET_W + 46)), 32)

    def minimumSizeHint(self):
        return self.sizeHint()

    def showEvent(self, e):
        super().showEvent(e)
        if ANIM_ON[0]:
            self._clock.start()
            self._t, self._live = 0.0, True
            self._timer.start()
        else:
            self._t, self._live = self.STATIC_T, False

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()
        self._live = False

    def _tick(self):
        self._t = self._clock.elapsed() / 1000.0
        self.update()

    # --- геометрия сети ---
    @staticmethod
    def _nodes(x0, cy):
        out = []
        for L, n in enumerate(LAYERS):
            gap = 5.8 if n == 3 else 5.0
            out.append([QPointF(x0 + L * LAYER_DX, cy + (i - (n - 1) / 2) * gap) for i in range(n)])
        return out

    def paintEvent(self, _):
        p = QPainter(self)
        self.paint_frame(p, self._t, self._live)
        p.end()

    def paint_frame(self, p, t, running=True):
        f, fm = self._fm()
        acc, gold, ink = QColor(T["accent"]), QColor(GOLD), QColor(T["text"])
        hot = _mix(acc, gold, 0.55)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setOpacity(min(1.0, t / 0.35) if running else 1.0)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        rad, cy = r.height() / 2, r.center().y()
        pill = QPainterPath()
        pill.addRoundedRect(r, rad, rad)
        # «стекло»
        glass = QLinearGradient(0, r.top(), 0, r.bottom())
        glass.setColorAt(0, QColor(40, 37, 36, 240))
        glass.setColorAt(1, QColor(21, 21, 24, 240))
        p.fillPath(pill, QBrush(glass))

        net = self._nodes(r.left() + 13, cy)
        out_node = net[-1][0]
        # события: прибытия импульсов в нейроны за последнюю секунду
        glow = {}
        fires = []                                             # моменты вспышек выходного нейрона
        k_last = int(t / PULSE_EVERY)
        comets = []
        for k in range(max(0, k_last - 6), k_last + 1):
            path = _pulse(k)
            if path is None:
                continue
            born = k * PULSE_EVERY
            for L, i in enumerate(path):
                dt = t - (born + L * HOP)
                if 0 <= dt < 0.6:
                    glow[(L, i)] = max(glow.get((L, i), 0.0), math.exp(-dt * 7))
                if L == len(LAYERS) - 1 and dt >= 0:
                    fires.append(dt)
            s = (t - born) / HOP
            if 0 <= s < len(LAYERS) - 1:
                L = int(s)
                comets.append((net[L][path[L]], net[L + 1][path[L + 1]], s - L))

        # фоновое созвездие (обрезано по плашке, очень приглушённое)
        p.save()
        p.setClipPath(pill)
        x_from, x_to = r.left() + NET_W + 14, r.right() - 4
        span = x_to - x_from
        stars = []
        for i in range(N_STARS):
            u = (_h(i, 1) + t * (0.018 + 0.02 * _h(i, 2))) % 1.0
            x = x_from + u * span
            y = cy + (r.height() / 2 - 4) * math.sin(t * (0.5 + 0.6 * _h(i, 3)) + 6.28 * _h(i, 4))
            fade = min(1.0, u / 0.12, (1 - u) / 0.12)
            stars.append((QPointF(x, y), fade))
        for a in range(N_STARS):
            for b in range(a + 1, N_STARS):
                pa, fa = stars[a]
                pb, fb = stars[b]
                d = math.hypot(pa.x() - pb.x(), pa.y() - pb.y())
                if d < LINK:
                    p.setPen(QPen(_alpha(acc, 85 * (1 - d / LINK) * fa * fb), 0.8))
                    p.drawLine(pa, pb)
        p.setPen(Qt.NoPen)
        for (c, fade) in stars:
            p.setBrush(_alpha(hot, 150 * fade))
            p.drawEllipse(c, 1.1, 1.1)
        p.restore()

        # связи сети
        p.setPen(QPen(QColor(255, 255, 255, 26), 0.7))
        for L in range(len(LAYERS) - 1):
            for a in net[L]:
                for b in net[L + 1]:
                    p.drawLine(a, b)
        # импульсы-кометы
        for a, b, u in comets:
            e = u * u * (3 - 2 * u)
            head = QPointF(a.x() + (b.x() - a.x()) * e, a.y() + (b.y() - a.y()) * e)
            tail = QPointF(a.x() + (b.x() - a.x()) * max(0.0, e - 0.55), a.y() + (b.y() - a.y()) * max(0.0, e - 0.55))
            g = QLinearGradient(tail, head)
            g.setColorAt(0, _alpha(acc, 0))
            g.setColorAt(1, _alpha(gold, 230))
            p.setPen(QPen(QBrush(g), 1.4, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(tail, head)
            p.setPen(Qt.NoPen)
            p.setBrush(_alpha(gold, 80))
            p.drawEllipse(head, 2.6, 2.6)
            p.setBrush(QColor("#fff3c4"))
            p.drawEllipse(head, 1.1, 1.1)
        # нейроны
        p.setPen(Qt.NoPen)
        for L, layer in enumerate(net):
            for i, c in enumerate(layer):
                g = glow.get((L, i), 0.0)
                last = L == len(LAYERS) - 1
                rr = (2.3 if last else 1.7) + 0.6 * g
                if g > 0.02:
                    p.setBrush(_alpha(acc, 110 * g))
                    p.drawEllipse(c, rr + 2.6, rr + 2.6)
                base = _mix(QColor(110, 96, 86), acc, 0.55 if last else 0.25)
                p.setBrush(_mix(base, _mix(acc, gold, 0.7) if last else acc, min(1.0, g * 1.4)))
                p.drawEllipse(c, rr, rr)
        # вспышка выхода: кольцо и искры
        fire = 0.0
        for dt in fires:
            if dt < 0.5:
                k = dt / 0.5
                fire = max(fire, 1 - k)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(_alpha(gold, 200 * (1 - k) ** 1.5), 1.1))
                p.drawEllipse(out_node, 2.5 + 8 * k, 2.5 + 8 * k)
                p.setPen(Qt.NoPen)
                seed = round((t - dt) * 1000)            # момент вспышки, мс
                for j in range(5):
                    ang = -0.9 + 1.8 * _h(seed, j)
                    sp = 16 + 18 * _h(seed, j + 7)
                    d = sp * k
                    sx = out_node.x() + math.cos(ang) * d
                    sy = out_node.y() + math.sin(ang) * d * 0.6
                    p.setBrush(_alpha(_mix(gold, QColor("#ffffff"), 0.4), 230 * (1 - k)))
                    p.drawEllipse(QPointF(sx, sy), 0.9, 0.9)
        # рамка: тонкая + медленный золотой отблеск
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_alpha(acc, 70 + 70 * fire), 1.0))
        p.drawRoundedRect(r, rad, rad)
        con = QConicalGradient(r.center(), -t * 90)
        con.setColorAt(0.0, _alpha(gold, 210))
        con.setColorAt(0.12, _alpha(acc, 0))
        con.setColorAt(0.5, _alpha(acc, 0))
        con.setColorAt(0.62, _alpha(acc, 150))
        con.setColorAt(0.75, _alpha(acc, 0))
        con.setColorAt(1.0, _alpha(gold, 210))
        p.setPen(QPen(QBrush(con), 1.3))
        p.drawRoundedRect(r, rad, rad)
        # текст: «теплеет» при вспышке, по нему проходит мягкий блик
        x0 = out_node.x() + 12
        tw = fm.horizontalAdvance(self.text)
        base = cy + (fm.ascent() - fm.descent()) / 2
        if fire > 0.01:
            rg = QRadialGradient(QPointF(x0 + 10, cy), 42)
            rg.setColorAt(0, _alpha(acc, 34 * fire))
            rg.setColorAt(1, _alpha(acc, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(rg))
            p.drawEllipse(QPointF(x0 + 10, cy), 42, 12)
        sh = ((t / 2.6) % 1.0) * (tw + 120) - 60 if running else -999
        g = QLinearGradient(x0 + sh - 30, 0, x0 + sh + 30, 0)
        warm = _mix(ink, QColor("#ffe6b8"), 0.6 * fire)
        g.setColorAt(0, warm)
        g.setColorAt(0.5, QColor("#ffe08a"))
        g.setColorAt(1, warm)
        p.setFont(f)
        p.setPen(QColor(0, 0, 0, 150))                         # тень отделяет текст от созвездия
        p.drawText(QPointF(x0, base + 1), self.text)
        p.setPen(QPen(QBrush(g), 1))
        p.drawText(QPointF(x0, base), self.text)
