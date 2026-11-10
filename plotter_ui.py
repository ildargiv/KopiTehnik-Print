"""Окно «Плоттер»: поле раскладки в реальных размерах, панель точных размеров, таблица файлов.
Логика — в plotter_layout.py (без Qt). Здесь только интерфейс (PySide6)."""
import os

from PySide6.QtCore import Qt, QRectF, QPointF, QLineF, QItemSelectionModel, Signal
from PySide6.QtGui import QColor, QFont, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut, QTransform
from PySide6.QtWidgets import (QAbstractItemView, QGridLayout, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

import plotter_layout as pl

IMG_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp", ".psd", ".psb", ".pdf"}
THUMB = 512
DEFAULT_DPI = 150.0          # если в файле нет физического размера


T = {}                           # тема программы (тот же словарь, что у окна), подставляется из photo_crop_qt
make_button = [None]             # фабрика кнопок в стиле программы: (текст, slot, ico) -> QPushButton


def _col(key, default):
    return QColor(T.get(key, default))


translate = [lambda s: s]       # photo_crop_qt подставляет сюда tr (прямой импорт дал бы цикл)


def _tr(s):
    return translate[0](s)


def load_file(path):
    """Читает файл: (миниатюра QImage, px_w, px_h, w_мм, h_мм). Физический размер из метаданных (DPI/лист PDF) или 150 dpi."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtCore import QSize
        doc = QPdfDocument()
        if doc.load(path) != QPdfDocument.Error.None_ or doc.pageCount() < 1:
            raise OSError("PDF не открылся")
        sz = doc.pagePointSize(0)
        w, h = sz.width() / 72 * 25.4, sz.height() / 72 * 25.4
        k = THUMB / max(sz.width(), sz.height())
        img = doc.render(0, QSize(max(1, round(sz.width() * k)), max(1, round(sz.height() * k))))
        sp = pl.standard_paper(w, h)
        if sp:
            w, h = sp[1], sp[2]
        return img, round(w / 25.4 * 300), round(h / 25.4 * 300), w, h
    from PIL import Image
    if ext in (".psd", ".psb"):
        try:
            from psd_tools import PSDImage
        except ImportError:
            raise OSError("Для PSD нужен модуль psd-tools (pip install psd-tools)")
        im = PSDImage.open(path).composite().convert("RGB")
        dpi = (DEFAULT_DPI, DEFAULT_DPI)
    else:
        Image.MAX_IMAGE_PIXELS = None
        im = Image.open(path)
        dpi = im.info.get("dpi") or (DEFAULT_DPI, DEFAULT_DPI)
        try:
            dx, dy = float(dpi[0]), float(dpi[1])
        except Exception:
            dx = dy = DEFAULT_DPI
        # 72 и 96 dpi в метаданных — «экранные» значения по умолчанию, а не настоящий размер: берём 150 dpi
        dpi = (dx if dx >= 10 and dx not in (72.0, 96.0) else DEFAULT_DPI, dy if dy >= 10 and dy not in (72.0, 96.0) else DEFAULT_DPI)
    pw, ph = im.size
    w, h = pw / dpi[0] * 25.4, ph / dpi[1] * 25.4
    sp = pl.standard_paper(w, h, pw, ph)           # файл формата А3 и т.п. ложится на рулон точно этим форматом
    if sp:
        w, h = sp[1], sp[2]
    th = im.copy()
    th.thumbnail((THUMB, THUMB))
    th = th.convert("RGBA")
    qi = QImage(th.tobytes("raw", "RGBA"), th.width, th.height, th.width * 4, QImage.Format_RGBA8888).copy()
    return qi, pw, ph, w, h


class PlotterCanvas(QWidget):
    """Поле раскладки: масштаб px/мм, линейки, сетка, рамки файлов с подписями размеров, перетаскивание, привязка."""
    changed = Signal()            # раскладка изменена (после отпускания мыши и т.п.)
    selected = Signal(object)

    zoomed = Signal(float)        # масштаб изменился (px/мм)

    RULER = 26
    MIN_K, MAX_K = 0.02, 8.0

    def __init__(self, layout, history):
        super().__init__()
        self.layout_, self.hist = layout, history
        self.k = 0.4              # пикселей на мм
        self.fit_mode = "width"   # «width» | «all» | None (вручную): по умолчанию рулон на всю ширину окна
        self.sel = None
        self.extra = []           # остальные выделенные файлы (sel — главный, его свойства показаны справа)
        self._band = None         # рамка выделения мышью (QRectF в пикселях) или None
        self._rs = None           # состояние перетаскивания ручки размера или None
        self.thumbs = {}          # id(item) -> QPixmap
        self.snap_on = True
        self._drag = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)
        self.setMinimumSize(300, 300)

    # --- геометрия
    def origin(self):
        return QPointF(self.RULER + 12, self.RULER + 12)

    def to_px(self, x, y):
        o = self.origin()
        return QPointF(o.x() + x * self.k, o.y() + y * self.k)

    def to_mm(self, p):
        o = self.origin()
        return (p.x() - o.x()) / self.k, (p.y() - o.y()) / self.k

    def item_rect(self, it):
        a = self.to_px(it.x, it.y)
        return QRectF(a.x(), a.y(), it.ow * self.k, it.oh * self.k)

    def real_k(self):
        """Пикселей на мм при настоящем размере на экране (1 мм бумаги = 1 мм на мониторе)."""
        try:
            return self.logicalDpiX() / 25.4
        except Exception:
            return 3.78

    def fit_view(self):
        """Пересчитать масштаб по режиму: «width» — рулон по ширине окна, «all» — вся раскладка целиком, None — масштаб задан вручную."""
        if self.fit_mode:
            w = max(100, self.width() - self.RULER - 40)
            k = w / max(1.0, self.layout_.printable_w)
            if self.fit_mode == "all":
                vh = self.parent().height() if self.parent() is not None else self.height()
                k = min(k, max(100, vh - self.RULER - 40) / max(self.layout_.length(), 400))
            self.k = min(self.MAX_K, max(self.MIN_K, k))
        self.update_size()

    def set_fit(self, mode):
        self.fit_mode = mode
        self.fit_view()

    def zoom_to(self, k):
        self.fit_mode = None
        self.k = min(self.MAX_K, max(self.MIN_K, k))
        self.update_size()

    def zoom_by(self, f):
        self.zoom_to(self.k * f)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.fit_mode:
            self.fit_view()

    def update_size(self):
        slack = 0 if self.fit_mode == "all" else 200
        h = int(self.RULER + 40 + max(self.layout_.length(), 400) * self.k + slack)
        self.setMinimumHeight(h)
        self.update()
        self.zoomed.emit(self.k)

    def set_thumb(self, it, qimage):
        self.thumbs[id(it)] = QPixmap.fromImage(qimage)

    def selection(self):
        """Все выделенные файлы в порядке раскладки (главный + остальные)."""
        ids = {id(i) for i in self.extra}
        if self.sel is not None:
            ids.add(id(self.sel))
        return [i for i in self.layout_.items if id(i) in ids]

    def set_selection(self, items, primary=None):
        items = list(items)
        self.sel = primary if primary in items else (items[-1] if items else None)
        self.extra = [i for i in items if i is not self.sel]
        self.selected.emit(self.sel)
        self.update()

    # --- ручки изменения размера
    HANDLE = 9                # сторона квадрата-ручки, px
    HIT = 8                   # радиус попадания в ручку, px

    def sel_bbox(self):
        """Рамка всех выделенных включённых файлов (x0, y0, x1, y1) в мм или None."""
        its = [i for i in self.selection() if i.enabled]
        if not its:
            return None
        return min(i.x for i in its), min(i.y for i in its), max(i.right for i in its), max(i.bottom for i in its)

    def handle_points(self):
        """Углы рамки группы в px: 0 — левый верхний, 1 — правый верхний, 2 — левый нижний, 3 — правый нижний."""
        bb = self.sel_bbox()
        if bb is None:
            return []
        x0, y0, x1, y1 = bb
        return [self.to_px(x0, y0), self.to_px(x1, y0), self.to_px(x0, y1), self.to_px(x1, y1)]

    def handle_at(self, pos):
        for n, pt in enumerate(self.handle_points()):
            if abs(pos.x() - pt.x()) <= self.HIT and abs(pos.y() - pt.y()) <= self.HIT:
                return n
        return None

    def _start_resize(self, n):
        x0, y0, x1, y1 = self.sel_bbox()
        its = [i for i in self.selection() if i.enabled]
        ax, ay = (x1 if n in (0, 2) else x0), (y1 if n in (0, 1) else y0)       # якорь — противоположный угол
        self.hist.push()
        self._rs = {"n": n, "ax": ax, "ay": ay, "W0": max(1e-6, x1 - x0), "H0": max(1e-6, y1 - y0), "moved": False,
                    "orig": [(i, i.x, i.y, i.w, i.h) for i in its]}

    def _do_resize(self, pos, shift):
        rs, L = self._rs, self.layout_
        mx, my = self.to_mm(pos)
        mx, my = max(0.0, mx), max(0.0, my)
        tol = 6 / self.k
        for edge in (0.0, L.printable_w):                    # привязка вертикального края к краям печатной зоны
            if abs(mx - edge) <= tol:
                mx = edge
        ax, ay, orig = rs["ax"], rs["ay"], rs["orig"]
        kx, ky = abs(mx - ax) / rs["W0"], abs(my - ay) / rs["H0"]
        kminx = max(5.0 / i.ow for i, *_ in orig)            # не меньше 5 мм у каждого файла
        kminy = max(5.0 / i.oh for i, *_ in orig)
        lock = getattr(getattr(self, "parent_page", None), "cb_lock", None)
        prop = lock.isChecked() if lock is not None else True
        if len(orig) == 1 and shift:
            prop = not prop
        if prop or len(orig) > 1:
            kx = ky = max(kx, ky, kminx, kminy)
        else:
            kx, ky = max(kx, kminx), max(ky, kminy)
        for it, x, y, w, h in orig:
            it.x, it.y = ax + (x - ax) * kx, ay + (y - ay) * ky
            if it.rot in (90, 270):
                it.h, it.w = h * kx, w * ky
            else:
                it.w, it.h = w * kx, h * ky
        rs["moved"] = True
        self.selected.emit(self.sel)
        self.update_size()

    def _hover_cursor(self, pos):
        n = self.handle_at(pos)
        if n is not None:
            self.setCursor(Qt.SizeFDiagCursor if n in (0, 3) else Qt.SizeBDiagCursor)
        elif any(i.enabled and self.item_rect(i).contains(pos) for i in self.selection()):
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.unsetCursor()

    def item_at(self, pos):
        for it in reversed(self.layout_.items):
            if it.enabled and self.item_rect(it).contains(pos):
                return it
        return None

    # --- рисование
    def paintEvent(self, e):
        L = self.layout_
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        p.fillRect(self.rect(), _col("canvas", "#303030"))
        o = self.origin()
        W = L.printable_w * self.k
        H = max(L.length(), 300) * self.k
        # рулон и печатная зона
        roll = QRectF(o.x() - L.edge * self.k, o.y() - L.edge * self.k, L.roll_w * self.k, H + 2 * L.edge * self.k)
        p.fillRect(roll, QColor("#f4f2ee"))
        zone = QRectF(o.x(), o.y(), W, H)
        p.fillRect(zone, QColor("#ffffff"))
        # сетка: 10 см и 1 м
        pen = QPen(QColor(0, 0, 0, 22))
        p.setPen(pen)
        mm = 0
        while mm <= L.printable_w:
            x = o.x() + mm * self.k
            p.setPen(QPen(QColor(0, 0, 0, 50 if mm % 1000 == 0 else 20)))
            p.drawLine(QPointF(x, o.y()), QPointF(x, o.y() + H))
            mm += 100
        mm = 0
        while mm <= H / self.k:
            y = o.y() + mm * self.k
            p.setPen(QPen(QColor(0, 0, 0, 50 if mm % 1000 == 0 else 20)))
            p.drawLine(QPointF(o.x(), y), QPointF(o.x() + W, y))
            mm += 100
        p.setPen(QPen(QColor("#999"), 1, Qt.DashLine))
        p.drawRect(zone)
        # файлы
        bad = {}
        for n, kind in L.problems():
            bad.setdefault(n, set()).add(kind)
        f = QFont(p.font())
        f.setPixelSize(11)
        p.setFont(f)
        for n, it in enumerate(L.items):
            if not it.enabled:
                continue
            r = self.item_rect(it)
            pm = self.thumbs.get(id(it))
            if pm:
                t = QTransform().rotate(it.rot)
                p.drawPixmap(r.toRect(), pm.transformed(t, Qt.SmoothTransformation))
            else:
                p.fillRect(r, QColor("#cfd8e3"))
            kinds = bad.get(n, set())
            col = _col("bad", "#d33") if kinds & {"overlap", "out"} else _col("warn", "#e90") if kinds & {"gap", "dpi"} else _col("ok", "#2a6")
            if it is self.sel or any(it is x for x in self.extra):
                p.setPen(QPen(_col("select", "#1e6fe8"), 3 if it is self.sel else 2))
            else:
                p.setPen(QPen(col, 2 if kinds else 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
            label = "%s × %s %s" % (self._n(it.ow / 10), self._n(it.oh / 10), _tr("см"))
            tw = p.fontMetrics().horizontalAdvance(label) + 8
            lab = QRectF(r.left(), r.top(), min(tw, max(r.width(), 60)), 17)
            p.fillRect(lab, QColor(0, 0, 0, 170))
            p.setPen(QColor("white"))
            p.drawText(lab.adjusted(4, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, label)
        if L.marks:                                           # метки реза
            p.setPen(QPen(QColor(0, 0, 0), 1))
            for x1, y1, x2, y2 in L.mark_segments():
                p.drawLine(QLineF(self.to_px(x1, y1), self.to_px(x2, y2)))
        # выбранный: размеры до краёв
        if self.sel and self.sel.enabled:
            it, r = self.sel, self.item_rect(self.sel)
            p.setPen(_col("select", "#1e6fe8"))
            p.drawText(QPointF(r.left() + 4, r.bottom() - 5), "x %s  y %s" % (self._n(it.x / 10), self._n(it.y / 10)))
        pts = self.handle_points()
        if pts:                                               # пунктирная рамка группы и 4 угловые ручки
            tl, br = pts[0], pts[3]
            p.setPen(QPen(_col("select", "#1e6fe8"), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(tl, br))
            h = self.HANDLE
            for pt in pts:
                p.setPen(QPen(QColor("white"), 1))
                p.setBrush(_col("select", "#1e6fe8"))
                p.drawRect(QRectF(pt.x() - h / 2, pt.y() - h / 2, h, h))
        if self._band is not None:                            # рамка выделения
            p.setPen(QPen(_col("select", "#1e6fe8"), 1, Qt.DashLine))
            p.setBrush(QColor(30, 111, 232, 40))
            p.drawRect(self._band)
        # линейки
        self._rulers(p, o, W, H)
        p.end()

    @staticmethod
    def _n(v):
        return ("%.1f" % v).replace(".", ",")

    def _rulers(self, p, o, W, H):
        R = self.RULER
        p.fillRect(QRectF(0, 0, self.width(), R), _col("surface", "#222"))
        p.fillRect(QRectF(0, 0, R, self.height()), _col("surface", "#222"))
        p.setPen(_col("text", "#ddd"))
        step = 100 if self.k > 0.15 else 500 if self.k > 0.04 else 1000
        mm = 0
        while mm <= self.layout_.printable_w:
            x = o.x() + mm * self.k
            p.drawLine(QPointF(x, R - 8), QPointF(x, R))
            p.drawText(QPointF(x + 2, R - 10), "%g" % (mm / 10))
            mm += step
        mm = 0
        while mm <= H / self.k:
            y = o.y() + mm * self.k
            p.drawLine(QPointF(R - 8, y), QPointF(R, y))
            p.save()
            p.translate(R - 10, y + 2)
            p.rotate(-90)
            p.drawText(QPointF(0, 0), "%g" % (mm / 10))
            p.restore()
            mm += step

    # --- мышь и клавиши
    def mousePressEvent(self, e):
        self.setFocus()
        if e.button() != Qt.LeftButton:
            return
        n = self.handle_at(e.position())                                     # ручка размера проверяется раньше самого файла
        if n is not None:
            self._start_resize(n)
            return
        it = self.item_at(e.position())
        if e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier):          # Ctrl/Shift: добавить файл в выделение или убрать
            cur = self.selection()
            if it is not None:
                cur = [i for i in cur if i is not it] if any(i is it for i in cur) else cur + [it]
                self.set_selection(cur, it if any(i is it for i in cur) else None)
            return
        if it is None:
            self.set_selected(None)
            self._band_start = e.position()
            self._band = QRectF(e.position(), e.position())
            return
        if not any(it is i for i in self.selection()):                       # щелчок по невыделенному — выделяем его одного
            self.set_selected(it)
        else:
            self.sel = it                                                    # по выделенному — тянем всю группу
            self.selected.emit(it)
        self.hist.push()
        x, y = self.to_mm(e.position())
        self._drag = (it, x - it.x, y - it.y, False, [(i, i.x, i.y) for i in self.selection()], it.x, it.y)

    def mouseMoveEvent(self, e):
        if self._rs is not None:
            self._do_resize(e.position(), bool(e.modifiers() & Qt.ShiftModifier))
            return
        if self._band is None and not self._drag:
            self._hover_cursor(e.position())
        if self._band is not None:
            r = QRectF(self._band_start, e.position()).normalized()
            self._band = r
            hit = [i for i in self.layout_.items if i.enabled and self.item_rect(i).intersects(r)]
            self.set_selection(hit)
            return
        if not self._drag:
            return
        it, dx, dy, _, group, ox, oy = self._drag
        x, y = self.to_mm(e.position())
        it.x, it.y = x - dx, max(0.0, y - dy)
        if self.snap_on:
            self.layout_.snap(it, tol=6 / self.k)
        mx, my = it.x - ox, it.y - oy
        for g, gx, gy in group:
            if g is not it:
                g.x, g.y = gx + mx, max(0.0, gy + my)
        self._drag = (it, dx, dy, True, group, ox, oy)
        self.selected.emit(it)
        self.update_size()

    def mouseReleaseEvent(self, e):
        if self._rs is not None:
            moved = self._rs["moved"]
            self._rs = None
            if not moved and self.hist.undo_s:
                self.hist.undo_s.pop()            # щелчок по ручке без движения не считается действием
            self.changed.emit()
            self.update()
            return
        if self._band is not None:
            self._band = None
            self.update()
        if self._drag:
            moved = self._drag[3]
            self._drag = None
            if not moved and self.hist.undo_s:
                self.hist.undo_s.pop()            # простой щелчок не считается действием
            self.changed.emit()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            self.zoom_by(1.15 if e.angleDelta().y() > 0 else 1 / 1.15)
            e.accept()
        else:
            e.ignore()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_A and e.modifiers() & Qt.ControlModifier:        # Ctrl+A: выделить все файлы
            self.set_selection([i for i in self.layout_.items if i.enabled])
            return
        its = self.selection()
        if not its:
            return super().keyPressEvent(e)
        step = 100.0 if e.modifiers() & Qt.ShiftModifier else 1.0
        d = {Qt.Key_Left: (-step, 0), Qt.Key_Right: (step, 0), Qt.Key_Up: (0, -step), Qt.Key_Down: (0, step)}.get(e.key())
        if d:
            self.hist.push()
            for it in its:
                it.x += d[0]
                it.y = max(0.0, it.y + d[1])
            self.after_edit()
        elif e.key() == Qt.Key_R:
            self.hist.push()
            for it in its:
                it.rotate(90)
            self.after_edit()
        elif e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.hist.push()
            for it in its:
                self.layout_.items.remove(it)
            self.set_selected(None)
            self.after_edit()
        else:
            super().keyPressEvent(e)

    def set_selected(self, it):
        self.sel = it
        self.extra = []
        self.selected.emit(it)
        self.update()

    def after_edit(self):
        self.selected.emit(self.sel)
        self.update_size()
        self.changed.emit()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if os.path.splitext(u.toLocalFile())[1].lower() in IMG_EXTS]
        if paths:
            self.parent_page.add_files(paths, at=self.to_mm(e.position()))


class PlotterPage(QWidget):
    """Страница режима «Плоттер»: поле слева, справа настройки рулона, свойства файла, таблица."""
    changed = Signal()
    proof_requested = Signal()      # «Пробный отпечаток»: окно программы печатает уменьшенную копию на A4
    roll_left_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.L = pl.Layout(roll_w=610)                    # HP DesignJet Z2100: рулон 61 см
        self.hist = pl.History(self.L)
        self.unit = "cm"
        self._busy = False
        self.canvas = PlotterCanvas(self.L, self.hist)
        self.canvas.parent_page = self
        self.canvas.selected.connect(self.sync_props)
        self.canvas.changed.connect(self.refresh)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.canvas)
        self.scroll = scroll

        # --- рулон
        self.cb_roll = QComboBox()
        for w in pl.ROLL_WIDTHS_MM:
            self.cb_roll.addItem("%d мм" % w, w)
        self.cb_roll.addItem(_tr("Своя ширина"), 0)
        self.cb_roll.setCurrentIndex(pl.ROLL_WIDTHS_MM.index(610))
        self.cb_roll.currentIndexChanged.connect(self._roll_changed)
        self.sp_roll = self._spin(1, 5000, 610, " мм")
        self.sp_roll.valueChanged.connect(self._roll_custom)
        self.sp_roll.setEnabled(False)
        self.sp_gap = self._spin(0, 500, 1.0, " см")
        self.sp_gap.setValue(self.L.gap / 10)
        self.sp_gap.valueChanged.connect(self._gap_changed)
        self.sp_edge = self._spin(0, 50, 5, " мм")
        self.sp_edge.valueChanged.connect(self._edge_changed)
        self.cb_snap = QCheckBox(_tr("Привязка"))
        self.cb_snap.setChecked(True)
        self.cb_snap.toggled.connect(lambda v: setattr(self.canvas, "snap_on", v))
        self.cb_rot = QCheckBox(_tr("Разрешить поворот при расстановке"))
        self.cb_rot.setChecked(True)
        self._roll_rows = [(_tr("Ширина рулона"), self.cb_roll), (None, self.sp_roll), (_tr("Расстояние между файлами"), self.sp_gap),
                           (_tr("Кромка рулона"), self.sp_edge), (None, self.cb_snap), (None, self.cb_rot)]

        self.cb_dpi = QComboBox()
        for d in (100, 150, 200, 300):
            self.cb_dpi.addItem("%d dpi" % d, d)
        self.cb_dpi.setCurrentIndex(1)
        self.cb_mirror = QCheckBox(_tr("Зеркально (для переноса)"))
        self.cb_neg = QCheckBox(_tr("Негатив"))
        self.cb_marks = QCheckBox(_tr("Метки реза"))
        self.cb_marks.toggled.connect(self._marks_changed)
        self.sp_left = self._spin(0, 500, 0, " м")
        self.sp_left.setToolTip(_tr("Сколько метров осталось в рулоне. 0 — не учитывать. После печати остаток уменьшается."))
        self.sp_left.valueChanged.connect(lambda v: (self.roll_left_changed.emit(v), self.refresh()))
        self._print_rows = [(_tr("Разрешение печати"), self.cb_dpi), (None, self.cb_mirror), (None, self.cb_neg), (None, self.cb_marks),
                            (_tr("Остаток рулона"), self.sp_left)]

        # --- итог
        self.l_total = QLabel()
        self.l_total.setWordWrap(True)
        self.l_total.setObjectName("plotTotal")
        self.l_note = QLabel()
        self.l_note.setWordWrap(True)
        self.l_warn = QLabel()
        self.l_warn.setWordWrap(True)
        self.l_warn.setStyleSheet("color:%s" % T.get("bad", "#d33"))

        # --- свойства файла
        self.cb_unit = QComboBox()
        for u, t in (("cm", "см"), ("mm", "мм"), ("in", "дюймы")):
            self.cb_unit.addItem(t, u)
        self.cb_unit.currentIndexChanged.connect(self._unit_changed)
        self.sp_w, self.sp_h = self._spin(0.1, 99999, 10), self._spin(0.1, 99999, 10)
        self.sp_x, self.sp_y = self._spin(-99999, 99999, 0), self._spin(-99999, 99999, 0)
        self.sp_pct = self._spin(1, 5000, 100, " %")
        self.cb_lock = QCheckBox(_tr("Сохранять пропорции"))
        self.cb_lock.setChecked(True)
        self.cb_rotv = QComboBox()
        for a in (0, 90, 180, 270):
            self.cb_rotv.addItem("%d°" % a, a)
        self.sp_copies = QSpinBox()
        self.sp_copies.setRange(1, 999)
        self.l_dpi = QLabel("—")
        self.l_src = QLabel("—")
        self.cb_on = QCheckBox(_tr("Печатать этот файл"))
        for w, fn in ((self.sp_w, self._set_w), (self.sp_h, self._set_h), (self.sp_x, self._set_x), (self.sp_y, self._set_y),
                      (self.sp_pct, self._set_pct)):
            w.editingFinished.connect(fn)
        self.cb_rotv.activated.connect(self._set_rot)
        self.sp_copies.editingFinished.connect(self._set_copies)
        self.cb_on.toggled.connect(self._set_on)
        self._size_rows = [(_tr("Единицы"), self.cb_unit), (_tr("Ширина"), self.sp_w), (_tr("Высота"), self.sp_h), (None, self.cb_lock),
                           (_tr("Масштаб"), self.sp_pct), ("X", self.sp_x), ("Y", self.sp_y), (_tr("Поворот"), self.cb_rotv),
                           (_tr("Копий"), self.sp_copies), ("DPI", self.l_dpi), (_tr("Исходный размер"), self.l_src), (None, self.cb_on)]
        self._size_btns = [(_tr("По ширине"), self._fit_width), (_tr("Как в файле"), self._orig_size),
                           ("150 dpi", lambda: self._dpi(150)), ("300 dpi", lambda: self._dpi(300))]
        self.g2 = None

        # --- кнопки
        bar = QHBoxLayout()
        for text, fn, ico in ((_tr("Добавить файлы…"), self.pick_files, "open"), (_tr("Расставить"), self.autopack, "sparkle"),
                              (_tr("Повернуть"), self._rotate_sel, "rot_r"), (_tr("Удалить"), self._delete_sel, None),
                              ("", self.undo, "undo"), ("", self.redo, "redo"), (_tr("Сохранить…"), self.save_layout, "save"),
                              (_tr("Открыть…"), self.open_layout, None)):
            bar.addWidget(self._button(text, fn, ico))
        bar.addStretch(1)

        # --- масштаб поля: − / + / по ширине / целиком / 1:1 (Ctrl+колесо тоже работает)
        self.l_zoom = QLabel("")
        self.l_zoom.setMinimumWidth(48)
        self.l_zoom.setAlignment(Qt.AlignCenter)
        self.l_zoom.setToolTip(_tr("Масштаб на экране: 100% = настоящий размер (1 мм бумаги = 1 мм на мониторе)"))
        for text, fn, tip in (("−", lambda: self.canvas.zoom_by(1 / 1.25), "Уменьшить (Ctrl+−)"),):
            b = self._button(text, fn, None)
            b.setToolTip(_tr(tip))
            bar.addWidget(b)
        bar.addWidget(self.l_zoom)
        for text, fn, tip in (("+", lambda: self.canvas.zoom_by(1.25), "Увеличить (Ctrl++)"),
                              (_tr("По ширине"), lambda: self.canvas.set_fit("width"), "Рулон на всю ширину окна (Ctrl+0)"),
                              (_tr("Весь рулон"), lambda: self.canvas.set_fit("all"), "Вся раскладка в окне (Ctrl+9)"),
                              ("1:1", lambda: self.canvas.zoom_to(self.canvas.real_k()), "Настоящий размер на экране (Ctrl+1)")):
            b = self._button(text, fn, None)
            b.setToolTip(_tr(tip))
            bar.addWidget(b)
        self.canvas.zoomed.connect(lambda k: self.l_zoom.setText("%d%%" % round(k / self.canvas.real_k() * 100)))

        # --- таблица
        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels([_tr("Файл"), _tr("Ширина, см"), _tr("Высота, см"), _tr("Поворот"), _tr("Копий"), "DPI"])
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.ExtendedSelection)      # Shift/Ctrl: несколько файлов, правки применяются ко всем
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setMaximumHeight(170)
        self.tbl.itemSelectionChanged.connect(self._table_selected)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(bar)
        lay.addWidget(self.scroll, 1)
        lay.addWidget(self.tbl)
        for keys, fn in ((QKeySequence.Undo, self.undo), (QKeySequence.Redo, self.redo)):
            QShortcut(keys, self, activated=fn)
        for keys, fn in (("Ctrl+0", lambda: self.canvas.set_fit("width")), ("Ctrl+9", lambda: self.canvas.set_fit("all")),
                         ("Ctrl+1", lambda: self.canvas.zoom_to(self.canvas.real_k())),
                         ("Ctrl+=", lambda: self.canvas.zoom_by(1.25)), ("Ctrl++", lambda: self.canvas.zoom_by(1.25)),
                         ("Ctrl+-", lambda: self.canvas.zoom_by(1 / 1.25))):
            QShortcut(QKeySequence(keys), self, activated=fn)
        self.restyle()
        self.refresh()

    def restyle(self):
        """Поля ввода и таблица в цветах текущей темы программы (иначе Qt рисует их белыми)."""
        t = lambda k, d: T.get(k, d)
        spin = ("QDoubleSpinBox, QSpinBox {background:%s;color:%s;border:1px solid %s;border-radius:8px;padding:4px 8px;min-width:96px;}"
                "QDoubleSpinBox:disabled, QSpinBox:disabled {color:%s;}" % (t("raised", "#333"), t("text", "#eee"), t("border", "#444"), t("muted", "#888")))
        for w in (self.sp_left, self.sp_roll, self.sp_gap, self.sp_edge, self.sp_w, self.sp_h, self.sp_x, self.sp_y, self.sp_pct, self.sp_copies):
            w.setStyleSheet(spin)
        self.tbl.setStyleSheet("QTableWidget{background:%s;color:%s;gridline-color:%s;border:0;selection-background-color:%s;selection-color:%s;}"
                               "QHeaderView::section{background:%s;color:%s;border:0;padding:6px;}"
                               "QTableCornerButton::section{background:%s;border:0;}"
                               % (t("surface", "#222"), t("text", "#eee"), t("border", "#444"), t("accent", "#f80"), t("accent_text", "#111"),
                                  t("raised", "#333"), t("muted", "#999"), t("raised", "#333")))
        self.l_warn.setStyleSheet("color:%s" % t("bad", "#d33"))

    def showEvent(self, e):
        self.restyle()
        super().showEvent(e)

    def _button(self, text, fn, ico=None):
        if make_button[0]:
            return make_button[0](text, fn, ico)
        b = QPushButton(text)
        b.clicked.connect(lambda _=False: fn())
        return b

    def panel_cards(self, card, row, lbl):
        """Карточки правой панели (оформление программы: card/row/lbl передаёт окно). Возвращает список виджетов."""
        def rows(lst):
            out = []
            for label, w in lst:
                out.append(row(label, w) if label else w)
            return out
        c_roll = card(_tr("Рулон"), *rows(self._roll_rows))
        c_print = card(_tr("Печать"), *rows(self._print_rows), self._button(_tr("Пробный отпечаток (A4)"), self.proof_requested.emit))
        c_tot = card(_tr("Итог"), self.l_total, self.l_note, self.l_warn)
        btns = QWidget()
        bl = QGridLayout(btns)
        bl.setContentsMargins(0, 0, 0, 0)
        for n, (text, fn) in enumerate(self._size_btns):
            bl.addWidget(self._button(text, fn), n // 2, n % 2)
        c_size = card(_tr("Размеры выбранного файла"), *rows(self._size_rows), btns)
        self.g2 = c_size
        self.sync_props(self.sel)
        return [c_tot, c_size, c_roll, c_print]

    # --- вспомогательное
    def _spin(self, lo, hi, val, suffix=""):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(2)
        s.setValue(val)
        s.setSuffix(suffix)
        s.setKeyboardTracking(False)
        return s

    def _u(self, mm):
        return pl.from_mm(mm, self.unit)

    def _mm(self, v):
        return pl.to_mm(v, self.unit)

    @property
    def sel(self):
        return self.canvas.sel

    # --- добавление файлов
    def pick_files(self):
        exts = " ".join("*" + x for x in sorted(IMG_EXTS))
        files, _ = QFileDialog.getOpenFileNames(self, _tr("Файлы для плоттера"), "", "%s (%s);;* (*.*)" % (_tr("Изображения и чертежи"), exts))
        if files:
            self.add_files(files)

    def add_files(self, paths, at=None):
        errors = []
        self.hist.push()
        y = max([i.bottom for i in self.L.active()] + [-self.L.gap]) + self.L.gap
        x = 0.0
        for p in paths:
            try:
                qi, pw, ph, w, h = load_file(p)
            except Exception as ex:
                errors.append("%s: %s" % (os.path.basename(p), ex))
                continue
            it = pl.Item(p, w, h, pw, ph, x, y)
            if it.ow > self.L.printable_w + 0.05 and it.oh <= self.L.printable_w + 0.05:
                it.rotate(90)                          # размер не трогаем: не влезает по ширине, но влезет, если повернуть
            if at:
                it.x, it.y = max(0.0, at[0]), max(0.0, at[1])
                self.L.clamp_inside(it)
                at = None
            else:
                it.x, it.y = 0.0, y
                y = it.bottom + self.L.gap
            self.L.add(it)
            self.canvas.set_thumb(it, qi)
            self.canvas.sel = it
        self.refresh()
        self.canvas.set_selected(self.canvas.sel)
        if errors:
            self.l_note.setText("\n".join(errors))
        self.changed.emit()

    # --- действия
    def autopack(self):
        self.hist.push()
        before, after = self.L.autopack(self.cb_rot.isChecked())
        self.refresh()
        self.l_note.setText("%s: %s → %s" % (_tr("Расстановка"), pl.fmt_len(before), pl.fmt_len(after)))

    def _rotate_sel(self):
        its = self.canvas.selection()
        if its:
            self.hist.push()
            for it in its:
                it.rotate(90)
            self.canvas.after_edit()

    def _delete_sel(self):
        its = self.canvas.selection()
        if its:
            self.hist.push()
            for it in its:
                self.L.items.remove(it)
            self.canvas.set_selected(None)
            self.canvas.after_edit()

    def undo(self):
        if self.hist.undo():
            self._after_history()

    def redo(self):
        if self.hist.redo():
            self._after_history()

    def _after_history(self):
        # после восстановления объекты новые: миниатюры подбираем по пути
        old = getattr(self, "_thumb_by_path", {})
        for it in self.L.items:
            if it.path in old:
                self.canvas.set_thumb(it, old[it.path])
        self.canvas.sel = None
        self.refresh()
        self.canvas.set_selected(None)

    def save_layout(self):
        f, _ = QFileDialog.getSaveFileName(self, _tr("Сохранить раскладку"), "", "Plotter layout (*.kplot)")
        if f:
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(self.L.to_json())

    def open_layout(self):
        f, _ = QFileDialog.getOpenFileName(self, _tr("Открыть раскладку"), "", "Plotter layout (*.kplot)")
        if not f:
            return
        with open(f, encoding="utf-8") as fh:
            self.hist.push()
            self.L.restore(fh.read())
            self.cb_marks.blockSignals(True)
            self.cb_marks.setChecked(self.L.marks)
            self.cb_marks.blockSignals(False)
        for it in self.L.items:
            try:
                qi = load_file(it.path)[0]
                self.canvas.set_thumb(it, qi)
            except Exception:
                pass
        self.canvas.sel = None
        self.refresh()

    # --- рулон
    def _roll_changed(self, i):
        w = self.cb_roll.currentData()
        self.sp_roll.setEnabled(not w)
        if w:
            self.L.roll_w = float(w)
            self.sp_roll.setValue(w)
            self.canvas.fit_view()
            self.refresh()

    def _roll_custom(self, v):
        if not self.cb_roll.currentData():
            self.L.roll_w = float(v)
            self.canvas.fit_view()
            self.refresh()

    def _marks_changed(self, on):
        if self.L.marks != on:
            self.hist.push()
            self.L.marks = on
            self.refresh()

    def roll_left_mm(self):
        return self.sp_left.value() * 1000.0

    def consume_roll(self, length_mm):
        """После успешной печати: вычесть израсходованную длину из остатка рулона."""
        if self.sp_left.value() > 0:
            self.sp_left.setValue(max(0.0, self.sp_left.value() - length_mm / 1000.0))

    def _gap_changed(self, v):
        self.L.gap = v * 10
        self.refresh()

    def _edge_changed(self, v):
        self.L.edge = float(v)
        self.canvas.fit_view()
        self.refresh()

    # --- свойства
    def _unit_changed(self):
        self.unit = self.cb_unit.currentData()
        self.sync_props(self.sel)

    def sync_props(self, it):
        if self.g2 is not None:
            self.g2.setEnabled(it is not None)
        widgets = (self.sp_w, self.sp_h, self.sp_x, self.sp_y, self.sp_pct, self.cb_rotv, self.sp_copies, self.cb_on, self.cb_lock)
        for w in widgets:
            w.blockSignals(True)
        if it:
            self.sp_w.setValue(self._u(it.ow))
            self.sp_h.setValue(self._u(it.oh))
            self.sp_x.setValue(self._u(it.x))
            self.sp_y.setValue(self._u(it.y))
            base = max(1e-6, it.w if it.rot in (0, 180) else it.h)
            self.sp_pct.setValue(100.0)
            self.cb_rotv.setCurrentIndex(self.cb_rotv.findData(it.rot))
            self.sp_copies.setValue(it.copies)
            self.cb_on.setChecked(it.enabled)
            d = it.dpi()
            self.l_dpi.setText("%.0f" % d if d else "—")
            self.l_dpi.setStyleSheet("color:%s" % T.get("bad", "#d33") if d and d < 100 else "")
            self.l_src.setText("%d × %d px" % (it.px_w, it.px_h) if it.px_w else "—")
            u = {"cm": " см", "mm": " мм", "in": " ″"}[self.unit]
            for w in (self.sp_w, self.sp_h, self.sp_x, self.sp_y):
                w.setSuffix(u)
        for w in widgets:
            w.blockSignals(False)
        self.canvas.update()
        self._sync_table_sel()

    def _edit(self, fn):
        """Применить правку ко всем выделенным файлам (выделить несколько: рамкой на поле, Ctrl/Shift или в таблице)."""
        its = self.canvas.selection()
        if not its:
            return
        self.hist.push()
        for it in its:
            fn(it)
        self.canvas.after_edit()
        self.refresh()
        self.sync_props(self.sel)

    def _set_w(self):
        it, v = self.sel, self._mm(self.sp_w.value())
        self._edit(lambda i: (i.set_height if i.rot in (90, 270) else i.set_width)(v, self.cb_lock.isChecked()))

    def _set_h(self):
        v = self._mm(self.sp_h.value())
        self._edit(lambda i: (i.set_width if i.rot in (90, 270) else i.set_height)(v, self.cb_lock.isChecked()))

    def _set_x(self):
        v = self._mm(self.sp_x.value())
        s = self.sel
        d = v - s.x if s is not None else 0.0                # группа сдвигается так, чтобы главный файл встал в X
        self._edit(lambda i: setattr(i, "x", max(0.0, i.x + d)))

    def _set_y(self):
        v = self._mm(self.sp_y.value())
        s = self.sel
        d = v - s.y if s is not None else 0.0
        self._edit(lambda i: setattr(i, "y", max(0.0, i.y + d)))

    def _set_pct(self):
        v = self.sp_pct.value()
        if abs(v - 100) > 1e-6:
            self._edit(lambda i: i.set_scale(v))

    def _set_rot(self):
        v = self.cb_rotv.currentData()
        self._edit(lambda i: setattr(i, "rot", v))

    def _set_copies(self):
        self._edit(lambda i: setattr(i, "copies", self.sp_copies.value()))

    def _set_on(self, on):
        self._edit(lambda i: setattr(i, "enabled", on))

    def _fit_width(self):
        self._edit(self.L.fit_to_width)

    def _orig_size(self):
        self._edit(lambda i: i.set_size_for_dpi(DEFAULT_DPI))

    def _dpi(self, d):
        self._edit(lambda i: i.set_size_for_dpi(d))

    # --- таблица и итог
    def _table_selected(self):
        if self._busy:
            return
        rows = sorted({i.row() for i in self.tbl.selectedIndexes() if 0 <= i.row() < len(self.L.items)})
        cur = self.tbl.currentRow()
        items = [self.L.items[r] for r in rows]
        self._from_table = True
        try:
            self.canvas.set_selection(items, self.L.items[cur] if cur in rows else None)
        finally:
            self._from_table = False

    def _sync_table_sel(self):
        if getattr(self, "_from_table", False):
            return
        its = self.canvas.selection()
        self._busy = True
        self.tbl.clearSelection()
        sm = self.tbl.selectionModel()
        for it in its:
            if it in self.L.items:
                idx = self.tbl.model().index(self.L.items.index(it), 0)
                sm.select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        self._busy = False

    def refresh(self):
        self._thumb_by_path = {i.path: self.canvas.thumbs[id(i)].toImage() for i in self.L.items if id(i) in self.canvas.thumbs}
        L = self.L
        self._busy = True
        self.tbl.setRowCount(len(L.items))
        for r, it in enumerate(L.items):
            d = it.dpi()
            vals = (it.name, "%.1f" % (it.ow / 10), "%.1f" % (it.oh / 10), "%d°" % it.rot, str(it.copies), "%.0f" % d if d else "—")
            for c, v in enumerate(vals):
                ti = QTableWidgetItem(v)
                if not it.enabled:
                    ti.setForeground(QColor("#999"))
                self.tbl.setItem(r, c, ti)
        self._busy = False
        n = len(L.active())
        self.l_total.setText("%s: %s × %s    %s: %.2f м²    %s: %d" % (_tr("Рулон"), "%g мм" % L.roll_w, pl.fmt_len(L.length()), _tr("Площадь"), L.area_m2(),
                                                                       _tr("Файлов"), n))
        warns = []
        kinds = {k for _, k in L.problems()}
        if "overlap" in kinds:
            warns.append(_tr("Файлы перекрываются."))
        if "out" in kinds:
            warns.append(_tr("Файл выходит за печатное поле."))
        if "gap" in kinds:
            warns.append(_tr("Расстояние между файлами меньше заданного."))
        if "dpi" in kinds:
            warns.append(_tr("Низкое разрешение (меньше 100 dpi)."))
        if "marks" in kinds:
            warns.append(_tr("Расстояние между файлами меньше места под метки реза (6 мм)."))
        if self.sp_left.value() > 0 and L.length() > self.roll_left_mm():
            warns.append(_tr("Не хватит рулона: нужно") + " %s, " % pl.fmt_len(L.length()) + _tr("осталось") + " %s." % pl.fmt_len(self.roll_left_mm()))
        if L.too_long():
            warns.append(_tr("Раскладка длиннее 3,27 м: драйвер не примет такую бумагу. Сократите раскладку."))
        self.l_warn.setText("\n".join(warns))
        self.canvas.update_size()
        self.changed.emit()
