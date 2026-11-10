"""Раскладка на рулон плоттера (без Qt): размеры, зазоры, длина рулона, упаковка, сохранение.

Все размеры в миллиметрах. Начало координат — левый верхний угол печатной зоны; Y растёт вниз по рулону.
"""
import json
import math

ROLL_WIDTHS_MM = (297, 420, 432, 594, 610, 841, 914, 1067, 1118)
DEFAULT_EDGE_MM = 5.0          # непечатаемая кромка рулона с каждой стороны
DEFAULT_GAP_MM = 10.0
MAX_PAPER_LEN_MM = 3276.7      # dmPaperLength: short в 0,1 мм
UNITS = {"mm": 1.0, "cm": 10.0, "in": 25.4}


# Стандартные форматы бумаги, мм (меньшая сторона, большая)
PAPERS = {"A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420), "A4": (210, 297), "A5": (148, 210),
          "B1": (707, 1000), "B2": (500, 707), "B3": (353, 500), "B4": (250, 353)}
COMMON_DPI = (300, 150, 200, 600, 254, 360, 100, 96, 72)      # порядок = что вероятнее для файла на печать


def standard_paper(w_mm, h_mm, px_w=0, px_h=0, tol=0.02):
    """Если размер файла (мм) близок к стандартному формату — возвращает (имя, ширина, высота) этого формата в ориентации файла.
    Если по метаданным размер не совпал, но пиксели ровно соответствуют формату при привычном dpi — тоже берём формат."""
    def match(a, b):
        lo, hi = min(a, b), max(a, b)
        for name, (pw, ph) in PAPERS.items():
            if abs(lo - pw) <= pw * tol and abs(hi - ph) <= ph * tol:
                return name
        return None
    n = match(w_mm, h_mm)
    if not n and px_w and px_h:
        for d in COMMON_DPI:
            n = match(px_w / d * 25.4, px_h / d * 25.4)
            if n:
                break
    if not n:
        return None
    lo, hi = PAPERS[n]
    portrait = (px_w <= px_h) if (px_w and px_h) else (w_mm <= h_mm)
    return (n, lo, hi) if portrait else (n, hi, lo)


def to_mm(value, unit="mm"):
    return float(value) * UNITS[unit]


def from_mm(value, unit="mm"):
    return float(value) / UNITS[unit]


class Item:
    """Один файл на рулоне. w, h — размер в мм ДО поворота; rot — 0/90/180/270."""

    def __init__(self, path, w, h, px_w=0, px_h=0, x=0.0, y=0.0, rot=0, copies=1, enabled=True, name=None):
        self.path, self.w, self.h = path, float(w), float(h)
        self.px_w, self.px_h = int(px_w), int(px_h)
        self.x, self.y, self.rot = float(x), float(y), int(rot) % 360
        self.copies, self.enabled = max(1, int(copies)), bool(enabled)
        self.name = name or str(path).replace("\\", "/").rsplit("/", 1)[-1]

    @property
    def ow(self):
        """Ширина занимаемого прямоугольника с учётом поворота."""
        return self.h if self.rot in (90, 270) else self.w

    @property
    def oh(self):
        return self.w if self.rot in (90, 270) else self.h

    @property
    def right(self):
        return self.x + self.ow

    @property
    def bottom(self):
        return self.y + self.oh

    def set_width(self, w, keep_ratio=True):
        """Задать ширину (по ширине до поворота). При keep_ratio высота пересчитывается."""
        w = max(0.1, float(w))
        if keep_ratio and self.w > 0:
            self.h = self.h * w / self.w
        self.w = w

    def set_height(self, h, keep_ratio=True):
        h = max(0.1, float(h))
        if keep_ratio and self.h > 0:
            self.w = self.w * h / self.h
        self.h = h

    def set_scale(self, pct):
        k = float(pct) / 100.0
        self.w, self.h = self.w * k, self.h * k

    def rotate(self, step=90):
        """Поворот вокруг центра: центр прямоугольника остаётся на месте."""
        cx, cy = self.x + self.ow / 2, self.y + self.oh / 2
        self.rot = (self.rot + step) % 360
        self.x, self.y = cx - self.ow / 2, cy - self.oh / 2

    def dpi(self):
        """Эффективное разрешение при текущем размере (по меньшему из направлений); 0 — размер в пикселях неизвестен."""
        if not self.px_w or not self.px_h or self.w <= 0 or self.h <= 0:
            return 0.0
        return min(self.px_w / (self.w / 25.4), self.px_h / (self.h / 25.4))

    def set_size_for_dpi(self, dpi):
        """Исходный размер при заданном dpi."""
        if self.px_w and self.px_h and dpi > 0:
            self.w, self.h = self.px_w / dpi * 25.4, self.px_h / dpi * 25.4

    def to_dict(self):
        return {"path": self.path, "name": self.name, "w": self.w, "h": self.h, "px_w": self.px_w, "px_h": self.px_h,
                "x": self.x, "y": self.y, "rot": self.rot, "copies": self.copies, "enabled": self.enabled}

    @classmethod
    def from_dict(cls, d):
        return cls(d["path"], d["w"], d["h"], d.get("px_w", 0), d.get("px_h", 0), d.get("x", 0), d.get("y", 0),
                   d.get("rot", 0), d.get("copies", 1), d.get("enabled", True), d.get("name"))


class Layout:
    def __init__(self, roll_w=914.0, edge=DEFAULT_EDGE_MM, gap=DEFAULT_GAP_MM, bottom=DEFAULT_EDGE_MM):
        self.roll_w, self.edge, self.gap, self.bottom_margin = float(roll_w), float(edge), float(gap), float(bottom)
        self.items = []
        self.marks = False                 # метки реза в углах каждого файла
        self.mark_mm = 5.0                 # длина линии метки
        self.mark_off = 1.0                # отступ метки от угла файла
        self.fixed_length = None           # длина бумаги задана жёстко (пробный отпечаток на A4)

    # --- геометрия
    @property
    def printable_w(self):
        return max(0.0, self.roll_w - 2 * self.edge)

    def active(self):
        return [i for i in self.items if i.enabled]

    def length(self):
        """Длина рулона: нижний край самого нижнего включённого файла + нижнее поле."""
        act = self.active()
        if not act:
            return 0.0
        return max(i.bottom for i in act) + self.bottom_margin

    def area_m2(self):
        return self.printable_w * self.length() / 1e6

    def paper_size_mm(self):
        """(ширина, длина) бумаги для драйвера: ширина рулона не меняется, длина — вся раскладка плюс верхняя кромка."""
        if self.fixed_length:
            return self.roll_w, float(self.fixed_length)
        return self.roll_w, self.length() + self.edge

    def mark_segments(self):
        """Линии меток реза (x1, y1, x2, y2) в мм раскладки: по два штриха в каждом углу каждого файла, снаружи рамки."""
        if not self.marks:
            return []
        o, m = self.mark_off, self.mark_mm
        out = []
        for it in self.expand_copies():
            for cx, sx in ((it.x, -1), (it.right, 1)):
                for cy, sy in ((it.y, -1), (it.bottom, 1)):
                    out.append((cx + sx * o, cy, cx + sx * (o + m), cy))
                    out.append((cx, cy + sy * o, cx, cy + sy * (o + m)))
        return out

    def proof_layout(self, paper=(210.0, 297.0), edge=5.0):
        """Уменьшенная копия раскладки для пробного отпечатка на листе paper (мм): всё сжато с сохранением пропорций."""
        act = self.active()
        W = max(self.printable_w, 1.0)
        H = max(self.length(), 1.0)
        k = min((paper[0] - 2 * edge) / W, (paper[1] - 2 * edge) / H, 1.0)
        out = Layout(paper[0], edge, self.gap * k, edge)
        out.marks, out.mark_mm, out.mark_off = self.marks, self.mark_mm * k, self.mark_off * k
        for it in act:
            c = Item.from_dict(it.to_dict())
            c.w, c.h, c.x, c.y = it.w * k, it.h * k, it.x * k, it.y * k
            out.items.append(c)
        out.fixed_length = float(paper[1])
        return out

    def too_long(self):
        return self.length() + self.edge > MAX_PAPER_LEN_MM

    # --- проверки
    def problems(self, min_dpi=100.0):
        """Список (индекс, текст) нарушений: выход за поле, перекрытие, зазор меньше заданного, низкий DPI."""
        out = []
        act = [(n, i) for n, i in enumerate(self.items) if i.enabled]
        eps = 0.05
        for n, i in act:
            if i.x < -eps or i.y < -eps or i.right > self.printable_w + eps:
                out.append((n, "out"))
            d = i.dpi()
            if d and d < min_dpi:
                out.append((n, "dpi"))
        if self.marks and self.gap < self.mark_off + self.mark_mm - 0.05 and len(act) > 1:
            out.append((act[0][0], "marks"))
        for a in range(len(act)):
            for b in range(a + 1, len(act)):
                (na, ia), (nb, ib) = act[a], act[b]
                dx = max(ib.x - ia.right, ia.x - ib.right)
                dy = max(ib.y - ia.bottom, ia.y - ib.bottom)
                gap = max(dx, dy)
                if dx < -eps and dy < -eps:
                    out.append((na, "overlap"))
                    out.append((nb, "overlap"))
                elif gap < self.gap - eps:
                    out.append((na, "gap"))
                    out.append((nb, "gap"))
        return out

    # --- действия
    def add(self, item):
        self.items.append(item)
        return item

    def clamp_inside(self, item):
        item.x = min(max(0.0, item.x), max(0.0, self.printable_w - item.ow))
        item.y = max(0.0, item.y)

    def fit_to_width(self, item):
        """Масштабировать файл по ширине печатной зоны."""
        k = self.printable_w / item.ow if item.ow else 1.0
        item.w, item.h = item.w * k, item.h * k
        item.x = 0.0

    def snap(self, item, tol=5.0):
        """Привязка к краям зоны и к соседям (с зазором). Возвращает True, если что-то сдвинули."""
        moved = False
        cand_x = [0.0, self.printable_w - item.ow]
        cand_y = [0.0]
        for o in self.active():
            if o is item:
                continue
            cand_x += [o.x, o.right - item.ow, o.right + self.gap, o.x - self.gap - item.ow]
            cand_y += [o.y, o.bottom - item.oh, o.bottom + self.gap, o.y - self.gap - item.oh]
        bx = min(cand_x, key=lambda v: abs(v - item.x))
        if abs(bx - item.x) <= tol:
            item.x, moved = bx, True
        by = min(cand_y, key=lambda v: abs(v - item.y))
        if abs(by - item.y) <= tol:
            item.y, moved = max(0.0, by), True
        return moved

    def align(self, items, how):
        """Выравнивание: left, right, hcenter, top, bottom, vcenter."""
        if not items:
            return
        if how == "left":
            v = min(i.x for i in items)
            for i in items:
                i.x = v
        elif how == "right":
            v = max(i.right for i in items)
            for i in items:
                i.x = v - i.ow
        elif how == "hcenter":
            v = (min(i.x for i in items) + max(i.right for i in items)) / 2
            for i in items:
                i.x = v - i.ow / 2
        elif how == "top":
            v = min(i.y for i in items)
            for i in items:
                i.y = v
        elif how == "bottom":
            v = max(i.bottom for i in items)
            for i in items:
                i.y = v - i.oh
        elif how == "vcenter":
            v = (min(i.y for i in items) + max(i.bottom for i in items)) / 2
            for i in items:
                i.y = v - i.oh / 2

    def distribute_v(self, items):
        """Равные зазоры (self.gap) по вертикали в порядке сверху вниз."""
        y = None
        for i in sorted(items, key=lambda t: t.y):
            if y is None:
                y = i.y
            i.y = y
            y = i.bottom + self.gap

    def expand_copies(self):
        """Копии становятся отдельными файлами в раскладке (для упаковки/печати); positions копий — те же, нужно упаковать."""
        out = []
        for i in self.items:
            n = i.copies if i.enabled else 0
            for k in range(n):
                c = Item.from_dict(i.to_dict())
                c.copies = 1
                out.append(c)
        return out

    # --- упаковка
    def autopack(self, allow_rotate=True, mode="min_length"):
        """Раскладка «полками» с лучшим вариантом из нескольких сортировок; возвращает (было_мм, стало_мм).
        mode: min_length — несколько сортировок и поворотов, выбираем самую короткую; list — в порядке списка; column — столбцом."""
        before = self.length()
        act = self.active()
        if not act:
            return before, before
        W = self.printable_w
        best = None
        orders = {
            "list": [lambda i: 0],
            "column": [lambda i: 0],
            "min_length": [lambda i: -i.oh, lambda i: -i.ow, lambda i: -(i.ow * i.oh), lambda i: -max(i.ow, i.oh)],
        }[mode]
        rotate_opts = (False, True) if (allow_rotate and mode == "min_length") else (False,)
        def rotated(placed):
            return sum(1 for it, p in placed.items() if p[2] != it.rot)

        def consider(placed):
            nonlocal best
            if placed is None:
                return
            length = max(p[1] + p[3] for p in placed.values())
            score = (round(length, 1), rotated(placed))              # при равной длине — меньше поворотов
            if best is None or score < best[0]:
                best = (score, placed)
        for key in orders:
            for rot_fit in rotate_opts:
                placed = self._shelf_pack(act, key, rot_fit, W, column=(mode == "column"))
                if placed is not None:                               # у полочной упаковки в p[1] лежит y, в p[3] высота
                    consider({it: (p[0], p[1], p[2], p[3]) for it, p in placed.items()})
        if mode == "min_length":                                     # свободная упаковка: каждый файл поворачивается отдельно, если это короче
            keys = [lambda i: -(i.ow * i.oh), lambda i: -max(i.ow, i.oh), lambda i: -i.oh, lambda i: -i.ow, lambda i: -(i.ow + i.oh)]
            for key in keys:
                for heur in ("bl", "bw"):
                    for allow in ((False, True) if allow_rotate else (False,)):
                        consider(self._maxrects_pack(act, key, heur, W, allow))
        if best is None:
            return before, before
        for it, (x, y, rot, _) in best[1].items():
            it.x, it.y, it.rot = x, y, rot
        return before, self.length()

    def _maxrects_pack(self, act, key, heur, W, allow_rot):
        """Упаковка по свободным прямоугольникам (MaxRects) в полосу шириной W: файл ставится туда, где ниже всего,
        при allow_rot для каждого файла выбирается лучшая из двух ориентаций. Возвращает {item: (x, y, rot, oh)} или None."""
        gap, BIG = self.gap, 1e9
        free = [(0.0, 0.0, W + gap, BIG)]                            # ширина на gap больше: каждому файлу прибавляем gap справа и снизу
        out = {}
        for it in sorted(act, key=key):
            best = None
            for w, h, r in [(it.ow, it.oh, False)] + ([(it.oh, it.ow, True)] if allow_rot else []):
                if w > W + 0.05:
                    continue
                ww, hh = w + gap, h + gap
                for fx, fy, fw, fh in free:
                    if ww <= fw + 0.05 and hh <= fh:
                        sc = (fy + hh, fx, r) if heur == "bl" else (fw - ww, fy + hh, fx, r)
                        if best is None or sc < best[0]:
                            best = (sc, fx, fy, ww, hh, w, h, r)
            if best is None:
                return None
            _, px, py, ww, hh, w, h, r = best
            out[it] = (px, py, (it.rot + 90) % 360 if r else it.rot, h)
            nxt = []
            for fx, fy, fw, fh in free:
                if px >= fx + fw or px + ww <= fx or py >= fy + fh or py + hh <= fy:
                    nxt.append((fx, fy, fw, fh))
                    continue
                if px > fx:
                    nxt.append((fx, fy, px - fx, fh))
                if px + ww < fx + fw:
                    nxt.append((px + ww, fy, fx + fw - px - ww, fh))
                if py > fy:
                    nxt.append((fx, fy, fw, py - fy))
                if py + hh < fy + fh:
                    nxt.append((fx, py + hh, fw, fy + fh - py - hh))
            free = [a for n, a in enumerate(nxt)
                    if not any(n != m and b[0] <= a[0] + 1e-6 and b[1] <= a[1] + 1e-6 and b[0] + b[2] >= a[0] + a[2] - 1e-6 and b[1] + b[3] >= a[1] + a[3] - 1e-6
                               and (b != a or m < n) for m, b in enumerate(nxt))]
        return out

    def _shelf_pack(self, act, key, rot_fit, W, column=False):
        """Полочная упаковка. rot_fit: поворачивать файл так, чтобы длинная сторона шла вдоль рулона (меньше расход по длине)."""
        order = sorted(act, key=key) if key(act[0]) != 0 or len(act) < 2 else list(act)
        placed = {}
        shelf_y = x = shelf_h = 0.0
        first = True
        for it in order:
            rot = it.rot
            ow, oh = it.ow, it.oh
            if rot_fit and oh > ow and oh <= W:
                rot = (rot + 90) % 360
                ow, oh = oh, ow                           # кладём широкой стороной поперёк рулона
            if ow > W + 0.05:
                if oh <= W + 0.05:
                    rot = (rot + 90) % 360
                    ow, oh = oh, ow
                else:
                    return None
            if column:
                x = 0.0
                shelf_y = 0.0 if first else shelf_y + shelf_h + self.gap
                shelf_h = oh
                placed[it] = (x, shelf_y, rot, oh)
                first = False
                continue
            if first:
                x, shelf_y, shelf_h, first = 0.0, 0.0, oh, False
            elif x + self.gap + ow <= W + 0.05:
                x += self.gap
            else:
                shelf_y += shelf_h + self.gap
                x, shelf_h = 0.0, 0.0
            placed[it] = (x, shelf_y, rot, oh)
            x += ow
            shelf_h = max(shelf_h, oh)
        # высота «полки» = самая высокая из лежащих на ней: пересчитаем нижние границы
        return {it: (p[0], p[1], p[2], it_h) for it, p in placed.items() for it_h in [self._oh_after(it, p[2])]}

    @staticmethod
    def _oh_after(it, rot):
        return it.w if rot in (90, 270) else it.h

    # --- сохранение
    def to_json(self):
        return json.dumps({"version": 1, "roll_w": self.roll_w, "edge": self.edge, "gap": self.gap, "bottom": self.bottom_margin,
                           "marks": self.marks, "mark_mm": self.mark_mm,
                           "items": [i.to_dict() for i in self.items]}, ensure_ascii=False, indent=1)

    @classmethod
    def from_json(cls, text):
        d = json.loads(text)
        lay = cls(d.get("roll_w", 914), d.get("edge", DEFAULT_EDGE_MM), d.get("gap", DEFAULT_GAP_MM), d.get("bottom", DEFAULT_EDGE_MM))
        lay.items = [Item.from_dict(x) for x in d.get("items", [])]
        lay.marks, lay.mark_mm = bool(d.get("marks", False)), float(d.get("mark_mm", 5.0))
        return lay

    def snapshot(self):
        return self.to_json()

    def restore(self, snap):
        other = Layout.from_json(snap)
        self.roll_w, self.edge, self.gap, self.bottom_margin, self.items = other.roll_w, other.edge, other.gap, other.bottom_margin, other.items
        self.marks, self.mark_mm = other.marks, other.mark_mm


class History:
    """Отмена/повтор: хранит снимки раскладки."""

    def __init__(self, layout, limit=100):
        self.layout, self.limit = layout, limit
        self.undo_s, self.redo_s = [], []

    def push(self):
        self.undo_s.append(self.layout.snapshot())
        del self.undo_s[:-self.limit]
        self.redo_s.clear()

    def undo(self):
        if not self.undo_s:
            return False
        self.redo_s.append(self.layout.snapshot())
        self.layout.restore(self.undo_s.pop())
        return True

    def redo(self):
        if not self.redo_s:
            return False
        self.undo_s.append(self.layout.snapshot())
        self.layout.restore(self.redo_s.pop())
        return True


def fmt_len(mm):
    """Длина для показа: «2,34 м» или «85,0 см»."""
    return ("%.2f м" % (mm / 1000)).replace(".", ",") if mm >= 1000 else ("%.1f см" % (mm / 10)).replace(".", ",")
