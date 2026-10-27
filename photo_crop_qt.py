#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PhotoCrop — новый интерфейс на Qt (PySide6).

Вся обработка (кадрирование, цвет, профили, сохранение, печать, агент) остаётся в photo_crop.py —
этот файл только окно. Положите его рядом с photo_crop.py.

Запуск:      python photo_crop_qt.py
Установка:   pip install PySide6 pillow
Самопроверка (собирает окно, делает снимок экрана и отчёт):  python photo_crop_qt.py --selftest
"""
import base64
import struct
import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if "--selftest" in sys.argv:                                # самопроверка пишет настройки, пресеты и журнал: только во временную папку,
    os.environ["APPDATA"] = tempfile.mkdtemp(prefix="photocrop_selftest_")      # настоящие настройки пользователя не трогаем
import print_stats as ps                                  # noqa: E402  (счётчик печати)
import logo_anim_led as la                                 # noqa: E402  (анимированный логотип «LED-табло»)
import agent_badge_neural as abn                           # noqa: E402  (плашка «ИИ-агент работает»)
import brand_datestamp as bd                               # noqa: E402  (фирменное начертание «Дата-штамп»: название и знак)
import photo_crop as pc                                    # noqa: E402  (движок программы)
import color_tools as ct                                   # noqa: E402  (уровни, кривые, выборочный цвет)
import printer_corr as pcr                                 # noqa: E402  (поправка принтера: цвет на выходе, не на экране)
import print_quick as pqk                                  # noqa: E402  (быстрый старт печати: три ячейки настроек)
import epson_priv as ep                                    # noqa: E402  (без полей и цветокоррекция драйвера Epson)
import gui_agent as ga                                     # noqa: E402  (ИИ-агент внутри окна)
import i18n                                                # noqa: E402  (переводы интерфейса)

if len(sys.argv) > 1 and sys.argv[1] in ("agent", "mcp", "mcp-config", "mcp-install", "mcp-uninstall", "--print-project"):
    pc.main()                                              # режим агента и окно печати — как в прежней программе
    sys.exit(0)

try:
    from PySide6.QtCore import (Qt, QSize, QRect, QRectF, QPointF, QTimer, Signal, QObject, QThreadPool, QRunnable,
                                QAbstractListModel, QModelIndex, QEvent, QPropertyAnimation, QEasingCurve, Property, QByteArray,
                                QVariantAnimation)
    from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QPixmap, QImage, QIcon, QPolygonF, QPainterPath, QFont, QIntValidator, QLinearGradient, QRadialGradient, QConicalGradient, QFontMetricsF,
                               QKeySequence, QShortcut, QFontMetrics, QTransform)
    from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QToolButton, QHBoxLayout,
                                   QVBoxLayout, QGridLayout, QComboBox, QLineEdit, QSlider, QRadioButton, QButtonGroup,
                                   QListView, QStyledItemDelegate, QStyle, QScrollArea, QStackedWidget, QDialog, QFileDialog,
                                   QMessageBox, QProgressBar, QProgressDialog, QAbstractItemView, QGraphicsDropShadowEffect, QListWidget,
                                   QListWidgetItem, QTreeWidget, QTreeWidgetItem, QMenu, QSizePolicy, QAbstractButton, QTableWidget, QTableWidgetItem, QTabWidget,
                                   QInputDialog)
    from PySide6.QtSvg import QSvgRenderer
except ImportError:
    sys.stderr.write("PhotoCrop: не установлена библиотека PySide6.\nВыполните в командной строке:  pip install PySide6\n")
    try:
        import tkinter
        from tkinter import messagebox
        _r = tkinter.Tk()
        _r.withdraw()
        messagebox.showerror("PhotoCrop", "Не установлена библиотека PySide6.\n\nВыполните в командной строке:\n    pip install PySide6")
    except Exception:
        pass
    sys.exit(1)

tr, trf = pc.tr, pc.trf
LOG_PATH = pc.SETTINGS_PATH.parent / "qt_error.log"

# ---------------------------------------------------------------- дизайн: цвета тем и иконки

THEMES = {
    # Фирменная: нейтральный графит (не искажает восприятие цвета фото) и три краски печати —
    # оранжевая = главное действие, голубая = выделение, жёлтая = рамка кадра.
    "brand": dict(title="Фирменная", bg="#1b1c1f", surface="#232529", raised="#2d3035", hover="#383c42", border="#3a3e45",
                  text="#eceef1", muted="#9aa0aa", accent="#ff7a1a", accent_text="#1a1205", select="#2ec4e6",
                  canvas="#111214", frame="#ffd21f", ok="#3ccf7a", warn="#f0a030", bad="#ff5a5a"),
    "dark": dict(title="Тёмная", bg="#1e1f22", surface="#26282c", raised="#303338", hover="#3a3e44", border="#3b3f46",
                 text="#e8eaed", muted="#989ea8", accent="#4f8cff", accent_text="#ffffff", select="#4f8cff",
                 canvas="#131416", frame="#ffd21f", ok="#3ccf7a", warn="#f0a030", bad="#ff5a5a"),
    "light": dict(title="Светлая", bg="#eef0f3", surface="#ffffff", raised="#f1f3f6", hover="#e6e9ee", border="#d9dde3",
                  text="#1c1f24", muted="#667085", accent="#2f6bff", accent_text="#ffffff", select="#2f6bff",
                  canvas="#c9ced6", frame="#ffc400", ok="#1f9d57", warn="#c77700", bad="#d92d20"),
    "mono": dict(title="Чёрно-серо-белая", bg="#202020", surface="#2a2a2a", raised="#353535", hover="#424242", border="#454545",
                 text="#f2f2f2", muted="#9d9d9d", accent="#f2f2f2", accent_text="#111111", select="#ffffff",
                 canvas="#6e6e6e", frame="#ffffff", ok="#d0d0d0", warn="#d0d0d0", bad="#ffffff"),
    # Татарская: глубокий изумруд (цвет флага и куполов), золотая нить татарской вышивки, бирюза и красный тюльпан-лалә.
    # Под верхней панелью — орнаментный пояс из тюльпанов. Зелёный = главное действие, бирюза = выделение, золото = рамка.
    "tatar": dict(title="Татарская", bg="#10201b", surface="#162a24", raised="#1d352d", hover="#264439", border="#2c4a3f",
                  text="#eef4ef", muted="#8fb0a2", accent="#1fae73", accent_text="#04170e", select="#3ccfd0",
                  canvas="#0b1411", frame="#ffcf4a", ok="#4fd98a", warn="#f0b030", bad="#ff6a5f",
                  orn="tatar", orn_bg="#0b1612", orn1="#f2c14e", orn2="#d9453a", orn3="#2fbfc2"),
    # Марийская: белый льняной холст и красная вышивка (ромбы и кресты — солнечные знаки), тёмно-коричневая «чёрная» нить.
    "mari": dict(title="Марийская", bg="#f3ecdf", surface="#fffbf3", raised="#f7f0e3", hover="#ecdfca", border="#dccfb8",
                 text="#2a1f1c", muted="#7a6a60", accent="#c4262e", accent_text="#ffffff", select="#8c1d24",
                 canvas="#c9c1b3", frame="#e5242b", ok="#2e8b57", warn="#c77700", bad="#b3261e",
                 orn="mari", orn_bg="#fbf6ec", orn1="#c4262e", orn2="#2a1f1c", orn3="#c4262e"),
}
DEFAULT_THEME = "brand"
T = dict(THEMES[DEFAULT_THEME])            # текущая тема (читают все, кто рисует сам)

ICONS = {
    "open": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2.8v2.4M12 18.8v2.4M2.8 12h2.4M18.8 12h2.4M5.5 5.5l1.7 1.7M16.8 16.8l1.7 1.7M5.5 18.5l1.7-1.7M16.8 7.2l1.7-1.7"/>',
    "prev": '<path d="M14.5 6l-6 6 6 6"/>',
    "next": '<path d="M9.5 6l6 6-6 6"/>',
    "down": '<path d="M6 9.5l6 6 6-6"/>',
    "rot_l": '<path d="M4 9a8 8 0 1 1-1 5"/><path d="M4 4v5h5"/>',
    "rot_r": '<path d="M20 9a8 8 0 1 0 1 5"/><path d="M20 4v5h-5"/>',
    "mirror_h": '<path d="M12 3.5v17" stroke-dasharray="2 2.2"/><path d="M9 7L3.8 17H9z"/><path d="M15 7l5.2 10H15z"/>',
    "mirror_v": '<path d="M3.5 12h17" stroke-dasharray="2 2.2"/><path d="M7 9L17 9 12 3.8z"/><path d="M7 15h10l-5 5.2z"/>',
    "flip": '<rect x="3" y="8" width="8" height="12" rx="1.5"/><rect x="13" y="12" width="8" height="8" rx="1.5" stroke-dasharray="2.5 2.5"/><path d="M14 6h5m0 0l-2-2m2 2l-2 2"/>',
    "undo": '<path d="M8 8H15a5 5 0 0 1 0 10H9"/><path d="M11 5L8 8l3 3"/>',
    "redo": '<path d="M16 8H9a5 5 0 0 0 0 10h6"/><path d="M13 5l3 3-3 3"/>',
    "reset": '<path d="M5 5v5h5"/><path d="M5.5 10a7.5 7.5 0 1 1 1 6.5"/>',
    "color": '<path d="M5 6h9M18 6h1M5 12h2M11 12h8M5 18h10"/><circle cx="16" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
    "grid": '<rect x="3.5" y="3.5" width="17" height="17" rx="2"/><path d="M9.2 3.5v17M14.8 3.5v17M3.5 9.2h17M3.5 14.8h17"/>',
    "check_all": '<rect x="3.5" y="3.5" width="17" height="17" rx="4"/><path d="M8 12.3l2.8 2.8L16.2 9"/>',
    "check_none": '<rect x="3.5" y="3.5" width="17" height="17" rx="4"/>',
    "trash": '<path d="M4.5 7h15M9.5 7V4.8h5V7M6.5 7l.9 12.2h9.2L17.5 7M10 10.5v5.5M14 10.5v5.5"/>',
    "print": '<path d="M7 8V3.8h10V8"/><rect x="3.5" y="8" width="17" height="8.5" rx="2"/><path d="M7 13.5h10v6.7H7z"/>',
    "edit": '<path d="M4 20h4L19.2 8.8a1.9 1.9 0 0 0 0-2.7l-1.3-1.3a1.9 1.9 0 0 0-2.7 0L4 16z"/><path d="M13.5 6.5l4 4"/>',
    "save": '<path d="M5 3.8h11l3.2 3.2V19a1.2 1.2 0 0 1-1.2 1.2H5A1.2 1.2 0 0 1 3.8 19V5A1.2 1.2 0 0 1 5 3.8z"/><path d="M8 3.8v5h7v-5M7.5 20v-6.5h9V20"/>',
    "doc": '<path d="M6 3.8h8l4 4v12.4H6z"/><path d="M14 3.8V8h4M9 12h6M9 15.5h6"/>',
    "edit": '<path d="M4.5 19.5l1-4.2L15.8 5a1.8 1.8 0 0 1 2.5 0l.7.7a1.8 1.8 0 0 1 0 2.5L8.7 18.5z"/><path d="M14 6.8l3.2 3.2"/>',
    "pipette": '<path d="M14.5 5.5l4 4"/><path d="M17.2 3.3a2.1 2.1 0 0 1 3 3l-2.4 2.4-3-3z"/><path d="M14.8 7.7L5.5 17v1.8h1.8l9.3-9.3"/>',
    "plus": '<path d="M12 5.5v13M5.5 12h13"/>',
    "minus": '<path d="M5.5 12h13"/>',
    "check": '<path d="M5.5 12.5l4.2 4.2 8.8-9.2"/>',
    "up": '<path d="M12 19V6m0 0l-5.5 5.5M12 6l5.5 5.5"/>',
    "back": '<path d="M19 12H6m0 0l5.5-5.5M6 12l5.5 5.5"/>',
    "image": '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M4 17l5-4.5 3.5 3 3-2.5 4.5 4"/>',
    "tilt_l": '<path d="M6 16l10-9"/><path d="M6 10v6h6"/>',
    "tilt_r": '<path d="M18 16L8 7"/><path d="M18 10v6h-6"/>',
    "level": '<path d="M3.5 12h17"/><path d="M8 8l-4 4 4 4M16 8l4 4-4 4"/>',
    "profile": '<circle cx="9" cy="9.5" r="5.2"/><circle cx="15" cy="9.5" r="5.2"/><circle cx="12" cy="14.5" r="5.2"/>',
    "project": '<path d="M6 3.8h8.5L19 8.2V19a1.2 1.2 0 0 1-1.2 1.2H6A1.2 1.2 0 0 1 4.8 19V5A1.2 1.2 0 0 1 6 3.8z"/><path d="M14 3.8v4.7h4.8"/>',
    "more": '<circle cx="5.5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="18.5" cy="12" r="1.3"/>',
    "eye": '<path d="M2.5 12S6 5.8 12 5.8 21.5 12 21.5 12 18 18.2 12 18.2 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/>',
    "sparkle": '<path d="M11 3.5l1.9 5.1 5.1 1.9-5.1 1.9L11 17.5l-1.9-5.1L4 10.5l5.1-1.9z"/><path d="M18.5 15.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/>',
    "disk": '<rect x="3.5" y="6" width="17" height="12" rx="2"/><circle cx="16.5" cy="12" r="1.2"/><path d="M7 12h5"/>',
    "desktop": '<rect x="3.5" y="4.5" width="17" height="11.5" rx="1.8"/><path d="M8.5 20h7M12 16v4"/>',
    "download": '<path d="M12 4v11m0 0l-4.5-4.5M12 15l4.5-4.5M5 19.5h14"/>',
    "move": '<path d="M12 3v18M3 12h18M12 3l-3 3M12 3l3 3M12 21l-3-3M12 21l3-3M3 12l3-3M3 12l3 3M21 12l-3-3M21 12l-3 3"/>',
    "paste": '<rect x="5" y="5" width="14" height="16" rx="2"/><path d="M9 5V3.8h6V5M9 11h6M9 15h4"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/>',
    "lock": '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
    "swap": '<path d="M4 8h13m0 0l-3.5-3.5M17 8l-3.5 3.5M20 16H7m0 0l3.5-3.5M7 16l3.5 3.5"/>',
    "zoom_in": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5l5 5M10.5 7.8v5.4M7.8 10.5h5.4"/>',
    "zoom_out": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5l5 5M7.8 10.5h5.4"/>',
    "copy": '<rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M5.5 15.5h-.3A1.7 1.7 0 0 1 3.5 13.8V5.2a1.7 1.7 0 0 1 1.7-1.7h8.6a1.7 1.7 0 0 1 1.7 1.7v.3"/>',
    "nozzle": '<path d="M12 3.3c3.4 4.2 5.8 7.3 5.8 10.4a5.8 5.8 0 0 1-11.6 0c0-3.1 2.4-6.2 5.8-10.4z"/><path d="M9.3 14.2a2.8 2.8 0 0 0 2.7 2.8"/>',
    "head_clean": '<rect x="5" y="3.5" width="14" height="7" rx="1.8"/><path d="M8.5 10.5v1.8M12 10.5v1.8M15.5 10.5v1.8"/><path d="M8 15.3l-1.2 2.4M12 15.3v2.7M16 15.3l1.2 2.4M6.3 20.6h.01M12 20.8h.01M17.7 20.6h.01"/>',
    "driver": ('<path d="M6.5 7.5V3.8h9v3.7"/><path d="M11 15.5H5a1.8 1.8 0 0 1-1.8-1.8V9.3A1.8 1.8 0 0 1 5 7.5h12a1.8 1.8 0 0 1 1.8 1.8v1.7"/>'
               '<path d="M6.5 13v6.2h4.5"/><circle cx="17" cy="17.5" r="2.3"/>'
               '<path d="M17 13.2v1.2M17 20.6v1.2M12.7 17.5h1.2M20.1 17.5h1.2M14 14.5l.8.8M20 20.5l-.8-.8M14 20.5l.8-.8M20 14.5l-.8.8"/>'),
}


def svg_bytes(name, color, width=1.7):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="%s" '
            'stroke-width="%s" stroke-linecap="round" stroke-linejoin="round">%s</svg>' % (color, width, ICONS[name])).encode("utf-8")


# --- ORN BEGIN
def orn_tile(kind, c):
    """Один повтор орнаментного пояса как SVG: (текст, ширина, высота). c — цвета темы orn1..orn3."""
    g, r, t = c["orn1"], c["orn2"], c["orn3"]
    if kind == "tatar":                      # тюльпан (лалә) в золоте и красном, бирюзовый ромб между ними
        body = (
            '<path d="M0 1.5H40M0 14.5H40" stroke="%(g)s" stroke-opacity=".55" stroke-width="1"/>'
            '<g transform="translate(10 0)">'
            '<path d="M0 2.4C3.5 4.9 3.7 9.5 0 12.3C-3.7 9.5 -3.5 4.9 0 2.4Z" fill="%(g)s"/>'
            '<path d="M-1.3 12.2C-6.2 11.6 -7.8 6.6 -6.5 3.6C-4.3 5.3 -3.1 7.6 -1.3 10.1Z" fill="%(r)s"/>'
            '<path d="M1.3 12.2C6.2 11.6 7.8 6.6 6.5 3.6C4.3 5.3 3.1 7.6 1.3 10.1Z" fill="%(r)s"/></g>'
            '<path d="M30 3.4L34.6 8L30 12.6L25.4 8Z" fill="%(t)s"/><circle cx="30" cy="8" r="1.4" fill="%(g)s"/>'
            '<circle cx="20" cy="8" r="1" fill="%(g)s" fill-opacity=".8"/><circle cx="0" cy="8" r="1" fill="%(g)s" fill-opacity=".8"/>'
            '<circle cx="40" cy="8" r="1" fill="%(g)s" fill-opacity=".8"/>')
        w, h = 40, 16
    else:                                    # марийский ромб с отростками и крест: красная нить по льну
        body = (
            '<path d="M0 1.2H28M0 14.8H28" stroke="%(r)s" stroke-width="1"/>'
            '<path d="M14 3L20 8L14 13L8 8Z" fill="none" stroke="%(g)s" stroke-width="1.5"/>'
            '<path d="M14 5.6L16.4 8L14 10.4L11.6 8Z" fill="%(g)s"/>'
            '<rect x="4" y="7" width="2" height="2" fill="%(g)s"/><rect x="22" y="7" width="2" height="2" fill="%(g)s"/>'
            '<rect x="13" y="0.6" width="2" height="2" fill="%(g)s"/><rect x="13" y="13.4" width="2" height="2" fill="%(g)s"/>'
            '<path d="M-2.5 8H2.5M0 5.5V10.5M25.5 8H30.5M28 5.5V10.5" stroke="%(r)s" stroke-width="1.4"/>')
        w, h = 28, 16
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" fill="none">%s</svg>'
           % (w, h, w, h, body % {"g": g, "r": r, "t": t}))
    return svg, w, h
# --- ORN END


_PIX_CACHE = {}


def pix(name, color=None, size=18, width=1.7):
    """Иконка как картинка нужного цвета и размера (рисуется с запасом ×3 — чёткая на любом масштабе экрана)."""
    color = color or T["text"]
    key = (name, color, size, width)
    pm = _PIX_CACHE.get(key)
    if pm is None:
        k = 3
        pm = QPixmap(size * k, size * k)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        QSvgRenderer(QByteArray(svg_bytes(name, color, width))).render(p, QRectF(0, 0, size * k, size * k))
        p.end()
        pm.setDevicePixelRatio(k)
        _PIX_CACHE[key] = pm
    return pm


def icon(name, color=None, size=18):
    return QIcon(pix(name, color, size))


def mix(c1, c2, t):
    a, b = QColor(c1), QColor(c2)
    return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t)).name()


def ui_dir():
    d = pc.SETTINGS_PATH.parent / "ui"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _asset(name, color, size=14, width=2.2):
    """Иконка в файл PNG (для таблицы стилей: стрелка списка, галочка флажка). Возвращает путь с прямыми слэшами."""
    path = ui_dir() / ("%s_%s_%d.png" % (name, color.lstrip("#"), size))
    if not path.exists():
        pm = QPixmap(size * 2, size * 2)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        QSvgRenderer(QByteArray(svg_bytes(name, color, width))).render(p, QRectF(0, 0, size * 2, size * 2))
        p.end()
        pm.save(str(path), "PNG")
    return str(path).replace("\\", "/")


def build_qss(t):
    chev = _asset("down", t["muted"])
    chk = _asset("check", t["accent_text"], 12, 3.0)
    acc_hi = mix(t["accent"], "#ffffff" if QColor(t["accent"]).lightness() < 200 else "#000000", 0.14)
    fams = "".join('"%s", ' % f for f in i18n.FONT_FAMILIES.get(pc.get_language(), []))       # CJK / тайский / деванагари / арабский
    return f"""
    * {{ font-family: "Segoe UI Variable Text", "Segoe UI", {fams}"Inter", "Noto Sans", sans-serif; font-size: 13px; color: {t['text']}; outline: 0; }}
    QMainWindow, QDialog, #root {{ background: {t['bg']}; }}
    QLabel {{ background: transparent; }}
    QLabel[role="muted"] {{ color: {t['muted']}; font-size: 12px; }}
    QLabel[role="title"] {{ color: {t['muted']}; font-size: 12px; font-weight: 600; }}
    QLabel[role="logo"] {{ font-size: 15px; font-weight: 600; }}
    QLabel[role="h1"] {{ font-size: 16px; font-weight: 600; }}
    #topbar {{ background: {t['bg']}; border-bottom: 1px solid {t['border']}; }}
    #card {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 13px; }}
    #pill {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 14px; }}
    #copies {{ background: {t['accent']}; border: none; border-radius: 12px; }}
    #copies QLabel {{ background: transparent; color: {t['accent_text']}; font-size: 17px; font-weight: 700; }}
    #copies QToolButton {{ background: transparent; border-radius: 9px; padding: 3px; }}
    #copies QToolButton:hover {{ background: rgba(0,0,0,0.18); }}
    #copies QToolButton:pressed {{ background: rgba(0,0,0,0.30); }}
    #copiesq {{ background: {t['raised']}; border: 1px solid {t['text']}; border-radius: 12px; }}
    #copiesq QLabel {{ background: transparent; color: {t['text']}; font-size: 17px; font-weight: 700; }}
    #copiesq QToolButton {{ background: transparent; border-radius: 9px; padding: 3px; }}
    #copiesq QToolButton:hover {{ background: {t['hover']}; }}
    #copiesq QToolButton:pressed {{ background: {t['border']}; }}
    #sep {{ background: {t['border']}; }}
    QPushButton {{ background: {t['raised']}; border: 1px solid {t['border']}; border-radius: 9px; padding: 9px 16px; min-height: 18px; font-size: 13px; font-weight: 500; }}
    QPushButton:hover {{ background: {t['hover']}; }}
    QPushButton:pressed {{ background: {t['border']}; }}
    QPushButton:disabled {{ color: {t['muted']}; }}
    QPushButton[kind="primary"] {{ background: {t['accent']}; border-color: {t['accent']}; color: {t['accent_text']}; font-weight: 600; }}
    QPushButton[kind="primary"]:hover {{ background: {acc_hi}; border-color: {acc_hi}; }}
    QPushButton[kind="primary"]:disabled {{ background: {t['raised']}; border-color: {t['border']}; color: {t['muted']}; }}
    QPushButton[big="true"] {{ padding: 13px 16px; border-radius: 11px; font-size: 14px; }}
    QPushButton[kind="seg"] {{ background: transparent; border: 1px solid transparent; border-radius: 7px; padding: 6px 13px; color: {t['muted']}; font-weight: 400; }}
    QPushButton[kind="seg"]:hover {{ color: {t['text']}; }}
    QPushButton[kind="seg"]:checked {{ background: {t['surface']}; border-color: {t['border']}; color: {t['text']}; }}
    QPushButton[kind="chip"] {{ background: {t['raised']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 6px 4px; min-width: 34px; font-weight: 500; }}
    QPushButton[kind="chip"]:checked {{ background: {t['accent']}; border-color: {t['accent']}; color: {t['accent_text']}; font-weight: 700; }}
    QPushButton[kind="link"] {{ background: transparent; border: none; color: {t['muted']}; padding: 4px 6px; }}
    QPushButton[kind="link"]:hover {{ color: {t['text']}; }}
    QPushButton[kind="place"] {{ background: transparent; border: none; text-align: left; padding: 8px 10px; border-radius: 8px; }}
    QPushButton[kind="place"]:hover {{ background: {t['hover']}; }}
    #seg {{ background: {t['raised']}; border: 1px solid {t['border']}; border-radius: 9px; }}
    QToolButton {{ background: transparent; border: none; border-radius: 9px; padding: 6px; }}
    QToolButton:hover {{ background: {t['hover']}; }}
    QToolButton:pressed {{ background: {t['border']}; }}
    QToolButton[boxed="true"] {{ background: {t['raised']}; border: 1px solid {t['border']}; }}
    QToolButton::menu-indicator {{ image: none; }}
    QLineEdit, QComboBox {{ background: {t['raised']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 6px 10px;
        selection-background-color: {t['select']}; selection-color: #000000; }}
    QLineEdit:focus, QComboBox:focus {{ border-color: {t['select']}; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox::down-arrow {{ image: url("{chev}"); width: 14px; height: 14px; }}
    QComboBox QAbstractItemView {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 4px;
        selection-background-color: {t['hover']}; selection-color: {t['text']}; }}
    QMenu {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 10px; padding: 6px; }}
    QMenu::item {{ padding: 7px 26px 7px 12px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {t['hover']}; }}
    QSlider::groove:horizontal {{ height: 4px; background: {t['hover']}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {t['select']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; background: #ffffff; border: 1px solid rgba(0,0,0,70); }}
    QRadioButton, QCheckBox {{ spacing: 8px; background: transparent; }}
    QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 8px; border: 1.5px solid {t['muted']}; background: transparent; }}
    QRadioButton::indicator:checked {{ width: 6px; height: 6px; border: 5px solid {t['accent']}; background: {t['accent_text']}; }}
    QCheckBox::indicator {{ width: 15px; height: 15px; border-radius: 5px; border: 1.5px solid {t['muted']}; }}
    QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; image: url("{chk}"); }}
    QProgressBar {{ background: {t['hover']}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
    QProgressBar::chunk {{ background: {t['accent']}; border-radius: 3px; }}
    QScrollArea, QListView, QListWidget {{ background: transparent; border: none; }}
    QAbstractScrollArea > QWidget#qt_scrollarea_viewport {{ background: transparent; }}
    #scrollInner {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t['hover']}; border-radius: 3px; min-height: 36px; }}
    QScrollBar::handle:vertical:hover {{ background: {t['muted']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QScrollBar:horizontal {{ height: 0; }}
    QToolTip {{ background: {t['surface']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 5px 8px; }}
    QMessageBox {{ background: {t['bg']}; }}
    """


# ---------------------------------------------------------------- маленькие строительные блоки

def lbl(text, role=None, wrap=False):
    w = QLabel(tr(text))
    if role:
        w.setProperty("role", role)
    w.setWordWrap(wrap)
    return w


def hint(text):
    """Мелкая пояснительная подпись с переносом по словам, без лишней высоты."""
    w = lbl(text, "muted", wrap=True)
    w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
    return w


class WrapLabel(QLabel):
    """Подпись в строке «подпись — элемент»: когда места хватает — одна строка, когда тесно — переносится по словам,
    а не раздувает панель (обычный QLabel с переносом просит узкую колонку и переносится без нужды)."""

    def __init__(self, text):
        super().__init__(text)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self.text()) + 2, fm.height() + 2)

    def minimumSizeHint(self):
        return QSize(48, self.fontMetrics().height() + 2)


PRESETS = (1, 2, 3)                                   # кнопки быстрых пресетов цвета


class LogoMark(QWidget):
    """Знак компании, как в конвертере: плитка с текучим градиентом, мягкое свечение, пробегающий блик
    и «прыжок» при наведении курсора."""
    SIZE = 44

    def __init__(self, letter="К"):
        super().__init__()
        self.letter = letter
        self.setFixedSize(self.SIZE, self.SIZE)
        self._flow, self._shine, self._pop = 0.0, -1.0, 0.0
        self.setCursor(Qt.PointingHandCursor)
        self._flow_anim = QVariantAnimation(self, duration=7000, startValue=0.0, endValue=1.0, loopCount=-1)
        self._flow_anim.valueChanged.connect(self._on_flow)
        self._shine_anim = QVariantAnimation(self, duration=1100, startValue=-0.5, endValue=1.5)
        self._shine_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._shine_anim.valueChanged.connect(self._on_shine)
        self._shine_anim.finished.connect(lambda: self._on_shine(-1.0))
        self._shine_timer = QTimer(self)
        self._shine_timer.setInterval(5200)
        self._shine_timer.timeout.connect(self._shine_anim.start)
        self._pop_anim = QVariantAnimation(self, duration=420)
        self._pop_anim.valueChanged.connect(self._on_pop)

    def _on_flow(self, v):
        self._flow = float(v)
        self.update()

    def _on_shine(self, v):
        self._shine = float(v)
        self.update()

    def _on_pop(self, v):
        self._pop = float(v)
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        self._flow_anim.start()
        self._shine_timer.start()
        QTimer.singleShot(700, self._shine_anim.start)

    def hideEvent(self, e):
        super().hideEvent(e)
        self._flow_anim.stop()
        self._shine_timer.stop()

    def _pop_to(self, end, curve):
        self._pop_anim.stop()
        self._pop_anim.setStartValue(self._pop)
        self._pop_anim.setEndValue(end)
        self._pop_anim.setEasingCurve(curve)
        self._pop_anim.start()

    def enterEvent(self, e):
        super().enterEvent(e)
        self._pop_to(1.0, QEasingCurve.OutBack)
        if self._shine_anim.state() != QVariantAnimation.Running:
            self._shine_anim.start()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self._pop_to(0.0, QEasingCurve.OutCubic)

    def paintEvent(self, _):
        import math
        s = self.SIZE
        a1, a2 = QColor(T["accent"]), QColor(mix(T["accent"], "#ffd21f", 0.75))
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        c = QPointF(s / 2, s / 2)
        breathe = 0.5 + 0.5 * math.sin(self._flow * 2 * math.pi)
        halo = QRadialGradient(c, s * 0.62)
        halo.setColorAt(0.55, QColor(a1.red(), a1.green(), a1.blue(), max(0, min(255, int(60 + 50 * breathe + 60 * self._pop)))))
        halo.setColorAt(1, QColor(a1.red(), a1.green(), a1.blue(), 0))
        p.fillRect(self.rect(), halo)
        p.translate(c)
        k = 1.0 + 0.12 * self._pop
        p.scale(k, k)
        p.rotate(-7 * self._pop)
        p.translate(-c)
        bd.draw_mark(p, QRectF(0, 0, s, s), True)
        p.end()


class BrandTitle(QWidget):
    """Название компании, как в конвертере: буквы один раз «падают» при открытии окна, потом по ним плывёт цвет.
    Часть после первого слова показана тихо рядом."""

    def __init__(self):
        super().__init__()
        self.brand = self.tail = ""
        self._flow, self._intro, self._intro_done = 0.0, 0.0, False
        self._flow_anim = QVariantAnimation(self, duration=5200, startValue=0.0, endValue=1.0, loopCount=-1)
        self._flow_anim.valueChanged.connect(self._on_flow)
        self._intro_anim = QVariantAnimation(self, duration=1100, startValue=0.0, endValue=1.0)
        self._intro_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._intro_anim.valueChanged.connect(self._on_intro)
        self._intro_anim.finished.connect(self._intro_finished)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

    def _intro_finished(self):
        self._intro_done, self._intro = True, 1.0
        self.update()

    def setText(self, text):
        self.brand, self.tail = (text if bd.set_name(text) else "КопиТехник Принт"), ""
        self.updateGeometry()
        self.update()

    H = 17                                            # высота матрицы названия, px

    def sizeHint(self):
        bd.set_name(self.brand)
        return QSize(int(bd.wordmark_size(self.H)[0]) + 6, 34)

    def minimumSizeHint(self):
        return self.sizeHint()

    def _on_flow(self, v):
        self._flow = float(v)
        self.update()

    def _on_intro(self, v):
        self._intro = float(v)
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        if ANIM_ON[0]:
            self._flow_anim.start()
        if not self._intro_done and self._intro_anim.state() != QVariantAnimation.Running:
            self._intro_anim.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._flow_anim.stop()

    def paintEvent(self, _):
        bd.set_name(self.brand)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        phase = self._flow if self._flow_anim.state() == QVariantAnimation.Running else None
        bd.draw_wordmark(p, 3, (self.height() - self.H) / 2, self.H, True, phase=phase, reveal=self._intro)
        p.end()


ANIM_ON = [True]           # зеркало настройки «Анимация» для самостоятельных виджетов
abn.T, abn.ANIM_ON = T, ANIM_ON
la.ANIM_ON = ANIM_ON


class ModeSwitch(QWidget):
    """Переключатель режимов ФОТО / ДОКУМЕНТ: бегунок плавно переезжает с лёгким «пружинным» отскоком, значок подсвечивается."""
    changed = Signal(str)
    ITEMS = (("photo", "Фото", "image"), ("doc", "Документ", "doc"))

    def __init__(self, value="photo"):
        super().__init__()
        self.value, self._x, self._hover = value, (0.0 if value == "photo" else 1.0), -1
        self.setFixedSize(236, 40)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self._anim = QPropertyAnimation(self, b"knobx", self)
        self._anim.setDuration(380)
        self._anim.setEasingCurve(QEasingCurve.OutBack)

    def getKx(self):
        return self._x

    def setKx(self, v):
        self._x = float(v)
        self.update()

    knobx = Property(float, getKx, setKx)       # не «x»: так уже называется положение виджета

    def set(self, value, animate=True):
        if value == self.value:
            return
        self.value = value
        end = 0.0 if value == "photo" else 1.0
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._x)
            self._anim.setEndValue(end)
            self._anim.start()
        else:
            self._x = end
            self.update()

    def _idx(self, pos):
        return 0 if pos.x() < self.width() / 2 else 1

    def mouseMoveEvent(self, e):
        self._hover = self._idx(e.position())
        self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            v = self.ITEMS[self._idx(e.position())][0]
            if v != self.value:
                self.set(v)
                self.changed.emit(v)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H, pad = self.width(), self.height(), 3
        track = QRectF(0.5, 0.5, W - 1, H - 1)
        p.setPen(QPen(QColor(T["border"]), 1))
        p.setBrush(QColor(T["raised"]))
        p.drawRoundedRect(track, H / 2, H / 2)
        cw = (W - 2 * pad) / 2
        x = pad + cw * self._x
        thumb = QRectF(x, pad, cw, H - 2 * pad)
        glow = QColor(T["accent"])                                   # мягкое свечение под бегунком
        for i, a in enumerate((16, 30, 46)):
            glow.setAlpha(a)
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(thumb.adjusted(-(3 - i), -(3 - i) / 2, 3 - i, (3 - i) / 2), (H - 2 * pad) / 2 + 2, (H - 2 * pad) / 2 + 2)
        grad = QLinearGradient(thumb.topLeft(), thumb.bottomLeft())
        grad.setColorAt(0, QColor(mix(T["accent"], "#ffffff", 0.18)))
        grad.setColorAt(1, QColor(T["accent"]))
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(thumb, (H - 2 * pad) / 2, (H - 2 * pad) / 2)
        f = QFont(p.font())
        f.setPixelSize(13)                                         # тот же шрифт и размер, что у кнопок («Открыть»)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        for i, (key, text, ico) in enumerate(self.ITEMS):
            text = tr(text)
            cell = QRectF(pad + cw * i, pad, cw, H - 2 * pad)
            near = max(0.0, 1.0 - abs(self._x - i))                  # 1 — бегунок под этим пунктом
            col = QColor(mix(T["muted"] if self._hover != i else T["text"], T["accent_text"], near))
            pm = pix(ico, col.name(), 18)
            fm = QFontMetrics(f)
            tw = fm.horizontalAdvance(text)
            total = 18 + 7 + tw
            lift = -1.0 * near
            x0 = cell.center().x() - total / 2
            p.drawPixmap(QPointF(x0, cell.center().y() - 9 + lift), pm)
            p.setPen(col)
            p.drawText(QRectF(x0 + 25, cell.top() + lift, tw + 4, cell.height()), Qt.AlignVCenter | Qt.AlignLeft, text)
        p.end()


class MotionButton(QPushButton):
    """Кнопка с живым откликом: плавная подсветка при наведении и волна от места нажатия."""

    def __init__(self, text=""):
        super().__init__(text)
        self._hv, self._rp, self._pt = 0.0, 1.0, QPointF()
        self._ah = QPropertyAnimation(self, b"hv", self)
        self._ah.setDuration(160)
        self._ah.setEasingCurve(QEasingCurve.OutCubic)
        self._ar = QPropertyAnimation(self, b"rp", self)
        self._ar.setDuration(420)
        self._ar.setEasingCurve(QEasingCurve.OutQuad)
        self._ar.setStartValue(0.0)
        self._ar.setEndValue(1.0)

    def getHv(self):
        return self._hv

    def setHv(self, v):
        self._hv = float(v)
        self.update()

    def getRp(self):
        return self._rp

    def setRp(self, v):
        self._rp = float(v)
        self.update()

    hv = Property(float, getHv, setHv)
    rp = Property(float, getRp, setRp)

    def _fade(self, to):
        self._ah.stop()
        self._ah.setStartValue(self._hv)
        self._ah.setEndValue(to)
        self._ah.start()

    def enterEvent(self, e):
        self._fade(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._fade(0.0)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled():
            self._pt = e.position()
            self._ar.stop()
            self._ar.start()
        super().mousePressEvent(e)

    def paintEvent(self, e):
        super().paintEvent(e)
        if not self.isEnabled() or (self._hv <= 0.001 and self._rp >= 1.0):
            return
        primary = self.property("kind") == "primary"
        base = QColor(T["accent_text"] if primary else T["accent"])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 9, 9)
        p.setClipPath(path)
        c = QColor(base)
        c.setAlphaF((0.20 if primary else 0.10) * self._hv)
        p.fillPath(path, c)
        if self._rp < 1.0:
            r = max(self.width(), self.height()) * 1.1 * self._rp
            c2 = QColor(base)
            c2.setAlphaF(0.30 * (1.0 - self._rp))
            p.setPen(Qt.NoPen)
            p.setBrush(c2)
            p.drawEllipse(self._pt, r, r)
        p.end()


class GearButton(MotionButton):
    """Кнопка «Настройки» в шапке: шестерёнка + подпись. Шестерёнка плавно поворачивается при наведении
    и делает полный оборот по щелчку; цвета берутся из текущей темы."""
    TEETH = 8

    def __init__(self, text, tip, slot):
        super().__init__(tr(text))
        self.setToolTip(tr(tip))
        self.setCursor(Qt.PointingHandCursor)
        self._rot = 0.0
        self._ag = QPropertyAnimation(self, b"rot", self)
        self.setFixedHeight(34)
        self.clicked.connect(lambda _=False: slot())
        self.pressed.connect(self._spin)

    def getRot(self):
        return self._rot

    def setRot(self, v):
        self._rot = float(v)
        self.update()

    rot = Property(float, getRot, setRot)

    def _go(self, to, ms, curve):
        self._ag.stop()
        if not ANIM_ON[0]:
            self._rot = float(to)
            self.update()
            return
        self._ag.setDuration(ms)
        self._ag.setEasingCurve(curve)
        self._ag.setStartValue(self._rot)
        self._ag.setEndValue(float(to))
        self._ag.start()

    def enterEvent(self, e):
        self._go(45.0 + 360.0 * round(self._rot / 360.0), 520, QEasingCurve.OutBack)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._go(360.0 * round(self._rot / 360.0), 420, QEasingCurve.InOutCubic)
        super().leaveEvent(e)

    def _spin(self):
        self._go(self._rot + 360.0, 800, QEasingCurve.OutCubic)

    def _font(self):
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setWeight(QFont.DemiBold)
        return f

    def sizeHint(self):
        return QSize(14 + 18 + 8 + QFontMetrics(self._font()).horizontalAdvance(self.text()) + 14, 34)

    def minimumSizeHint(self):
        return self.sizeHint()

    def _gear(self, r_out):
        r_in = r_out * 0.76
        path = QPainterPath()
        pts = []
        n = self.TEETH
        for i in range(n):
            a0 = 360.0 / n * i
            for da, rr in ((-12, r_in), (-7, r_out), (7, r_out), (12, r_in)):
                t = math.radians(a0 + da)
                pts.append(QPointF(rr * math.cos(t), rr * math.sin(t)))
        path.addPolygon(QPolygonF(pts))
        path.closeSubpath()
        path.addEllipse(QPointF(0, 0), r_out * 0.34, r_out * 0.34)
        path.setFillRule(Qt.OddEvenFill)
        return path

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        hv = self._hv
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 11, 11)
        acc = T["accent"]
        p.setPen(QPen(QColor(mix(T["border"], acc, 0.15 + 0.5 * hv)), 1))
        p.setBrush(QColor(mix(mix(T["raised"], T["hover"], hv), acc, 0.04 + 0.08 * hv)))
        p.drawPath(path)
        if self._rp < 1.0:
            p.save()
            p.setClipPath(path)
            R = max(self.width(), self.height()) * 1.1 * self._rp
            c = QColor(acc)
            c.setAlphaF(0.28 * (1.0 - self._rp))
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawEllipse(self._pt, R, R)
            p.restore()
        p.save()
        p.translate(14 + 9, self.height() / 2.0)
        p.rotate(self._rot)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(mix(T["muted"], acc, 0.35 + 0.65 * hv)))
        p.drawPath(self._gear(9.0))
        p.restore()
        p.setFont(self._font())
        p.setPen(QColor(mix(T["text"], acc, 0.25 * hv)))
        p.drawText(QRectF(14 + 18 + 8, 0, self.width() - 14 - 18 - 8 - 8, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        p.end()


def btn(text, slot=None, kind=None, big=False, ico=None, ico_color=None, tip=None):
    b = MotionButton(tr(text))
    if kind:
        b.setProperty("kind", kind)
    if big:
        b.setProperty("big", "true")
    if ico:
        b.setIcon(icon(ico, ico_color or (T["accent_text"] if kind == "primary" else T["text"])))
        b.setIconSize(QSize(18, 18))
    if tip:
        b.setToolTip(tr(tip))
    if slot:
        b.clicked.connect(lambda _=False: slot())
    b.setCursor(Qt.PointingHandCursor)
    return b


class ActionButton(MotionButton):
    """Плитка действия на всю ширину: значок в цветной подложке, название и короткая серая подпись.
    При нажатии плитка слегка «вдавливается», волна мягкая и широкая; busy() — бегущая полоска по нижнему краю
    и пульс вокруг значка, done() — короткая вспышка цветом результата."""

    def __init__(self, text="", sub="", ico="settings", tone="accent"):
        super().__init__(text)
        self.sub, self.ico, self.tone = sub, ico, tone
        self._pr, self._bz, self._fl, self._fc, self._want_flash = 0.0, 1.0, 0.0, "ok", False
        self._ar.setDuration(560)
        self._ap = QPropertyAnimation(self, b"pr", self)
        self._ab = QPropertyAnimation(self, b"bz", self)
        self._ab.setDuration(900)
        self._ab.setEasingCurve(QEasingCurve.InOutCubic)
        self._ab.setStartValue(0.0)
        self._ab.setEndValue(1.0)
        self._ab.finished.connect(self._busy_end)
        self._af = QPropertyAnimation(self, b"fl", self)
        self._af.setDuration(650)
        self._af.setEasingCurve(QEasingCurve.OutQuad)
        self._af.setStartValue(1.0)
        self._af.setEndValue(0.0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def getPr(self):
        return self._pr

    def setPr(self, v):
        self._pr = float(v)
        self.update()

    def getBz(self):
        return self._bz

    def setBz(self, v):
        self._bz = float(v)
        self.update()

    def getFl(self):
        return self._fl

    def setFl(self, v):
        self._fl = float(v)
        self.update()

    pr = Property(float, getPr, setPr)
    bz = Property(float, getBz, setBz)
    fl = Property(float, getFl, setFl)

    def _fonts(self):
        f1, f2 = QFont(self.font()), QFont(self.font())
        f1.setPixelSize(14)
        f1.setWeight(QFont.DemiBold)
        f2.setPixelSize(12)
        return f1, f2

    def sizeHint(self):
        f1, f2 = self._fonts()
        m1, m2 = QFontMetrics(f1), QFontMetrics(f2)
        tw = max(m1.horizontalAdvance(self.text()), m2.horizontalAdvance(self.sub) if self.sub else 0)
        th = m1.height() + (m2.height() + 1 if self.sub else 0)
        return QSize(10 + 34 + 11 + tw + 34, max(34, th) + 18)

    def minimumSizeHint(self):
        return QSize(120, self.sizeHint().height())

    def _tint(self):
        if not self.isEnabled():
            return QColor(T["muted"])
        if self.tone == "select" and T["select"].lower() == T["accent"].lower():
            return QColor(T["text"])
        return QColor(T.get(self.tone, T["accent"]))

    def _press(self, to):
        self._ap.stop()
        if not ANIM_ON[0]:
            self.setPr(to)
            return
        self._ap.setDuration(120 if to else 260)
        self._ap.setEasingCurve(QEasingCurve.OutQuad if to else QEasingCurve.InOutCubic)
        self._ap.setStartValue(self._pr)
        self._ap.setEndValue(to)
        self._ap.start()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled():
            self._press(1.0)
            if not ANIM_ON[0]:
                QPushButton.mousePressEvent(self, e)
                return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press(0.0)                            # до super(): по щелчку может открыться модальный диалог
        super().mouseReleaseEvent(e)

    def busy(self):
        self._want_flash = False
        if ANIM_ON[0]:
            self._ab.stop()
            self._ab.start()

    def done(self, ok=True):
        self._fc = "ok" if ok else "bad"
        if not ANIM_ON[0]:
            return
        if self._ab.state() == QVariantAnimation.Running:
            self._want_flash = True
        else:
            self._af.stop()
            self._af.start()

    def _busy_end(self):
        if self._want_flash:
            self._want_flash = False
            self._af.stop()
            self._af.start()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on, k, hv = self.isEnabled(), self._pr, (self._hv if self.isEnabled() else 0.0)
        tint = self._tint()
        tn = tint.name()
        r = QRectF(self.rect()).adjusted(0.5 + 1.5 * k, 0.5 + 1.5 * k, -0.5 - 1.5 * k, -0.5 - 0.5 * k)
        path = QPainterPath()
        path.addRoundedRect(r, 11, 11)
        bg = mix(mix(T["raised"], T["hover"], hv), tn, 0.04 + 0.05 * hv)
        bg = mix(bg, T["border"], 0.55 * k)
        edge = mix(T["border"], tn, (0.18 + 0.47 * hv) if on else 0.0)
        if self._fl > 0.0:
            bg = mix(bg, T[self._fc], 0.14 * self._fl)
            edge = mix(edge, T[self._fc], self._fl)
        p.setPen(QPen(QColor(edge), 1))
        p.setBrush(QColor(bg))
        p.drawPath(path)
        p.save()
        p.setClipPath(path)
        if self._rp < 1.0:
            R = math.hypot(r.width(), r.height()) * (0.15 + 0.95 * self._rp)
            fade = 1.0 - self._rp
            g = QRadialGradient(self._pt, max(1.0, R))
            for at, a in ((0.0, 0.24), (0.7, 0.16), (1.0, 0.0)):
                c = QColor(tint)
                c.setAlphaF(a * fade)
                g.setColorAt(at, c)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(self._pt, R, R)
            ring = QColor(tint)
            ring.setAlphaF(0.35 * fade)
            p.setPen(QPen(ring, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(self._pt, R * 0.92, R * 0.92)
        dy = 1.0 * k
        badge = QRectF(r.left() + 9, r.center().y() - 17 + dy * 0.5, 34, 34)
        if self._bz < 1.0:
            seg = r.width() * 0.38
            x = r.left() - seg + (r.width() + seg) * self._bz
            under = QColor(tint)
            under.setAlphaF(0.12)
            p.fillRect(QRectF(r.left(), r.bottom() - 3, r.width() * self._bz, 3), under)
            lg = QLinearGradient(QPointF(x, 0), QPointF(x + seg, 0))
            c0, c1 = QColor(tint), QColor(tint)
            c0.setAlphaF(0.0)
            lg.setColorAt(0.0, c0)
            lg.setColorAt(0.65, c1)
            lg.setColorAt(1.0, c0)
            p.fillRect(QRectF(x, r.bottom() - 3, seg, 3), QBrush(lg))
            for ph in (0.0, 0.5):
                q = (self._bz * 2 + ph) % 1.0
                pc_ = QColor(tint)
                pc_.setAlphaF(0.45 * (1.0 - q))
                p.setPen(QPen(pc_, 1.5))
                p.setBrush(Qt.NoBrush)
                s = 1 + 7 * q
                p.drawRoundedRect(badge.adjusted(-s, -s, s, s), 9 + s, 9 + s)
        p.restore()
        bc = QColor(tint)
        bc.setAlphaF((0.16 + 0.08 * hv) if on else 0.10)
        p.setPen(Qt.NoPen)
        p.setBrush(bc)
        p.drawRoundedRect(badge, 9, 9)
        sc = 1.0 - 0.08 * k
        p.save()
        p.translate(badge.center())
        p.scale(sc, sc)
        p.drawPixmap(QPointF(-10, -10), pix(self.ico, tn, 20))
        p.restore()
        f1, f2 = self._fonts()
        m1, m2 = QFontMetrics(f1), QFontMetrics(f2)
        tx = badge.right() + 11
        tw = max(10.0, r.right() - 28 - tx)
        th = m1.height() + (m2.height() + 1 if self.sub else 0)
        ty = r.center().y() - th / 2 + dy
        p.setFont(f1)
        p.setPen(QColor(T["text"] if on else T["muted"]))
        p.drawText(QRectF(tx, ty, tw, m1.height()), Qt.AlignLeft | Qt.AlignVCenter, m1.elidedText(self.text(), Qt.ElideRight, int(tw)))
        if self.sub:
            p.setFont(f2)
            p.setPen(QColor(T["muted"]))
            p.drawText(QRectF(tx, ty + m1.height() + 1, tw, m2.height()), Qt.AlignLeft | Qt.AlignVCenter,
                       m2.elidedText(self.sub, Qt.ElideRight, int(tw)))
        p.drawPixmap(QPointF(r.right() - 26 + 2 * hv, r.center().y() - 8 + dy), pix("next", mix(T["muted"], tn, hv) if on else T["border"], 16))
        p.end()


def tile(text, slot=None, sub="", ico="settings", tone="accent", tip=None):
    b = ActionButton(tr(text), tr(sub) if sub else "", ico, tone)
    if tip:
        b.setToolTip(tr(tip))
    if slot:
        b.clicked.connect(lambda _=False: slot())
    b.setCursor(Qt.PointingHandCursor)
    return b


def ibtn(name, tip, slot=None, size=34, boxed=False, color=None, isize=18):
    """Кнопка-иконка без подписи; смысл — во всплывающей подсказке."""
    b = QToolButton()
    b.setIcon(icon(name, color, isize))
    b.setIconSize(QSize(isize, isize))
    b.setFixedSize(size, size)
    b.setToolTip(tr(tip))
    b.setCursor(Qt.PointingHandCursor)
    if boxed:
        b.setProperty("boxed", "true")
    if slot:
        b.clicked.connect(lambda _=False: slot())
    return b


def hbox(*items, spacing=8, margins=(0, 0, 0, 0)):
    l = QHBoxLayout()
    l.setSpacing(spacing)
    l.setContentsMargins(*margins)
    for it in items:
        _add(l, it)
    return l


def vbox(*items, spacing=8, margins=(0, 0, 0, 0)):
    l = QVBoxLayout()
    l.setSpacing(spacing)
    l.setContentsMargins(*margins)
    for it in items:
        _add(l, it)
    return l


def _add(l, it):
    if it is None:
        l.addStretch(1)
    elif isinstance(it, int):
        l.addSpacing(it)
    elif isinstance(it, (QHBoxLayout, QVBoxLayout, QGridLayout)):
        l.addLayout(it)
    else:
        l.addWidget(it)


def shrinkable_combo(c, min_w=110, max_w=200):
    """Список не раздувает панель: ширина не зависит от самого длинного пункта (длинный текст обрезается), не уже min_w."""
    c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    c.setMinimumContentsLength(8)
    c.setMinimumWidth(min_w)
    c.setMaximumWidth(max_w)
    c.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    return c


def row(left, right):
    """Строка «подпись слева — элемент справа»."""
    return hbox(left if not isinstance(left, str) else WrapLabel(tr(left)), None, right)


def help_popup(anchor, text):
    """Подсказка по нажатию на «?»: небольшое окошко под кнопкой, закрывается кликом в сторону."""
    from PySide6.QtWidgets import QWidgetAction
    m = QMenu(anchor)
    lab = QLabel(tr(text))
    lab.setWordWrap(True)
    lab.setMaximumWidth(320)
    lab.setContentsMargins(10, 8, 10, 8)
    a = QWidgetAction(m)
    a.setDefaultWidget(lab)
    m.addAction(a)
    m.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))


def help_btn(text):
    b = QToolButton()
    b.setText("?")
    b.setFixedSize(22, 22)
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip(tr("Подсказка"))
    b.setProperty("boxed", "true")
    b.clicked.connect(lambda _=False: help_popup(b, text))
    return b


def card(title, *items, help=None):
    f = QFrame()
    f.setObjectName("card")
    l = vbox(spacing=9, margins=(13, 12, 13, 12))
    if title:
        l.addWidget(lbl(title, "title")) if not help else l.addLayout(hbox(lbl(title, "title"), None, help_btn(help)))
    for it in items:
        _add(l, it)
    f.setLayout(l)
    return f


def vsep():
    s = QFrame()
    s.setObjectName("sep")
    s.setFixedSize(1, 20)
    return s


class Segmented(QFrame):
    """Переключатель из нескольких вариантов в одной рамке."""
    changed = Signal(object)

    def __init__(self, options, value=None):
        super().__init__()
        self.setObjectName("seg")
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        l = hbox(spacing=2, margins=(3, 3, 3, 3))
        self.values = []
        for i, (text, val) in enumerate(options):
            b = QPushButton(tr(text))
            b.setProperty("kind", "seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.group.addButton(b, i)
            self.values.append(val)
            l.addWidget(b)
        self.setLayout(l)
        self.set(value if value is not None else options[0][1])
        self.group.idClicked.connect(lambda i: self.changed.emit(self.values[i]))

    def set(self, value):
        if value in self.values:
            self.group.button(self.values.index(value)).setChecked(True)

    def value(self):
        i = self.group.checkedId()
        return self.values[i] if i >= 0 else None

    def clear(self):
        """Снимает выбор со всех кнопок (для двух рядов вкладок, где активна одна кнопка из обоих рядов)."""
        self.group.setExclusive(False)
        for b in self.group.buttons():
            b.setChecked(False)
        self.group.setExclusive(True)


class PageStack(QWidget):
    """Как QStackedWidget, но высота равна высоте только видимой страницы (у обычного — самой высокой из всех)."""
    currentChanged = Signal(int)

    def __init__(self):
        super().__init__()
        self._lay = vbox()
        self.setLayout(self._lay)
        self._pages, self._cur = [], -1

    def addWidget(self, w):
        self._pages.append(w)
        self._lay.addWidget(w)
        w.setVisible(not self._pages[:-1])
        if len(self._pages) == 1:
            self._cur = 0

    def count(self):
        return len(self._pages)

    def widget(self, i):
        return self._pages[i]

    def currentIndex(self):
        return self._cur

    def setCurrentIndex(self, i):
        for k, w in enumerate(self._pages):
            w.setVisible(k == i)
        self._cur = i
        self.updateGeometry()
        self.currentChanged.emit(i)


class Switch(QAbstractButton):
    """Выключатель с плавным ходом бегунка."""

    def __init__(self, on=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(bool(on))
        self.setFixedSize(36, 20)
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 1.0 if on else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(130)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self.toggled.connect(self._run)

    def _run(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def set(self, on):
        """Меняет положение без сигнала и без анимации."""
        self.blockSignals(True)
        self.setChecked(bool(on))
        self.blockSignals(False)
        self._pos = 1.0 if on else 0.0
        self.update()

    def getKnob(self):
        return self._pos

    def setKnob(self, v):
        self._pos = float(v)
        self.update()

    knob = Property(float, getKnob, setKnob)        # не «pos»: так уже называется положение виджета

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(mix(T["hover"], T["accent"], self._pos)))
        p.drawRoundedRect(QRectF(0, 0, 36, 20), 10, 10)
        p.setBrush(QColor(mix("#ffffff", T["accent_text"], self._pos)))
        p.drawEllipse(QRectF(3 + 16 * self._pos, 3, 14, 14))
        p.end()


def pil_to_qimage(im):
    im = im.convert("RGB")
    data = im.tobytes("raw", "RGB")
    return QImage(data, im.width, im.height, im.width * 3, QImage.Format_RGB888).copy()


def ask(parent, text, title="PhotoCrop"):
    if ga.CTX["active"]:                                       # команда агента: диалог не показываем, отвечаем «да» и сообщаем в notes
        ga.CTX["notes"].append(tr(text))
        return True
    return QMessageBox.question(parent, title, tr(text), QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes


SOFT = [False]        # переключатель в настройках: спрашивать ли подтверждение у обычных действий


def ask_soft(parent, text, title="PhotoCrop"):
    """Подтверждение действия, которое можно отменить (Ctrl+Z) или повторить: по умолчанию не спрашивает."""
    return True if not SOFT[0] else ask(parent, text, title)


def info(parent, text, title="PhotoCrop"):
    if ga.CTX["active"]:
        ga.CTX["notes"].append(tr(text))
        return
    QMessageBox.information(parent, title, tr(text))


def warn(parent, text, title="PhotoCrop"):
    if ga.CTX["active"]:
        ga.CTX["notes"].append(tr(text))
        return
    QMessageBox.warning(parent, title, tr(text))


# ---------------------------------------------------------------- миниатюры (в фоне)

class _ThumbSignals(QObject):
    done = Signal(str, int, int, QImage)


class ThumbJob(QRunnable):
    def __init__(self, sig, path, rotation, size):
        super().__init__()
        self.sig, self.path, self.rotation, self.img_size = sig, path, rotation, size

    def run(self):
        try:
            with pc.Image.open(self.path) as im0:
                im0.draft("RGB", (self.img_size * 2, self.img_size * 2))
                icc = im0.info.get("icc_profile")
                im = pc.ImageOps.exif_transpose(im0)
                if self.rotation:
                    im = pc.orient_img(im, self.rotation)
                im = pc.to_rgb(im, icc)
                im = pc.ImageOps.fit(im, (self.img_size, self.img_size), pc.RESAMPLE_FAST)
            img = pil_to_qimage(im)
        except Exception:
            img = QImage()
        try:
            self.sig.done.emit(self.path, self.rotation, self.img_size, img)
        except RuntimeError:
            pass


class ThumbCache(QObject):
    """Квадратные миниатюры: готовые лежат в памяти, недостающие считаются в фоновых потоках."""
    ready = Signal()

    def __init__(self):
        super().__init__()
        self.pm, self.pending = {}, set()
        self.sig = _ThumbSignals()
        self.sig.done.connect(self._done)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max(2, min(4, (os.cpu_count() or 4) - 1)))

    def get(self, path, rotation=0, size=160):
        key = (str(path), int(rotation), size)
        pm = self.pm.get(key)
        if pm is None and key not in self.pending:
            self.pending.add(key)
            self.pool.start(ThumbJob(self.sig, key[0], key[1], size))
        return pm

    def _done(self, path, rotation, size, img):
        key = (path, rotation, size)
        self.pending.discard(key)
        if len(self.pm) > 1500:
            self.pm.clear()
        self.pm[key] = QPixmap.fromImage(img) if not img.isNull() else QPixmap()
        self.ready.emit()


# ---------------------------------------------------------------- левая колонка: плитки фото

TILE_W, TILE_H = 118, 142


class ThumbModel(QAbstractListModel):
    def __init__(self, app):
        super().__init__()
        self.app = app

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.app.files)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.ToolTipRole and index.isValid() and index.row() < len(self.app.files):
            return self.app.files[index.row()].name
        return None

    def refresh(self):
        self.beginResetModel()
        self.endResetModel()
        if hasattr(self.app, "smart_filter"):
            self.app.smart_filter()

    def touch(self, i):
        if 0 <= i < len(self.app.files):
            ix = self.index(i, 0)
            self.dataChanged.emit(ix, ix)


class ThumbDelegate(QStyledItemDelegate):
    def __init__(self, app):
        super().__init__()
        self.app = app

    def sizeHint(self, option, index):
        return QSize(TILE_W, TILE_H)

    def paint(self, p, option, index):
        app, i = self.app, index.row()
        if i >= len(app.files):
            return
        f = app.files[i]
        st = app.states.get(f)
        cur, chk = (i == app.idx), (f in app.checked)
        r = QRectF(option.rect).adjusted(1.5, 1.5, -1.5, -1.5)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        light = app.smart_light(f)
        tint = {"red": 0.58, "orange": 0.40, "green": 0.20}.get(light, 0.0)       # красный фон у кадров, которые надо исправить
        p.setPen(QPen(QColor(T["select"]), 2.5) if cur else (QPen(QColor(sm_light_color(light)), 1.6) if tint else Qt.NoPen))
        p.setBrush(QColor(mix(T["surface"], sm_light_color(light), tint)) if tint else QColor(T["surface"]))
        p.drawRoundedRect(r, 11, 11)
        side = r.width() - 10
        img = QRectF(r.x() + 5, r.y() + 5, side, side)
        clip = QPainterPath()
        clip.addRoundedRect(img, 7, 7)
        p.setClipPath(clip)
        pm = app.thumbs.get(f, st.rotation if st else 0)
        if pm is not None and not pm.isNull():
            p.setOpacity(1.0 if chk else 0.38)
            p.drawPixmap(img, pm, QRectF(pm.rect()))
            p.setOpacity(1.0)
        else:
            p.fillRect(img, QColor(T["raised"]))
        p.setClipping(False)
        c = QRectF(img.x() + 5, img.y() + 5, 22, 22)                 # кружок отметки
        if chk:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T["accent"]))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 220), 1.5))
            p.setBrush(QColor(0, 0, 0, 115))
        p.drawEllipse(c)
        p.drawPixmap(QRectF(c.x() + 4.5, c.y() + 4.5, 13, 13),
                     pix("check" if chk else "plus", T["accent_text"] if chk else "#ffffff", 13, 2.6), QRectF(0, 0, 39, 39))
        mk = app.smart_marker(f)
        if mk:                                                       # маркер умной рамки: цвет = вердикт
            s_, seen, smp = mk
            col = sm_light_color(light)
            glyph = {"check": "!", "manual": "!", "hand": "✎", "stale": "↻"}.get(s_, "")
            if seen and s_ in ("check", "manual"):
                col, glyph = T["ok"], "✓"
            elif s_ == "hand":
                glyph = "✎"
            if smp and s_ == "ok":
                col, glyph = T["select"], "?"
            dm = 17 if glyph else 9
            mx, my = img.x() + 6, img.bottom() - dm - 6
            p.setPen(QPen(QColor(0, 0, 0, 150), 1))
            p.setBrush(QColor(col))
            p.drawEllipse(QRectF(mx, my, dm, dm))
            if glyph:
                gf = QFont(p.font())
                gf.setPixelSize(11)
                gf.setBold(True)
                p.setFont(gf)
                p.setPen(QColor("#111111"))
                p.drawText(QRectF(mx, my, dm, dm), Qt.AlignCenter, glyph)
        badge = ""
        if st is not None:
            badge = ("×%d" % st.copies) if st.copies > 1 else ""
            marks = [m for m, on in (("кадр", st.edited and not st.adj), ("цвет", bool(st.adj))) if on]
            if st.adj:
                badge = ("◐ " + badge).strip()
            elif marks and not badge:
                badge = "✎"
        if badge:
            fnt = QFont(p.font())
            fnt.setPixelSize(11)
            fnt.setBold(True)
            p.setFont(fnt)
            w = QFontMetrics(fnt).horizontalAdvance(badge) + 12
            b = QRectF(img.right() - w - 5, img.y() + 6, w, 19)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 160))
            p.drawRoundedRect(b, 6, 6)
            p.setPen(QColor("#ffffff"))
            p.drawText(b, Qt.AlignCenter, badge)
        fnt = QFont(p.font())
        fnt.setPixelSize(11)
        fnt.setBold(False)
        p.setFont(fnt)
        p.setPen(QColor(T["text"] if cur else T["muted"]))
        tr_ = QRectF(r.x() + 7, img.bottom() + 3, r.width() - 14, r.bottom() - img.bottom() - 5)
        p.drawText(tr_, Qt.AlignVCenter | Qt.AlignLeft, QFontMetrics(fnt).elidedText(f.name, Qt.ElideMiddle, int(tr_.width())))
        p.restore()


class ThumbView(QListView):
    """Сетка плиток. Щелчок по кружку — отметка, по самой плитке — открыть фото в рабочем поле."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setSpacing(4)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedWidth(2 * TILE_W + 3 * 8 + 12)
        self._model, self._delegate = ThumbModel(app), ThumbDelegate(app)   # ссылки держим сами: Qt ими не владеет
        self.setModel(self._model)
        self.setItemDelegate(self._delegate)
        self.verticalScrollBar().setSingleStep(24)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            pos = e.position().toPoint()
            ix = self.indexAt(pos)
            if ix.isValid():
                r = self.visualRect(ix)
                if pos.x() - r.x() < 38 and pos.y() - r.y() < 38:
                    self.app.toggle_check(ix.row(), bool(e.modifiers() & Qt.ShiftModifier))
                else:
                    self.app.on_tile(ix.row())
                return
        super().mouseReleaseEvent(e)

    def see(self, i):
        if 0 <= i < len(self.app.files):
            self.scrollTo(self.model().index(i, 0), QAbstractItemView.EnsureVisible)


# ---------------------------------------------------------------- рабочее поле: фото и рамка кадра

class CropCanvas(QWidget):
    HANDLE = 10
    ROT_OFFSET = 30
    CORNERS = ("nw", "ne", "se", "sw")
    PILL_ZONE = 58                       # место внизу под плавающую панель инструментов

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.geom = None                 # (ox, oy, k, P, rh) — как фото лежит на экране
        self.drag = None
        self.guides = []
        self.pill = None
        self.pbtn = None                 # кнопка «Печать фото» в верхнем углу
        self.cbtn = None                 # кнопка «До / После» левее неё
        self.cmp = False                 # режим сравнения: слева от линии снимок без правок, справа — с правками
        self.cmp_x = 0.5                 # положение линии: доля ширины снимка
        self.cmp_drag = False
        self.img_rect = None             # где снимок лежит на экране (x, y, w, h)
        self.pick = None                 # режим пипетки: функция (доля x, доля y), вызывается по следующему щелчку
        self._orig_key = None
        self._orig_pm = None
        self._pb_pending = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setMinimumSize(440, 340)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # ---- рисование
    @staticmethod
    def _lerp(a, b, t):
        return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t

    def _edge_pts(self, P):
        L = self._lerp
        return {"n": L(P[0], P[1], .5), "e": L(P[1], P[2], .5), "s": L(P[2], P[3], .5), "w": L(P[3], P[0], .5)}

    def resizeEvent(self, e):
        self.place_pill()

    def place_pill(self):
        if self.pill is not None:
            groups = getattr(self, "pill_groups", [])
            for g in groups:
                for w_ in g:
                    w_.setVisible(True)
            self.pill.adjustSize()
            for idx in (2, 4, 5):                             # узкое окно: сначала прячем наклон рамки, потом «цвет/сброс», потом отмену
                if self.pill.sizeHint().width() <= self.width() - 20 or idx >= len(groups):
                    break
                for w_ in groups[idx]:
                    w_.setVisible(False)
                self.pill.layout().activate()
                self.pill.adjustSize()
            self.pill.move(int((self.width() - self.pill.width()) / 2), self.height() - self.pill.height() - 14)
        self.place_pbtn()

    def place_pbtn(self):
        """Кнопка «Печать фото» — в правом верхнем углу; видна, когда открыто фото; ниже цветной полосы статуса умной рамки."""
        b = self.pbtn
        if b is None:
            return
        app = self.app
        cur = app.cur()
        b.adjustSize()
        y = 12 + (34 if (cur and app.mode() != "fit" and app.smart_banner_shown(cur[0])) else 0)
        x = max(8, self.width() - b.width() - 12)
        if b.x() != x or b.y() != y:
            b.move(x, y)
        b.setEnabled(not (app.saving or app.printing))
        show = bool(cur)
        if b.isVisible() != show:
            b.setVisible(show)
        if show:
            b.raise_()
        c = self.cbtn
        if c is not None:
            c.adjustSize()
            cx = max(8, b.x() - c.width() - 8)
            if c.x() != cx or c.y() != y:
                c.move(cx, y)
            c.setEnabled(b.isEnabled())
            if c.isVisible() != show:
                c.setVisible(show)
            if show:
                c.raise_()

    # ---- сравнение «до / после»
    def set_compare(self, on):
        self.cmp = bool(on)
        self.cmp_drag = False
        self.setCursor(Qt.SplitHCursor if self.cmp else Qt.ArrowCursor)
        self.update()

    def _orig_pixmap(self):
        raw = self.app.raw
        if raw is None:
            return None
        if self._orig_key is not id(raw):
            self._orig_key = id(raw)
            self._orig_pm = QPixmap.fromImage(pil_to_qimage(raw))
        return self._orig_pm

    def _cmp_under(self, p, rect):
        """Левая от линии часть снимка — без правок (рисуется поверх снимка с правками)."""
        self.img_rect = rect
        if not self.cmp:
            return
        pm = self._orig_pixmap()
        if pm is None:
            return
        x, y, w, h = rect
        sx = x + w * self.cmp_x
        p.save()
        p.setClipRect(QRectF(x, y, sx - x, h), Qt.IntersectClip)
        p.drawPixmap(QRectF(x, y, w, h), pm, QRectF(pm.rect()))
        p.restore()

    def _cmp_over(self, p):
        """Линия-разделитель, ручка и подписи «До» / «После»."""
        if not self.cmp or not self.img_rect:
            return
        x, y, w, h = self.img_rect
        sx = x + w * self.cmp_x
        p.save()
        p.setPen(QPen(QColor(0, 0, 0, 140), 4))
        p.drawLine(QPointF(sx, y), QPointF(sx, y + h))
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawLine(QPointF(sx, y), QPointF(sx, y + h))
        cy = y + h / 2
        p.setPen(QPen(QColor(0, 0, 0, 160), 1))
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QPointF(sx, cy), 14, 14)
        p.setPen(QPen(QColor("#222222"), 2))
        for d in (-1, 1):
            p.drawLine(QPointF(sx + d * 9, cy), QPointF(sx + d * 4, cy - 5))
            p.drawLine(QPointF(sx + d * 9, cy), QPointF(sx + d * 4, cy + 5))
        fnt = QFont(p.font())
        fnt.setPixelSize(12)
        fnt.setBold(True)
        p.setFont(fnt)
        for text, tx, al in ((tr("До"), x + 8, Qt.AlignLeft), (tr("После"), x + w - 78, Qt.AlignRight)):
            r = QRectF(tx, y + 8, 70, 22)
            if (al == Qt.AlignLeft and tx + 30 < sx) or (al == Qt.AlignRight and tx + 30 > sx):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 150))
                p.drawRoundedRect(r, 6, 6)
                p.setPen(QColor("#ffffff"))
                p.drawText(r, Qt.AlignCenter, text)
        p.restore()

    def _cmp_mouse(self, e, kind):
        if not self.img_rect:
            return
        x, y, w, h = self.img_rect
        if kind == "press" and e.button() == Qt.LeftButton:
            self.cmp_drag = True
        if kind == "release":
            self.cmp_drag = False
            return
        if self.cmp_drag:
            self.cmp_x = min(1.0, max(0.0, (e.position().x() - x) / max(1.0, w)))
            self.update()

    def paintEvent(self, e):
        self._paint(e)
        if self.pbtn is not None and not self._pb_pending:       # положение кнопки уточняем после отрисовки, а не внутри неё
            self._pb_pending = True
            QTimer.singleShot(0, self._pb_later)

    def _pb_later(self):
        self._pb_pending = False
        self.place_pbtn()

    def _paint(self, e):
        app = self.app
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        cw, ch = self.width(), self.height()
        bg = QPainterPath()
        bg.addRoundedRect(QRectF(0, 0, cw, ch), 14, 14)
        p.fillPath(bg, QColor(T["canvas"]))
        p.setClipPath(bg)
        cur = app.cur()
        if not cur or app.preview_pm is None:
            self.geom = None
            self.img_rect = None
            fnt = QFont(p.font())
            fnt.setPixelSize(15)
            p.setFont(fnt)
            p.setPen(QColor(T["muted"]))
            msg = (tr("Ни одно фото не отмечено.\nОтметьте «+» на превью слева — фото появится здесь.") if app.files
                   else tr("Нажмите «Открыть» и выберите фото или папку"))
            p.drawText(QRectF(0, 0, cw, ch - self.PILL_ZONE), Qt.AlignCenter, msg)
            p.end()
            return
        f, st, W, H, paper = cur
        pm = app.preview_pm
        uh = ch - self.PILL_ZONE
        if app.mode() == "fit":
            pad = 18
            k = min((cw - 2 * pad) / paper[0], (uh - 2 * pad) / paper[1])
            PW, PH = paper[0] * k, paper[1] * k
            px, py = (cw - PW) / 2, (uh - PH) / 2
            p.fillRect(QRectF(px + 5, py + 6, PW, PH), QColor(0, 0, 0, 70))
            p.fillRect(QRectF(px, py, PW, PH), QColor("#ffffff"))
            kk = min(PW / W, PH / H)
            dw, dh = W * kk, H * kk
            p.drawPixmap(QRectF(px + (PW - dw) / 2, py + (PH - dh) / 2, dw, dh), pm, QRectF(pm.rect()))
            self._cmp_under(p, (px + (PW - dw) / 2, py + (PH - dh) / 2, dw, dh))
            self._bleed(p, [(px, py), (px + PW, py), (px + PW, py + PH), (px, py + PH)], paper[0], paper[0] > paper[1] + 1e-6)
            self.geom = None
            self._cmp_over(p)
            p.end()
            return
        padx, pad_top, pad_bot = 20, self.ROT_OFFSET + 14, 18       # поля минимальные: сверху — место под ручку поворота
        k = min((cw - 2 * padx) / W, (uh - pad_top - pad_bot) / H)
        dw, dh = max(1.0, W * k), max(1.0, H * k)
        ox, oy = (cw - dw) / 2, pad_top + (uh - pad_top - pad_bot - dh) / 2
        g = pc.frame_geom(W, H, paper, st)
        P = [(ox + x * k, oy + y * k) for x, y in pc.frame_corners(*g)]
        poly = QPolygonF([QPointF(x, y) for x, y in P])
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawPolygon(poly)                                           # «бумага»: видна там, где рамка вышла за фото
        p.drawPixmap(QRectF(ox, oy, dw, dh), pm, QRectF(pm.rect()))
        self._cmp_under(p, (ox, oy, dw, dh))
        shade = QPainterPath()
        shade.setFillRule(Qt.OddEvenFill)
        shade.addRect(QRectF(0, 0, cw, ch))
        shade.addPolygon(poly)
        shade.closeSubpath()
        p.fillPath(shade, QColor(0, 0, 0, 150))
        if app.s["grid"]:
            p.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.DashLine))
            L = self._lerp
            for t_ in (1 / 3, 2 / 3):
                a1, b1 = L(P[0], P[1], t_), L(P[3], P[2], t_)
                a2, b2 = L(P[0], P[3], t_), L(P[1], P[2], t_)
                p.drawLine(QPointF(*a1), QPointF(*b1))
                p.drawLine(QPointF(*a2), QPointF(*b2))
        app.smart_overlay(p, ox, oy, k, W, H, f)
        self._bleed(p, P, paper[0], paper[0] > paper[1] + 1e-6)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(T["frame"]), 2))
        p.drawPolygon(poly)
        p.setPen(QPen(QColor(T["select"]), 1, Qt.DashLine))
        for gk, gv in self.guides:                                    # линии прилипания
            if gk == "v":
                p.drawLine(QPointF(ox + gv * k, oy), QPointF(ox + gv * k, oy + dh))
            else:
                p.drawLine(QPointF(ox, oy + gv * k), QPointF(ox + dw, oy + gv * k))
        top = self._lerp(P[0], P[1], 0.5)
        a = math.radians(st.angle)
        rh = (top[0] + self.ROT_OFFSET * math.sin(a), top[1] - self.ROT_OFFSET * math.cos(a))
        p.setPen(QPen(QColor(T["frame"]), 2))
        p.drawLine(QPointF(*top), QPointF(*rh))
        p.setPen(QPen(QColor(0, 0, 0, 200), 1.2))
        p.setBrush(QColor(T["frame"]))
        p.drawEllipse(QPointF(*rh), 7, 7)
        for hx, hy in self._edge_pts(P).values():
            p.drawRoundedRect(QRectF(hx - 4, hy - 4, 8, 8), 2, 2)
        p.setBrush(QColor("#ffffff"))
        for hx, hy in P:
            p.drawRoundedRect(QRectF(hx - 5.5, hy - 5.5, 11, 11), 3, 3)
        self.geom = (ox, oy, k, P, rh)
        self._cmp_over(p)
        app.smart_banner(p, cw, f)
        p.end()

    def _bleed(self, p, P, paper_w_mm, rot=False):
        """Серая шкала подрезки вокруг рамки: полоса снаружи — запас за краем листа (+), внутри — отступ (−).
        Значения заданы для листа, который принтер всегда печатает вертикально: у лежащего боком (альбомного) кадра
        они поворачиваются вместе с ним, как при печати (sheet_plan): левый край кадра = низ листа, верхний = лево, и т. д."""
        sides = self.app.bleed_mm()
        if not any(abs(v) > 1e-9 for v in sides):
            return
        names = ("Л", "В", "П", "Н")
        if rot:
            sl, sT, sr, sb = sides
            sides, names = (sb, sl, sT, sr), ("Н", "Л", "В", "П")
        ux, uy = P[1][0] - P[0][0], P[1][1] - P[0][1]
        L = math.hypot(ux, uy) or 1.0
        ux, uy = ux / L, uy / L
        vx, vy = P[3][0] - P[0][0], P[3][1] - P[0][1]
        Hh = math.hypot(vx, vy) or 1.0
        vx, vy = vx / Hh, vy / Hh
        mm = L / max(1e-6, paper_w_mm)
        edges = ((P[3], P[0], (-ux, -uy)), (P[0], P[1], (-vx, -vy)), (P[1], P[2], (ux, uy)), (P[2], P[3], (vx, vy)))
        fnt = QFont(p.font())
        fnt.setPixelSize(10)
        fnt.setBold(True)
        p.setFont(fnt)
        for (a, b, n), v, nm in zip(edges, sides, names):
            if abs(v) < 1e-9:
                continue
            d = max(2.0, abs(v) * mm) * (1 if v > 0 else -1)
            a2 = (a[0] + n[0] * d, a[1] + n[1] * d)
            b2 = (b[0] + n[0] * d, b[1] + n[1] * d)
            p.setPen(QPen(QColor(210, 210, 210, 200), 1))
            p.setBrush(QColor(150, 150, 150, 215 if v > 0 else 130))
            p.drawPolygon(QPolygonF([QPointF(*a), QPointF(*b), QPointF(*b2), QPointF(*a2)]))
            mid = QPointF((a[0] + b[0] + a2[0] + b2[0]) / 4, (a[1] + b[1] + a2[1] + b2[1]) / 4)
            p.setPen(QColor("#ffffff"))
            p.drawText(QRectF(mid.x() - 30, mid.y() - 8, 60, 16), Qt.AlignCenter, "%s %+g" % (nm, v))

    # ---- мышь
    def _to_img(self, ex, ey):
        ox, oy, k, _, _ = self.geom
        return (ex - ox) / k, (ey - oy) / k

    def _corner_at(self, ex, ey):
        for name, (hx, hy) in zip(self.CORNERS, self.geom[3]):
            if abs(ex - hx) <= self.HANDLE and abs(ey - hy) <= self.HANDLE:
                return name
        return None

    def _edge_at(self, ex, ey):
        for name, (hx, hy) in self._edge_pts(self.geom[3]).items():
            if abs(ex - hx) <= self.HANDLE and abs(ey - hy) <= self.HANDLE:
                return name
        return None

    def _rot_at(self, ex, ey):
        rx, ry = self.geom[4]
        return (ex - rx) ** 2 + (ey - ry) ** 2 <= 12 ** 2

    def mousePressEvent(self, e):
        if self.pick is not None:                             # пипетка: щелчок по фото берёт эталон белого
            cur = self.app.cur()
            if cur and self.geom and e.button() == Qt.LeftButton:
                _f, _st, W, H, _paper = cur
                ix, iy = self._to_img(e.position().x(), e.position().y())
                fn, self.pick = self.pick, None
                self.unsetCursor()
                if 0 <= ix <= W and 0 <= iy <= H:
                    fn(ix / W, iy / H)
            elif e.button() != Qt.LeftButton:
                self.pick = None
                self.unsetCursor()
            return
        if self.cmp:                                          # режим «до / после»: рамку не двигаем, тянем линию
            self._cmp_mouse(e, "press")
            return
        if e.button() != Qt.LeftButton:
            return
        self.setFocus()
        app = self.app
        cur = app.cur()
        if not cur or not self.geom:
            return
        f, st, W, H, paper = cur
        ex, ey = e.position().x(), e.position().y()
        g = pc.frame_geom(W, H, paper, st)
        ix, iy = self._to_img(ex, ey)
        handle = self._rot_at(ex, ey) or self._corner_at(ex, ey) or self._edge_at(ex, ey)
        if not handle and not pc.point_in_frame(g, ix, iy):
            return                                           # клик мимо рамки её не двигает
        app.push_undo([f])
        if self._rot_at(ex, ey):
            self.drag = ("rotate",)
        elif self._corner_at(ex, ey):
            self.drag = ("corner",)
        elif self._edge_at(ex, ey):
            edge = self._edge_at(ex, ey)
            cx, cy, w, h, ang = g
            sx, sy = {"n": (0, -1), "e": (1, 0), "s": (0, 1), "w": (-1, 0)}[edge]
            dx, dy = pc.rot(-sx * w / 2 if sx else 0, -sy * h / 2 if sy else 0, ang)
            self.drag = ("edge", edge, cx + dx, cy + dy)
        else:
            self.drag = ("move", ix - st.cx * W, iy - st.cy * H)
        app.mark(f)
        app.redraw()

    def mouseMoveEvent(self, e):
        if self.cmp:
            self._cmp_mouse(e, "move")
            return
        ex, ey = e.position().x(), e.position().y()
        app = self.app
        cur = app.cur()
        if not cur or not self.geom:
            return
        f, st, W, H, paper = cur
        if not self.drag:
            self._hover(ex, ey, cur)
            return
        ix, iy = self._to_img(ex, ey)
        kind = self.drag[0]
        self.guides = []
        mods = e.modifiers()
        snap_on = app.s["snap"] and not (mods & Qt.ControlModifier)
        thr = float(app.settings.get("snap_px", 10)) / max(1e-6, self.geom[2])
        r = paper[0] / paper[1]
        if kind == "move":
            _, dx, dy = self.drag
            st.cx, st.cy = (ix - dx) / W, (iy - dy) / H
            if snap_on:
                sx, sy, self.guides = pc.snap_move(W, H, pc.frame_geom(W, H, paper, st), thr)
                st.cx += sx / W
                st.cy += sy / H
        elif kind == "rotate":
            st.angle = pc.angle_from_mouse(st.cx * W, st.cy * H, ix, iy, 15 if (mods & Qt.ShiftModifier) else None)
        elif kind == "corner":
            st.scale = pc.frame_resize_center((st.cx * W, st.cy * H), (ix, iy), st.angle, r, min(W, H * r))
            if snap_on and abs(st.scale - 1.0) * min(W, H * r) <= thr:
                st.scale = 1.0
        else:
            _, edge, ax, ay = self.drag
            cx, cy, sc = pc.frame_resize_edge((ax, ay), edge, (ix, iy), st.angle, r, min(W, H * r))
            st.cx, st.cy, st.scale = cx / W, cy / H, sc
        pc.normalize(st)
        app.redraw()

    def mouseReleaseEvent(self, e):
        if self.cmp:
            self._cmp_mouse(e, "release")
            return
        if self.guides:
            self.guides = []
            self.update()
        if self.drag and self.app.idx >= 0:
            self.app.undo_trim(self.app.files[self.app.idx])
            self.app.thumbs_view.model().touch(self.app.idx)
        self.drag = None

    def mouseDoubleClickEvent(self, e):
        self.app.reset_frame()

    def _hover(self, ex, ey, cur):
        f, st, W, H, paper = cur
        corner = self._corner_at(ex, ey)
        if self._rot_at(ex, ey):
            self.setCursor(Qt.PointingHandCursor)
        elif corner:
            self.setCursor(Qt.SizeFDiagCursor if corner in ("nw", "se") else Qt.SizeBDiagCursor)
        elif self._edge_at(ex, ey):
            self.setCursor(Qt.SizeHorCursor if self._edge_at(ex, ey) in ("e", "w") else Qt.SizeVerCursor)
        else:
            ix, iy = self._to_img(ex, ey)
            self.setCursor(Qt.SizeAllCursor if pc.point_in_frame(pc.frame_geom(W, H, paper, st), ix, iy) else Qt.CrossCursor)

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if not d:
            return
        if e.modifiers() & Qt.ShiftModifier:
            self.app.tilt(1 if d > 0 else -1)
        else:
            self.app.zoom(pc.WHEEL_STEP ** max(-5.0, min(5.0, d / 120.0)))


class Histogram(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(74)
        self.h = None

    def set(self, h):
        self.h = h
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(QColor(T["border"]), 1))
        p.setBrush(QColor(T["canvas"]))
        p.drawRoundedRect(r, 8, 8)
        if self.h:
            h = self.h
            cap = sorted(h[i * 256 + j] for i in range(3) for j in range(2, 254))[-12] or 1
            w, hh = self.width() - 8, self.height() - 8
            for ch, col in ((0, "#ff5a5a"), (1, "#4fd06a"), (2, "#5a8cff")):
                path = QPainterPath()
                for j in range(256):
                    x, y = 4 + j * w / 255.0, 4 + hh - min(1.0, h[ch * 256 + j] / cap) * hh
                    path.lineTo(x, y) if j else path.moveTo(x, y)
                p.setPen(QPen(QColor(col), 1.2))
                p.setBrush(Qt.NoBrush)
                p.drawPath(path)
        p.end()


# ---------------------------------------------------------------- уровни, кривые и выборочный цвет (вкладка «Цвет»)

CH_NAMES = (("RGB", "rgb"), ("R", "r"), ("G", "g"), ("B", "b"))
CH_COLORS = {"rgb": "#d6d8dd", "r": "#ff5a5a", "g": "#4fd06a", "b": "#5a8cff"}


def hist_channel(h, ch):
    """256 значений гистограммы канала ("rgb" — сумма трёх) из 768-значной pc.hist_rgb."""
    if not h:
        return None
    if ch == "rgb":
        return [h[i] + h[256 + i] + h[512 + i] for i in range(256)]
    k = {"r": 0, "g": 1, "b": 2}[ch]
    return list(h[k * 256:(k + 1) * 256])


def paint_hist_fill(p, rect, hv, color):
    """Залитая гистограмма в прямоугольнике rect; «пики» чёрного и белого отсекаются, чтобы не прижимать остальное."""
    if not hv:
        return
    cap = sorted(hv[2:254])[-6] or 1
    path = QPainterPath()
    path.moveTo(rect.left(), rect.bottom())
    for j in range(256):
        path.lineTo(rect.left() + j * rect.width() / 255.0, rect.bottom() - min(1.0, hv[j] / cap) * rect.height())
    path.lineTo(rect.right(), rect.bottom())
    path.closeSubpath()
    c = QColor(color)
    c.setAlpha(110)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawPath(path)


class ChannelBar(Segmented):
    """Выбор канала RGB / R / G / B."""

    def __init__(self):
        super().__init__([(n, c) for n, c in CH_NAMES], "rgb")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        for b, (_, c) in zip(self.group.buttons(), CH_NAMES):
            b.setToolTip(tr({"rgb": "Все каналы сразу", "r": "Красный канал", "g": "Зелёный канал", "b": "Синий канал"}[c]))


class _LevelsCanvas(QWidget):
    """Гистограмма с тремя бегунками: чёрная точка, гамма (середина), белая точка."""

    def __init__(self, ed):
        super().__init__()
        self.ed, self.drag = ed, None
        self.setFixedHeight(132)
        self.setMouseTracking(True)

    def _plot(self):
        return QRectF(10, 6, self.width() - 20, self.height() - 34)

    def _marks(self):
        b, g, w = self.ed.row()[:3]
        r = self._plot()
        xb, xw = r.left() + b / 255.0 * r.width(), r.left() + w / 255.0 * r.width()
        return {"b": xb, "g": xb + (xw - xb) * 0.5 ** g, "w": xw}

    def _pick(self, x):
        m = self._marks()
        best = min(m, key=lambda k: abs(m[k] - x))
        return best if abs(m[best] - x) <= 12 else None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.drag = self._pick(e.position().x())

    def mouseMoveEvent(self, e):
        if self.drag is None:
            self.setCursor(Qt.SizeHorCursor if self._pick(e.position().x()) else Qt.ArrowCursor)
            return
        r = self._plot()
        v = min(255.0, max(0.0, (e.position().x() - r.left()) / r.width() * 255.0))
        self.ed.drag_to(self.drag, v)

    def mouseReleaseEvent(self, e):
        self.drag = None

    def mouseDoubleClickEvent(self, e):
        k = self._pick(e.position().x())
        if k:
            self.ed.reset_mark(k)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._plot()
        p.setPen(QPen(QColor(T["border"]), 1))
        p.setBrush(QColor(T["canvas"]))
        p.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 6, 6)
        ch = self.ed.channel()
        paint_hist_fill(p, r, hist_channel(self.ed.hist, ch), CH_COLORS[ch])
        for k, x in self._marks().items():
            y = r.bottom() + 8
            tri = QPolygonF([QPointF(x, y), QPointF(x - 7, y + 14), QPointF(x + 7, y + 14)])
            p.setPen(QPen(QColor(T["border"]), 1))
            p.setBrush(QColor({"b": "#000000", "g": "#9a9a9a", "w": "#ffffff"}[k]))
            p.drawPolygon(tri)
        p.end()


class LevelsEditor(QWidget):
    """Уровни: канал, гистограмма с бегунками, числа входа/выхода, «Авто» и «Сбросить»."""
    changed = Signal(object)
    auto_requested = Signal()

    def __init__(self):
        super().__init__()
        self.rows = [list(ct.LEVELS_NEUTRAL) for _ in range(4)]
        self.hist = None
        self.bar = ChannelBar()
        self.bar.changed.connect(lambda _c: self._refresh())
        self.canvas = _LevelsCanvas(self)
        self.f = []
        for i, tip in enumerate(("Чёрная точка (вход)", "Гамма (середина)", "Белая точка (вход)", "Выход: чёрный", "Выход: белый")):
            e = QLineEdit()
            e.setAlignment(Qt.AlignCenter)
            e.setToolTip(tr(tip))
            e.editingFinished.connect(lambda i=i: self._typed(i))
            self.f.append(e)
        self.f[0].setMinimumWidth(40)
        grid = QGridLayout()
        grid.setSpacing(4)
        for c, t in enumerate(("Вход: чёрный", "гамма", "белый")):
            grid.addWidget(lbl(t, "muted"), 0, c)
            grid.addWidget(self.f[c], 1, c)
        grid.addWidget(lbl("Выход: чёрный", "muted"), 2, 0)
        grid.addWidget(lbl("белый", "muted"), 2, 2)
        grid.addWidget(self.f[3], 3, 0)
        grid.addWidget(self.f[4], 3, 2)
        self.setLayout(vbox(hbox(self.bar, None), self.canvas, grid,
                            hbox(btn("Авто", lambda: self.auto_requested.emit(), ico="sparkle"),
                                 btn("Сбросить", self.reset_all, "link"), None),
                            hint("Двойной щелчок по бегунку — сбросить его."), spacing=8))
        self._refresh()

    def channel(self):
        return self.bar.value()

    def row(self):
        return self.rows[ct.CHANNELS.index(self.channel())]

    def set_value(self, levels):
        self.rows = [list(r) for r in ct.levels_full(levels)]
        self._refresh()

    def set_hist(self, h):
        self.hist = h
        self.canvas.update()

    def _refresh(self):
        b, g, w, ob, ow = self.row()
        for e, v in zip(self.f, (b, g, w, ob, ow)):
            e.setText(("%.2f" % v) if e is self.f[1] else ("%d" % round(v)))
        self.canvas.update()

    def _emit(self):
        self._refresh()
        self.changed.emit(ct.norm_levels(self.rows))

    def _set_row(self, b, g, w, ob, ow):
        self.rows[ct.CHANNELS.index(self.channel())] = list(ct.norm_levels_row((b, g, w, ob, ow)))

    def drag_to(self, mark, v):
        b, g, w, ob, ow = self.row()
        if mark == "b":
            b = min(v, w - 1)
        elif mark == "w":
            w = max(v, b + 1)
        else:
            x = min(0.98, max(0.02, (v - b) / max(1.0, w - b)))
            g = min(10.0, max(0.1, math.log(0.5) / math.log(x)))
        self._set_row(b, g, w, ob, ow)
        self._emit()

    def reset_mark(self, mark):
        b, g, w, ob, ow = self.row()
        if mark == "b":
            b = 0.0
        elif mark == "w":
            w = 255.0
        else:
            g = 1.0
        self._set_row(b, g, w, ob, ow)
        self._emit()

    def _typed(self, i):
        vals = list(self.row())
        try:
            vals[i] = float(self.f[i].text().replace(",", "."))
        except ValueError:
            self._refresh()
            return
        self._set_row(*vals)
        self._emit()

    def reset_all(self):
        self.rows = [list(ct.LEVELS_NEUTRAL) for _ in range(4)]
        self._emit()


class CurveEditor(QWidget):
    """Кривая: точки двигаются мышью, щелчок по пустому месту добавляет точку, двойной щелчок или правая кнопка удаляют."""
    changed = Signal(object)                       # tuple из четырёх списков точек (как curves)
    hovered = Signal(str)

    def __init__(self, size=260):
        super().__init__()
        self.pts = [list(ct.CURVE_NEUTRAL) for _ in range(4)]
        self.ch = "rgb"
        self.hist = None
        self.drag = None
        self.setMinimumSize(size, size)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

    def heightForWidth(self, w):
        return w

    def set_value(self, curves):
        self.pts = [list(map(tuple, c)) for c in ct.curves_full(curves)]
        self.update()

    def set_channel(self, ch):
        self.ch = ch
        self.update()

    def cur(self):
        return self.pts[ct.CHANNELS.index(self.ch)]

    def _box(self):
        m = 12
        s = min(self.width(), self.height()) - 2 * m
        return QRectF((self.width() - s) / 2.0, (self.height() - s) / 2.0, s, s)

    def _to_px(self, x, y):
        r = self._box()
        return QPointF(r.left() + x / 255.0 * r.width(), r.bottom() - y / 255.0 * r.height())

    def _from_px(self, pos):
        r = self._box()
        return (min(255.0, max(0.0, (pos.x() - r.left()) / r.width() * 255.0)),
                min(255.0, max(0.0, (r.bottom() - pos.y()) / r.height() * 255.0)))

    def _hit(self, pos):
        for i, (x, y) in enumerate(self.cur()):
            q = self._to_px(x, y)
            if abs(q.x() - pos.x()) <= 12 and abs(q.y() - pos.y()) <= 12:
                return i
        return None

    def _emit(self):
        self.changed.emit(tuple(tuple(c) for c in self.pts))

    def mousePressEvent(self, e):
        pos = e.position()
        i = self._hit(pos)
        pts = self.cur()
        if e.button() == Qt.RightButton:
            if i is not None and 0 < i < len(pts) - 1:
                del pts[i]
                self._emit()
                self.update()
            return
        if e.button() != Qt.LeftButton:
            return
        if i is None:
            x, _y = self._from_px(pos)
            x = int(round(x))
            near = [k for k, (px, _) in enumerate(pts) if abs(px - x) < 2]
            if near:                                       # рядом по горизонтали уже есть точка — берём её, а не молчим
                self.drag = near[0]
                self.update()
                return
            tab = ct.curve_lut(pts)
            pts.append((x, tab[x]))
            pts.sort()
            i = [p[0] for p in pts].index(x)
            self._emit()
        self.drag = i
        self.update()

    def mouseDoubleClickEvent(self, e):
        i = self._hit(e.position())
        pts = self.cur()
        if i is not None and 0 < i < len(pts) - 1:
            del pts[i]
            self.drag = None
            self._emit()
            self.update()

    def mouseMoveEvent(self, e):
        x, y = self._from_px(e.position())
        pts = self.cur()
        if self.drag is not None and self.drag < len(pts):
            i = self.drag
            nx = pts[i][0]
            if 0 < i < len(pts) - 1:
                nx = int(round(min(pts[i + 1][0] - 1, max(pts[i - 1][0] + 1, x))))
            pts[i] = (nx, int(round(y)))
            self._emit()
            self.update()
        else:
            self.setCursor(Qt.PointingHandCursor if self._hit(e.position()) is not None else Qt.CrossCursor)
        tab = ct.curve_lut(pts)
        xi = int(round(x))
        self.hovered.emit(trf("Вход {a} → выход {b}", a=xi, b=tab[xi]))

    def mouseReleaseEvent(self, e):
        self.drag = None

    def leaveEvent(self, e):
        self.hovered.emit("")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._box()
        p.setPen(QPen(QColor(T["border"]), 1))
        p.setBrush(QColor(T["canvas"]))
        p.drawRoundedRect(r.adjusted(-3, -3, 3, 3), 6, 6)
        paint_hist_fill(p, r, hist_channel(self.hist, self.ch), CH_COLORS[self.ch])
        p.setPen(QPen(QColor(T["border"]), 1))
        for k in range(1, 4):
            f = k / 4.0
            p.drawLine(QPointF(r.left() + f * r.width(), r.top()), QPointF(r.left() + f * r.width(), r.bottom()))
            p.drawLine(QPointF(r.left(), r.top() + f * r.height()), QPointF(r.right(), r.top() + f * r.height()))
        p.setPen(QPen(QColor(T["muted"]), 1, Qt.DashLine))
        p.drawLine(r.bottomLeft(), r.topRight())
        pts = self.cur()
        tab = ct.curve_lut(pts)
        path = QPainterPath()
        for i in range(256):
            q = self._to_px(i, tab[i])
            path.lineTo(q) if i else path.moveTo(q)
        p.setPen(QPen(QColor(CH_COLORS[self.ch]), 2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        for i, (x, y) in enumerate(pts):
            q = self._to_px(x, y)
            p.setPen(QPen(QColor("#111111"), 1.5))
            p.setBrush(QColor("#ffffff") if i == self.drag else QColor(CH_COLORS[self.ch]))
            p.drawEllipse(q, 5.5, 5.5)
        p.end()


class CurvesPanel(QWidget):
    """Кривые целиком: канал, поле кривой, быстрые формы и сброс. Используется и во вкладке, и на большом экране."""
    changed = Signal(object)

    def __init__(self, size=260):
        super().__init__()
        self.bar = ChannelBar()
        self.ed = CurveEditor(size)
        self.l_read = lbl("", "muted")
        self.bar.changed.connect(self.ed.set_channel)
        self.ed.changed.connect(self.changed.emit)
        self.ed.hovered.connect(self.l_read.setText)
        shapes = hbox(btn("Контраст S", lambda: self.shape(((0, 0), (64, 48), (192, 208), (255, 255))), tip="Мягкая S-кривая: больше контраста"),
                      btn("Светлее", lambda: self.shape(((0, 0), (128, 150), (255, 255))), tip="Поднять средние тона"),
                      btn("Темнее", lambda: self.shape(((0, 0), (128, 108), (255, 255))), tip="Опустить средние тона"), spacing=6)
        self.setLayout(vbox(hbox(self.bar, None), self.ed, self.l_read, shapes,
                            hbox(btn("Сбросить канал", self.reset_channel, "link"), btn("Сбросить всё", self.reset_all, "link"), None),
                            hint("Щелчок по кривой — новая точка, двойной щелчок или правая кнопка — удалить точку."),
                            spacing=8))

    def set_value(self, curves):
        self.ed.set_value(curves)

    def set_hist(self, h):
        self.ed.hist = h
        self.ed.update()

    def shape(self, pts):
        self.ed.cur()[:] = list(pts)
        self.ed._emit()
        self.ed.update()

    def reset_channel(self):
        self.shape(ct.CURVE_NEUTRAL)

    def reset_all(self):
        self.ed.pts = [list(ct.CURVE_NEUTRAL) for _ in range(4)]
        self.ed._emit()
        self.ed.update()


class PhotoPreview(QWidget):
    """Редактируемое фото рядом с редактором: как главное окно, с применённой коррекцией."""

    def __init__(self):
        super().__init__()
        self.pm = None
        self.setMinimumSize(360, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_pixmap(self, pm):
        self.pm = pm
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T["canvas"]))
        p.drawRoundedRect(QRectF(self.rect()), 10, 10)
        if self.pm is None or self.pm.isNull():
            p.setPen(QColor(T["muted"]))
            p.drawText(self.rect(), Qt.AlignCenter, tr("Нет фото"))
        else:
            r = QRectF(self.rect()).adjusted(8, 8, -8, -8)
            k = min(r.width() / self.pm.width(), r.height() / self.pm.height())
            w, h = self.pm.width() * k, self.pm.height() * k
            p.drawPixmap(QRectF(r.center().x() - w / 2, r.center().y() - h / 2, w, h), self.pm, QRectF(self.pm.rect()))
        p.end()


class ColorWindow(QDialog):
    """Большой экран уровней и кривых: слева редактор, справа само фото с живой коррекцией."""

    def __init__(self, app):
        super().__init__(app)
        self.setWindowTitle(tr("Уровни и кривые"))
        self.setModal(False)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        geo = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else QRect(0, 0, 1400, 900)
        self.resize(min(1360, geo.width() - 60), min(880, geo.height() - 80))
        self.levels = LevelsEditor()
        self.panel = CurvesPanel(520)
        self.stack = PageStack()
        self.stack.addWidget(self.levels)
        self.stack.addWidget(self.panel)
        self.seg = Segmented([("Уровни", 0), ("Кривые", 1)], 1)
        self.seg.changed.connect(self.show_tab)
        self.preview = PhotoPreview()
        b_orig = btn("Показать оригинал (удерживайте)", None, ico="eye")
        b_orig.pressed.connect(lambda: app.adj_show_original(True))
        b_orig.released.connect(lambda: app.adj_show_original(False))
        left = vbox(self.seg, self.stack, None, spacing=10)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(560)
        right = vbox(self.preview, hbox(b_orig, None, btn("Закрыть", self.close, "primary"), spacing=8), spacing=10)
        self.setLayout(hbox(lw, right, spacing=16, margins=(16, 14, 16, 14)))
        self.show_tab(1)

    def show_tab(self, i):
        self.stack.setCurrentIndex(i)
        self.seg.set(i)


class SelColorPanel(QWidget):
    """Выборочный цвет: для каждого из шести цветов — оттенок, насыщенность и яркость."""
    changed = Signal(object)
    NAMES = (("R", "Красный", "#ff5a5a"), ("Y", "Жёлтый", "#ffd21f"), ("G", "Зелёный", "#4fd06a"),
             ("C", "Голубой", "#3fd0e0"), ("B", "Синий", "#5a8cff"), ("M", "Пурпурный", "#d96bff"))

    def __init__(self):
        super().__init__()
        self.vals = [list(ct.SEL_NEUTRAL) for _ in ct.SEL_COLORS]
        self.cur = 0
        self.lock = False
        row = hbox(spacing=4)
        self.chips = []
        for i, (k, name, col) in enumerate(self.NAMES):
            b = MotionButton(k)
            b.setProperty("kind", "chip")
            b.setCheckable(True)
            b.setToolTip(tr(name))
            b.setStyleSheet("QPushButton{color:%s;font-weight:700;}QPushButton:checked{color:%s;}" % (col, T["accent_text"]))
            b.clicked.connect(lambda _=False, i=i: self.pick(i))
            self.chips.append(b)
            row.addWidget(b)
        self.sl, self.val = [], []
        sl_rows = []
        for j, (name, step) in enumerate((("Оттенок", 1), ("Насыщенность", 1), ("Яркость", 1))):
            s = _ResetSlider(Qt.Horizontal)
            s.setRange(-100, 100)
            s.setValue(0)
            v = lbl("0", "muted")
            v.setFixedWidth(34)
            v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            s.valueChanged.connect(lambda x, j=j: self._moved(j, x))
            s.reset.connect(lambda j=j: self.sl[j].setValue(0))
            self.sl.append(s)
            self.val.append(v)
            sl_rows.append(vbox(hbox(lbl(name), None, v), s, spacing=1, margins=(0, 3, 0, 3)))
        self.l_name = lbl("", "muted")
        self.setLayout(vbox(row, self.l_name, *sl_rows, hbox(btn("Сбросить цвет", self.reset_cur, "link"), btn("Сбросить всё", self.reset_all, "link"), None),
                            hint("Серые и нейтральные цвета не затрагиваются."), spacing=6))
        self.pick(0)

    def pick(self, i):
        self.cur = i
        for k, b in enumerate(self.chips):
            b.setChecked(k == i)
        self.l_name.setText(tr(self.NAMES[i][1]))
        self._show()

    def _show(self):
        self.lock = True
        for j, s in enumerate(self.sl):
            v = int(round(self.vals[self.cur][j]))
            s.setValue(v)
            self.val[j].setText("%+d" % v if v else "0")
        self.lock = False

    def set_value(self, sel):
        self.vals = [list(r) for r in ct.selcol_full(sel)]
        self._show()

    def _moved(self, j, x):
        self.val[j].setText("%+d" % x if x else "0")
        if self.lock:
            return
        self.vals[self.cur][j] = float(x)
        self.changed.emit(ct.norm_selcol(self.vals))

    def reset_cur(self):
        self.vals[self.cur] = list(ct.SEL_NEUTRAL)
        self._show()
        self.changed.emit(ct.norm_selcol(self.vals))

    def reset_all(self):
        self.vals = [list(ct.SEL_NEUTRAL) for _ in ct.SEL_COLORS]
        self._show()
        self.changed.emit(ct.norm_selcol(self.vals))


class SendOverlay(QWidget):
    """Большая анимация в центре окна — на первый лист: лист плавно опускается в принтер, индикатор мигает,
    в конце появляется галочка."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._t = 0.0
        self.pm = None
        self.kind = "print"
        self.text = ""
        self.anim = QPropertyAnimation(self, b"t", self)
        self.anim.setDuration(1250)
        self.anim.setEasingCurve(QEasingCurve.Linear)
        self.anim.finished.connect(self.hide)
        self.hide()

    def getT(self):
        return self._t

    def setT(self, v):
        self._t = float(v)
        self.update()

    t = Property(float, getT, setT)

    def play(self, pm, kind="print", text=""):
        self.pm, self.kind, self.text = pm, kind, text
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.anim.stop()
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()

    @staticmethod
    def _ease(x):
        x = max(0.0, min(1.0, x))
        return x * x * (3 - 2 * x)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        t = self._t
        cw, ch = self.width(), self.height()
        fade = self._ease(t / 0.12) * self._ease((1.0 - t) / 0.14)
        p.fillRect(self.rect(), QColor(0, 0, 0, int(125 * fade)))
        p.setOpacity(fade)
        pw_, ph_ = 190.0, 96.0                                       # принтер
        bx, by = cw / 2 - pw_ / 2, ch / 2 + 20
        slot_y = by + 16
        appear = self._ease(t / 0.18)                                # лист появляется, слегка увеличиваясь
        feed = self._ease((t - 0.22) / 0.5)                          # и уходит в щель
        sw, sh = 150.0 * (0.9 + 0.1 * appear), 200.0 * (0.9 + 0.1 * appear)
        sx = cw / 2 - sw / 2
        sy = (slot_y - sh - 26) + (sh + 20) * feed
        p.save()
        p.setClipRect(QRectF(0, 0, cw, slot_y))                      # ниже щели лист уже «внутри»
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawRoundedRect(QRectF(sx + 5, sy + 7, sw, sh), 5, 5)
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(sx, sy, sw, sh), 5, 5)
        if self.pm is not None and not self.pm.isNull():
            m = 9.0
            p.drawPixmap(QRectF(sx + m, sy + m, sw - 2 * m, sw - 2 * m), self.pm, QRectF(self.pm.rect()))
        p.restore()
        p.setPen(Qt.NoPen)                                           # тень и корпус
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawRoundedRect(QRectF(bx + 4, by + 10, pw_, ph_), 16, 16)
        p.setPen(QPen(QColor(T["border"]), 1))
        p.setBrush(QColor(T["surface"]))
        p.drawRoundedRect(QRectF(bx, by, pw_, ph_), 16, 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T["canvas"]))
        p.drawRoundedRect(QRectF(bx + 16, by + 12, pw_ - 32, 8), 4, 4)        # щель
        p.setBrush(QColor(T["raised"]))
        p.drawRoundedRect(QRectF(bx + 22, by + ph_ - 20, pw_ - 44, 8), 4, 4)   # лоток
        done = self._ease((t - 0.74) / 0.12)
        blink = 0.5 + 0.5 * math.sin(t * 34.0)
        p.setBrush(QColor(mix(T["hover"], T["accent"], 1.0 if done > 0 else blink)))
        p.drawEllipse(QRectF(bx + pw_ - 30, by + 34, 10, 10))
        if done > 0:                                                 # галочка в конце
            r = 17.0 * (0.6 + 0.4 * done)
            c = QPointF(bx + pw_ / 2, by + 52)
            p.setBrush(QColor(T["accent"]))
            p.drawEllipse(c, r, r)
            ic = pix("check", T["accent_text"], 20, 2.6)
            p.drawPixmap(QRectF(c.x() - 10, c.y() - 10, 20, 20), ic, QRectF(0, 0, 60, 60))
        else:
            ic = pix("save" if self.kind == "save" else "print", T["muted"], 28)
            p.drawPixmap(QRectF(bx + pw_ / 2 - 14, by + 38, 28, 28), ic, QRectF(0, 0, 84, 84))
        if self.text:
            p.setPen(QColor("#ffffff"))
            fnt = QFont(p.font())
            fnt.setPixelSize(15)
            fnt.setBold(True)
            p.setFont(fnt)
            p.drawText(QRectF(0, by + ph_ + 14, cw, 28), Qt.AlignCenter, self.text)
        p.end()


class FlyOverlay(QWidget):
    """Следующие листы: маленький лист появляется рядом с кнопкой «Печать», коротко летит по дуге и исчезает в ней."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._t = 0.0
        self.pm = None
        self.a = self.b = QPointF(0, 0)
        self.size, self.lift = 1.0, 90.0
        self.on_arrive = None
        self.anim = QPropertyAnimation(self, b"t", self)
        self.anim.setDuration(620)
        self.anim.setEasingCurve(QEasingCurve.InOutCubic)
        self.anim.finished.connect(self._finished)
        self.hide()

    def getT(self):
        return self._t

    def setT(self, v):
        self._t = float(v)
        self.update()

    t = Property(float, getT, setT)

    def play(self, pm, a, b, on_arrive=None, size=1.0, lift=90.0):
        self.pm, self.a, self.b, self.on_arrive = pm, a, b, on_arrive
        self.size, self.lift = size, lift
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.anim.stop()
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()

    def _finished(self):
        self.hide()
        if self.on_arrive:
            self.on_arrive()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        t = self._t
        x = self.a.x() + (self.b.x() - self.a.x()) * t
        y = self.a.y() + (self.b.y() - self.a.y()) * t - self.lift * math.sin(math.pi * t)     # дуга
        k = self.size * (1.0 - 0.72 * t)
        w, h = 96.0 * k, 128.0 * k
        p.setOpacity(min(1.0, t / 0.12) * (1.0 if t < 0.85 else max(0.0, (1.0 - t) / 0.15)))
        p.translate(x, y)
        p.rotate(-10.0 + 22.0 * t)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 80))
        p.drawRoundedRect(QRectF(-w / 2 + 3, -h / 2 + 5, w, h), 4, 4)
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(-w / 2, -h / 2, w, h), 4, 4)
        if self.pm is not None and not self.pm.isNull():
            m = 6.0 * k
            p.drawPixmap(QRectF(-w / 2 + m, -h / 2 + m, w - 2 * m, w - 2 * m), self.pm, QRectF(self.pm.rect()))
        p.end()


class PrintButton(QPushButton):
    """Кнопка «Печать» с собственной анимацией: полоса хода печати по нижнему краю и вспышка на каждый принятый лист."""

    def __init__(self, text):
        super().__init__(text)
        self._pulse = 0.0
        self.frac = None                       # None — печать не идёт; 0..1 — доля отправленных листов
        self._anim = QPropertyAnimation(self, b"pulse", self)
        self._anim.setDuration(520)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def getPulse(self):
        return self._pulse

    def setPulse(self, v):
        self._pulse = float(v)
        self.update()

    pulse = Property(float, getPulse, setPulse)

    def flash(self):
        self._anim.stop()
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def set_progress(self, frac):
        self.frac = frac
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.frac is None and self._pulse <= 0.001:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        clip = QPainterPath()
        clip.addRoundedRect(r, 11, 11)
        p.setClipPath(clip)
        if self._pulse > 0.001:                                      # вспышка: светлая волна от центра
            c = QColor("#ffffff")
            c.setAlpha(int(120 * self._pulse))
            w = r.width() * (1.0 - self._pulse * 0.6)
            p.fillRect(QRectF(r.center().x() - w / 2, r.top(), w, r.height()), c)
        if self.frac is not None:
            p.fillRect(QRectF(r.left(), r.bottom() - 4, r.width(), 4), QColor(0, 0, 0, 70))
            p.fillRect(QRectF(r.left(), r.bottom() - 4, r.width() * max(0.0, min(1.0, self.frac)), 4), QColor(T["accent_text"]))
        p.end()


# ---------------------------------------------------------------- вид «Лист»: несколько фото на одном листе

NUP = {1: (1, 1), 2: (1, 2), 3: (1, 3), 4: (2, 2), 6: (2, 3), 8: (2, 4), 9: (3, 3),
       12: (3, 4), 16: (4, 4), 24: (4, 6)}                                # быстрый выбор: фото на листе -> (столбцов, рядов) на книжном листе
NUP_MAX = 30


def nup_grid(n):
    """Сетка (столбцов, рядов) на книжном листе для любого числа фото: ближайшая к квадрату без пустых ячеек
    (простое число — в один ряд)."""
    n = max(1, min(NUP_MAX, int(n)))
    if n in NUP:
        return NUP[n]
    c = max(d for d in range(1, int(n ** 0.5) + 1) if n % d == 0)
    return c, n // c


class NupPicker(QFrame):
    """Сколько фото на листе: быстрые кнопки и ручной ввод числа."""
    changed = Signal(int)

    def __init__(self, value=1):
        super().__init__()
        self.group = QButtonGroup(self)
        self.group.setExclusive(False)
        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)
        self.btns = {}
        for i, n in enumerate(NUP):
            b = MotionButton(str(n))
            b.setProperty("kind", "chip")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=n: self._pick(k))
            self.btns[n] = b
            grid.addWidget(b, i // 5, i % 5)
        self.spin = QLineEdit()
        self.spin.setValidator(QIntValidator(1, NUP_MAX))
        self.spin.setFixedWidth(64)
        self.spin.setAlignment(Qt.AlignCenter)
        self.spin.setToolTip(tr("Своё число фото на листе"))
        self.spin.editingFinished.connect(self._typed)
        self.setLayout(vbox(grid, hbox(lbl("Своё число", "muted"), self.spin, None), spacing=6))
        self.set(value)

    def _pick(self, n):
        self.set(n)
        self.changed.emit(int(n))

    def _typed(self):
        t = self.spin.text().strip()
        if t.isdigit() and 1 <= int(t) <= NUP_MAX and int(t) != self.cur:
            self._pick(int(t))
        else:
            self.spin.setText(str(self.cur))

    def set(self, n):
        self.cur = int(n)
        for k, b in self.btns.items():
            b.setChecked(k == n)
        self.spin.setText(str(self.cur))

    def value(self):
        return self.cur


class Aff:
    """Аффинное преобразование (как QTransform: каждая следующая операция применяется к точке первой).
    x' = a·x + c·y + e,  y' = b·x + d·y + f."""

    def __init__(self, a=1.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0):
        self.m = (a, b, c, d, e, f)

    def _mul(self, o):                       # сначала o, потом self
        a, b, c, d, e, f = self.m
        A, B, C, D, E, F = o
        return Aff(a * A + c * B, b * A + d * B, a * C + c * D, b * C + d * D, a * E + c * F + e, b * E + d * F + f)

    def translate(self, x, y):
        return self._mul((1, 0, 0, 1, x, y))

    def scale(self, sx, sy):
        return self._mul((sx, 0, 0, sy, 0, 0))

    def rotate(self, deg):                   # по часовой стрелке на экране (ось y вниз)
        r = math.radians(deg)
        return self._mul((math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0))

    def map(self, x, y):
        a, b, c, d, e, f = self.m
        return a * x + c * y + e, b * x + d * y + f

    def inverted(self):
        a, b, c, d, e, f = self.m
        det = a * d - b * c or 1e-12
        A, B, C, D = d / det, -b / det, -c / det, a / det
        return Aff(A, B, C, D, -(A * e + C * f), -(B * e + D * f))


def cell_transform(W, H, paper, st, mode, rot, cx, cy, k):
    """Как снимок W×H ложится в свою ячейку листа: точка снимка (px) -> точка экрана.
    paper — размер кадра фото, мм; rot — фото лежит в ячейке боком; (cx, cy) — центр ячейки на экране; k — px/мм."""
    t = Aff().translate(cx, cy)
    if rot:
        t = t.rotate(-90)
    if mode == "fit":
        sc = min(paper[0] * k / W, paper[1] * k / H)
        return t.scale(sc, sc).translate(-W / 2.0, -H / 2.0)
    fx, fy, fw, fh, ang = pc.frame_geom(W, H, paper, st)
    sc = paper[0] * k / fw
    return t.scale(sc, sc).rotate(-ang).translate(-fx, -fy)


class _PrevSignals(QObject):
    done = Signal(object, QImage)


class _PrevJob(QRunnable):
    def __init__(self, sig, key, adj):
        super().__init__()
        self.sig, self.key, self.adj = sig, key, adj

    def run(self):
        try:
            path, rotation = self.key[0], self.key[1]
            with pc.Image.open(path) as im0:
                im0.draft("RGB", (1300, 1300))
                icc = im0.info.get("icc_profile")
                im = pc.ImageOps.exif_transpose(im0)
                if rotation:
                    im = pc.orient_img(im, rotation)
                im = pc.to_rgb(im, icc)
                im.thumbnail((1100, 1100), pc.RESAMPLE_FAST)
            if self.adj:
                im = pc.adjust_tile(im, pc.merge_adj({}, type("S", (), {"adj": dict(self.adj)})()), 100, preview=True)
            img = pil_to_qimage(im)
        except Exception:
            img = QImage()
        try:
            self.sig.done.emit(self.key, img)
        except RuntimeError:
            pass


class PreviewCache(QObject):
    """Картинки фото для листа (с цветокоррекцией), считаются в фоне."""
    ready = Signal()

    def __init__(self):
        super().__init__()
        self.pm, self.last, self.pending = {}, {}, set()
        self.sig = _PrevSignals()
        self.sig.done.connect(self._done)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)

    def get(self, f, st):
        key = (str(f), int(st.rotation), tuple(sorted(st.adj.items())))
        pm = self.pm.get(key)
        if pm is None:
            if key not in self.pending:
                self.pending.add(key)
                self.pool.start(_PrevJob(self.sig, key, dict(st.adj)))
            pm = self.last.get((key[0], key[1]))          # пока считается новая — показываем прежнюю
        return pm

    def _done(self, key, img):
        self.pending.discard(key)
        if len(self.pm) > 80:
            self.pm.clear()
        pm = QPixmap.fromImage(img) if not img.isNull() else QPixmap()
        self.pm[key] = pm
        self.last[(key[0], key[1])] = pm
        self.ready.emit()


class SheetView(QWidget):
    """Готовый лист. Фото кадрируется прямо здесь: тянете мышью — фото сдвигается в своём окошке, колесо — масштаб,
    Shift+колесо — наклон. За круглую ручку фото переносится: в сетке — меняется местами с другим,
    в свободном режиме — ставится куда угодно; за уголки (свободный режим) меняется размер."""
    PILL_ZONE = 66
    GRIP = 11

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.page = 0
        self.sel = None                  # ключ выбранного места на листе
        self.drag = None
        self.target = None
        self.g = None                    # (x0, y0, k): лист на экране, px/мм
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setMinimumSize(440, 340)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        pill = self.pill = QFrame(self)
        pill.setObjectName("pill")
        self.l_page = lbl("0 / 0")
        self.l_page.setMinimumWidth(96)
        self.l_page.setAlignment(Qt.AlignCenter)
        self.sw_free = Switch(app.s["free"])
        self.sw_free.setToolTip(tr("Свободный режим: фото можно ставить куда угодно и менять их размер"))
        self.sw_free.toggled.connect(lambda on: app.set_free(bool(on)))
        pill.setLayout(hbox(ibtn("prev", "Предыдущий лист", lambda: self.turn(-1)), self.l_page,
                            ibtn("next", "Следующий лист", lambda: self.turn(1)), vsep(),
                            app.copies_chip(), vsep(), 4,
                            lbl("Свободно"), self.sw_free, 4, vsep(),
                            ibtn("reset", "Вернуть раскладку по сетке и исходный порядок", app.reset_layout),
                            spacing=4, margins=(5, 5, 8, 5)))
        sh = QGraphicsDropShadowEffect(pill)
        sh.setBlurRadius(30)
        sh.setOffset(0, 8)
        sh.setColor(QColor(0, 0, 0, 110))
        pill.setGraphicsEffect(sh)
        self._build_panel()

    # ---- окошко выбранного фото: размер цифрами, поворот, масштаб
    def _build_panel(self):
        pn = self.panel = QFrame(self)
        pn.setObjectName("pill")
        self.e_w, self.e_h = QLineEdit(), QLineEdit()
        for e_, which in ((self.e_w, "w"), (self.e_h, "h")):
            e_.setFixedWidth(58)
            e_.setAlignment(Qt.AlignCenter)
            e_.editingFinished.connect(lambda w_=which: self.set_size(w_))
        self.e_w.setToolTip(tr("Ширина фото на листе, мм"))
        self.e_h.setToolTip(tr("Высота фото на листе, мм"))
        self.b_lock = QToolButton()
        self.b_lock.setCheckable(True)
        self.b_lock.setChecked(True)
        self.b_lock.setIcon(icon("lock", T["select"], 16))
        self.b_lock.setFixedSize(30, 30)
        self.b_lock.setToolTip(tr("Сохранять пропорции при изменении размера"))
        self.b_lock.toggled.connect(lambda on: self.b_lock.setIcon(icon("lock", T["select"] if on else T["muted"], 16)))
        a = self.app
        r1 = hbox(lbl("Ш", "muted"), self.e_w, lbl("×", "muted"), lbl("В", "muted"), self.e_h, lbl("мм", "muted"), self.b_lock, spacing=5)
        r2 = hbox(ibtn("rot_l", "Повернуть фото влево на 90°", lambda: self._act(lambda: a.rotate_photo(270)), 30, isize=17),
                  ibtn("rot_r", "Повернуть фото вправо на 90°", lambda: self._act(lambda: a.rotate_photo(90)), 30, isize=17),
                  ibtn("swap", "Повернуть место на листе: ширина ⇄ высота", self.flip_slot, 30, isize=17),
                  ibtn("tilt_l", "Наклонить фото влево", lambda: self._act(lambda: a.tilt(-0.5)), 30, isize=17),
                  ibtn("tilt_r", "Наклонить фото вправо", lambda: self._act(lambda: a.tilt(0.5)), 30, isize=17),
                  ibtn("zoom_in", "Крупнее", lambda: self._act(lambda: a.zoom(1 / 1.06)), 30, isize=17),
                  ibtn("zoom_out", "Мельче", lambda: self._act(lambda: a.zoom(1.06)), 30, isize=17),
                  ibtn("reset", "Вернуть это фото в сетку", self.slot_reset, 30, isize=17),
                  ibtn("trash", "Убрать фото с листа", self.slot_remove, 30, isize=17), spacing=1)
        pn.setLayout(vbox(r1, r2, spacing=4, margins=(8, 7, 8, 7)))
        sh = QGraphicsDropShadowEffect(pn)
        sh.setBlurRadius(26)
        sh.setOffset(0, 6)
        sh.setColor(QColor(0, 0, 0, 110))
        pn.setGraphicsEffect(sh)
        pn.hide()

    def _act(self, fn):
        cur = self._sel_slot()
        if cur:
            self.app.select_file(cur["f"])
            fn()
            self.refresh()

    def _free_rect(self, key, rect):
        """Ставит место в свободное положение (свободный режим включается сам)."""
        app = self.app
        if not app.s["free"]:
            app.set_free(True)
        app.free[key] = tuple(rect)

    def set_size(self, which):
        cur = self._sel_slot()
        if not cur:
            return
        x, y, w, h = cur["rect"]
        try:
            v = max(10.0, min(2000.0, float((self.e_w if which == "w" else self.e_h).text().replace(",", "."))))
        except ValueError:
            self._place_panel(True)
            return
        if which == "w":
            nw, nh = v, (h * v / w if self.b_lock.isChecked() else h)
        else:
            nw, nh = (w * v / h if self.b_lock.isChecked() else w), v
        if abs(nw - w) < 0.05 and abs(nh - h) < 0.05:
            return
        self._free_rect(cur["key"], (x, y, nw, nh))
        self.app.redraw()
        self._place_panel(True)

    def flip_slot(self):
        cur = self._sel_slot()
        if cur:
            x, y, w, h = cur["rect"]
            self._free_rect(cur["key"], (x + (w - h) / 2, y + (h - w) / 2, h, w))
            self.app.redraw()

    def slot_reset(self):
        cur = self._sel_slot()
        if cur:
            self.app.free.pop(cur["key"], None)
            self.app.redraw()

    def slot_remove(self):
        cur = self._sel_slot()
        if cur:
            app = self.app
            self.sel = None
            app.checked.discard(cur["f"])
            app.upd_counts()
            app.sync_work()
            self.refresh()

    def _place_panel(self, force=False):
        cur = self._sel_slot() if self.g else None
        if not cur:
            self.panel.hide()
            return
        r = self._rect(cur["rect"])
        if force or not (self.e_w.hasFocus() or self.e_h.hasFocus()):
            self.e_w.setText("%g" % round(cur["rect"][2], 1))
            self.e_h.setText("%g" % round(cur["rect"][3], 1))
        self.panel.adjustSize()
        pw_, ph_ = self.panel.width(), self.panel.height()
        x = r.right() + 12
        if x + pw_ > self.width() - 8:
            x = r.left() - pw_ - 12
        y = r.top()
        if x < 8:                                   # сбоку места нет — под фото или над ним
            x = r.center().x() - pw_ / 2
            y = r.bottom() + 10
            if y + ph_ > self.height() - self.PILL_ZONE:
                y = r.top() + 10
        x = max(8, min(self.width() - pw_ - 8, x))
        y = max(8, min(self.height() - self.PILL_ZONE - ph_, y))
        self.panel.move(int(x), int(y))
        self.panel.show()
        self.panel.raise_()

    def resizeEvent(self, e):
        self.pill.adjustSize()
        self.pill.move(int((self.width() - self.pill.width()) / 2), self.height() - self.pill.height() - 14)
        QTimer.singleShot(0, self._place_panel)

    def refresh(self):
        self.update()
        QTimer.singleShot(0, self._place_panel)

    # ---- листы
    def n_sheets(self):
        sl = self.app.slots()
        return (sl[-1]["sheet"] + 1) if sl else 0

    def page_slots(self):
        return [x for x in self.app.slots() if x["sheet"] == self.page]

    def turn(self, d):
        n = self.n_sheets()
        if n:
            self.page = max(0, min(n - 1, self.page + d))
            self.refresh()

    def show_photo_page(self, f):
        """Переходит на лист, где лежит фото f."""
        for x in self.app.slots():
            if x["f"] == f:
                if self.sel is None or self.sel[0] != f:
                    self.sel = x["key"]
                self.page = next((y["sheet"] for y in self.app.slots() if y["key"] == self.sel), x["sheet"])
                break
        self.update()

    # ---- геометрия
    def _rect(self, mm):
        x0, y0, k = self.g
        return QRectF(x0 + mm[0] * k, y0 + mm[1] * k, mm[2] * k, mm[3] * k)

    def _transform(self, slot):
        app = self.app
        W, H, paper, rot = app.slot_paper(slot["f"], slot["rect"])
        r = self._rect(slot["rect"])
        return cell_transform(W, H, paper, app.states[slot["f"]], app.mode(), rot, r.center().x(), r.center().y(), self.g[2]), W, H

    def _grip(self, r):
        return QPointF(r.center().x(), r.top() + 20)

    def _corners(self, r):
        return {"nw": r.topLeft(), "ne": r.topRight(), "se": r.bottomRight(), "sw": r.bottomLeft()}

    def _slot_at(self, pos):
        for x in reversed(self.page_slots()):
            if self._rect(x["rect"]).contains(pos):
                return x
        return None

    def _sel_slot(self):
        return next((x for x in self.page_slots() if x["key"] == self.sel), None)

    # ---- рисование
    def paintEvent(self, e):
        app = self.app
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        cw, ch = self.width(), self.height()
        bg = QPainterPath()
        bg.addRoundedRect(QRectF(0, 0, cw, ch), 14, 14)
        p.fillPath(bg, QColor(T["canvas"]))
        p.setClipPath(bg)
        n = self.n_sheets()
        self.page = max(0, min(max(0, n - 1), self.page))
        self.l_page.setText((tr("Лист") + " %d / %d" % (self.page + 1, n)) if n else "0 / 0")
        if not n:
            self.g = None
            fnt = QFont(p.font())
            fnt.setPixelSize(15)
            p.setFont(fnt)
            p.setPen(QColor(T["muted"]))
            p.drawText(QRectF(0, 0, cw, ch - self.PILL_ZONE), Qt.AlignCenter,
                       tr("Отметьте фото слева — они разложатся по листам") if app.files else tr("Нажмите «Открыть» и выберите фото или папку"))
            p.end()
            return
        L = app.layout_spec()
        PW, PH = L["PW"], L["PH"]
        uh = ch - self.PILL_ZONE
        pad = 26
        k = min((cw - 2 * pad) / PW, (uh - 2 * pad) / PH)
        Wp, Hp = PW * k, PH * k
        x0, y0 = (cw - Wp) / 2, (uh - Hp) / 2
        self.g = (x0, y0, k)
        sheet = QRectF(x0, y0, Wp, Hp)
        p.fillRect(QRectF(x0 + 6, y0 + 8, Wp, Hp), QColor(0, 0, 0, 80))
        p.fillRect(sheet, QColor("#ffffff"))
        slots = self.page_slots()
        for x in slots:
            r = self._rect(x["rect"])
            pm = app.previews.get(x["f"], app.states[x["f"]])
            p.save()
            p.setClipRect(r.intersected(sheet))
            if pm is not None and not pm.isNull():
                t, W, H = self._transform(x)
                p.setWorldTransform(QTransform(*t.m), True)
                p.drawPixmap(QRectF(0, 0, W, H), pm, QRectF(pm.rect()))
            else:
                p.fillRect(r, QColor(T["hover"]))
            p.restore()
        if self.target is not None:                                   # место, с которым поменяется фото
            tslot = next((x for x in slots if x["key"] == self.target), None)
            if tslot:
                p.setPen(QPen(QColor(T["accent"]), 3, Qt.DashLine))
                p.setBrush(QColor(255, 255, 255, 60))
                p.drawRect(self._rect(tslot["rect"]).adjusted(2, 2, -2, -2))
        cur = self._sel_slot()
        if cur:
            r = self._rect(cur["rect"])
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(T["select"]), 2.5))
            p.drawRect(r.adjusted(1.5, 1.5, -1.5, -1.5))
            gp = self._grip(r)                                        # круглая ручка переноса
            p.setPen(QPen(QColor(0, 0, 0, 160), 1))
            p.setBrush(QColor(T["select"]))
            p.drawEllipse(gp, self.GRIP, self.GRIP)
            ic = pix("move", "#000000", 14, 2.0)
            p.drawPixmap(QRectF(gp.x() - 7, gp.y() - 7, 14, 14), ic, QRectF(0, 0, 42, 42))
            p.setBrush(QColor("#ffffff"))                              # уголки — менять размер
            for c in self._corners(r).values():
                p.drawRoundedRect(QRectF(c.x() - 5.5, c.y() - 5.5, 11, 11), 3, 3)
        p.end()

    # ---- мышь
    def _hit(self, pos):
        cur = self._sel_slot()
        if cur:
            r = self._rect(cur["rect"])
            for name, c in self._corners(r).items():
                if abs(pos.x() - c.x()) <= 9 and abs(pos.y() - c.y()) <= 9:
                    return ("resize", name, cur)
            gp = self._grip(r)
            if (pos.x() - gp.x()) ** 2 + (pos.y() - gp.y()) ** 2 <= (self.GRIP + 3) ** 2:
                return ("move", None, cur)
        x = self._slot_at(pos)
        return ("pan", None, x) if x else (None, None, None)

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or not self.g:
            return
        self.setFocus()
        app = self.app
        pos = e.position()
        kind, name, slot = self._hit(pos)
        if not kind:
            self.sel = None
            self.refresh()
            return
        self.sel = slot["key"]
        app.select_file(slot["f"])
        self._place_panel(True)
        if kind == "pan":
            if app.mode() != "crop":
                self.update()
                return
            t, W, H = self._transform(slot)
            inv = t.inverted()
            st = app.states[slot["f"]]
            app.push_undo([slot["f"]])
            self.drag = ("pan", slot["f"], inv, inv.map(pos.x(), pos.y()), (st.cx, st.cy), W, H)
        elif kind == "move":
            self.drag = ("move", slot["key"], tuple(slot["rect"]), pos, pos, app.s["free"], slot["key"] in app.free)
        else:
            self.drag = ("resize", slot["key"], tuple(slot["rect"]), name, pos)
        self.update()

    def mouseMoveEvent(self, e):
        pos = e.position()
        app = self.app
        if not self.drag or not self.g:
            kind, name, _ = self._hit(pos) if self.g else (None, None, None)
            self.setCursor(Qt.OpenHandCursor if kind == "pan" else Qt.SizeAllCursor if kind == "move"
                           else (Qt.SizeFDiagCursor if name in ("nw", "se") else Qt.SizeBDiagCursor) if kind == "resize" else Qt.ArrowCursor)
            return
        k = self.g[2]
        kind = self.drag[0]
        if kind == "pan":
            _, f, inv, p0, c0, W, H = self.drag
            p1 = inv.map(pos.x(), pos.y())
            st = app.states[f]
            st.cx, st.cy = c0[0] - (p1[0] - p0[0]) / W, c0[1] - (p1[1] - p0[1]) / H     # фото едет за курсором
            pc.normalize(st)
            st.edited = True
            self.setCursor(Qt.ClosedHandCursor)
        elif kind == "move":
            _, key, r0, start, _, was_free, had_rect = self.drag
            # над другим фото (в сетке) — обмен местами; в остальных случаях фото свободно едет за мышью
            over = None
            if not was_free and len(key) == 2:
                over = next((x for x in reversed(self.page_slots()) if x["key"] != key and len(x["key"]) == 2
                             and self._rect(x["grid"]).contains(pos)), None)
            self.target = over["key"] if over else None
            if over:
                if not had_rect:
                    app.free.pop(key, None)
            else:
                x = r0[0] + (pos.x() - start.x()) / k
                y = r0[1] + (pos.y() - start.y()) / k
                self._free_rect(key, (x, y, r0[2], r0[3]))
                x, y = app.snap_rect(key, x, y, r0[2], r0[3], not (e.modifiers() & Qt.ControlModifier))
                app.free[key] = (x, y, r0[2], r0[3])
        else:
            _, key, r0, name, start = self.drag
            dx, dy = (pos.x() - start.x()) / k, (pos.y() - start.y()) / k
            sx = 1 if name in ("ne", "se") else -1
            sy = 1 if name in ("se", "sw") else -1
            w = max(15.0, r0[2] + sx * dx)
            h = max(15.0, r0[3] + sy * dy)
            if not (e.modifiers() & Qt.ShiftModifier):               # по умолчанию пропорции ячейки сохраняются
                f_ = max(w / r0[2], h / r0[3])
                w, h = r0[2] * f_, r0[3] * f_
            x = r0[0] if sx > 0 else r0[0] + r0[2] - w               # противоположный угол остаётся на месте
            y = r0[1] if sy > 0 else r0[1] + r0[3] - h
            self._free_rect(key, (x, y, w, h))
        self._place_panel()
        self.update()

    def mouseReleaseEvent(self, e):
        app = self.app
        d, self.drag = self.drag, None
        if d:
            if d[0] == "pan":
                app.undo_trim(d[1])
                app.thumbs_view.viewport().update()
            elif d[0] == "move" and self.target is not None:
                if not d[5]:
                    app.set_free(False if not app.free else True)
                app.swap_slots(d[1], self.target)
            elif d[0] == "move" and not d[5] and not app.free:
                app.set_free(False)
        self.target = None
        self.setCursor(Qt.ArrowCursor)
        app.update_info()
        self.refresh()

    def mouseDoubleClickEvent(self, e):
        if self._slot_at(e.position()):
            self.app.set_view("crop")

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if not d:
            return
        slot = self._slot_at(e.position()) if self.g else None
        if slot is None:
            self.turn(-1 if d > 0 else 1)
            return
        app = self.app
        self.sel = slot["key"]
        app.select_file(slot["f"])
        if e.modifiers() & Qt.ShiftModifier:
            app.tilt(0.5 if d > 0 else -0.5)
        else:
            app.zoom(1.03 ** max(-5.0, min(5.0, -d / 120.0)))        # колесо от себя — фото крупнее (рамка меньше)
        self.update()


# ---------------------------------------------------------------- главное окно

class SaveSignals(QObject):
    progress = Signal(int, int, str)
    done = Signal(int, list, object, list)
    sheets_ready = Signal(list, str)
    printed = Signal(str, int, str)
    doc_edited = Signal(str)
    queue = Signal(object, str)
    smart_progress = Signal(int, int, str)
    smart_done = Signal(object, str)
    smart_msg = Signal(str)
    smart_models = Signal(str)


class AgentInvoker(QObject):
    """Выполняет функции агента в потоке окна: HTTP-сервер агента работает в своих потоках, а окном можно управлять только отсюда."""
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run, Qt.QueuedConnection)

    def _run(self, job):
        fn, fut = job
        try:
            fut.set_result(fn())
        except BaseException as ex:                           # noqa: BLE001: исключение уходит в поток запроса
            fut.set_exception(ex)

    def invoke(self, fn):
        if threading.current_thread() is threading.main_thread():
            return fn()
        from concurrent.futures import Future
        fut = Future()
        self.call.emit((fn, fut))
        return fut.result()


# ---------------------------------------------------------------- «Умная рамка» (SmartCrop): рамка, которая не режет людей
SM_TIERS = ("head", "torso", "pet", "hands", "arms", "legs", "feet", "other")
SM_TIER_RU = {"head": "Голова", "torso": "Тело", "pet": "Питомец", "hands": "Кисти рук", "arms": "Руки", "legs": "Ноги",
              "feet": "Стопы", "other": "Прочее"}
SM_DEFAULTS = {
    "enabled": False,            # главный выключатель режима
    "auto": True,                # анализировать сразу при открытии фото и при смене листа/формата
    "apply": True,               # ставить найденные рамки (иначе только проверять и помечать)
    "protect": True,             # не трогать рамки, которые поправили вручную
    "scope": "checked",          # что анализировать: отмеченные / все
    "orient_mode": "photo",      # ориентация кадра: photo — как у фото; person — «Человек»: ИИ подбирает книжную/альбомную по человеку
    "only_bad": False,           # слева показывать только кадры, которые нужно проверить
    "next_after_seen": True,     # после «Проверено» перейти к следующему проблемному кадру
    "hide_boxes": False,         # скрыть ВСЕ рамки ИИ на фото (люди, лица, части тела, скелет)
    "show_people": True,         # обводить найденных людей на фото
    "show_parts": True,          # показывать части тела (голова, тело, кисти, руки, ноги, стопы) и скелет нейросети позы
    "gpu": True,                 # использовать видеокарту (CUDA), если есть
    "sample_ok": 0,              # % «ok»-кадров, которые тоже надо посмотреть (ловит тихие промахи детектора)
    "priority": list(SM_TIERS),  # что беречь в первую очередь
    "head_margin": 12,           # запас вокруг головы, % её размера
    "tier_base": 5,              # во сколько раз каждая следующая часть важнее
    "sens": 50,                  # чувствительность поиска людей, 0..100
    "many": 8,                   # групповое фото — от скольких человек
    "min_dpi": 150,              # меньше — предупреждать о разрешении
    "bg_ratio": 12,              # люди мельче N % от самого крупного (с лицом) — «дальний план»
    "ignore_small": True,        # мелких людей на дальнем плане не учитывать совсем
    "faceless_low": True,        # люди без видимого лица (спиной, часть тела) — наинизший приоритет
    "sort": True,                # после анализа выстроить фото по степени: красные первыми, зелёные в конце
    "algo": "simple",            # метод: simple — простой (взвешенная цена), enhanced — улучшенный (голова → тело → … строго по очереди)
    "tol": 2,                    # улучшенный: допуск между ступенями, % (разница меньше — ничья)
}
SM_CFG_KEYS = ("priority", "head_margin", "tier_base", "sens", "many", "min_dpi", "bg_ratio", "algo", "tol", "ignore_small", "faceless_low")
SM_LEVEL_RU = {"ok": "всё цело", "note": "заметка", "check": "проверить", "manual": "вручную", "hand": "правлено вручную",
               "stale": "нужно пересчитать"}


def _sm_module():
    try:
        import smart_crop
        return smart_crop, ""
    except Exception as ex:
        return None, "%s: %s" % (ex.__class__.__name__, ex)


def sm_color(status):
    return {"ok": T["ok"], "note": T["muted"], "check": T["warn"], "manual": T["bad"],
            "hand": T["select"], "stale": T["muted"]}.get(status, T["muted"])


def sm_light_color(light):
    """Светофор умной рамки: красный — резать вручную, оранжевый — посмотреть, зелёный — в порядке / уже поправлено."""
    return {"red": T["bad"], "orange": T["warn"], "green": T["ok"], "grey": T["muted"]}.get(light, T["muted"])


SM_LIGHT_RU = {"red": "красный", "orange": "жёлтый", "green": "зелёный", "grey": "серый"}


class SmartMixin:
    """Умная рамка: поиск людей (SmartCrop), вердикты ok/note/check/manual, маркеры на миниатюрах, очередь проверки."""
    SM_NEUTRAL = (0.5, 0.5, 1.0, 0.0, None)

    # ---------- состояние
    def smart_init(self):
        self.sm = dict(SM_DEFAULTS)
        self.sm.update({k: v for k, v in (self.settings.get("smart") or {}).items() if k in SM_DEFAULTS})
        pr = [t for t in self.sm["priority"] if t in SM_TIERS]
        self.sm["priority"] = pr + [t for t in SM_TIERS if t not in pr]
        self.sm_res, self.sm_seen, self.sm_sample = {}, {}, set()
        self._sm_busy, self._sm_rerun, self._sm_cancel = False, False, threading.Event()
        self._sm_env, self._sm_sc, self._sm_sc_key = None, None, None
        self._sm_ver, self._sm_sync_sig, self._sm_job, self._sm_list_sig = 0, None, None, None
        self._sm_timer = QTimer(self)
        self._sm_timer.setSingleShot(True)
        self._sm_timer.setInterval(700)
        self._sm_timer.timeout.connect(lambda: self.smart_run(auto=True))
        self.sig.smart_progress.connect(self._smart_progress)
        self.sig.smart_done.connect(self._smart_done)
        self.sig.smart_msg.connect(self._smart_msg)
        self.sig.smart_models.connect(self._smart_models_done)

    def smart_reset(self):
        self.sm_res, self.sm_seen, self.sm_sample = {}, {}, set()
        self._sm_sync_sig = self._sm_list_sig = None
        self._sm_orig = {}                                       # исходный порядок фото — чтобы вернуть после сортировки

    def smart_config(self):
        c = self.sm
        s = max(0, min(100, int(c["sens"])))
        return {"priority": list(c["priority"]), "tier_base": float(c["tier_base"]), "head_margin": c["head_margin"] / 100.0,
                "min_person_conf": round(0.55 - 0.004 * s, 3), "min_face_conf": round(0.80 - 0.004 * s, 3),
                "many_persons": int(c["many"]), "min_dpi": int(c["min_dpi"]), "background_ratio": c["bg_ratio"] / 100.0,
                "portrait_fit": c["orient_mode"] == "person", "ignore_background": bool(c["ignore_small"]), "faceless_lowest": bool(c["faceless_low"]),
                "algo": c["algo"] if c["algo"] in ("simple", "enhanced") else "simple", "tier_eps": max(0.1, float(c["tol"])) / 100.0}

    def smart_fmt(self):
        """Размер места фото на листе, мм (короткая, длинная сторона): целый лист или ячейка при нескольких фото на листе."""
        if self.sheet_mode():
            L = self.layout_spec()
            return (min(L["cw"], L["ch"]), max(L["cw"], L["ch"]))
        f = pc.FORMATS[self.s["format"]]
        return (f[0], f[1])

    def smart_sig(self):
        return (self.s["format"], self.s["nup"], self.s["borders"], self.s["border_mm"], self.s.get("cell_mode"), self.cell_mm(), self.s["orient"], self.sm["orient_mode"], self._sm_ver)

    def sm_base_orient(self, f, st):
        o = pc.ORIENTS[self.s["orient"]]
        if o:
            return o
        try:
            W, H = pc.true_size(f, st.rotation)
            return "portrait" if H >= W else "landscape"
        except Exception:
            return "portrait"

    @staticmethod
    def sm_key(st):
        return (round(st.cx, 4), round(st.cy, 4), round(st.scale, 4), round(st.angle, 2), st.orient)

    def sm_touched(self, f):
        """Рамку правили вручную (она не нейтральная и не совпадает с поставленной умной рамкой)."""
        st = self.states.get(f)
        if st is None:
            return False
        k = self.sm_key(st)
        r = self.sm_res.get(f)
        return k != self.SM_NEUTRAL and (r is None or r.get("key") != k)

    # ---------- проверка установки
    def smart_env(self, refresh=False):
        if self._sm_env is not None and not refresh:
            return self._sm_env
        sm, err = _sm_module()
        env = {"module": sm is not None, "err": err, "missing": [], "yunet": False, "yolox": False, "pose": False, "gpu": False}
        if sm is not None:
            for mod, pipname in (("numpy", "numpy"), ("cv2", "opencv-python"), ("onnxruntime", "onnxruntime")):
                try:
                    __import__(mod)
                except Exception:
                    env["missing"].append(pipname)
            try:
                env["yunet"] = (sm.MODELS_DIR / sm.MODEL_FILES["yunet"][0]).is_file()
                env["yolox"] = any((sm.MODELS_DIR / sm.MODEL_FILES[k][0]).is_file() for k in ("yolox_s", "yolox_tiny"))
                env["pose"] = (sm.MODELS_DIR / sm.MODEL_FILES["mp_pose"][0]).is_file()
            except Exception:
                pass
            if "onnxruntime" not in env["missing"]:
                try:
                    import onnxruntime as ort
                    env["gpu"] = "CUDAExecutionProvider" in ort.get_available_providers()
                except Exception:
                    pass
        env["deps_ok"] = env["module"] and not env["missing"]
        env["ready"] = env["deps_ok"] and env["yunet"] and env["yolox"]
        self._sm_env = env
        return env

    def smart_env_text(self):
        e = self.smart_env()
        if not e["module"]:
            return tr("Файл smart_crop.py не найден рядом с программой."), "bad"
        if e["missing"]:
            return tr("Не хватает библиотек: ") + ", ".join(e["missing"]) + tr(". Выполните: pip install numpy opencv-python onnxruntime"), "bad"
        if not e["ready"]:
            return tr("Нужно скачать модели распознавания (лица и люди, около 42 МБ) — кнопка ниже. Без них люди не находятся."), "warn"
        dev = tr("видеокарта (CUDA)") if e["gpu"] and self.sm["gpu"] else tr("процессор")
        if self.sm["algo"] == "enhanced":
            if not e["pose"]:
                return tr("Улучшенный метод: нужна модель позы (скелет, около 5,5 МБ) — кнопка ниже. Пока её нет, руки и ноги оцениваются по размеру головы, а не нейросетью."), "warn"
            return tr("Готово: лица YuNet + люди YOLOX + скелет MediaPipe · ") + dev, "ok"
        return tr("Готово: лица YuNet + люди YOLOX · ") + dev, "ok"

    def smart_env_refresh(self):
        self.smart_env(True)
        self.smart_page_sync()

    def smart_cropper(self):
        sm, err = _sm_module()
        if sm is None:
            return None, err
        os.environ["PHOTOCROP_SMART_GPU"] = "1" if self.sm["gpu"] else "0"
        key = (bool(self.sm["gpu"]), str(sm.MODELS_DIR), self.sm["algo"], bool(self.smart_env().get("pose")))
        if self._sm_sc is None or self._sm_sc_key != key:
            self._sm_sc = sm.SmartCropper(self.smart_config())
            self._sm_sc_key = key
        else:
            self._sm_sc.cfg = sm.make_config(self.smart_config())
        return self._sm_sc, ""

    def smart_download(self):
        sm, err = _sm_module()
        if sm is None:
            warn(self, "Не найден smart_crop.py:\n%s" % err)
            return
        if self._sm_busy:
            return
        self._sm_busy = True
        self.b_sm_models.setEnabled(False)
        self.l_sm_env.setText(tr("Скачиваю модели…"))

        def work():
            msg = ""
            try:
                sm.download_models(("yunet", "yolox_s", "mp_pose"), log=lambda m: self.sig.smart_msg.emit(m))
            except Exception as ex:
                msg = "%s: %s" % (ex.__class__.__name__, ex)
            self.sig.smart_models.emit(msg)
        threading.Thread(target=work, daemon=True).start()

    def _smart_msg(self, m):
        try:
            self.l_sm_prog.setText(m)
            self.l_sm_prog.show()
        except RuntimeError:
            pass

    def _smart_models_done(self, err):
        self._sm_busy = False
        self._sm_sc = None
        self.b_sm_models.setEnabled(True)
        self.smart_env(True)
        self.smart_page_sync()
        if err:
            warn(self, "Не удалось скачать модели:\n%s\n\nСкачайте вручную: python smart_crop.py setup" % err)
        elif self.sm["enabled"] and self.sm["auto"] and self.files:
            self.smart_run(auto=True)

    # ---------- включение, настройки
    def smart_toggle(self, on):
        if self._building:
            return
        on = bool(on)
        if on and not self.smart_env(True)["deps_ok"]:
            txt, _ = self.smart_env_text()
            self.sm["enabled"] = False
            self.sw_sm.set(False)
            self.smart_page_sync()
            warn(self, txt)
            return
        self.sm["enabled"] = on
        if not on:
            self._sm_cancel.set()
        self.smart_page_sync()
        self.smart_refresh_all()
        if on and self.files and self.sm["auto"]:
            self.smart_run(auto=True)

    def _sm_set(self, key, value, cfg=False):
        if self._building:
            return
        self.sm[key] = value
        if cfg or key in SM_CFG_KEYS:
            self.smart_cfg_changed()
        elif key in ("show_people", "hide_boxes"):
            self.canvas.update()
        elif key == "only_bad":
            self.smart_filter()
        elif key in ("orient_mode",):
            self.smart_cfg_changed()
        elif key == "gpu":
            self._sm_env = None
            self._sm_sc = None
            self.smart_page_sync()

    def smart_cfg_changed(self):
        self._sm_ver += 1
        self._sm_sync_sig = None
        self.thumbs_view.viewport().update()
        self.smart_sync(True)
        if self.sm["enabled"] and self.sm["auto"] and self.files and self.sm_res:
            self._sm_timer.start()                 # пересчитать через паузу, когда подвигали ползунок

    def smart_defaults(self):
        keep = {k: self.sm[k] for k in ("enabled",)}
        self.sm.update(dict(SM_DEFAULTS, priority=list(SM_TIERS)))
        self.sm.update(keep)
        self._building = True
        self.smart_page_widgets_from_state()
        self._building = False
        self.smart_cfg_changed()

    def smart_move_tier(self, i, d):
        pr = self.sm["priority"]
        j = i + d
        if 0 <= j < len(pr):
            pr[i], pr[j] = pr[j], pr[i]
            self.smart_tiers_sync()
            self.smart_cfg_changed()

    def smart_clear_cache(self):
        sm, _ = _sm_module()
        if sm is None:
            return
        import shutil
        shutil.rmtree(sm.CACHE_DIR, ignore_errors=True)
        info(self, "Кэш распознавания очищен. Следующий анализ найдёт людей заново.")

    # ---------- анализ
    def smart_files(self):
        return self.checked_files() if self.sm["scope"] == "checked" else list(self.files)

    def smart_run(self, files=None, auto=False):
        if not self.sm["enabled"] or not self.files:
            return
        if self._sm_busy:
            self._sm_rerun = True
            self._sm_cancel.set()
            return
        env = self.smart_env()
        if not env["deps_ok"]:
            if not auto:
                warn(self, self.smart_env_text()[0])
            return
        if not env["ready"] and auto:
            self.smart_page_sync()
            return
        if not env["ready"] and not auto and ask(self, "Модели распознавания не скачаны: без них люди не находятся (только лица по каскадам Хаара).\n\nСкачать сейчас (около 42 МБ)?"):
            self.smart_download()
            return
        files = [f for f in (files if files is not None else self.smart_files()) if f in self.states]
        if not files:
            if not auto:
                info(self, "Нет отмеченных фото для анализа.")
            return
        glob = pc.ORIENTS[self.s["orient"]]
        jobs = []
        for f in files:
            st = self.states[f]
            jobs.append((f, st.rotation, glob or ("auto" if self.sm["orient_mode"] == "person" else self.sm_base_orient(f, st))))
        self._sm_job = {"sig": self.smart_sig(), "rot": {f: rot for f, rot, _ in jobs}, "auto": auto}
        self._sm_busy, self._sm_rerun = True, False
        self._sm_cancel.clear()
        self.sm_prog.setRange(0, len(jobs))
        self.sm_prog.setValue(0)
        self.sm_prog.show()
        self.l_sm_prog.setText(tr("Ищу людей…"))
        self.l_sm_prog.show()
        self.b_sm_stop.show()
        self.b_sm_run.setEnabled(False)
        threading.Thread(target=self._smart_work, args=(jobs, self.smart_fmt()), daemon=True).start()

    def _smart_work(self, jobs, fmt):
        out = {}
        try:
            sc, err = self.smart_cropper()
            if err:
                self.sig.smart_done.emit({}, err)
                return
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def one(job):
                f, rot, ori = job
                if self._sm_cancel.is_set():
                    return f, None, "cancel"
                try:
                    return f, sc.analyze(f, fmt, ori, rot), None
                except Exception as ex:
                    return f, None, "%s: %s" % (ex.__class__.__name__, ex)
            done = 0
            with ThreadPoolExecutor(max_workers=2) as ex:
                for fu in as_completed([ex.submit(one, j) for j in jobs]):
                    f, dec, e = fu.result()
                    done += 1
                    if e != "cancel":
                        out[f] = (dec, e)
                    self.sig.smart_progress.emit(done, len(jobs), f.name)
            self.sig.smart_done.emit(out, "")
        except Exception as ex:
            self.sig.smart_done.emit(out, "%s: %s" % (ex.__class__.__name__, ex))

    def _smart_progress(self, n, total, name):
        try:
            self.sm_prog.setValue(n)
            self.l_sm_prog.setText("%d / %d · %s" % (n, total, name))
        except RuntimeError:
            pass

    def smart_stop(self):
        self._sm_cancel.set()

    def _sm_apply(self, f, dec):
        st = self.states[f]
        st.cx, st.cy = dec["cx"], dec["cy"]
        st.scale = max(pc.MIN_SCALE, min(pc.MAX_SCALE, dec["scale"]))
        st.angle = 0.0
        st.orient = None if dec["orient"] == self.sm_base_orient(f, st) else dec["orient"]
        st.edited = bool(st.rotation or st.copies != 1 or st.adj)     # автоматическая рамка — не ручная правка

    def _smart_done(self, out, err):
        self._sm_busy = False
        self.sm_prog.hide()
        self.b_sm_stop.hide()
        self.b_sm_run.setEnabled(True)
        job, self._sm_job = self._sm_job or {}, None
        if self._sm_rerun and self.sm["enabled"]:
            self._sm_rerun = False
            self.l_sm_prog.hide()
            QTimer.singleShot(0, lambda: self.smart_run(auto=True))
            return
        if err and not out:
            self.l_sm_prog.setText(err)
            self.l_sm_prog.show()
            if job and not job.get("auto"):
                warn(self, "Умная рамка: %s" % err)
            self.smart_page_sync()
            return
        todo = []
        for f, (dec, e) in out.items():
            if f not in self.states:
                continue
            if dec is None:
                dec = {"status": "manual", "risk": 1.0, "cuts": [], "alternatives": [], "detections": [],
                       "reasons": [{"code": "read_error", "level": "manual", "message": "Не удалось обработать файл: %s" % e}]}
            st = self.states[f]
            hand = bool(self.sm["protect"] and self.sm_touched(f))
            rec = {"dec": dec, "rot": job.get("rot", {}).get(f, st.rotation), "sig": job.get("sig"), "key": None, "hand": hand}
            self.sm_res[f] = rec
            if self.sm["apply"] and not hand and "cx" in dec and st.rotation == rec["rot"]:
                todo.append(f)
        if todo:
            self.push_undo(todo)
            for f in todo:
                self._sm_apply(f, self.sm_res[f]["dec"])
                self.sm_res[f]["key"] = self.sm_key(self.states[f])
        # выборочная проверка «ok»: часть безупречных кадров тоже смотрим глазами
        oks = sorted((f for f in out if f in self.sm_res and self.sm_res[f]["dec"]["status"] == "ok"), key=pc.natural_key)
        k = int(round(len(oks) * self.sm["sample_ok"] / 100.0))
        import random
        self.sm_sample = (self.sm_sample - set(out)) | (set(random.Random(7).sample(oks, min(len(oks), k))) if k else set())
        bad = len(self.smart_bad())
        self.l_sm_prog.setText(trf("Готово: {n} фото. К проверке: {b}", n=len(out), b=bad) + (" " + tr("(остановлено)") if self._sm_cancel.is_set() else ""))
        self.l_sm_prog.show()
        if self.sm["sort"] and not self._sm_cancel.is_set():
            self.smart_sort(jump=bool(bad))                      # красные — первыми; открываем самый проблемный
        self.smart_refresh_all()
        if todo:
            self.redraw()

    # ---------- статус и очередь проверки
    def smart_status(self, f):
        """None | ok | note | check | manual | hand (правили вручную) | stale (устарело, нужен пересчёт)."""
        if not self.sm["enabled"]:
            return None
        r, st = self.sm_res.get(f), self.states.get(f)
        if r is None or st is None:
            return None
        if st.rotation != r["rot"] or r["sig"] != self.smart_sig():
            return "stale"
        if r["hand"] or (r["key"] is not None and self.sm_key(st) != r["key"]):
            return "hand"
        return r["dec"]["status"]

    def smart_seen(self, f):
        r = self.sm_res.get(f)
        return bool(r) and self.sm_seen.get(f) == r["dec"]["status"]

    def smart_marker(self, f):
        s = self.smart_status(f)
        if s is None:
            return None
        return s, self.smart_seen(f), f in self.sm_sample

    def smart_light(self, f):
        """red | orange | green | grey | None. Поправил оператор вручную или нажал «Проверено» — кадр становится зелёным."""
        s = self.smart_status(f)
        if s is None:
            return None
        if s == "stale":
            return "grey"
        if s == "hand" or self.smart_seen(f):
            return "green"
        return {"manual": "red", "check": "orange"}.get(s, "green")

    def smart_rank(self, f):
        """Место в списке при сортировке: красные, жёлтые, устаревшие, заметки, «цело», в конце — уже просмотренные и поправленные."""
        s = self.smart_status(f)
        if s is None:
            return 6
        light = self.smart_light(f)
        if light == "green":
            if s == "hand" or self.smart_seen(f):
                return 5
            return 4 if s == "ok" else 3
        return {"red": 0, "orange": 1, "grey": 2}[light]

    def smart_sort(self, restore=False, jump=False):
        """Выстроить фото: красные первыми, зелёные в конце (внутри группы — прежний порядок). restore — вернуть исходный порядок."""
        if not self.files or not self.sm["enabled"] and not restore:
            return
        cur = self.files[self.idx] if 0 <= self.idx < len(self.files) else None
        if restore:
            if not self._sm_orig:
                return
            key = lambda f: self._sm_orig.get(f, 10 ** 9)
        else:
            if not self._sm_orig:
                self._sm_orig = {f: i for i, f in enumerate(self.files)}
            for f in self.files:
                self._sm_orig.setdefault(f, len(self._sm_orig))
            key = lambda f: (self.smart_rank(f), self._sm_orig.get(f, 10 ** 9))
        new = sorted(self.files, key=key)
        if new == self.files:
            return
        self.files = new
        self.slot_order = []                                     # порядок на листах строится заново по новому порядку фото
        self.thumbs_view.model().refresh()
        self._sm_sync_sig = self._sm_list_sig = None
        target = new[0] if (jump and not restore) else cur
        self.idx = -1
        self.show_photo(new.index(target) if target in new else 0)

    def smart_bad(self):
        out = []
        for i, f in enumerate(self.files):
            if f in self.checked and not self.smart_seen(f):
                s = self.smart_status(f)
                if s in ("check", "manual") or (s == "ok" and f in self.sm_sample):
                    out.append(i)
        return out

    def smart_next(self, d=1):
        if not self.sm["enabled"]:
            return
        bad = self.smart_bad()
        if not bad:
            self.l_sm_prog.setText(tr("Кадров для проверки нет."))
            self.l_sm_prog.show()
            return
        cur = self.idx
        if d > 0:
            nxt = next((i for i in bad if i > cur), bad[0])
        else:
            nxt = next((i for i in reversed(bad) if i < cur), bad[-1])
        self.show_photo(nxt)

    def smart_mark_seen(self):
        if not self.sm["enabled"] or not (0 <= self.idx < len(self.files)):
            return
        f = self.files[self.idx]
        r = self.sm_res.get(f)
        if not r:
            return
        if self.smart_seen(f):
            self.sm_seen.pop(f, None)
        else:
            self.sm_seen[f] = r["dec"]["status"]
            self.smart_refresh_all()
            if self.sm["next_after_seen"] and self.smart_bad():
                self.smart_next(1)
                return
        self.smart_refresh_all()

    def smart_use_alt(self, name):
        if not (0 <= self.idx < len(self.files)):
            return
        f = self.files[self.idx]
        r = self.sm_res.get(f)
        alt = next((a for a in (r["dec"].get("alternatives") if r else []) or [] if a["name"] == name), None)
        if not alt:
            return
        st = self.states[f]
        self.push_undo([f])
        if name == "fit":                                   # весь снимок целиком: рамка с белыми полями вокруг
            W, H = pc.true_size(f, st.rotation)
            sh, lg = self.smart_fmt()
            rr = sh / lg if alt["orient"] == "portrait" else lg / sh
            maxw = min(W, H * rr)
            st.cx = st.cy = 0.5
            st.scale = max(pc.MIN_SCALE, min(pc.MAX_SCALE, max(W, H * rr) / maxw))
        else:
            st.cx, st.cy = alt["cx"], alt["cy"]
            st.scale = max(pc.MIN_SCALE, min(pc.MAX_SCALE, alt["scale"]))
        st.angle = 0.0
        st.orient = None if alt["orient"] == self.sm_base_orient(f, st) else alt["orient"]
        st.edited = bool(st.rotation or st.copies != 1 or st.adj)
        r["key"], r["hand"] = self.sm_key(st), False
        self.sm_seen[f] = r["dec"]["status"]               # вариант выбран глазами — кадр проверен
        self.redraw()
        self.smart_refresh_all()

    def smart_reapply(self):
        if not (0 <= self.idx < len(self.files)):
            return
        f = self.files[self.idx]
        r = self.sm_res.get(f)
        if not r or "cx" not in r["dec"]:
            return
        self.push_undo([f])
        self._sm_apply(f, r["dec"])
        r["key"], r["hand"] = self.sm_key(self.states[f]), False
        self.redraw()
        self.smart_refresh_all()

    # ---------- обновление вида
    def smart_refresh_all(self):
        self._sm_sync_sig = None
        self.thumbs_view.viewport().update()
        self.smart_filter()
        self.smart_sync(True)
        self.canvas.update()

    def smart_filter(self):
        v = self.thumbs_view
        on = self.sm["enabled"] and self.sm["only_bad"]
        for i, f in enumerate(self.files):
            hide = False
            if on:
                s = self.smart_status(f)
                hide = (s in ("ok", "note") and f not in self.sm_sample) or (s in ("ok", "note", "check", "manual") and self.smart_seen(f))
            v.setRowHidden(i, hide)

    SM_PART_LETTER = {"head": "Г", "torso": "Т", "hands": "К", "arms": "Р", "legs": "Н", "feet": "С", "pet": "П", "other": "?"}
    SM_BONES = ((5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16))

    def smart_parts_overlay(self, p, ox, oy, k, W, H, r):
        """Части тела, которые защищает рамка (цвет = ступень важности), и скелет, найденный нейросетью позы."""
        sm, _err = _sm_module()
        if sm is None:
            return
        algo = r["dec"].get("algo", "simple")
        fnt = QFont(p.font())
        fnt.setPixelSize(10)
        fnt.setBold(True)
        for d in r["dec"].get("detections", []):
            try:
                person = sm._person_from_fraction(d, (W, H))
                parts = sm.person_parts(person, algo)
            except Exception:
                continue
            if person.ignored:                                       # мелкий дальний план: не учитывается — только серая рамка
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(150, 150, 150, 200), 1, Qt.DotLine))
                b = person.box
                p.drawRect(QRectF(ox + b[0] * k, oy + b[1] * k, (b[2] - b[0]) * k, (b[3] - b[1]) * k))
                continue
            kp = person.keypoints
            for part in parts:
                b = part.box
                col = QColor(*sm.TIER_COLORS.get(part.kind, (200, 200, 200)))
                if person.low:                                       # без лица: самый низкий приоритет — приглушённо
                    col.setAlpha(120)
                rc = QRectF(ox + b[0] * k, oy + b[1] * k, (b[2] - b[0]) * k, (b[3] - b[1]) * k)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(col, 1.5, Qt.DashLine if person.low else Qt.SolidLine))
                p.drawRect(rc)
                if rc.width() > 14 and rc.height() > 14:
                    p.setFont(fnt)
                    p.setPen(Qt.NoPen)
                    col.setAlpha(225)
                    p.setBrush(col)
                    p.drawRect(QRectF(rc.x(), rc.y(), 12, 12))
                    p.setPen(QColor("#101010"))
                    p.drawText(QRectF(rc.x(), rc.y(), 12, 12), Qt.AlignCenter, self.SM_PART_LETTER.get(part.kind, "?"))
            if kp and algo == "enhanced":                            # скелет нейросети
                pt = lambda i: QPointF(ox + kp[i][0] * k, oy + kp[i][1] * k)
                p.setPen(QPen(QColor(255, 255, 255, 210), 2))
                for a_, b_ in self.SM_BONES:
                    if kp[a_][2] >= 0.3 and kp[b_][2] >= 0.3:
                        p.drawLine(pt(a_), pt(b_))
                p.setPen(QPen(QColor(0, 0, 0, 170), 1))
                for i in range(len(kp)):
                    if kp[i][2] >= 0.3 and i >= 5:
                        p.setBrush(QColor(60, 230, 120) if kp[i][2] >= 0.6 else QColor(255, 190, 40))
                        rr = 3.2 if i < 17 else 2.2
                        p.drawEllipse(pt(i), rr, rr)

    def smart_source_text(self, r):
        """Откуда взяты части тела: нейросеть позы / размер головы / пропорции рамки."""
        dets = [d for d in r["dec"].get("detections", []) if d.get("kind") == "person"]
        n_kp = sum(1 for d in dets if d.get("keypoints"))
        if r["dec"].get("algo") == "enhanced":
            if n_kp:
                return trf("Конечности: нейросеть позы (скелет найден у {n} из {m} чел.), остальные — по размеру головы", n=n_kp, m=len(dets))
            return tr("Конечности: по размеру головы (скелет нейросети не найден или нет модели)")
        return tr("Конечности: по пропорциям рамки человека (простой метод)")

    def smart_overlay(self, p, ox, oy, k, W, H, f):
        """Найденные люди поверх фото: рамка человека, на лице — яркая рамка; неуверенные — пунктиром."""
        if not self.sm["enabled"]:
            return
        r, st = self.sm_res.get(f), self.states.get(f)
        if not r or not st or st.rotation != r["rot"] or self.sm.get("hide_boxes", False):
            return
        if self.sm.get("show_parts", True):
            self.smart_parts_overlay(p, ox, oy, k, W, H, r)
        if not self.sm["show_people"]:
            return
        p.setBrush(Qt.NoBrush)
        for d in r["dec"].get("detections", []):
            b = d.get("box")
            if not b:
                continue
            col = QColor(T["ok"] if d.get("kind") != "person" else T["select"])
            col.setAlpha(210)
            if d.get("ignored"):
                col = QColor(150, 150, 150, 170)
            pen = QPen(col, 1.4, Qt.DotLine if d.get("ignored") else (Qt.DashLine if d.get("conf", 1) < 0.55 else Qt.SolidLine))
            p.setPen(pen)
            p.drawRoundedRect(QRectF(ox + b[0] * W * k, oy + b[1] * H * k, (b[2] - b[0]) * W * k, (b[3] - b[1]) * H * k), 3, 3)
            fc = d.get("face")
            if fc:
                p.setPen(QPen(QColor(T["accent"]), 1.8))
                p.drawRoundedRect(QRectF(ox + fc[0] * W * k, oy + fc[1] * H * k, (fc[2] - fc[0]) * W * k, (fc[3] - fc[1]) * H * k), 2, 2)

    def smart_banner_shown(self, f):
        """Рисуется ли над кадром цветная полоса статуса (чтобы не закрывать её кнопками)."""
        if not self.sm["enabled"]:
            return False
        return self.smart_light(f) not in (None, "grey")

    def smart_banner(self, p, cw, f):
        """Полоса сверху над кадром: цвет светофора и короткая причина — сразу видно, красное это фото или зелёное."""
        light = self.smart_light(f) if self.sm["enabled"] else None
        if light is None or light == "grey":
            return
        s = self.smart_status(f)
        r = self.sm_res.get(f)
        if light == "green":
            txt = tr("Поправлено вручную") if s == "hand" else (tr("Проверено") if self.smart_seen(f) else tr("Кадр в порядке"))
        else:
            reasons = (r["dec"].get("reasons") if r else None) or []
            why = reasons[0].get("message", "") if reasons else ""
            txt = (tr("Исправьте кадр вручную") if light == "red" else tr("Посмотрите кадр")) + (" · " + why if why else "")
        col = QColor(sm_light_color(light))
        h = 30
        p.save()
        p.setPen(Qt.NoPen)
        col.setAlpha(238)
        p.setBrush(col)
        p.drawRect(QRectF(0, 0, cw, h))
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawEllipse(QRectF(12, h / 2 - 5, 10, 10))
        f_ = QFont(p.font())
        f_.setPixelSize(13)
        f_.setBold(True)
        p.setFont(f_)
        p.setPen(QColor("#ffffff") if light == "red" else QColor("#101010"))
        fm = QFontMetrics(f_)
        p.drawText(QRectF(30, 0, cw - 42, h), Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText(txt, Qt.ElideRight, int(cw - 42)))
        p.restore()

    def smart_cur_html(self, f):
        r = self.sm_res.get(f)
        s = self.smart_status(f)
        if r is None or s is None:
            if self.sm["enabled"]:
                return "<span style='color:%s'>%s</span>" % (T["muted"], tr("Для этого фото анализа ещё нет."))
            return ""
        dec = r["dec"]
        light = self.smart_light(f)
        col = sm_light_color(light)
        head = "<b style='color:%s'>● %s</b>" % (col, tr(SM_LEVEL_RU.get(s, s)).capitalize())
        if s in ("ok", "note", "check", "manual"):
            head += " · " + trf("людей: {n}", n=dec.get("persons", 0)) + (" · %d dpi" % dec["dpi"] if dec.get("dpi") else "")
        if self.smart_seen(f):
            head += " · <span style='color:%s'>✓ %s</span>" % (T["ok"], tr("проверено"))
        lines = []
        if s != "stale":
            lines.append("<span style='color:%s'>%s</span>" % (T["muted"], self.smart_source_text(r)))
        if s == "hand":
            lines.append(tr("Рамка поправлена вручную — автоматически не меняется."))
        elif s == "stale":
            lines.append(tr("Формат, ориентация или настройки изменились — нужен пересчёт."))
        for x in dec.get("reasons", [])[:6]:
            lines.append("<span style='color:%s'>•</span> %s" % (sm_color(x.get("level", "note")), x.get("message", "")))
        if not lines and s == "ok":
            lines.append(tr("Люди и питомцы целы."))
        return head + "<br>" + "<br>".join(lines)

    def smart_sync(self, force=False):
        try:
            self._smart_sync(force)
        except RuntimeError:                       # виджеты вкладки пересоздаются при смене темы
            pass

    def _smart_sync(self, force=False):
        if not hasattr(self, "l_sm_cur"):
            return
        f = self.files[self.idx] if 0 <= self.idx < len(self.files) else None
        counts = {"ok": 0, "note": 0, "check": 0, "manual": 0}
        for g in self.files:
            s = self.smart_status(g)
            if s in counts:
                counts[s] += 1
        s_cur = self.smart_status(f) if f else None
        sig = (f, s_cur, bool(f and self.smart_seen(f)), tuple(counts.values()), self.sm["enabled"], self._sm_busy, len(self.sm_res))
        if sig == self._sm_sync_sig and not force:
            return
        self._sm_sync_sig = sig
        for k, w in self.sm_cnt.items():
            w.setText(str(counts[k]))
        self.l_sm_cur.setText(self.smart_cur_html(f) if f else "")
        light = self.smart_light(f) if f else None
        self.l_sm_cur.setStyleSheet(("background-color: %s; border-radius: 8px; padding: 8px;" % mix(T["surface"], sm_light_color(light), 0.30)) if light else "")
        self.thumbs_view.viewport().update()                     # цвет плиток меняется сразу, как оператор поправил кадр
        self.canvas.update()
        r = self.sm_res.get(f) if f else None
        alts = {a["name"]: a for a in (r["dec"].get("alternatives") or [])} if (r and s_cur not in (None, "stale")) else {}
        labels = {"other_orientation": ("Другая ориентация", "rot_r"), "fit": ("Вписать целиком", "image"), "extend": ("С белыми полями", "move")}
        for name, b in self.sm_alt_btns.items():
            a = alts.get(name)
            b.setVisible(a is not None)
            if a is not None:
                tip = a.get("label", "")
                if "white_pct" in a:
                    tip += " · " + trf("белых полей около {p}%", p="%g" % a["white_pct"])
                if a.get("problems"):
                    tip += " · " + trf("всё равно режется: {n}, до {c}%", n=a["problems"], c="%g" % a.get("worst_cut_pct", 0))
                b.setToolTip(tip)
        self.b_sm_reapply.setVisible(s_cur == "hand" and bool(r) and "cx" in r["dec"])
        self.b_sm_seen.setEnabled(bool(r))
        self.b_sm_seen.setText(tr("Снять отметку") if (f and self.smart_seen(f)) else tr("Проверено"))
        bad = [self.files[i] for i in self.smart_bad()]
        lsig = tuple(bad)
        if lsig != self._sm_list_sig:
            self._sm_list_sig = lsig
            self.sm_list.clear()
            for g in bad[:300]:
                rr = self.sm_res[g]
                top = (rr["dec"].get("reasons") or [{"message": ""}])[0].get("message", "")
                it = QListWidgetItem("%s  %s — %s" % ("!" if rr["dec"]["status"] == "manual" else "●", g.name, top[:70]))
                it.setData(Qt.UserRole, str(g))
                it.setForeground(QColor(sm_color(rr["dec"]["status"])))
                self.sm_list.addItem(it)
            self.sm_list.setVisible(bool(bad))
            self.l_sm_list.setVisible(bool(bad))
            self.l_sm_list.setText(trf("Нужно посмотреть: {n}", n=len(bad)))

    def _sm_list_clicked(self, item):
        p = item.data(Qt.UserRole)
        for i, f in enumerate(self.files):
            if str(f) == p:
                self.on_tile(i)
                return

    def smart_export_sheet(self):
        sm, err = _sm_module()
        decs = [r["dec"] for f, r in self.sm_res.items() if f in self.states and "frame_px" in r["dec"]]
        if sm is None or not decs:
            info(self, "Сначала выполните анализ.")
            return
        p, _ = QFileDialog.getSaveFileName(self, tr("Контактный лист для проверки"), "проверка.jpg", "JPEG (*.jpg)")
        if not p:
            return
        cfg_sample = self.sm["sample_ok"] / 100.0

        def work():
            try:
                res = sm.contact_sheet(decs, p, only_flagged=True, sample_ok=cfg_sample)
                self.sig.smart_msg.emit(tr("Контактный лист сохранён: ") + p if res else tr("Проблемных кадров нет — лист не нужен."))
            except Exception as ex:
                self.sig.smart_msg.emit("%s: %s" % (ex.__class__.__name__, ex))
        threading.Thread(target=work, daemon=True).start()

    def smart_export_json(self):
        decs = [dict(r["dec"], file=str(f)) for f, r in self.sm_res.items() if f in self.states]
        if not decs:
            info(self, "Сначала выполните анализ.")
            return
        p, _ = QFileDialog.getSaveFileName(self, tr("Сохранить решения"), "решения.json", "JSON (*.json)")
        if p:
            try:
                pc.write_json_atomic(p, decs)
            except OSError as ex:
                warn(self, "Не удалось сохранить файл:\n%s" % ex)

    # ---------- вкладка
    def _sm_slider(self, key, lo, hi, text, tip, unit=""):
        sl = _ResetSlider(Qt.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(int(self.sm[key]))
        val = lbl("%d%s" % (self.sm[key], unit), "muted")
        val.setFixedWidth(46)
        val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sl.valueChanged.connect(lambda v: (self._sm_set(key, int(v)), val.setText("%d%s" % (v, unit))))
        sl.reset.connect(lambda: sl.setValue(int(SM_DEFAULTS[key])))
        head = lbl(text)
        head.setToolTip(tr(tip))
        sl.setToolTip(tr(tip) + "\n" + tr("Двойной щелчок — вернуть исходное значение."))
        self._sm_sliders[key] = (sl, val, unit)
        return vbox(head, hbox(sl, val, spacing=6), spacing=2)

    def _sm_switch(self, key, text, tip=None, cb=None):
        sw = Switch(self.sm[key])
        sw.toggled.connect(lambda on: (self._sm_set(key, bool(on)), cb(on) if cb else None))
        head = lbl(text, wrap=True)
        if tip:
            head.setToolTip(tr(tip))
            sw.setToolTip(tr(tip))
        self._sm_switches[key] = sw
        return hbox(head, sw, spacing=8)

    def _page_smart(self):
        c = self.sm
        self._sm_sliders, self._sm_switches = {}, {}
        # --- режим вкл/выкл
        self.sw_sm = Switch(c["enabled"])
        self.sw_sm.toggled.connect(self.smart_toggle)
        self.l_sm_env = lbl("", "muted", wrap=True)
        self.b_sm_models = btn("Скачать модели", self.smart_download, ico="download", tip="Лица (YuNet) и люди (YOLOX), около 42 МБ, один раз")
        self.b_sm_hide = btn("Скрыть рамки ИИ", lambda: None, ico="eye", tip="Убрать с фото все рамки, которые рисует ИИ (люди, лица, части тела, скелет). Сама умная рамка кадра остаётся.")
        self.b_sm_hide.setCheckable(True)
        self.b_sm_hide.setChecked(bool(c.get("hide_boxes", False)))
        self.b_sm_hide.toggled.connect(lambda on: self._sm_set("hide_boxes", bool(on)))
        head = card("Умная рамка", hbox(self.b_sm_hide, None), lbl("Подбирает рамку так, чтобы не отрезать людей и питомцев; сомнительные кадры помечает для проверки.", "muted", wrap=True),
                    hbox(lbl("Включить режим", "title"), self.sw_sm, spacing=8), self.l_sm_env,
                    hbox(self.b_sm_models, ibtn("reset", "Проверить установку", self.smart_env_refresh, 34, True), None, spacing=6))
        # --- анализ
        self.seg_sm_scope = Segmented([("Отмеченные", "checked"), ("Все", "all")], c["scope"])
        self.seg_sm_scope.changed.connect(lambda v: self._sm_set("scope", v))
        self.sm_prog = QProgressBar()
        self.sm_prog.setTextVisible(False)
        self.sm_prog.hide()
        self.l_sm_prog = lbl("", "muted", wrap=True)
        self.l_sm_prog.hide()
        self.b_sm_run = btn("Анализировать", lambda: self.smart_run(), "primary", ico="sparkle", tip="Найти людей и поставить рамки")
        self.b_sm_stop = btn("Остановить", self.smart_stop, "link")
        self.b_sm_stop.hide()
        self.seg_sm_algo = Segmented([("Простой", "simple"), ("Улучшенный", "enhanced")], c["algo"])
        self.seg_sm_algo.changed.connect(lambda v: (self._sm_set("algo", v), self.smart_algo_sync(), self.smart_page_sync()))
        self.l_sm_algo = lbl("", "muted", wrap=True)
        self.seg_sm_orient = Segmented([("Как у фото", "photo"), ("Человек", "person")], c["orient_mode"])
        self.seg_sm_orient.changed.connect(lambda v: (self._sm_set("orient_mode", v), self.smart_algo_sync()))
        self.l_sm_orient = lbl("", "muted", wrap=True)
        analysis = card("Анализ",
                        lbl("Метод", "muted"), hbox(self.seg_sm_algo, None), self.l_sm_algo,
                        lbl("Ориентация кадра", "muted"), hbox(self.seg_sm_orient, None), self.l_sm_orient,
                        self._sm_switch("auto", "Автоматически при открытии фото и смене формата", "Рамки ставятся сами, как только открыты фото или изменён лист"),
                        self._sm_switch("apply", "Ставить найденные рамки", "Выключено — только проверять и помечать кадры, рамки не менять"),
                        self._sm_switch("protect", "Не трогать рамки, правленные вручную", "Если вы подвинули рамку сами, автоматика её не перезапишет"),
                        self._sm_switch("sort", "После анализа сортировать фото: красные первыми", "Красные и жёлтые кадры — в начало списка, зелёные — в конец. Поправленные вручную становятся зелёными."),
                        lbl("Что анализировать", "muted"), hbox(self.seg_sm_scope, None),
                        hbox(self.b_sm_run, self.b_sm_stop, None, spacing=8), self.sm_prog, self.l_sm_prog)
        # --- результат
        self.sm_cnt = {}
        chips = hbox(spacing=10)
        for key, title in (("ok", "цело"), ("note", "заметка"), ("check", "проверить"), ("manual", "вручную")):
            dot = QLabel("●")
            dot.setStyleSheet("color: %s; background: transparent;" % sm_color(key))
            num = lbl("0")
            f_ = QFont(num.font())
            f_.setBold(True)
            num.setFont(f_)
            self.sm_cnt[key] = num
            dot.setToolTip(tr(title))
            num.setToolTip(tr(title))
            chips.addWidget(dot)
            chips.addWidget(num)
        chips.addStretch(1)
        self.l_sm_cur = QLabel("")
        self.l_sm_cur.setWordWrap(True)
        self.l_sm_cur.setTextFormat(Qt.RichText)
        self.sm_alt_btns = {}
        for name, (text, ic) in (("other_orientation", ("Другая ориентация", "rot_r")), ("fit", ("Вписать целиком", "image")), ("extend", ("С белыми полями", "move")), ("wide", ("Шире", "image"))):
            b = btn(text, lambda n=name: self.smart_use_alt(n), ico=ic)
            b.hide()
            self.sm_alt_btns[name] = b
        self.b_sm_reapply = btn("Вернуть умную рамку", self.smart_reapply, "link")
        self.b_sm_reapply.hide()
        self.b_sm_seen = btn("Проверено", self.smart_mark_seen, ico="check", tip="Отметить кадр проверенным (V)")
        self.b_sm_seen.setEnabled(False)
        nav = hbox(ibtn("prev", "Предыдущий кадр для проверки (Shift+N)", lambda: self.smart_next(-1), 34, True),
                   btn("Следующий", lambda: self.smart_next(1), ico="next", tip="Следующий кадр, который стоит проверить (N)"),
                   self.b_sm_seen, None, spacing=6)
        self.l_sm_list = lbl("", "muted")
        self.l_sm_list.hide()
        self.sm_list = QListWidget()
        self.sm_list.setMaximumHeight(150)
        self.sm_list.itemClicked.connect(self._sm_list_clicked)
        self.sm_list.setStyleSheet("QListWidget::item { border-radius: 7px; padding: 3px 4px; }"
                                   "QListWidget::item:hover { background: %s; }" % T["hover"])
        self.sm_list.hide()
        legend = QLabel("<span style='color:%s'>●</span> %s &nbsp; <span style='color:%s'>●</span> %s &nbsp; <span style='color:%s'>●</span> %s"
                        % (T["bad"], tr("исправить вручную"), T["warn"], tr("посмотреть"), T["ok"], tr("в порядке или поправлено")))
        legend.setTextFormat(Qt.RichText)
        legend.setWordWrap(True)
        result = card("Результат", chips, legend, self.l_sm_cur,
                      hbox(self.sm_alt_btns["other_orientation"], self.sm_alt_btns["fit"], spacing=6),
                      hbox(self.sm_alt_btns["extend"], self.sm_alt_btns["wide"], spacing=6),
                      hbox(self.b_sm_reapply, None, spacing=6),
                      hbox(btn("Отсортировать", lambda: self.smart_sort(jump=True), ico="grid", tip="Красные кадры — в начало списка, зелёные — в конец"),
                           btn("Исходный порядок", lambda: self.smart_sort(restore=True), "link"), None, spacing=6),
                      nav, self._sm_switch("only_bad", "Слева показывать только кадры для проверки", "Остальные миниатюры скрываются"),
                      self.l_sm_list, self.sm_list)
        # --- дополнительно
        self.sm_tier_rows = []
        tiers = vbox(spacing=3)
        for i in range(len(SM_TIERS)):
            n = QLabel("")
            n.setFixedWidth(18)
            n.setAlignment(Qt.AlignCenter)
            name = lbl("")
            tiers.addLayout(hbox(n, name, None, ibtn("up", "Важнее", lambda _=False, i=i: self.smart_move_tier(i, -1), 26, True, isize=14),
                                 ibtn("down", "Менее важно", lambda _=False, i=i: self.smart_move_tier(i, 1), 26, True, isize=14), spacing=6))
            self.sm_tier_rows.append((n, name))
        adv = card("Дополнительно",
                   lbl("Что беречь в первую очередь (сверху — важнее)", "muted"), tiers,
                   self._sm_slider("head_margin", 0, 40, "Запас вокруг головы", "Насколько оставлять место вокруг головы, % от её размера", "%"),
                   self._sm_slider("tol", 0, 10, "Допуск между ступенями", "Улучшенный метод: разница срезов меньше этой считается ничьёй — тогда решает следующая ступень (тело, кисти, руки…)", "%"),
                   self._sm_slider("tier_base", 2, 10, "Строгость к важному", "Во сколько раз каждая следующая часть важнее: чем выше, тем сильнее рамка бережёт головы за счёт мелочей", "×"),
                   self._sm_slider("sens", 0, 100, "Чувствительность поиска людей", "Выше — находит больше людей, но чаще ошибается; ниже — пропускает неуверенных", ""),
                   self._sm_slider("bg_ratio", 0, 30, "Мелкие люди на дальнем плане", "Люди мельче этой доли от самого крупного (с лицом) считаются дальним планом", "%"),
                   self._sm_switch("ignore_small", "Не учитывать мелких людей", "Люди дальнего плана вообще не влияют на рамку и не дают замечаний; выключено — они лишь менее важны"),
                   self._sm_switch("faceless_low", "Люди без лица — наинизший приоритет", "Стоящие спиной и те, у кого в кадр попала только часть тела: если рядом есть человек с лицом, ему ничего не режется, а такому — в последнюю очередь"),
                   self._sm_slider("many", 3, 30, "Групповое фото — от, чел.", "Начиная с этого числа людей кадр всегда стоит проверить", ""),
                   self._sm_slider("min_dpi", 100, 300, "Предупреждать о разрешении ниже, dpi", "Если из-за рамки разрешение печати ниже, кадр помечается", ""),
                   self._sm_slider("sample_ok", 0, 30, "Выборочно проверять «цело»", "Часть безупречных кадров тоже попадает в очередь проверки — так видно, пропустил ли детектор людей молча", "%"),
                   self._sm_switch("show_people", "Обводить найденных людей на фото", "Рамки людей и лиц поверх фото; пунктир — детектор не уверен"),
                   self._sm_switch("show_parts", "Показывать части тела и скелет", "Цветные рамки частей (Г голова, Т тело, К кисти, Р руки, Н ноги, С стопы) и скелет нейросети позы в улучшенном методе"),
                   self._sm_switch("next_after_seen", "После «Проверено» — к следующему", None),
                   self._sm_switch("gpu", "Использовать видеокарту (CUDA)", "Ускоряет поиск людей, если установлен onnxruntime-gpu"),
                   hbox(btn("Контактный лист…", self.smart_export_sheet, ico="image", tip="Картинка со всеми кадрами для проверки"),
                        btn("Решения (JSON)…", self.smart_export_json, ico="save"), spacing=6),
                   hbox(btn("Очистить кэш", self.smart_clear_cache, "link"), None, btn("Сбросить настройки", self.smart_defaults, "link")))
        self.sm_cards = [analysis, result, adv]
        self.smart_tiers_sync()
        self.smart_page_sync()
        return self._scroll(head, analysis, result, adv)

    def smart_algo_sync(self):
        """Подсказка к выбранному методу; ползунки, которые относятся только к одному из методов, гасятся."""
        if not hasattr(self, "l_sm_algo"):
            return
        enh = self.sm["algo"] == "enhanced"
        self.l_sm_algo.setText(tr("Улучшенный: части тела считаются от размера головы, а важность идёт строго по очереди — голова → тело → кисти → руки → ноги → стопы (порядок меняется ниже). Нижняя ступень никогда не вытесняет верхнюю.")
                               if enh else
                               tr("Простой: части тела по пропорциям рамки человека, срезы складываются с весами ступеней («Строгость к важному»)."))
        if hasattr(self, "l_sm_orient"):
            self.l_sm_orient.setText(tr("Человек: ИИ сам выбирает книжную или альбомную ориентацию и срезает лишнее, оставляя людей крупно, как на портрете, с небольшим запасом фона (фото может «повернуться» на 90°).")
                                     if self.sm["orient_mode"] == "person" else
                                     tr("Как у фото: горизонтальное остаётся горизонтальным, вертикальное — вертикальным. Другую ориентацию можно выбрать вручную для одного кадра."))
        en = self.sm["enabled"]
        for key, on in (("tol", enh), ("tier_base", not enh)):
            sl, val, unit = self._sm_sliders[key]
            sl.setEnabled(en and on)

    def smart_tiers_sync(self):
        for i, (n, name) in enumerate(self.sm_tier_rows):
            n.setText(str(i + 1))
            name.setText(tr(SM_TIER_RU[self.sm["priority"][i]]))

    def smart_page_sync(self):
        if not hasattr(self, "sm_cards"):
            return
        txt, level = self.smart_env_text()
        self.l_sm_env.setText(txt)
        self.l_sm_env.setStyleSheet("color: %s;" % {"ok": T["ok"], "warn": T["warn"], "bad": T["bad"]}[level])
        e = self.smart_env()
        self.b_sm_models.setVisible(e["deps_ok"] and (not e["ready"] or (self.sm["algo"] == "enhanced" and not e.get("pose"))))
        for w in self.sm_cards:
            w.setEnabled(self.sm["enabled"])
        self.smart_algo_sync()
        self.smart_sync(True)

    def smart_page_widgets_from_state(self):
        for key, (sl, val, unit) in self._sm_sliders.items():
            sl.setValue(int(self.sm[key]))
            val.setText("%d%s" % (self.sm[key], unit))
        for key, sw in self._sm_switches.items():
            sw.set(bool(self.sm[key]))
        self.b_sm_hide.blockSignals(True)
        self.b_sm_hide.setChecked(bool(self.sm.get("hide_boxes", False)))
        self.b_sm_hide.blockSignals(False)
        self.seg_sm_scope.set(self.sm["scope"])
        self.seg_sm_algo.set(self.sm["algo"])
        self.seg_sm_orient.set(self.sm["orient_mode"])
        self.smart_algo_sync()
        self.smart_tiers_sync()

    def smart_after_open(self, files=None):
        """Новые фото открыты — анализ запускается сам (если режим включён)."""
        if self.sm["enabled"] and self.sm["auto"] and self.files:
            QTimer.singleShot(250, lambda: self.smart_run(files=files, auto=True))


# ---------------------------------------------------------------- обновление с GitHub
APP_VERSION = "1.5.0"
RELEASES_API = "https://api.github.com/repos/ildargiv/KopiTehnik-Print/releases/latest"
RELEASES_PAGE = "https://github.com/ildargiv/KopiTehnik-Print/releases/latest"
GITHUB_URL = "https://github.com/ildargiv/KopiTehnik-Print"
AUTHOR = "Ildar Gaisin (Гайсин Ильдар)"
LICENSE_TEXT = "Лицензия: PolyForm Noncommercial 1.0.0. Бесплатно для личного и некоммерческого использования; для коммерческого нужно разрешение автора."
LICENSE_URL = "https://polyformproject.org/licenses/noncommercial/1.0.0"


import updater                                                   # noqa: E402


def _ver(tag):
    import re
    return tuple(int(x) for x in re.findall(r"\d+", str(tag))[:3]) or (0,)


def fetch_latest_release(timeout=8):
    """(тег, адрес страницы, файлы релиза, описание) последнего релиза на GitHub или None, если проверить не удалось."""
    import urllib.request
    try:
        rq = urllib.request.Request(RELEASES_API, headers={"User-Agent": "KopiTehnikPrint", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(rq, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
        return str(d.get("tag_name", "")), str(d.get("html_url") or RELEASES_PAGE), updater.assets_from_release(d), str(d.get("body") or "")
    except Exception:
        return None


def update_available(latest):
    return bool(latest and latest[0] and _ver(latest[0]) > _ver(APP_VERSION))


# ---------------------------------------------------------------- режим «Документ»: PDF и Word, печать с отдельным профилем
import doc_tools as dt                                          # noqa: E402

DOC_EXTS = {".pdf", ".doc", ".docx", ".docm", ".dot", ".dotx", ".rtf", ".odt", ".wps", ".xls", ".xlsx", ".xlsm", ".ods",
            ".ppt", ".pptx", ".pptm", ".pps", ".ppsx", ".odp"}


class DocView(QWidget):
    """Окно просмотра документа: пустой экран с кнопкой или постраничный просмотр PDF."""

    def __init__(self, app):
        super().__init__()
        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtPdfWidgets import QPdfView
        self.app = app
        self.doc = QPdfDocument(self)
        self.view = QPdfView(self)
        self.view.setDocument(self.doc)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.view.setPageSpacing(12)
        self.view.setStyleSheet("background: transparent; border: none;")
        self.empty = QWidget()
        self.empty.setAttribute(Qt.WA_TranslucentBackground)
        self.b_open = btn("Открыть документ…", app.doc_open, "primary", big=True, ico="open")
        el = vbox(None, hbox(None, lbl("Документ", "h1"), None), hbox(None, lbl("PDF, Word, Excel, PowerPoint и другие офисные файлы", "muted"), None),
                  hbox(None, self.b_open, None), None, spacing=10)
        self.empty.setLayout(el)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.view)
        self.setLayout(vbox(self.stack))
        self.setAcceptDrops(True)

    def load(self, pdf):
        self.doc.load(str(pdf))
        self.stack.setCurrentIndex(1 if self.doc.pageCount() > 0 else 0)
        return self.doc.pageCount()

    def clear(self):
        self.doc.close()
        self.stack.setCurrentIndex(0)

    def paintEvent(self, e):
        p = QPainter(self)
        bg = QPainterPath()
        bg.addRoundedRect(QRectF(self.rect()), 14, 14)
        p.fillPath(bg, QColor(T["canvas"]))
        p.end()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.isLocalFile():
                self.app.doc_load(Path(u.toLocalFile()))
                break


class DocMixin:
    """Режим «Документ»: открыть PDF/Word, выбрать страницы и бумагу, напечатать со своим профилем принтера.
    Правка PDF и распознавание текста запускаются в программе «КопиТехник Конвертор»."""

    def _doc_init(self):
        st = self.settings
        self.doc = {"src": None, "pdf": None, "pages": 0}
        self.d = {"paper": st.get("doc_paper") if st.get("doc_paper") in dt.PAPERS else "A4",
                  "fit": st.get("doc_fit") if st.get("doc_fit") in ("fit", "shrink", "actual") else "fit",
                  "margin": str(st.get("doc_margin", "5")), "cm_on": bool(st.get("doc_cm_on", False)), "icc": st.get("doc_icc", ""),
                  "range": "", "copies": 1}

    def _page_doc(self):
        d = self.d
        self.l_doc = lbl("Документ не открыт", wrap=True)
        self.l_doc2 = lbl("", "muted", wrap=True)
        self.b_doc_edit = btn("Редактировать PDF", lambda: self.doc_convert(False), ico="move", tip="Откроется в программе «КопиТехник Конвертор»")
        self.b_doc_ocr = btn("Распознать текст", lambda: self.doc_convert(True), ico="sparkle", tip="Распознавание в «КопиТехник Конвертор»")
        doc = card("Документ", self.l_doc, self.l_doc2, btn("Открыть документ…", self.doc_open, ico="open"),
                   self.b_doc_edit, self.b_doc_ocr)
        cb = QComboBox()
        cb.addItems(list(dt.PAPERS))
        cb.setCurrentText(d["paper"])
        cb.activated.connect(lambda _i: (d.__setitem__("paper", cb.currentText()), self.settings.__setitem__("doc_paper", cb.currentText())))
        seg = QComboBox()
        for text, val in (("По листу", "fit"), ("Только уменьшить", "shrink"), ("Как есть", "actual")):
            seg.addItem(tr(text), val)
        seg.setCurrentIndex(max(0, seg.findData(d["fit"])))
        seg.activated.connect(lambda i: (d.__setitem__("fit", seg.itemData(i)), self.settings.__setitem__("doc_fit", seg.itemData(i))))
        e_mar = QLineEdit(d["margin"])
        e_mar.setFixedWidth(46)
        e_mar.textEdited.connect(lambda v: (d.__setitem__("margin", v), self.settings.__setitem__("doc_margin", v)))
        e_rng = QLineEdit()
        e_rng.setPlaceholderText(tr("все, или 1-3, 5, 8-"))
        e_rng.textEdited.connect(lambda v: d.__setitem__("range", v))
        l_cop = lbl("1")
        l_cop.setFixedWidth(30)
        l_cop.setAlignment(Qt.AlignCenter)

        def step(k):
            d["copies"] = max(1, min(99, d["copies"] + k))
            l_cop.setText(str(d["copies"]))
        cop = hbox(ibtn("minus", "Меньше копий", lambda: step(-1), 30, True, isize=15), l_cop,
                   ibtn("plus", "Больше копий", lambda: step(1), 30, True, isize=15), spacing=4)
        self.l_doc_printer = lbl("", "muted", wrap=True)
        prn = card("Печать документа", row("Бумага", cb), row("Как страница ложится на лист", seg),
                   row("Поля, мм", e_mar), row("Страницы", e_rng), row("Копий", cop), self.l_doc_printer)
        sw = Switch(d["cm_on"])
        sw.toggled.connect(lambda on: (d.__setitem__("cm_on", bool(on)), self.settings.__setitem__("doc_cm_on", bool(on))))
        self.l_doc_icc = lbl(self._doc_icc_text(), "muted", wrap=True)
        prof = card("Профиль для документов", row("Использовать профиль принтера", sw), self.l_doc_icc,
                    btn("Выбрать профиль…", self.doc_pick_icc, ico="profile"),
                    lbl("У документов своя бумага и свой профиль, он не связан с профилем фото.", "muted", wrap=True))
        return self._scroll(doc, prn, prof)

    def _doc_icc_text(self):
        p = self.d["icc"].strip()
        return Path(p).name if p else tr("Профиль не выбран")

    def doc_pick_icc(self):
        p, _ = QFileDialog.getOpenFileName(self, tr("Цветовой профиль принтера"), self.settings.get("icc_dir") or "",
                                           "ICC (*.icc *.icm);;* (*.*)")
        if p:
            self.d["icc"] = p
            self.settings["doc_icc"] = p
            self.l_doc_icc.setText(self._doc_icc_text())

    # ---- открыть
    def doc_open(self):
        p, _ = QFileDialog.getOpenFileName(self, tr("Открыть документ"), self.start_dir(),
                                           "%s (%s);;* (*.*)" % (tr("Документы"), " ".join("*" + x for x in sorted(DOC_EXTS))))
        if p:
            self.doc_load(Path(p))

    def doc_load(self, path):
        import office_convert as oc
        ext = path.suffix.lower()
        if ext not in DOC_EXTS:
            warn(self, "Этот тип файла не поддерживается.")
            return
        pdf = path
        if ext != ".pdf":
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                pdf = oc.cached_pdf(path)
            except Exception as ex:
                warn(self, tr("Не удалось перевести документ в PDF") + ":\n%s" % ex)
                return
            finally:
                QApplication.restoreOverrideCursor()
        n = self.doc_view.load(pdf)
        if n <= 0:
            warn(self, "Не удалось открыть PDF.")
            return
        self.doc.update(src=path, pdf=pdf, pages=n)
        self.l_doc.setText(path.name)
        self.l_doc2.setText(trf("Страниц: {n}", n=n) + ("" if ext == ".pdf" else "  ·  " + tr("переведён в PDF")))

    # ---- конвертер: правка PDF и распознавание
    def doc_convert(self, ocr):
        src = self.doc["src"]
        if not src:
            info(self, "Сначала откройте документ.")
            return
        exe = dt.find_converter(self.settings.get("converter_path", ""))
        if not exe:
            box = QMessageBox(self)
            box.setWindowTitle("PhotoCrop")
            box.setText(tr("Правка PDF и распознавание делаются в программе «КопиТехник Конвертор». Она не найдена на этом компьютере."))
            go = box.addButton(tr("Скачать конвертер"), QMessageBox.AcceptRole)
            hand = box.addButton(tr("Указать Converter.exe…"), QMessageBox.ActionRole)
            box.addButton(tr("Отмена"), QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is go:
                import webbrowser
                webbrowser.open(dt.CONVERTER_RELEASES)
            elif box.clickedButton() is hand:
                p, _ = QFileDialog.getOpenFileName(self, "Converter.exe", "", "Converter.exe (*.exe)")
                if p:
                    self.settings["converter_path"] = p
                    self.doc_convert(ocr)
            return
        self.l_doc2.setText(tr("Открыт конвертер: закончите правку и сохраните."))
        QApplication.setOverrideCursor(Qt.WaitCursor)

        def work():
            try:
                self.sig.doc_edited.emit(dt.run_edit(exe, src, ocr) or "")
            except Exception as ex:
                self.sig.doc_edited.emit("!" + str(ex))
        threading.Thread(target=work, daemon=True).start()

    def _doc_edited(self, result):
        QApplication.restoreOverrideCursor()
        if result.startswith("!"):
            warn(self, tr("Не удалось запустить конвертер") + ":\n" + result[1:])
        elif result:
            self.doc_load(Path(result))
            self.l_doc2.setText(self.l_doc2.text() + "  ·  " + tr("изменён в конвертере"))
        else:
            self.l_doc2.setText(trf("Страниц: {n}", n=self.doc["pages"]))

    # ---- печать
    def print_doc(self):
        if self.saving or self.printing:
            return
        pdf = self.doc["pdf"]
        if not pdf or self.doc["pages"] <= 0:
            info(self, "Сначала откройте документ.")
            return
        pr, d = self.pr, self.d
        if not pr["printer"] or self.blob is None:
            self.show_page(2)
            info(self, "Принтер не выбран или недоступен. Выберите принтер на вкладке «Принтер».")
            return
        try:
            pages = dt.parse_range(d["range"], self.doc["pages"])
        except ValueError as ex:
            warn(self, tr("Неверный диапазон страниц") + ": %s" % ex)
            return
        cm = None
        if d["cm_on"]:
            try:
                cm = pc.cm_build(d["icc"], self.s["intent"], self.s["bpc"], self.s["embed"])
            except ValueError as ex:
                warn(self, str(ex))
                return
        try:
            margin = max(0.0, min(30.0, float(str(d["margin"]).replace(",", ".") or 0)))
        except ValueError:
            margin = 0.0
        pw, ph = dt.PAPERS[d["paper"]]
        try:
            blob = self.blob
            code = self._match_paper(pw, ph)
            blob = pc.devmode_write(blob, {"paper": code} if code is not None else {"paper_mm": [pw, ph]})
            blob = pc.prepare_blob(pr["printer"], blob, "portrait", {"paper": pc.PAPER_DRIVER, "icm_off": bool(pr["icm_off"])})
            geom = pc.printer_geometry(pr["printer"], blob, "portrait")
            ppi = pc.resolve_ppi({"ppi": pr["ppi"]}, geom)
        except Exception as ex:
            warn(self, tr("Не удалось подготовить печать") + ":\n%s" % ex)
            return
        total = len(pages) * d["copies"]
        text = "%s\n%s: %s\n%s: %s, %s: %d\n%s: %d" % (self.doc["src"].name, tr("Принтер"), pr["printer"], tr("Бумага"), d["paper"],
                                                       tr("копий"), d["copies"], tr("Листов к печати"), total)
        try:
            e_ = self._epson()
            if cm and e_.supported("ccor") and e_.color_correction_off(self.blob) is False:
                text += "\n" + tr("Внимание: цветокоррекция драйвера включена, она исказит цвет профиля. Отключите её на странице «Принтер».")
        except ValueError:
            pass
        if pcr.active(self.s["pcorr"]):
            text += "\n" + tr("Поправка принтера: включена")
        if cm:
            text += "\n%s: %s" % (tr("Профиль принтера"), cm["name"])
        if SOFT[0] and not ask(self, text + "\n\n" + tr("Начать печать?")):
            return
        name, src = self.doc["src"].name, self.doc["src"]
        self.cancel.clear()
        self.printing = True
        self._print_files = []
        self._busy(total, tr("Подготовка…"), [], "print")
        self.b_print.set_progress(0.0)
        self.b_cancel.show()
        job = dict(printer=pr["printer"], blob=blob, geom=geom, ppi=ppi, pages=pages, copies=d["copies"], fit=d["fit"], margin=margin,
                   cm=cm, pdf=str(pdf), name=name, paper=d["paper"], total=total,
                   pcorr=pcr.norm(self.s["pcorr"]) if pcr.active(self.s["pcorr"]) else None)

        def work():
            try:
                done, sent = self._doc_print_job(job)
                self.sig.printed.emit("done" if done else "cancelled", sent, "")
            except Exception as ex:
                self.sig.printed.emit("error", 0, "%s: %s" % (ex.__class__.__name__, ex))
        threading.Thread(target=work, daemon=True).start()

    def _doc_print_job(self, j):
        """В потоке: страницы рендерятся и одним заданием уходят на принтер. В журнал печати идёт только полностью отправленное задание."""
        from PySide6.QtCore import QSize
        from PySide6.QtPdf import QPdfDocument
        doc = QPdfDocument()
        if doc.load(j["pdf"]) != QPdfDocument.Error.None_:
            raise OSError("Не удалось открыть PDF для печати.")
        paper_w, paper_h = j["geom"]["paper"]
        W, H = round(paper_w / 25.4 * j["ppi"]), round(paper_h / 25.4 * j["ppi"])
        sent = 0
        with pc.PrinterJob(j["printer"], j["blob"], j["name"]) as job:
            for pi in j["pages"]:
                sz = doc.pagePointSize(pi)
                pgw, pgh = sz.width() / 72 * 25.4, sz.height() / 72 * 25.4
                x, y, w, h, rot = dt.place_page(pgw, pgh, paper_w, paper_h, j["fit"], j["margin"])
                px, py, pw_, ph_ = (round(v / 25.4 * j["ppi"]) for v in (x, y, w, h))
                rw, rh = (ph_, pw_) if rot else (pw_, ph_)
                for _ in range(j["copies"]):
                    if self.cancel.is_set():
                        job.abort()
                        return False, 0
                    qi = doc.render(pi, QSize(max(1, rw), max(1, rh)))
                    qi = qi.convertToFormat(QImage.Format_RGBA8888)
                    im = pc.Image.frombuffer("RGBA", (qi.width(), qi.height()), bytes(qi.constBits()), "raw", "RGBA", qi.bytesPerLine(), 1)
                    if rot:
                        im = im.transpose(pc.Image.ROTATE_90)
                    sheet = pc.Image.new("RGB", (W, H), "white")
                    sheet.paste(im, (px, py), im)
                    if j["cm"]:
                        sheet = pc.apply_printer_profile(sheet, None, j["cm"])
                    if j.get("pcorr"):                           # поправка принтера: после профиля, как и у фото
                        sheet = pcr.apply(sheet, j["pcorr"])
                    job.page(sheet)
                    sent += 1
                    self.sig.progress.emit(sent - 1, j["total"], "\x01" + tr("Отправляю в печать страницу") + " %d…" % (pi + 1))
            job.finish()
        try:
            import print_stats
            print_stats.record(j["printer"], 0, "%gx%g" % dt.PAPERS[j["paper"]], "document", "app", sent, [j["name"]], kind="doc")
        except Exception:
            pass
        return True, sent


LOCK_EVENTS = {QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick, QEvent.KeyPress, QEvent.KeyRelease,
               QEvent.Wheel, QEvent.ContextMenu, QEvent.Shortcut, QEvent.DragEnter, QEvent.Drop}


class MainWindow(SmartMixin, DocMixin, QMainWindow):
    _only = None                         # на время расчёта листа — печатать только это фото
    update_checked = Signal(object, bool)    # (результат проверки, показать ли ответ «обновлений нет»)
    update_progress = Signal(int, int)       # скачано, всего байт
    update_downloaded = Signal(object)       # путь к файлу или текст ошибки (str)

    def __init__(self):
        super().__init__()
        st = self.settings = pc.load_settings()
        pc.set_language(st.get("language") or i18n.detect_language(pc.LANGS))      # первый запуск: язык по локали системы
        SOFT[0] = bool(st.get("confirm_actions", False))
        ANIM_ON[0] = bool(st.get("anim", True))
        T.clear()
        T.update(THEMES.get(st.get("theme"), THEMES[DEFAULT_THEME]))
        self.theme_name = st.get("theme") if st.get("theme") in THEMES else DEFAULT_THEME
        first = lambda d, v: v if v in d else next(iter(d))
        self.s = {                                          # всё, что раньше было «переменными окна»
            "format": first(pc.FORMATS, st.get("format")), "orient": next(iter(pc.ORIENTS)),         # при каждом запуске «Авто (по фото)»: горизонтальное — горизонтально, вертикальное — вертикально
            
            "mode": next(iter(pc.MODES)), "grid": bool(st.get("grid", True)), "snap": bool(st.get("snap", True)),
            "recursive": bool(st.get("recursive", False)), "out_mode": st.get("out_mode", "orig"),
            "out_name": st.get("out_name", pc.OUT_SUBDIR), "outdir": st.get("outdir_custom", ""),
            "subfolder": bool(st.get("subfolder", False)), "copies_name": bool(st.get("copies_in_name", True)),
            "dpi": ("%g" % float(st.get("dpi", 300) or 300)),
            "resize": bool(st.get("resize", True)), "filetype": first(pc.FILETYPES, st.get("filetype")),
            "quality": int(st.get("quality", 95)), "cm_on": bool(st.get("cm_on", False)), "icc": st.get("icc", ""),
            "intent": first(pc.INTENTS, st.get("intent")), "bpc": bool(st.get("bpc", False)), "embed": bool(st.get("embed", True)),
            "pcorr": pcr.norm(st.get("pcorr")),
            "proof": False, "gamut": False, "adj_scope": "one",
            "nup": (int(st["nup"]) if str(st.get("nup", "")).isdigit() and 1 <= int(st["nup"]) <= NUP_MAX else 1), "borders": bool(st.get("borders", False)),
            "border_mm": ("%g" % float(st.get("border_mm", 3) or 3)), "fill": bool(st.get("sheet_fill", False)), "free": False,
            "cell_mode": bool(st.get("cell_mode", False)), "cell_w": ("%g" % float(st.get("cell_w", 50) or 50)), "cell_h": ("%g" % float(st.get("cell_h", 70) or 70)),
        }
        self.view = "crop"
        self.files, self.states, self.checked = [], {}, set()
        self.idx, self.src_dir = -1, None
        self.raw = self.icc = self.preview = self.adj_img = self.preview_pm = None
        self.img_size = (0, 0)
        self.gamut_pct = None
        self.show_orig = False
        self.saving = False
        self.adj_clipboard = None
        self._undo, self._redo, self._undo_key, self._undo_t = [], [], None, 0.0
        self._auto_sig = None
        self._last_check = None
        self._building = False
        self.thumbs = ThumbCache()
        self.thumbs.ready.connect(self._thumbs_ready)
        self.previews = PreviewCache()
        self.previews.ready.connect(lambda: self.sheet_view.update())
        self.slot_order, self.free, self._layout_sig = [], {}, None
        self.last_print = None
        self.agent, self.agent_server = None, None
        self.sig = SaveSignals()
        self.sig.progress.connect(self._save_progress)
        self.sig.done.connect(self._save_done)
        self.sig.sheets_ready.connect(self._print_sheets_ready)
        self.sig.printed.connect(self._print_done)
        self.sig.doc_edited.connect(self._doc_edited)
        self._doc_init()
        self.sig.queue.connect(self._queue_ready)
        self.smart_init()
        pr = self.pr = {"printer": "", "ppi": "Авто", "sharp": 0, "marks": False, "shrink": "0", "icm_off": True, "copies": 1,
                        "one_by_one": True, "pause": 2, "paper_auto": True}
        pr.update({k: v for k, v in (st.get("qt_print") or {}).items() if k in pr})
        self.printers, self.blob, self.caps = [], None, {}
        self.cancel = threading.Event()
        self.printing = False
        self._adj_timer = QTimer(self)
        self._adj_timer.setSingleShot(True)
        self._adj_timer.setInterval(40)
        self._adj_timer.timeout.connect(self._adj_redraw)
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(pc.AUTOSAVE_SECONDS * 1000)
        self._auto_timer.timeout.connect(self._autosave_tick)
        self._auto_timer.start()
        self.setWindowTitle(tr("КопиТехник Принт — кадрирование для фотопечати"))
        self.setAcceptDrops(True)
        self.resize(1400, 880)
        self.build()
        self._shortcuts()
        self._agent_timer = QTimer(self)
        self._agent_timer.setInterval(500)
        self._agent_timer.timeout.connect(self._agent_hint)
        self._agent_timer.start()
        self._lock_off = False                                  # «Забрать управление»: замок снят, пока агент не затихнет
        self._lock_banner = None
        QApplication.instance().installEventFilter(self)
        if st.get("agent_enabled", False) and "--selftest" not in sys.argv:
            self.agent_start()

    # ---------- ИИ-агент внутри окна (MCP по loopback; клиент подключается через `PhotoCropQt.exe mcp`)
    def agent_start(self):
        """Включает сервер агента. Возвращает порт или 0, если не удалось."""
        if self.agent_server is not None:
            return self.agent_server.port
        import agent_bridge as ab
        if not self.settings.get("agent_token"):
            self.settings["agent_token"] = ab.new_token()
        self._agent_inv = getattr(self, "_agent_inv", None) or AgentInvoker()
        self.agent = ga.GuiAgent(self)
        self.agent.invoke = self._agent_inv.invoke
        srv = None
        for want in (int(self.settings.get("agent_port") or 0), 0):          # прежний порт (адрес для HTTP-клиентов не меняется), иначе любой
            srv = ab.AgentHttpServer(lambda msg: pc.mcp_handle(self.agent, msg), self.settings["agent_token"], want)
            try:
                srv.start()
                break
            except OSError as ex:
                srv = None
                err = ex
        if srv is None:
            self.agent = None
            warn(self, tr("Не удалось включить ИИ-агента") + ":\n%s" % err)
            return 0
        self.settings["agent_port"] = srv.port
        self.agent_server = srv
        self.settings["agent_enabled"] = True
        return srv.port

    def agent_stop(self):
        if self.agent_server is not None:
            try:
                self.agent_server.stop()
            except Exception:
                pass
        self.agent_server, self.agent = None, None
        self.settings["agent_enabled"] = False

    AGENT_LOCK_SECONDS = 8                                      # замок держится, пока с последней команды агента прошло меньше

    def agent_locked(self):
        """True: агент сейчас работает в этом окне — ввод пользователя блокируется (окно только для просмотра)."""
        a = self.agent
        if a is None or not self.settings.get("agent_lock", True):
            return False
        busy = time.time() - a.last_request < self.AGENT_LOCK_SECONDS
        if not busy:
            self._lock_off = False                              # агент затих — замок снова будет включаться сам
        return busy and not self._lock_off

    def take_control(self):
        self._lock_off = True
        self._agent_hint()

    def _build_lock_banner(self):
        fr = QFrame(self)
        fr.setObjectName("lockbanner")
        fr.setStyleSheet("#lockbanner { background: %s; border: 1px solid %s; border-radius: 12px; }" % (T["raised"], T["accent"]))
        lab = lbl("ИИ-агент работает: окно только для просмотра")
        b = btn("Забрать управление", self.take_control, tip="Снять блокировку: агент продолжит работу, но ваши действия могут ему мешать")
        fr.setLayout(hbox(lab, b, spacing=12, margins=(14, 6, 8, 6)))
        fr.hide()
        self._lock_banner = fr
        return fr

    def _place_lock_banner(self):
        fr = self._lock_banner
        if fr is not None and fr.isVisible():
            fr.adjustSize()
            fr.move(max(8, (self.width() - fr.width()) // 2), 66)
            fr.raise_()

    def eventFilter(self, obj, ev):
        """Пока агент работает, ввод в основном окне блокируется (смотреть можно, менять нельзя)."""
        try:
            if isinstance(obj, QWidget) and ev.type() in LOCK_EVENTS and obj.window() is self and self.agent_locked():
                fr = self._lock_banner
                w = obj
                while w is not None:
                    if w is fr:
                        return False                            # кнопка «Забрать управление» работает
                    w = w.parentWidget()
                return True
        except RuntimeError:
            pass
        return super().eventFilter(obj, ev)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_lock_banner()

    def _agent_hint(self):
        """Плашка «ИИ-агент работает» в шапке и замок ввода (последняя команда агента меньше 15 / 8 секунд назад)."""
        if hasattr(self, "l_agent"):
            a = self.agent
            busy = a is not None and time.time() - a.last_request < 15 and bool(self.settings.get("agent_badge", True))
            self.l_agent.setVisible(busy)
        locked = self.agent_locked()
        if locked and self._lock_banner is None:
            self._build_lock_banner()
        if self._lock_banner is not None and self._lock_banner.isVisible() != locked:
            self._lock_banner.setVisible(locked)
            self._place_lock_banner()

    def agent_confirm_print(self, files, total):
        text = trf("ИИ-агент хочет напечатать листов: {n}.", n=total if total is not None else "?") + "\n" + tr("Принтер") + ": " + str(self.pr.get("printer"))
        return QMessageBox.question(self, "PhotoCrop", text + "\n\n" + tr("Разрешить?"), QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.Yes) == QMessageBox.Yes

    # ---------- построение окна (вызывается заново при смене языка или темы)
    def build(self):
        self._building = True
        QApplication.instance().setStyleSheet(build_qss(T))
        QApplication.setLayoutDirection(Qt.RightToLeft if pc.get_language() in i18n.RTL_LANGS else Qt.LeftToRight)
        _PIX_CACHE.clear()
        self._cop_lbls = []
        try:                                         # на узком экране (ноутбук, масштаб 125–150 %) панели делаем теснее
            self.compact = int(QApplication.primaryScreen().availableGeometry().width()) < 1600
        except Exception:
            self.compact = False
        root = QWidget()
        root.setObjectName("root")
        self.thumbs_view = ThumbView(self)
        self.canvas = CropCanvas(self)
        self.sheet_view = SheetView(self)
        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.canvas)
        self.center_stack.addWidget(self.sheet_view)
        self.doc_view = DocView(self)
        self.center_stack.addWidget(self.doc_view)
        self.overlay = SendOverlay(self.center_stack)
        outer = vbox(self._topbar(), spacing=0)
        if T.get("orn"):
            outer.addWidget(OrnBand())
        self.left_w = self._left()
        main = hbox(self.left_w, self._center(), self._right(), spacing=0)
        main.setStretch(1, 1)
        outer.addLayout(main, 1)
        root.setLayout(outer)
        self.setCentralWidget(root)
        self.fly = FlyOverlay(root)
        self._building = False
        self.center_stack.setCurrentIndex(1 if self.view == "sheet" else 0)
        self.upd_counts()
        self.sync_inspector()
        self.redraw()
        if "--selftest" not in sys.argv and not getattr(self, "_upd_wired", False):
            self._upd_wired = True
            self.update_checked.connect(self._update_result)
            if self.settings.get("check_updates", True):
                QTimer.singleShot(4000, lambda: self.check_updates(False))

    def check_updates(self, manual=True):
        """Проверка последнего релиза на GitHub в фоне; manual — ответить и когда обновлений нет."""
        threading.Thread(target=lambda: self.update_checked.emit(fetch_latest_release(), manual), daemon=True).start()

    def _update_result(self, latest, manual):
        if latest is None:
            if manual:
                warn(self, "Не удалось проверить обновления. Проверьте подключение к интернету.")
            return
        if not update_available(latest):
            if manual:
                info(self, "%s %s" % (tr("У вас последняя версия:"), APP_VERSION))
            return
        if not manual and self.settings.get("skip_update") == latest[0]:
            return
        asset = updater.pick_asset(latest[2]) if len(latest) > 2 else None
        box = QMessageBox(self)
        box.setWindowTitle(tr("Доступно обновление"))
        box.setText("%s %s → %s" % (tr("Вышла новая версия:"), APP_VERSION, latest[0]))
        if asset:
            box.setInformativeText(tr("Программа сама скачает обновление, закроется, обновится и запустится снова."))
        if len(latest) > 3 and latest[3].strip():
            box.setDetailedText(latest[3].strip()[:2500])
        go = box.addButton(tr("Обновить сейчас") if asset else tr("Открыть страницу загрузки"), QMessageBox.AcceptRole)
        page = box.addButton(tr("Открыть страницу загрузки"), QMessageBox.ActionRole) if asset else None
        skip = box.addButton(tr("Пропустить эту версию"), QMessageBox.DestructiveRole)
        box.addButton(tr("Позже"), QMessageBox.RejectRole)
        box.setDefaultButton(go)
        box.exec()
        if box.clickedButton() is go and asset:
            self._update_install(latest, asset)
        elif box.clickedButton() in (go, page):
            import webbrowser
            webbrowser.open(latest[1])
        elif box.clickedButton() is skip:
            self.settings["skip_update"] = latest[0]

    def _update_install(self, latest, asset):
        """Скачивает обновление с индикатором и запускает замену; программа закрывается и открывается уже новой."""
        dlg = QProgressDialog(trf("Скачиваю версию {v}…", v=latest[0]), tr("Отмена"), 0, 100, self)
        dlg.setWindowTitle(tr("Обновление"))
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)
        stop = threading.Event()
        dlg.canceled.connect(stop.set)

        def on_progress(got, total):
            dlg.setMaximum(100 if total else 0)
            if total:
                dlg.setValue(min(100, int(got * 100 / total)))
                dlg.setLabelText(trf("Скачиваю версию {v}: {a} из {b} МБ", v=latest[0], a="%.1f" % (got / 1048576), b="%.1f" % (total / 1048576)))

        def on_done(res):
            self.update_progress.disconnect(on_progress)
            self.update_downloaded.disconnect(on_done)
            dlg.close()
            if isinstance(res, str):
                if not stop.is_set():
                    warn(self, res + "\n\n" + tr("Скачайте новую версию вручную:") + " " + latest[1])
                return
            try:
                self.persist()
                updater.launch(res)
            except Exception as ex:
                warn(self, trf("Не удалось запустить обновление: {e}", e=ex) + "\n\n" + latest[1])
                return
            QApplication.instance().quit()

        self.update_progress.connect(on_progress)
        self.update_downloaded.connect(on_done)

        def work():
            try:
                path = updater.download(asset, progress=lambda a, b: self.update_progress.emit(a, b), cancelled=stop.is_set)
                self.update_downloaded.emit(path)
            except updater.UpdateError as ex:
                self.update_downloaded.emit(str(ex))
            except Exception as ex:
                self.update_downloaded.emit("%s" % ex)
        threading.Thread(target=work, daemon=True).start()
        dlg.show()

    def copies_chip(self):
        """Копий каждого листа: заметная цветная плашка в плавающей панели над рабочим полем (одна величина на все панели)."""
        fr = QFrame()
        fr.setObjectName("copiesq")
        fr.setToolTip(tr("Копий каждого листа при печати"))
        l = lbl(str(self.pr["copies"]))
        l.setFixedWidth(30)
        l.setAlignment(Qt.AlignCenter)
        self._cop_lbls.append(l)
        ac = T["text"]
        fr.setLayout(hbox(ibtn("copy", "Копий каждого листа при печати", None, 28, color=ac, isize=16),
                          ibtn("minus", "Меньше копий листа", lambda: self.sheet_copies(-1), 28, color=ac, isize=15), l,
                          ibtn("plus", "Больше копий листа", lambda: self.sheet_copies(1), 28, color=ac, isize=15),
                          spacing=1, margins=(5, 3, 5, 3)))
        return fr

    def _pos_width(self, txt):
        """Ширина счётчика «2 / 10» в плашке: меряем шрифтом плашки (17 px, жирный), а не обычным шрифтом подписи."""
        f = QFont(self.l_pos.font())
        f.setPixelSize(17)
        f.setWeight(QFont.Bold)
        return max(42, QFontMetrics(f).horizontalAdvance(txt) + 16)

    def nav_chip(self, sz, isz):
        """Листание фото: такая же цветная плашка, как у счётчика копий."""
        fr = QFrame()
        fr.setObjectName("copies")
        ac = T["accent_text"]
        fr.setLayout(hbox(ibtn("prev", "Предыдущее фото (←)", lambda: self.go(-1), 28, color=ac, isize=17), self.l_pos,
                          ibtn("next", "Следующее фото (→)", lambda: self.go(1), 28, color=ac, isize=17),
                          spacing=1, margins=(5, 3, 5, 3)))
        return fr

    def sheet_copies(self, d):
        self.pr["copies"] = max(1, min(99, int(self.pr["copies"]) + d))
        for l in self._cop_lbls:
            try:
                l.setText(str(self.pr["copies"]))
            except RuntimeError:
                pass

    def _topbar(self):
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(58)
        la.set_theme(T["bg"], T["text"])                         # цвета логотипа следуют теме
        brand = tr("КопиТехник Принт")
        logo = la.LogoMarkAnim(brand[:1].upper())
        name = la.BrandTitleAnim()                               # название видно и на узком экране
        name.setText(brand)
        cp = self.compact

        self._caps = []
        self._photo_only = []                        # элементы верхней панели, нужные только в режиме «Фото»

        def cap(text):                               # подпись у элемента; на узком экране скрыта (смысл — в подсказке)
            c_ = lbl(text, "muted")
            self._photo_only.append(c_)
            self._caps.append(c_)
            if cp:
                c_.hide()
            return c_
        self.l_agent = abn.AgentBadgeNeural(tr("ИИ-агент работает"))
        self.l_agent.hide()
        self.cb_format = QComboBox()
        self.cb_format.addItems(list(pc.FORMATS))
        self.cb_format.setCurrentText(self.s["format"])
        self.cb_format.setMinimumWidth(120 if self.compact else 150)
        self.cb_format.currentTextChanged.connect(lambda v: self._layout_set("format", v))
        self.mode_switch = ModeSwitch(getattr(self, "app_mode", "photo"))
        self.mode_switch.changed.connect(self.set_app_mode)
        self.seg_nup = NupPicker(self.s["nup"])
        self.seg_nup.setToolTip(tr("Сколько фото печатать на одном листе"))
        self.seg_nup.changed.connect(lambda v: self._layout_set("nup", v))
        self.seg_cell = Segmented([("По числу", False), ("По размеру", True)], bool(self.s["cell_mode"]))
        self.seg_cell.setToolTip(tr("По числу — выбираете, сколько фото на листе. По размеру — задаёте размер рамки, лист нарезается на столько таких рамок, сколько влезает."))
        self.seg_cell.changed.connect(lambda v: self._layout_set("cell_mode", bool(v)))
        self.e_cell = {}
        for k in ("cell_w", "cell_h"):
            e = QLineEdit(self.s[k])
            e.setFixedWidth(56)
            e.setAlignment(Qt.AlignCenter)
            e.textEdited.connect(lambda v, k=k: self._layout_set(k, v))
            self.e_cell[k] = e
        self.w_cell = QWidget()
        self.w_cell.setLayout(hbox(lbl("Рамка", "muted"), self.e_cell["cell_w"], lbl("×", "muted"), self.e_cell["cell_h"], lbl("мм", "muted"), None, spacing=6))
        self.l_cell_fit = lbl("", "muted", wrap=True)
        self.sw_borders = Switch(self.s["borders"])
        self.sw_borders.setToolTip(tr("Выключено — печать без полей, фото вплотную. Включено — белое поле по краю листа и между фото."))
        self.sw_borders.toggled.connect(lambda on: self._layout_set("borders", bool(on)))
        self.e_border = QLineEdit(self.s["border_mm"])
        self.e_border.setFixedWidth(46)
        self.e_border.setToolTip(tr("Поле по краю листа и расстояние между фото, мм"))
        self.e_border.textEdited.connect(lambda v: self._layout_set("border_mm", v))
        self.e_border.setEnabled(self.s["borders"])
        self.seg_view = Segmented([("Кадр", "crop"), ("Лист", "sheet")], self.view)
        self.seg_view.changed.connect(self.set_view)
        self.seg_view.setFixedHeight(38)                         # та же высота и вид, что у вкладок справа, и по центру шапки
        self.b_grid = ibtn("grid", "Сетка третей", self._toggle_grid, color=T["select"] if self.s["grid"] else T["muted"])
        more = ibtn("project", "Проект: открыть или сохранить рамки и настройки")
        menu = QMenu(more)
        menu.addAction(tr("Открыть проект…"), self.load_project)
        menu.addAction(tr("Сохранить проект…"), self.save_project)
        more.setMenu(menu)
        more.setPopupMode(QToolButton.InstantPopup)
        l = hbox(logo, name, 10, btn("Открыть", self.open_any, "primary", ico="open", tip="Открыть фото или папку (Ctrl+O)"), 10,
                 self.mode_switch, 10, cap("Бумага"), self.cb_format, 6,
                 None, self.l_agent,
                 self.seg_view, 6, self.b_grid, more, GearButton("Настройки", "Настройки программы: оформление, язык, печать", self.open_settings),
                 spacing=8, margins=(16, 0, 12, 0))
        bar.setLayout(l)
        self._photo_only += [self.cb_format, self.seg_view, self.b_grid]
        return bar

    @staticmethod
    def _logo():
        """Знак программы: три краски печати — голубая, пурпурная, жёлтая."""
        k = 3
        pm = QPixmap(24 * k, 24 * k)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(k, k)
        p.setPen(Qt.NoPen)
        for (x, y), col in (((1, 1), "#00b7eb"), ((10, 1), "#ff7a1a"), ((5.5, 9.5), "#ffd400")):
            c = QColor(col)
            c.setAlpha(215)
            p.setBrush(c)
            p.drawEllipse(QRectF(x, y, 13, 13))
        p.end()
        pm.setDevicePixelRatio(k)
        return pm

    def _left(self):
        w = QWidget()
        self.l_count = lbl("", "muted")
        head = hbox(lbl("Фото", "h1"), self.l_count, None,
                    ibtn("check_all", "Отметить все фото", lambda: self.check_all(True), 30, isize=17),
                    ibtn("check_none", "Снять все отметки", lambda: self.check_all(False), 30, isize=17),
                    ibtn("trash", "Убрать неотмеченные из списка", self.remove_unchecked, 30, isize=17), spacing=2)
        lay = vbox(head, self.thumbs_view, spacing=8, margins=(14, 12, 2, 12))
        lay.setStretch(1, 1)
        w.setLayout(lay)
        return w

    def _center(self):
        w = QWidget()
        pill = QFrame(self.canvas)
        pill.setObjectName("pill")
        self.l_pos = lbl("0 / 0")
        self.l_pos.setMinimumWidth(42)
        self.l_pos.setAlignment(Qt.AlignCenter)
        self.l_angle = lbl("0,0°", "muted")
        self.l_angle.setMinimumWidth(40)
        self.l_angle.setAlignment(Qt.AlignCenter)
        sz, isz = (30, 17) if self.compact else (34, 18)

        def ib(name, tip, slot):
            return ibtn(name, tip, slot, sz, False, None, isz)
        self.b_undo = ib("undo", "Отменить (Ctrl+Z)", self.undo)
        self.b_redo = ib("redo", "Повторить (Ctrl+Y)", self.redo)
        pill.setLayout(hbox(
            self.nav_chip(sz, isz), vsep(),
            ib("rot_l", "Повернуть фото влево на 90°", lambda: self.rotate_photo(270)),
            ib("rot_r", "Повернуть фото вправо на 90°", lambda: self.rotate_photo(90)),
            ib("mirror_h", "Отразить фото слева направо", lambda: self.flip_photo("h")),
            ib("mirror_v", "Отразить фото сверху вниз", lambda: self.flip_photo("v")),
            ib("flip", "Рамка: книжная ⇄ альбомная (R)", self.flip_frame), vsep(),
            ib("tilt_l", "Наклонить рамку влево на 0,1° (Shift+колесо — на 1°)", lambda: self.tilt(-0.1)), self.l_angle,
            ib("tilt_r", "Наклонить рамку вправо на 0,1°", lambda: self.tilt(0.1)),
            ib("level", "Выровнять рамку (0°)", lambda: self.tilt(None)), vsep(),
            self.copies_chip(), vsep(),
            ib("color", "Коррекция цвета (C)", lambda: self.show_page(1)),
            ib("reset", "Сбросить рамку этого фото", self.reset_frame), vsep(),
            self.b_undo, self.b_redo, spacing=2, margins=(5, 5, 5, 5)))
        sh = QGraphicsDropShadowEffect(pill)
        sh.setBlurRadius(30)
        sh.setOffset(0, 8)
        sh.setColor(QColor(0, 0, 0, 110))
        pill.setGraphicsEffect(sh)
        groups, cur = [], []                                  # группы кнопок панели (после каждой — разделитель)
        lay_ = pill.layout()
        for i_ in range(lay_.count()):
            w_ = lay_.itemAt(i_).widget()
            if w_ is None:
                continue
            cur.append(w_)
            if w_.objectName() == "sep":
                groups.append(cur)
                cur = []
        groups.append(cur)
        self.canvas.pill_groups = groups
        self.canvas.pill = pill
        pb = btn("Печать фото", self.print_current, ico="print", tip="Напечатать только это фото (Ctrl+Shift+P)")
        pb.setParent(self.canvas)
        pb.hide()
        self.canvas.pbtn = pb
        cb = btn("До / После", None, ico="eye", tip="Сравнить: слева снимок без правок, справа с правками. Проведите линию мышью по фото")
        cb.setCheckable(True)
        cb.setParent(self.canvas)
        cb.toggled.connect(self.canvas.set_compare)
        cb.hide()
        self.canvas.cbtn = cb
        self.l_dot = QLabel("●")
        self.l_info = lbl("", "muted")
        st = hbox(self.l_dot, self.l_info, None, spacing=8, margins=(6, 8, 6, 0))
        lay = vbox(self.center_stack, st, spacing=0, margins=(8, 12, 8, 10))
        lay.setStretch(0, 1)                     # рабочее поле забирает всю свободную высоту
        w.setLayout(lay)
        QTimer.singleShot(0, self.canvas.place_pill)
        return w

    def _right(self):
        w = QWidget()
        w.setFixedWidth(316 if self.compact else 344)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._page_main())
        self.pages.addWidget(self._page_color())
        self.pages.addWidget(self._page_print())
        self.pages.addWidget(self._page_smart())
        self.pages.addWidget(self._page_doc())
        self.seg_page = Segmented([("Макет", 0), ("Цвет", 1), ("Умная рамка", 3), ("Принтер", 2), ("Документ", 4)], 0)
        self.seg_page.group.button(4).hide()                 # вкладка «Документ» видна только в режиме документа
        self.seg_page.setStyleSheet('QPushButton[kind="seg"]{padding:6px 9px;}')       # пять вкладок должны уместиться в панели
        for b in self.seg_page.group.buttons():                 # вкладки делят ширину панели поровну: край в край с карточками
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.seg_page.layout().setStretchFactor(b, 1)
        self.seg_page.changed.connect(self.show_page)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.l_prog = lbl("", "muted", wrap=True)
        self.l_prog.hide()
        self.b_cancel = btn("Отменить печать", self.cancel.set, "link")
        self.b_cancel.hide()
        self.b_save = btn("Сохранить отмеченные", lambda: self.save(True), big=True, ico="save", tip="Ctrl+Shift+S; Ctrl+S — только текущее фото")
        self.b_print = PrintButton(tr("Печать"))
        self.b_print.setProperty("kind", "primary")
        self.b_print.setProperty("big", "true")
        self.b_print.setIcon(icon("print", T["accent_text"]))
        self.b_print.setIconSize(QSize(18, 18))
        self.b_print.setToolTip("Ctrl+P")
        self.b_print.setCursor(Qt.PointingHandCursor)
        self.b_print.clicked.connect(lambda _=False: self.print_now())
        lay = vbox(hbox(self.seg_page, margins=(0, 0, 16, 0)), self.pages, self.progress, self.l_prog, self.b_cancel, self.b_save, self.b_print,
                   spacing=10, margins=(4, 12, 14, 12))
        lay.setStretch(1, 1)
        w.setLayout(lay)
        QTimer.singleShot(0, self.reload_printers)
        return w

    # ---------- страница «Принтер» (как панель Printers and Settings в Qimage)
    def _page_print(self):
        pr = self.pr

        def combo(slot):
            c = QComboBox()
            shrinkable_combo(c, 110, 200)
            c.activated.connect(lambda _i: slot())
            return c
        self.cb_printer = combo(self._printer_changed)
        self.cb_media = combo(lambda: self._drv_set("media_type", self.cb_media))
        self.cb_paper = combo(self._paper_changed)
        self.cb_source = combo(lambda: self._drv_set("source", self.cb_source))
        self.l_drv = lbl("", "muted", wrap=True)
        self.l_paper_drv = lbl("", wrap=True)
        self.pr["paper_auto"] = True                                    # размер бумаги драйвера всегда берётся из формата листа сверху
        self.sw_border = Switch(False)
        self.sw_border.toggled.connect(lambda on: self._epson_set("border", on))
        self.sw_ccor = Switch(False)
        self.sw_ccor.toggled.connect(lambda on: self._epson_set("ccor", on))
        self.cb_quality = QComboBox()
        shrinkable_combo(self.cb_quality, 110, 200)
        self.cb_quality.activated.connect(lambda _i: self._epson_set("quality", self.cb_quality.currentData()))
        self.l_quality = WrapLabel(tr("Качество печати"))
        self.l_border = WrapLabel(tr("Печать без полей"))
        self.l_ccor = WrapLabel(tr("Отключить цветокоррекцию драйвера"))
        for c_ in (self.cb_printer, self.cb_media, self.cb_source, self.cb_quality):
            c_.setMinimumWidth(160)
            c_.setMaximumWidth(240)
        self.b_nozzle = tile("Проверка дюз", lambda: self._epson_maint("nozzle_check"), "Узор из дюз", "nozzle")
        self.b_clean = tile("Прочистка головки", lambda: self._epson_maint("clean"), "Если есть полосы", "head_clean")
        self.epson_groups = {"quality": (self.l_quality, self.cb_quality), "border": (self.l_border, self.sw_border),
                             "ccor": (self.l_ccor, self.sw_ccor), "maint": (self.b_nozzle, self.b_clean)}
        for ws in self.epson_groups.values():
            for w_ in ws:
                w_.hide()
        self.l_prof = lbl("", wrap=True)
        self.b_prof_reset = btn("Сбросить к стандарту", self.profile_reset, "link", tip="Забыть сохранённые настройки этой связки (принтер, формат, тип бумаги)")
        self.sw_cm2 = Switch(self.s["cm_on"])
        self.sw_cm2.toggled.connect(lambda on: (self._cm_set("cm_on", on), self.sw_cm.set(on)))
        self.l_icc2 = lbl("", "muted", wrap=True)
        printer = card("Принтер и бумага",
                       row("Принтер", hbox(self.cb_printer, ibtn("reset", "Обновить список принтеров", self.reload_printers, 34, True), spacing=4)),
                       row("Тип бумаги", self.cb_media), self.l_paper_drv, row("Подача", self.cb_source),
                       tile("Свойства драйвера…", self.driver_props, "Все настройки печати", "driver", "select"),
                       row(self.l_quality, self.cb_quality), row(self.l_border, self.sw_border), row(self.l_ccor, self.sw_ccor),
                       self.b_nozzle, self.b_clean,
                       tile("Тестовый лист", self.add_test_sheet, "Цвет, кожа, шкалы", "image", "select"),
                       self.l_drv, self.l_prof, hbox(self.b_prof_reset, None),
                       row("Профиль принтера", self.sw_cm2), self.l_icc2,
                       btn("Выбрать профиль…", self.open_cm_dialog, ico="profile"),
                       help=("Тип бумаги, качество и поля задаются здесь или в «Свойствах драйвера», настройки запоминаются. "
                             "Размер бумаги драйвера берётся из формата листа вверху. "
                             "Профиль внизу (в строке «Профиль: …») запоминается отдельно для каждой связки «формат, тип бумаги, качество» "
                             "и сохраняется автоматически; «Сбросить к стандарту» забывает его. "
                             "Цветокоррекцию драйвера нужно отключать, когда включён цветовой профиль принтера."))
        self.cb_ppi = QComboBox()
        shrinkable_combo(self.cb_ppi, 80, 140)
        self.cb_ppi.addItems(pc.PPI_CHOICES)
        self.cb_ppi.setCurrentText(pr["ppi"] if pr["ppi"] in pc.PPI_CHOICES else pc.PPI_CHOICES[0])
        self.cb_ppi.activated.connect(lambda _i: (pr.__setitem__("ppi", self.cb_ppi.currentText()), self.profile_save()))
        sl = self.sl_sharp = _ResetSlider(Qt.Horizontal)
        sl.setRange(0, 200)
        sl.setValue(int(pr["sharp"]))
        l_sh = self.l_sharp = lbl(str(int(pr["sharp"])), "muted")
        l_sh.setFixedWidth(28)
        sl.valueChanged.connect(lambda v: (pr.__setitem__("sharp", int(v)), l_sh.setText(str(v)), self.profile_save()))
        sl.reset.connect(lambda: sl.setValue(0))
        sw_marks = Switch(pr["marks"])
        sw_icm = self.sw_icm = Switch(pr["icm_off"])
        sw_marks.toggled.connect(lambda on: pr.__setitem__("marks", bool(on)))
        sw_icm.toggled.connect(lambda on: (pr.__setitem__("icm_off", bool(on)), self.profile_save()))
        e_shrink = self.e_shrink = QLineEdit(str(pr["shrink"]))
        e_shrink.setFixedWidth(60)
        e_shrink.setToolTip(tr("Насколько уменьшить лист, чтобы принтер не срезал края при печати без полей. 0 — не менять."))
        e_shrink.textEdited.connect(lambda v: (pr.__setitem__("shrink", v), self.profile_save()))
        screen = card("Цвет на экране", row("Имитация печати на экране", self.sw_proof), row("Показать цвета вне охвата", self.sw_gamut))
        corr = self._pcorr_card()
        proc = card("Обработка", row("Разрешение печати, ppi", self.cb_ppi),
                    hbox(lbl("Резкость"), sl, l_sh), row("Метки реза", sw_marks),
                    row("Уменьшить лист, %", e_shrink), row("Цвет Windows (ICM) отключён", sw_icm))
        sw_one = Switch(pr["one_by_one"])
        sw_one.toggled.connect(lambda on: pr.__setitem__("one_by_one", bool(on)))
        e_pause = QLineEdit(str(pr["pause"]))
        e_pause.setFixedWidth(60)
        e_pause.textEdited.connect(lambda v: pr.__setitem__("pause", v))
        bleed = self._bleed_card()
        job = card("Задание", row("Каждый лист — отдельным заданием", sw_one),
                   row("Пауза между листами, сек", e_pause))
        self.l_queue = lbl("Нажмите «Обновить», чтобы увидеть очередь.", "muted", wrap=True)
        queue = card("Очередь печати", self.l_queue,
                     hbox(btn("Обновить", self.queue_refresh), btn("Очистить", self.queue_clear), spacing=6))
        return self._scroll(self._quick_card(), printer, screen, corr, proc, bleed, job, queue, btn("Старое окно печати…", self.open_print, "link"))

    def reload_printers(self):
        self.printers = pc.list_printers()
        self.cb_printer.clear()
        self.cb_printer.addItems(self.printers)
        want = self.pr["printer"] or self.settings.get("print_printer") or ""
        name = want if want in self.printers else (self.printers[0] if self.printers else "")
        self.pr["printer"] = name
        if name:
            self.cb_printer.setCurrentText(name)
        self._load_printer()
        self._qs_refresh()

    def _printer_changed(self):
        self.pr["printer"] = self.cb_printer.currentText()
        self._load_printer()
        self._qs_refresh()

    def _load_printer(self):
        """Настройки драйвера и возможности выбранного принтера -> списки «тип бумаги», «размер», «подача»."""
        name = self.pr["printer"]
        self.blob, self.caps = None, {}
        if name:
            stored = self.settings.get("print_devmodes", {}).get(name)
            if stored:
                try:
                    b = base64.b64decode(stored)
                    if pc.devmode_valid(b):
                        self.blob = b
                except Exception:
                    pass
            if self.blob is None:
                try:
                    self.blob = pc.default_devmode(name)
                except Exception:
                    self.blob = None
            try:
                self.caps = pc.printer_capabilities(name)
            except Exception:
                self.caps = {}
        self._fill_driver()

    def _fill_driver(self):
        cur = {}
        if self.blob is not None:
            try:
                cur = pc.devmode_read(self.blob)["settings"]
            except Exception:
                cur = {}

        def fill(cb, items, code, first=None):
            cb.clear()
            if first:
                cb.addItem(first, None)
            for it in items:
                cb.addItem(it[0], it[1])
            k = cb.findData(code) if code is not None else -1
            cb.setCurrentIndex(k if k >= 0 else 0)
            cb.setEnabled(bool(items) and self.blob is not None)
        media = [(m["name"] or str(m["code"]), m["code"]) for m in self.caps.get("media_types", [])]
        bins = [(b["name"] or str(b["code"]), b["code"]) for b in self.caps.get("bins", [])]
        papers = [("%s  (%g×%g)" % (p_["name"], p_["width_mm"], p_["height_mm"]), p_["code"])
                  for p_ in self.caps.get("papers", []) if p_.get("width_mm")]
        fill(self.cb_media, media, cur.get("media_type"))
        fill(self.cb_source, bins, cur.get("source"))
        fill(self.cb_paper, papers, None if self.pr["paper_auto"] else cur.get("paper"), tr("Авто — по размеру листа"))
        if not self.printers:
            self.l_drv.setText(tr("Принтеры не найдены. Листы можно сохранить в файлы."))
        elif self.blob is None:
            self.l_drv.setText(tr("Не удалось получить настройки драйвера этого принтера."))
        else:
            self.l_drv.setText("")
        self.l_drv.setVisible(bool(self.l_drv.text()))
        self._fill_epson()
        self.l_icc2.setText(self.l_icc.text())
        if self.pr["paper_auto"] or self.cb_paper.currentData() is None:
            self.l_paper_drv.setText(trf("Бумага в драйвере: авто, {f}", f=self.s["format"]))
        else:
            self.l_paper_drv.setText(trf("Бумага в драйвере: {p} (выбрана вручную)", p=self.cb_paper.currentText()))
        self.profile_apply()

    def _save_blob(self, profile=True):
        """profile=False — когда меняется часть ключа профиля (бумага, качество): настройки новой связки
        нужно подставить из её профиля, а не затереть текущими."""
        if self.pr["printer"] and self.blob:
            self.settings.setdefault("print_devmodes", {})[self.pr["printer"]] = base64.b64encode(self.blob).decode()
            self.settings["print_printer"] = self.pr["printer"]
            if profile:
                self.profile_save()

    # ---------- профили печати: свои настройки для связки «принтер + формат + тип бумаги»
    PROF_COLOR = ("cm_on", "icc", "intent", "bpc", "embed", "pcorr")  # лежат в self.s
    PROF_PR = ("icm_off", "ppi", "sharp", "shrink")                  # лежат в self.pr

    def _quality_name(self):
        """Название режима качества Epson в текущих настройках драйвера (пусто, если модель не изучена)."""
        try:
            e = self._epson()
            v = e.get(self.blob, "quality") if self.blob is not None else None
            return next((tr(n) for k, n in e.quality_modes(self.blob) if k == v), "") if v is not None else ""
        except (ValueError, struct.error):
            return ""

    def profile_key(self):
        media = self.cb_media.currentText() if hasattr(self, "cb_media") and self.cb_media.isEnabled() and self.cb_media.count() else ""
        return " | ".join((self.pr.get("printer", ""), self.s["format"], media, self._quality_name()))

    @staticmethod
    def _kparts(key):
        """Ключ профиля -> (принтер, формат, бумага, качество); старые ключи без качества дополняются пустым."""
        p = key.split(" | ")
        return tuple(p + [""] * (4 - len(p)))[:4]

    def profile_title(self, key=None):
        return " · ".join(x for x in self._kparts(key or self.profile_key())[1:] if x)

    def _profiles(self):
        return self.settings.setdefault("print_profiles", {})

    def profile_save(self):
        """Автосохранение: любое изменение цвета/обработки/драйвера запоминается за текущей связкой."""
        if getattr(self, "_prof_lock", False) or self._building or not self.pr.get("printer") or not hasattr(self, "l_prof"):
            return
        prof = {k: self.s[k] for k in self.PROF_COLOR}
        prof["pcorr"] = pcr.norm(self.s["pcorr"])
        prof.update({k: self.pr[k] for k in self.PROF_PR})
        if self.blob:
            prof["blob"] = base64.b64encode(self.blob).decode()
        self._profiles()[self.profile_key()] = prof
        self.profile_label()

    def profile_apply(self):
        """Выбрали принтер / формат / тип бумаги: подставляем сохранённые для связки настройки (или ближайшие)."""
        if getattr(self, "_prof_lock", False) or not hasattr(self, "l_prof") or not self.pr.get("printer"):
            return
        key = self.profile_key()
        profs = self._profiles()
        prof, how = profs.get(key), "own"
        if prof is None:                                             # ближайшая: тот же принтер и тип бумаги, другой формат
            pr_, _fmt, media, qual = self._kparts(key)
            near = [k for k in profs if self._kparts(k)[0] == pr_ and self._kparts(k)[2] == media and self._kparts(k)[3] == qual]
            if near:
                prof, how = profs[near[0]], near[0]
        self._prof_lock = True
        try:
            if prof:
                self._building = True
                for k in self.PROF_COLOR:
                    if k in prof:
                        self.s[k] = pcr.norm(prof[k]) if k == "pcorr" else prof[k]
                if "pcorr" not in prof:
                    self.s["pcorr"] = pcr.default()
                for k in self.PROF_PR:
                    if k in prof:
                        self.pr[k] = prof[k]
                try:
                    self.sw_cm.set(bool(self.s["cm_on"]))
                    self.sw_cm2.set(bool(self.s["cm_on"]))
                    self.sw_icm.set(bool(self.pr["icm_off"]))
                    self.cb_ppi.setCurrentText(self.pr["ppi"] if self.pr["ppi"] in pc.PPI_CHOICES else pc.PPI_CHOICES[0])
                    self.sl_sharp.setValue(int(self.pr["sharp"]))
                    self.l_sharp.setText(str(int(self.pr["sharp"])))
                    self.e_shrink.setText(str(self.pr["shrink"]))
                    self.pcorr_sync()
                except (AttributeError, RuntimeError):
                    pass
                self._building = False
                if how == "own" and prof.get("blob"):                # настройки драйвера этой связки (качество, подача...)
                    try:
                        b = base64.b64decode(prof["blob"])
                        if pc.devmode_valid(b) and b != self.blob:
                            self.blob = b
                            self.settings.setdefault("print_devmodes", {})[self.pr["printer"]] = prof["blob"]
                            self._fill_driver()
                    except Exception:
                        pass
                self.cm_changed()
            else:                                                    # у связки нет своего профиля: чужая поправка к ней не относится
                self.s["pcorr"] = pcr.default()
                self.pcorr_sync()
        finally:
            self._building = False
            self._prof_lock = False
        self.profile_label(how if prof else None)

    # ---------- поправка принтера: подгоняет отпечаток под экран, на экране не видна
    PC_ZONES = (("shadows", "Тени"), ("mids", "Средние"), ("lights", "Света"))

    def _pc_slider(self, label, get, setv, left="", right=""):
        s = _ResetSlider(Qt.Horizontal)
        s.setRange(-100, 100)
        val = lbl("0", "muted")
        val.setFixedWidth(34)
        val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        def moved(v):
            val.setText("%+d" % v if v else "0")
            if getattr(self, "_pc_lock", False):
                return
            setv(float(v))
            self.profile_save()
        s.valueChanged.connect(moved)
        s.reset.connect(lambda: s.setValue(0))
        s.setToolTip(((left + " ← → " + right) if left else "") + ("\n" if left else "") + tr("Двойной щелчок — сбросить"))
        self._pc_rows.append((s, get, val))
        name = lbl(label)
        name.setFixedWidth(70)
        return hbox(name, s, val, spacing=6)

    def _pcorr_card(self):
        self._pc_rows, self._pc_zone, self._pc_sel, self._pc_lock = [], "mids", 0, False
        pcv = lambda: self.s["pcorr"]

        def tone_get(i):
            return lambda: pcv()["tone"][self._pc_zone][i]

        def tone_set(i):
            def f(v):
                pcv()["tone"][self._pc_zone][i] = v
            return f

        def sel_get(i):
            return lambda: pcv()["sel"][self._pc_sel][i]

        def sel_set(i):
            def f(v):
                pcv()["sel"][self._pc_sel][i] = v
            return f

        def key_get(k):
            return lambda: pcv()[k]

        def key_set(k):
            def f(v):
                pcv()[k] = v
            return f
        self.sw_pcorr = Switch(bool(pcv()["on"]))
        self.sw_pcorr.toggled.connect(lambda on: (pcv().__setitem__("on", bool(on)), self.pcorr_sync(), self.profile_save()))
        self.seg_pc_zone = Segmented([(n, z) for z, n in self.PC_ZONES], "mids")
        self.seg_pc_zone.changed.connect(lambda z: (setattr(self, "_pc_zone", z), self.pcorr_sync()))
        names = [("Красный", 0), ("Жёлтый", 1), ("Зелёный", 2), ("Голубой", 3), ("Синий", 4), ("Пурпурный", 5)]
        self.seg_pc_sel = Segmented([(n, i) for n, i in names], 0)
        self.seg_pc_sel.changed.connect(lambda i: (setattr(self, "_pc_sel", i), self.pcorr_sync()))
        for b in self.seg_pc_sel.group.buttons():
            b.setStyleSheet("padding:6px 5px;")
        self.l_pcorr = lbl("", "muted", wrap=True)
        self.l_pc_prof = lbl("", "muted", wrap=True)
        body = vbox(
            hint("Подгоняет отпечаток под экран. На экране не видна, действует только при печати фото и документов, с профилем принтера и без него."),
            lbl("Нейтраль (серый)", "muted"), self.seg_pc_zone,
            self._pc_slider("Тепло", tone_get(0), tone_set(0), "холоднее", "теплее"),
            self._pc_slider("Пурпур", tone_get(1), tone_set(1), "зеленее", "пурпурнее"),
            lbl("По цветам", "muted"), self.seg_pc_sel,
            self._pc_slider("Оттенок", sel_get(0), sel_set(0)),
            self._pc_slider("Насыщ.", sel_get(1), sel_set(1)),
            self._pc_slider("Яркость", sel_get(2), sel_set(2)),
            lbl("Общее", "muted"),
            self._pc_slider("Гамма", key_get("gamma"), key_set("gamma"), "темнее", "светлее"),
            self._pc_slider("Цвета", key_get("sat"), key_set("sat"), "бледнее", "ярче"),
            self.l_pcorr, self.l_pc_prof,
            hbox(btn("Сбросить", self.pcorr_reset), btn("Тестовая страница", self.add_pcorr_test, ico="image"),
                 btn("Тестовый лист", self.add_test_sheet, ico="image"), None, spacing=6),
            spacing=6)
        self.w_pcorr_body = QWidget()
        self.w_pcorr_body.setLayout(body)
        body.setContentsMargins(0, 0, 0, 0)
        c = card("Поправка принтера", row("Включить для этой бумаги", self.sw_pcorr), self.w_pcorr_body)
        self.pcorr_sync()
        return c

    def pcorr_sync(self):
        """Показать значения поправки текущей связки в ползунках (профиль печати подставил свои)."""
        if not hasattr(self, "_pc_rows"):
            return
        c = self.s["pcorr"] = pcr.norm(self.s["pcorr"])
        self._pc_lock = True
        try:
            for s_, get, val in self._pc_rows:
                v = int(round(get()))
                s_.setValue(v)
                val.setText("%+d" % v if v else "0")
            self.sw_pcorr.set(bool(c["on"]))
            self.w_pcorr_body.setEnabled(bool(c["on"]))
            self.l_pc_prof.setText(trf("Относится к профилю печати: {t}", t=self.profile_title()) if self.pr.get("printer")
                                   else tr("Принтер не выбран: поправка запомнится за связкой «принтер + формат + бумага» после выбора принтера."))
            self.l_pcorr.setText(tr("Поправка включена и будет применена при печати.") if pcr.active(c)
                                 else (tr("Включено, но все значения нулевые.") if c["on"] else tr("Выключена: печать без поправки.")))
        finally:
            self._pc_lock = False

    def pcorr_reset(self):
        on = self.s["pcorr"]["on"]
        self.s["pcorr"] = pcr.default()
        self.s["pcorr"]["on"] = on
        self.pcorr_sync()
        self.profile_save()

    def add_pcorr_test(self):
        """Тестовая страница для подбора поправки: размера листа -> в список фото."""
        short, long_, tag = pc.FORMATS[self.s["format"]]
        w, h = (long_, short) if pc.ORIENTS[self.s["orient"]] == "landscape" else (short, long_)
        d = Path(tempfile.gettempdir()) / "PhotoCrop"
        d.mkdir(parents=True, exist_ok=True)
        p = d / ("Тест_поправки_%s.png" % tag)
        pcr.make_test_page(w, h, 300).save(p, dpi=(300, 300))
        self.load_files([p], add=True)

    def add_test_sheet(self):
        """Тестовый лист печати (клин, цвета, кожа, градиенты, резкость) на выбранный формат -> в список фото."""
        import test_sheet
        short, long_, tag = pc.FORMATS[self.s["format"]]
        w, h = (long_, short) if pc.ORIENTS[self.s["orient"]] == "landscape" else (short, long_)
        d = Path(tempfile.gettempdir()) / "PhotoCrop"
        d.mkdir(parents=True, exist_ok=True)
        p = d / ("Тестовый_лист_%s.png" % tag)
        test_sheet.build(w, h, 300).save(p, dpi=(300, 300))
        self.load_files([p], add=True)

    def profile_label(self, how="own"):
        if not hasattr(self, "l_prof"):
            return
        key = self.profile_key()
        own = key in self._profiles()
        if own:
            txt = trf("Профиль: {t}", t=self.profile_title(key))
        elif how and how != "own":
            txt = trf("Профиль: {t} (взято из «{n}»)", t=self.profile_title(key), n=self.profile_title(how))
        else:
            txt = trf("Профиль: {t} (общие настройки)", t=self.profile_title(key))
        self.l_prof.setText(txt)
        self.b_prof_reset.setVisible(own)

    def profile_reset(self):
        key = self.profile_key()
        if key in self._profiles() and ask(self, "Забыть сохранённые настройки этой связки и вернуть стандартные?"):
            del self._profiles()[key]
            self.s.update(cm_on=False, icc="", bpc=False, embed=True, pcorr=pcr.default())
            self.pr.update(icm_off=True, ppi="Авто", sharp=0, shrink="0")
            self._prof_lock = True
            try:
                self.sw_cm.set(False)
                self.sw_cm2.set(False)
                self.sw_icm.set(True)
                self.cb_ppi.setCurrentText(pc.PPI_CHOICES[0])
                self.sl_sharp.setValue(0)
                self.e_shrink.setText("0")
                self.pcorr_sync()
            finally:
                self._prof_lock = False
            self.cm_changed()
            self.profile_label(None)

    def _drv_set(self, field, cb):
        code = cb.currentData()
        if self.blob is None or code is None:
            return
        try:
            e = self._epson()
            nb = e.set_media(self.blob, code) if field == "media_type" and e.recipe else pc.devmode_write(self.blob, {field: int(code)})
            self.blob = pc.merge_devmode(self.pr["printer"], nb)
            self._save_blob(profile=field not in ("media_type",))
        except Exception as ex:
            warn(self, str(ex))
        self._fill_driver()

    def _epson(self):
        return ep.EpsonPriv(self.pr.get("printer", ""), ep.load_profiles(str(pc.AGENT_DIR / "epson_profiles.json")),
                           pc.printer_driver_name(self.pr.get("printer", "")))

    def _fill_epson(self):
        """Поля «качество», «без полей», «цветокоррекция» и кнопки обслуживания видны, только если для модели известны смещения."""
        e = self._epson()
        vis = {k: False for k in self.epson_groups}
        if self.blob is not None:
            try:
                for k, feat in (("quality", "quality"), ("border", "border"), ("ccor", "ccor"), ("maint", "maint")):
                    vis[k] = e.supported(feat)
                if vis["border"]:
                    self.sw_border.set(bool(e.get(self.blob, "border")))
                if vis["ccor"]:
                    self.sw_ccor.set(bool(e.color_correction_off(self.blob)))
                if vis["quality"]:
                    self.cb_quality.clear()
                    for v, name in e.quality_modes(self.blob):
                        self.cb_quality.addItem(tr(name), v)
                    self.cb_quality.setCurrentIndex(max(0, self.cb_quality.findData(e.get(self.blob, "quality"))))
            except (ValueError, struct.error):
                vis = {k: False for k in self.epson_groups}
        for k, ws in self.epson_groups.items():
            for w_ in ws:
                w_.setVisible(vis[k])

    def _epson_maint(self, action):
        port = pc.printer_port_name(self.pr.get("printer", "")).upper()
        if port.startswith(("FILE", "NUL", "PORTPROMPT")):
            warn(self, tr("Принтер не подключён: очередь печатает в файл. Команда обслуживания никуда не отправлена."))
            return
        text = {"nozzle_check": "Напечатать тест дюз? Будет израсходовано немного чернил и бумаги.",
                "clean": "Запустить прочистку печатающей головки? Тратит чернила и заполняет ёмкость отработки; делайте её, только если тест дюз показал пропуски."}[action]
        if not self._epson().maintenance_verified():
            text += " " + "Для этой модели команда стандартная для Epson, но на ней ещё не проверялась: если принтер не отреагирует, воспользуйтесь кнопками на самом принтере или в драйвере."
        if not ask(self, tr(text)):
            return
        b = self.b_nozzle if action == "nozzle_check" else self.b_clean
        b.busy()
        QTimer.singleShot(120 if ANIM_ON[0] else 0, lambda: self._epson_maint_send(action, b))     # кадр анимации успевает отрисоваться

    def _epson_maint_send(self, action, b):
        try:
            self._epson().maintenance(self.pr["printer"], action)
        except Exception as ex:
            b.done(False)
            warn(self, tr("Не удалось отправить команду принтеру") + ":\n%s" % ex)
            return
        b.done(True)

    def _epson_set(self, feature, on):
        if self.blob is None or getattr(self, "_prof_lock", False):
            return
        e = self._epson()
        try:
            if feature == "ccor":
                nb = e.set_color_correction_off(self.blob, on)
            else:
                nb = e.set(self.blob, feature, on)
            merged = pc.merge_devmode(self.pr["printer"], nb)
            if feature == "border" and on and e.recipe:
                m0 = struct.unpack_from("<I", self.blob, 196)[0]
                m1 = struct.unpack_from("<I", merged, 196)[0]
                if m0 != m1:
                    warn(self, trf("Печать без полей доступна только на фотобумаге: тип бумаги изменён на {m}. После отключения «Без полей» выберите нужный тип бумаги заново.", m=m1))
            if feature == "quality" and e.get(merged, "quality") != on:
                warn(self, tr("Драйвер не принял это качество печати. Выберите его в «Свойствах драйвера»."))
            else:
                self.blob = merged
                self._save_blob(profile=feature != "quality")
                if feature == "border" and on and e.get(merged, "border") is False:
                    warn(self, tr("Драйвер не включил печать без полей: для этого размера бумаги или типа бумаги она недоступна."))
        except Exception as ex:
            warn(self, str(ex))
        pc.clear_geom_cache()
        self._fill_driver()

    # ---------- быстрый старт: три ячейки «принтер + бумага + качество + формат + цвет»
    QS_COLORS = {pqk.GREEN: "#3fb950", pqk.ORANGE: "#f0883e", pqk.RED: "#e5534b", pqk.GRAY: ""}

    def _qs_slots(self):
        """Три ячейки текущего принтера: у каждого принтера свои."""
        name = self.pr.get("printer", "")
        store = pqk.norm_store(self.settings.get("print_quick"), name)
        self.settings["print_quick"] = store
        return store[name]

    def _quick_card(self):
        """Три строки: кнопка-ячейка на всю ширину и справа маленькие «сохранить» и «переименовать»."""
        self.qs_btns, self.qs_save, self.qs_ren = [], [], []
        rows = []
        for i in range(pqk.SLOTS):
            b = MotionButton("")
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setMinimumWidth(60)
            b.clicked.connect(lambda _=False, i=i: self._qs_apply(i))
            sv = ibtn("save", "Сохранить сюда текущие настройки", lambda i=i: self._qs_save(i), 34, True)
            rn = ibtn("edit", "Переименовать", lambda i=i: self._qs_rename(i), 34, True)
            self.qs_btns.append(b)
            self.qs_save.append(sv)
            self.qs_ren.append(rn)
            rows.append(hbox(b, sv, rn, spacing=6))
        self.l_qs = lbl("", "muted", wrap=True)
        self.l_qs.hide()
        card_ = card("Быстрый старт", *rows, self.l_qs,
                     help=("Ячейки привязаны к принтеру: у каждого принтера свои три, при смене принтера показываются только его. Ячейка запоминает формат листа, тип бумаги, качество, «без полей», цветокоррекцию драйвера, "
                           "цветовой профиль и обработку. Нажмите на ячейку, чтобы всё выставить разом; значок дискеты сохраняет "
                           "текущие настройки в ячейку. Зелёная рамка: ячейка сохранена. Серая: ячейка пуста."))
        self._qs_refresh()
        return card_

    def _qs_refresh(self):
        if not hasattr(self, "qs_btns"):
            return
        slots = self._qs_slots()
        printers = getattr(self, "printers", [])
        for i, sl in enumerate(slots):
            st = pqk.status(sl, printers)
            col = self.QS_COLORS[st]
            b = self.qs_btns[i]
            nm = tr(sl["name"]) if sl.get("empty") else sl["name"]
            b.setText(("" if sl.get("empty") else "● ") + (nm if len(nm) <= 20 else nm[:19] + "…"))
            b.setStyleSheet("QPushButton { border: 2px solid %s; border-radius: 8px; padding: 8px 4px; font-size: 12px; }" % col if col else "")
            b.setToolTip(tr("Пустая ячейка") if sl.get("empty") else sl["name"] + "\n" + self._qs_describe(sl))
            self.qs_ren[i].setEnabled(not sl.get("empty"))

    def _qs_describe(self, sl):
        s = sl["state"]
        parts = [sl.get("printer") if sl.get("bound") else tr("без привязки к принтеру"), s.get("format", ""), s.get("media", ""), s.get("quality", "")]
        if s.get("icc"):
            parts.append(Path(s["icc"]).name)
        return " · ".join(x for x in parts if x)

    def _qs_capture(self):
        """Текущие настройки печати одним словарём."""
        st = {k: self.s[k] for k in self.PROF_COLOR}
        st["pcorr"] = pcr.norm(self.s["pcorr"])
        st.update({k: self.pr[k] for k in self.PROF_PR})
        st["format"] = self.s["format"]
        st["media"] = self.cb_media.currentText() if self.cb_media.isEnabled() and self.cb_media.count() else ""
        st["quality"] = self._quality_name()
        if self.blob:
            st["blob"] = base64.b64encode(self.blob).decode()
        return st

    def _qs_save(self, i):
        slots = self._qs_slots()
        old = slots[i]
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Сохранить быстрый старт"))
        name = QLineEdit(old["name"] if not old.get("empty") else "")
        name.setPlaceholderText(tr("Например: матовая, высокое, зеркально"))
        name.setMaxLength(24)
        who = lbl(trf("Принтер: {p}", p=self.pr.get("printer") or "—"), "muted")
        ok, cancel = btn("Сохранить", None, "primary"), btn("Отмена")
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        dlg.setLayout(vbox(lbl("Название"), name, who, hbox(None, cancel, ok), spacing=8, margins=(14, 14, 14, 14)))
        dlg.setMinimumWidth(380)
        if not dlg.exec():
            return
        nm = " ".join(name.text().split())[:24] or "Быстрый старт %d" % (i + 1)
        printer = self.pr.get("printer", "")
        slots[i] = {"name": nm, "bound": True, "printer": printer,
                    "model": self._epson().model or "", "state": self._qs_capture()}
        self.persist()
        self._qs_refresh()

    def _qs_rename(self, i):
        slots = self._qs_slots()
        if slots[i].get("empty"):
            return
        dlg = QInputDialog(self)
        dlg.setWindowTitle(tr("Переименовать"))
        dlg.setLabelText(tr("Название ячейки"))
        dlg.setTextValue(slots[i]["name"])
        dlg.setOkButtonText(tr("Готово"))
        dlg.setCancelButtonText(tr("Отмена"))
        if not dlg.exec():
            return
        nm = " ".join(dlg.textValue().split())[:24]
        if nm:
            slots[i]["name"] = nm
            self.persist()
            self._qs_refresh()

    def _qs_apply(self, i):
        """Применить ячейку: принтер (если привязана), формат, настройки драйвера (бумага, качество, поля,
        цветокоррекция), цветовой профиль, обработка. Настройки драйвера — только для того же принтера/модели."""
        sl = self._qs_slots()[i]
        if sl.get("empty"):
            info(self, tr("Ячейка пуста. Настройте всё как нужно и нажмите «Сохранить» под кнопкой."))
            return
        st, notes = sl["state"], []
        self._prof_lock = True
        try:
            if sl.get("bound"):
                if sl["printer"] in self.printers:
                    if self.pr["printer"] != sl["printer"]:
                        self.cb_printer.setCurrentText(sl["printer"])
                        self._printer_changed()
                else:
                    notes.append(trf("Принтер «{p}» не найден, оставлен текущий.", p=sl["printer"]))
            if st.get("format") in pc.FORMATS:
                self.cb_format.setCurrentText(st["format"])
            if st.get("blob"):
                if pqk.driver_compatible(sl, self.pr.get("printer", ""), ep.model_of, self._epson().model):
                    try:
                        b = base64.b64decode(st["blob"])
                        if pc.devmode_valid(b):
                            self.blob = b
                            self._save_blob(profile=False)
                            self._fill_driver()
                    except Exception:
                        notes.append(tr("Настройки драйвера не удалось применить."))
                else:
                    notes.append(tr("Настройки драйвера (бумага, качество) относятся к другой модели и не применены."))
            self._building = True
            for k in self.PROF_COLOR:
                if k in st:
                    self.s[k] = pcr.norm(st[k]) if k == "pcorr" else st[k]
            for k in self.PROF_PR:
                if k in st:
                    self.pr[k] = st[k]
            try:
                self.sw_cm.set(bool(self.s["cm_on"]))
                self.sw_cm2.set(bool(self.s["cm_on"]))
                self.sw_icm.set(bool(self.pr["icm_off"]))
                self.cb_ppi.setCurrentText(self.pr["ppi"] if self.pr["ppi"] in pc.PPI_CHOICES else pc.PPI_CHOICES[0])
                self.sl_sharp.setValue(int(self.pr["sharp"]))
                self.l_sharp.setText(str(int(self.pr["sharp"])))
                self.e_shrink.setText(str(self.pr["shrink"]))
                self.pcorr_sync()
            except (AttributeError, RuntimeError):
                pass
        finally:
            self._building = False
            self._prof_lock = False
        self.cm_changed()
        self.profile_label()
        if self._ccor_on() and self.s.get("cm_on") and self.s.get("icc", "").strip():
            notes.append(tr("Цветокоррекция драйвера включена при цветовом профиле."))
        self.l_qs.setText(" ".join(notes))
        self.l_qs.setVisible(bool(notes))

    def _ccor_on(self):
        """True, если у модели известна цветокоррекция драйвера и она включена (искажает цвет профиля)."""
        try:
            e = self._epson()
            return self.blob is not None and e.supported("ccor") and e.color_correction_off(self.blob) is False
        except (ValueError, struct.error):
            return False

    def _ccor_check(self):
        """Выбрали цветовой профиль, а цветокоррекция драйвера включена: предупредить и предложить отключить."""
        if self.s.get("cm_on") and self.s.get("icc", "").strip() and self._ccor_on():
            if ask(self, tr("Цветокоррекция драйвера включена, она исказит цвет цветового профиля. Отключить её сейчас?")):
                self._epson_set("ccor", True)

    def _epson_summary(self):
        """Строки для окна подтверждения печати: тип бумаги, качество, поля, цветокоррекция драйвера."""
        out = []
        try:
            e = self._epson()
            if self.cb_media.isEnabled() and self.cb_media.count():
                out.append("%s: %s" % (tr("Тип бумаги"), self.cb_media.currentText()))
            q = self._quality_name()
            if q:
                out.append("%s: %s" % (tr("Качество печати"), q))
            if e.supported("border"):
                out.append("%s: %s" % (tr("Печать без полей"), tr("да") if e.get(self.blob, "border") else tr("нет")))
            if e.supported("ccor"):
                out.append("%s: %s" % (tr("Цветокоррекция драйвера"), tr("включена") if self._ccor_on() else tr("отключена")))
        except (ValueError, struct.error):
            pass
        return out

    def _paper_changed(self):
        code = self.cb_paper.currentData()
        self.pr["paper_auto"] = code is None
        if code is not None:
            self._drv_set("paper", self.cb_paper)

    def driver_props(self):
        if not self.pr["printer"] or self.blob is None:
            info(self, "Принтер не выбран или недоступен.")
            return
        try:
            new = pc.edit_devmode_dialog(self.pr["printer"], self.blob, int(self.winId()))
        except Exception as ex:
            warn(self, tr("Не удалось открыть свойства принтера") + ":\n%s" % ex)
            return
        if new:
            self.blob = new
            self._save_blob()
            self._fill_driver()

    def _match_paper(self, PW, PH):
        """Бумага драйвера того же размера, что и лист (с допуском 1,5 мм) -> код или None."""
        for p_ in self.caps.get("papers", []):
            w, h = p_.get("width_mm"), p_.get("height_mm")
            if w and h and abs(min(w, h) - PW) <= 1.5 and abs(max(w, h) - PH) <= 1.5:
                return p_["code"]
        return None

    def print_current(self):
        """Печать только открытого сейчас фото (кнопка в углу окна просмотра)."""
        cur = self.cur()
        if not cur:
            info(self, "Нет открытого фото для печати.")
            return
        self.print_now(only=cur[0])

    def print_now(self, only=None):
        """Печать прямо из этого окна: листы собираются и уходят на выбранный принтер.
        only — напечатать только это фото (остальные отметки не трогаются)."""
        if getattr(self, "app_mode", "photo") == "doc":
            return self.print_doc()
        if self.saving or self.printing:
            return
        files = [only] if only is not None else self.checked_files()
        if not files:
            info(self, "Ни одно фото не отмечено. Отметьте нужные («+» в углу превью).")
            return
        pr = self.pr
        if not pr["printer"] or self.blob is None:
            self.show_page(2)
            info(self, "Принтер не выбран или недоступен. Выберите принтер на вкладке «Принтер».")
            return
        cm = None
        if self.s["cm_on"]:
            try:
                cm = self.cm_build()
            except ValueError as ex:
                warn(self, str(ex))
                return
        try:
            self._only = only
            try:
                plan, photos, o, L = self.sheet_plan()
            finally:
                self._only = None
            if not plan["sheets"]:
                return
            num = lambda v, d: float(str(v).replace(",", ".")) if str(v).strip() else d
            o.update(sheet_copies=int(pr["copies"]), one_by_one=bool(pr["one_by_one"]), job_pause=max(0.0, min(60.0, num(pr["pause"], 2))),
                     marks=bool(pr["marks"]), sharp=float(pr["sharp"]), shrink_pct=num(pr["shrink"], 0), ppi=pr["ppi"])
            blob = self.blob
            if pr["paper_auto"]:
                code = self._match_paper(L["PW"], L["PH"])
                blob = pc.devmode_write(blob, {"paper": code} if code is not None else {"paper_mm": [L["PW"], L["PH"]]})
            blob = pc.prepare_blob(pr["printer"], blob, "portrait", {"paper": pc.PAPER_DRIVER, "icm_off": bool(pr["icm_off"])})
            geom = pc.printer_geometry(pr["printer"], blob, "portrait")
        except Exception as ex:
            warn(self, tr("Не удалось подготовить печать") + ":\n%s" % ex)
            return
        gw, gh = geom["paper"]
        total = len(plan["sheets"]) * int(pr["copies"])
        text = ("%s\n" % only.name if only is not None else "") + "%s: %s\n%s: %g×%g %s\n%s: %d" % (tr("Принтер"), pr["printer"], tr("Бумага в драйвере"), round(gw, 1), round(gh, 1), tr("мм"),
                                                 tr("Листов к печати"), total)
        for ln in self._epson_summary():
            text += "\n" + ln
        if pcr.active(self.s["pcorr"]):
            text += "\n" + tr("Поправка принтера: включена")
        if cm:
            text += "\n%s: %s" % (tr("Профиль принтера"), cm["name"])
            if self._ccor_on():
                text += "\n\n⚠ " + tr("Цветокоррекция драйвера включена при цветовом профиле — цвет исказится. Отключите её на странице «Принтер».")
            if not pr["icm_off"]:
                text += "\n\n⚠ " + tr("Включено управление цветом Windows (ICM) при включённом профиле принтера — цвет обработается дважды. Включите «Цвет Windows (ICM) отключён» на вкладке «Принтер».")
        if abs(min(gw, gh) - L["PW"]) > 2 or abs(max(gw, gh) - L["PH"]) > 2:
            text += "\n\n⚠ " + trf("Лист в программе {a}×{b} мм, а в драйвере другая бумага. Изображение будет растянуто на бумагу драйвера.",
                                    a="%g" % L["PW"], b="%g" % L["PH"])
        if (SOFT[0] or "⚠" in text) and not ask(self, text + "\n\n" + tr("Начать печать?")):       # без предупреждений печать идёт сразу
            return
        c = {"kind": "print", "printer": pr["printer"], "blob": blob, "title": "PhotoCrop", "o": o, "idxs": list(range(len(plan["sheets"]))),
             "plan": plan, "photos": photos, "ppi": pc.resolve_ppi(o, geom), "mode": self.mode(), "cm": cm,
             "pcorr": pcr.norm(self.s["pcorr"]) if pcr.active(self.s["pcorr"]) else None}
        self.cancel.clear()
        self.printing = True
        self._print_files = files
        self._busy(len(c["idxs"]), tr("Подготовка…"), [], "print")
        self.b_print.set_progress(0.0)
        self.b_cancel.show()

        def progress(j, n, text_):
            self.sig.progress.emit(j, n, "\x01" + str(text_))
        def work():
            try:
                res = pc.run_sheets_job(c, progress, self.cancel)
                self.sig.printed.emit(res[0], int(res[1]), "")
            except Exception as ex:
                self.sig.printed.emit("error", 0, "%s: %s" % (ex.__class__.__name__, ex))
        threading.Thread(target=work, daemon=True).start()

    def _sheet_sent(self, i, n):
        """Лист i (с нуля) из n ушёл на принтер: первый — большая анимация в центре, остальные летят к кнопке «Печать»."""
        self.b_print.setText("%s · %d / %d" % (tr("Печать"), i + 1, n))
        files = getattr(self, "_print_files", None) or []
        if not self.settings.get("anim", True) or not files:
            self.b_print.set_progress((i + 1) / max(1, n))
            return
        f = files[i % len(files)]
        pm = self.thumbs.get(f, self.states[f].rotation) if f in self.states else None
        if i == 0:
            self.overlay.play(pm, "print", trf("Печать: лист {a} из {b}", a=1, b=n))
            self.b_print.set_progress(1.0 / max(1, n))
            return
        root = self.centralWidget()
        b = QPointF(self.b_print.mapTo(root, self.b_print.rect().center()))
        c = QPointF(root.rect().center())
        dx, dy = c.x() - b.x(), c.y() - b.y()
        dist = math.hypot(dx, dy) or 1.0
        reach = 120.0                                  # лист стартует только в районе кнопки, а не из середины окна
        a = QPointF(b.x() + dx / dist * reach, b.y() + dy / dist * reach)

        def arrive(frac=(i + 1) / max(1, n)):
            self.b_print.set_progress(frac)
            self.b_print.flash()
        self.fly.play(pm, a, b, arrive, size=0.8, lift=36.0)

    def _print_done(self, kind, n, err):
        self.last_print = {"result": kind, "sheets_sent": n, "error": err or None}
        self.b_print.setText(tr("Печать"))
        self.b_print.set_progress(None)
        if kind == "done":
            self.b_print.flash()
        self.printing = self.saving = False
        self.b_save.setEnabled(True)
        self.b_print.setEnabled(True)
        self.b_cancel.hide()
        self.progress.hide()
        if kind == "done":
            self.l_prog.setText(trf("Отправлено на печать листов: {n}", n=n))
            self.queue_refresh()
        elif kind == "cancelled":
            self.l_prog.setText(trf("Печать отменена, отправлено листов: {n}", n=n))
        else:
            self.l_prog.setText(tr("Ошибка печати"))
            warn(self, err)

    def queue_refresh(self):
        name = self.pr["printer"]
        if not name:
            return
        self.l_queue.setText(tr("Запрашиваю очередь…"))

        def work():
            try:
                self.sig.queue.emit(pc.spooler_queue(name), "")
            except Exception as ex:
                self.sig.queue.emit([], str(ex))
        threading.Thread(target=work, daemon=True).start()

    def _queue_ready(self, jobs, err):
        if err:
            self.l_queue.setText(err[:300])
        elif not jobs:
            self.l_queue.setText(tr("Очередь пуста."))
        else:
            self.l_queue.setText("\n".join("%s — %s" % (j.get("document") or "?", j.get("status") or "") for j in jobs[:12])
                                 + ("\n… +%d" % (len(jobs) - 12) if len(jobs) > 12 else ""))

    def queue_clear(self):
        name = self.pr["printer"]
        if not name or not ask(self, "Удалить все задания из очереди этого принтера?"):
            return

        def work():
            try:
                pc.spooler_clear(name)
                self.sig.queue.emit(pc.spooler_queue(name), "")
            except Exception as ex:
                self.sig.queue.emit([], str(ex))
        threading.Thread(target=work, daemon=True).start()

    def _scroll(self, *cards):
        inner = QWidget()
        inner.setObjectName("scrollInner")
        l = vbox(*cards, None, spacing=10, margins=(0, 0, 6, 0))
        inner.setLayout(l)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)             # место под полосу занято всегда: карточки и вкладки не «гуляют» по ширине
        inner.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)     # ширину задаёт окно просмотра, а не самая длинная строка
        sa.setWidget(inner)
        sa.viewport().setAutoFillBackground(False)
        inner.setAutoFillBackground(False)
        return sa

    def _page_main(self):
        s = self.s
        # --- кадр
        self.seg_orient = Segmented([("Авто", "Авто (по фото)"), ("Книжная", "Книжная"), ("Альбомная", "Альбомная")], s["orient"])
        self.seg_orient.changed.connect(self._orient_changed)
        self.seg_mode = Segmented([("Кадрировать", "Кадрировать (заполнить лист)"), ("Вписать", "Вписать целиком (белые поля)")], s["mode"])
        self.seg_mode.changed.connect(self._mode_changed)
        self.seg_mode2 = Segmented([("Кадрировать", "Кадрировать (заполнить лист)"), ("Вписать", "Вписать целиком (белые поля)")], s["mode"])
        self.seg_mode2.setToolTip(tr("Кадрировать — фото заполняет рамку целиком, лишнее обрезается. Вписать — фото помещается в рамку целиком, без обрезки (где пропорции не совпали, остаются белые поля)."))
        self.seg_mode2.changed.connect(self._mode_changed)
        self.l_copies = lbl("1")
        self.l_copies.setFixedWidth(30)
        self.l_copies.setAlignment(Qt.AlignCenter)
        f = QFont(self.l_copies.font())
        f.setBold(True)
        self.l_copies.setFont(f)
        cop = hbox(ibtn("minus", "Меньше копий", lambda: self.copies_step(-1), 30, True, isize=15), self.l_copies,
                   ibtn("plus", "Больше копий", lambda: self.copies_step(1), 30, True, isize=15), spacing=4)
        photo = card("Кадр", lbl("Ориентация рамки", "muted"), hbox(self.seg_orient, None),
                     lbl("Как фото ложится в рамку", "muted"), hbox(self.seg_mode, None),
                     row("Копий этого фото", cop),
                     hbox(btn("Сбросить рамку", self.reset_frame, "link"), None, btn("Сбросить все", self.reset_all, "link")))
        # --- лист
        self.l_sheet = lbl("", wrap=True)
        self.l_sheet2 = lbl("", "muted", wrap=True)
        sw_fill = Switch(s["fill"])
        sw_fill.toggled.connect(lambda on: self._layout_set("fill", bool(on)))
        sheet = card("Лист", hbox(self.seg_cell, None), lbl("Фото на листе"), self.seg_nup, self.w_cell, self.l_cell_fit,
                     lbl("Как фото ложится в рамку", "muted"), hbox(self.seg_mode2, None),
                     row("Рамка и поля", hbox(self.sw_borders, self.e_border, lbl("мм", "muted"), spacing=6)),
                     self.l_sheet, self.l_sheet2, row("Весь лист — копии одного фото", sw_fill),
                     btn("Показать лист", lambda: self.set_view("sheet"), ico="image"))
        # --- цвет (профиль принтера выбирается на странице «Принтер»)
        self.sw_cm, self.sw_proof, self.sw_gamut = Switch(s["cm_on"]), Switch(False), Switch(False)
        self.sw_cm.toggled.connect(lambda on: (self._cm_set("cm_on", on), self.sw_cm2.set(on)))
        self.sw_proof.toggled.connect(lambda on: self._cm_set("proof", on))
        self.sw_gamut.toggled.connect(lambda on: self._cm_set("gamut", on))
        self.l_icc = lbl("", "muted", wrap=True)
        self.l_icc.hide()
        self._icc_info()
        self.cell_sync()
        self.cell_ui()
        return self._scroll(photo, sheet)

    # ---------- страница «Коррекция цвета» (вместо отдельного окна)
    ADJ_FMT_SIGNED = ("bright", "contrast", "shadows", "highlights", "sat", "vib", "temp", "tint", "r", "g", "b")

    def _page_color(self):
        self.adj_lock = True
        self.sliders, self.slider_lbl = {}, {}
        self.seg_scope = Segmented([("Это фото", "one"), ("Отмеченные", "all")], self.s["adj_scope"])
        self.seg_scope.setToolTip(tr("Куда применять коррекцию: только к текущему фото или ко всем отмеченным галочкой"))
        self.seg_scope.setStyleSheet('QPushButton[kind="seg"]:checked{border-color:%s;}' % T["text"])      # выбранный — тонкая белая рамка, размер не меняется
        for b in self.seg_scope.group.buttons():                                                             # две равные половины по центру карточки
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.seg_scope.layout().setStretchFactor(b, 1)
        self.seg_scope.changed.connect(lambda v: self._set("adj_scope", v, redraw=False))
        self.hist = Histogram()
        self.l_hist = lbl("", "muted", wrap=True)
        tabs = Segmented([(t_[0], i) for i, t_ in enumerate(pc.AdjustPanel.TABS)], 0)
        stack = PageStack()
        for title, rows in pc.AdjustPanel.TABS:
            page = QWidget()
            l = vbox(spacing=4)
            for label, key, lo, hi, step in rows:
                l.addLayout(self._slider(label, key, lo, hi, step))
            if title == "Основное":
                self.seg_auto = Segmented([("нет", ""), ("контраст", "contrast"), ("цвет", "color"), ("Ч/Б", "bw")], "")
                self.seg_auto.changed.connect(lambda v: self.adj_set({"auto": v}))
                l.addSpacing(4)
                l.addWidget(lbl("Авто-уровни"))
                l.addLayout(hbox(self.seg_auto, None))
            if title == "Цвет":
                self.sw_bw, self.sw_sepia = Switch(False), Switch(False)
                self.sw_bw.toggled.connect(lambda on: self.adj_set({"bw": bool(on)}))
                self.sw_sepia.toggled.connect(lambda on: self.adj_set({"sepia": bool(on)}))
                l.addSpacing(4)
                l.addLayout(row("Чёрно-белое", self.sw_bw))
                l.addLayout(row("Сепия", self.sw_sepia))
            l.addStretch(1)
            page.setLayout(l)
            stack.addWidget(page)
        n_tabs = len(pc.AdjustPanel.TABS)                   # дальше: уровни, кривые, выборочный цвет
        self.levels_ed = LevelsEditor()
        self.levels_ed.changed.connect(lambda v: self.levels_changed(v, self.levels_ed))
        self.levels_ed.auto_requested.connect(self.levels_auto)
        self.curves_panel = CurvesPanel(230)
        self.curves_panel.changed.connect(lambda v: self.curves_changed(self.curves_panel, v))
        if getattr(self, "curves_win", None) is not None:      # окно кривых от прежнего построения интерфейса
            self.curves_win.close()
            self.curves_win = None
        curv_page = QWidget()
        curv_page.setLayout(vbox(self.curves_panel, hbox(btn("На весь экран…", self.open_curves_window, ico="image"), None), spacing=8))
        self.levels_ed.layout().addLayout(hbox(btn("На весь экран…", lambda: self.open_color_window(0), ico="image"), None))
        self.sel_panel = SelColorPanel()
        self.sel_panel.changed.connect(self.selcol_changed)
        for w_ in (self.levels_ed, curv_page, self.sel_panel):
            stack.addWidget(w_)

        tabs2 = Segmented([("Уровни", n_tabs), ("Кривые", n_tabs + 1), ("По цветам", n_tabs + 2)], n_tabs)
        tabs2.clear()
        tabs.changed.connect(lambda i: (stack.setCurrentIndex(i), tabs2.clear()))
        tabs2.changed.connect(lambda i: (stack.setCurrentIndex(i), tabs.clear()))
        self.l_enh = lbl("", "muted", wrap=True)
        self.l_enh.hide()
        b_orig = ibtn("eye", "Показать оригинал (удерживайте)", None, 34, True)
        b_orig.pressed.connect(lambda: self.adj_show_original(True))
        b_orig.released.connect(lambda: self.adj_show_original(False))
        b_wb = ibtn("pipette", "Баланс белого: щёлкните по фото в месте, которое должно быть серым или белым", self.pick_white, 34, True)
        b_enh = btn("Улучшить", lambda: self.enhance(1), ico="sparkle", tip="Улучшение для печати на Epson: светлее, чуть контрастнее и резче. Подбирается под каждый снимок. Прежняя коррекция сбрасывается.")
        b_sup = btn("Супер", lambda: self.enhance(2), ico="sparkle", tip="Более сильное улучшение: ярче, сочнее, резче")
        self.b_pre, self.b_pre_save, self.b_pre_ren = {}, {}, {}
        cols = []
        for n in (1, 2, 3):
            b = btn(self.preset_name(n), lambda k=n: self.preset_pick(k))
            b.setProperty("kind", "chip")
            b.setMinimumWidth(0)
            self.b_pre[n] = b
            self.b_pre_save[n] = ibtn("save", "Запомнить текущие настройки ползунков в этот пресет. Он хранится, пока вы не сохраните в него другие.",
                                      lambda k=n: self.preset_save(k), 28, True, isize=15)
            self.b_pre_ren[n] = ibtn("edit", "Переименовать пресет", lambda k=n: self.preset_rename(k), 28, True, isize=15)
            cols.append(vbox(b, hbox(self.b_pre_save[n], self.b_pre_ren[n], None, spacing=4), spacing=4))
        quick = card(None, hbox(b_enh, b_sup, b_wb, b_orig, spacing=6),
                     hbox(*cols, spacing=6),
                     hbox(ibtn("sun", "Авто-яркость", self.auto_bright, 32, True, isize=16),
                          ibtn("copy", "Копировать настройки этого фото", self.adj_copy, 32, True, isize=16),
                          ibtn("paste", "Вставить настройки в это фото", lambda: self.adj_paste(False), 32, True, isize=16),
                          ibtn("check_all", "Применить настройки этого фото ко всем", self.adj_apply_all, 32, True, isize=16),
                          None,
                          ibtn("reset", "Сбросить коррекцию этого фото", lambda: self.adj_reset(False), 32, True, isize=16),
                          ibtn("trash", "Сбросить коррекцию у всех фото", lambda: self.adj_reset(True), 32, True, isize=16), spacing=4),
                     self.l_enh)
        top = card(None, self.seg_scope, self.hist, self.l_hist)
        sl = card(None, tabs, tabs2, stack, lbl("Двойной щелчок по ползунку — сбросить его.", "muted", wrap=True))
        self.adj_lock = False
        self._preset_tips()
        return self._scroll(top, quick, sl)

    def _slider(self, label, key, lo, hi, step):
        s = _ResetSlider(Qt.Horizontal)
        s.setRange(int(round(lo / step)), int(round(hi / step)))
        s.setValue(int(round(pc.NEUTRAL_ADJ[key] / step)))
        val = lbl("", "muted")
        val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        s.valueChanged.connect(lambda v, k=key, st=step: self._slider_moved(k, v * st))
        s.reset.connect(lambda k=key: self._slider_reset(k))
        self.sliders[key], self.slider_lbl[key] = (s, step), val
        return vbox(hbox(lbl(label), None, val), s, spacing=1, margins=(0, 3, 0, 3))

    def _adj_fmt(self, key, v):
        if key == "gamma":
            return "%.2f" % v
        if key == "sharp_radius":
            return "%.1f" % v
        return ("%+.0f" % v) if key in self.ADJ_FMT_SIGNED else ("%.0f" % v)

    def _slider_moved(self, key, v):
        v = round(v, 2)
        self.slider_lbl[key].setText(self._adj_fmt(key, v))
        if self.adj_lock or self.idx < 0:
            return
        if abs(self.cur_adj().get(key, pc.NEUTRAL_ADJ[key]) - v) < 1e-9:
            return
        self.adj_set({key: v}, key=("slider", key))

    def _slider_reset(self, key):
        self.adj_set({key: pc.NEUTRAL_ADJ[key]})
        self.sync_adj()

    def show_page(self, i):
        self.pages.setCurrentIndex(i)
        self.seg_page.set(i)
        if i == 1:
            self.sync_adj()
        elif i == 3:
            self.smart_page_sync()
        elif i == 2:
            self.bleed_sync()

    # ---------- мелкие обработчики
    def _set(self, key, value, redraw=True):
        if self._building:
            return
        self.s[key] = value
        if redraw:
            self.redraw()

    def _mode_changed(self, v):
        """«Кадрировать / Вписать»: один выбор, две копии переключателя (карточки «Кадр» и «Лист»)."""
        for sg in (self.seg_mode, self.seg_mode2):
            if sg.value() != v:
                sg.set(v)
        self._set("mode", v)

    def pick_white(self):
        """Пипетка «баланс белого»: следующий щелчок по фото — место, которое должно быть серым или белым."""
        if self.idx < 0:
            info(self, "Сначала откройте фото.")
            return
        self.canvas.pick = self._white_at
        self.canvas.setCursor(Qt.CrossCursor)
        self.update_hist(tr("Щёлкните по фото в месте, которое должно быть серым или белым (правая кнопка — отмена)"))

    def _white_at(self, fx, fy):
        f = self.files[self.idx]
        st = self.states[f]
        rad = 0.02
        try:
            r_ = pc.wb_solve(self.raw, st.adj, [fx - rad, fy - rad, fx + rad, fy + rad])
        except ValueError as ex:
            self.update_hist(str(ex))
            return
        self.adj_set(r_["set"], key="wb")
        self.sync_adj()
        self.update_hist(trf("Баланс белого: r {r}, g {g}, b {b}", r=r_["set"]["r"], g=r_["set"]["g"], b=r_["set"]["b"]))

    def _toggle_grid(self):
        self.s["grid"] = not self.s["grid"]
        self.b_grid.setIcon(icon("grid", T["select"] if self.s["grid"] else T["muted"]))
        self.redraw()

    # ---------- лист: бумага, сколько фото на листе, поля
    def _layout_set(self, key, value):
        if self._building:
            return
        self.s[key] = value
        if key == "borders":
            self.e_border.setEnabled(bool(value))
        if key == "format":
            self.profile_apply()
        if key in ("format", "nup", "borders", "border_mm", "cell_mode", "cell_w", "cell_h"):
            self.cell_sync()
            self.smart_cfg_changed()
            self.bleed_sync()
            self.cell_ui()
        self.redraw()

    def cell_ui(self):
        """Что показывать в карточке «Лист»: быстрый выбор числа или размер рамки."""
        on = bool(self.s.get("cell_mode"))
        try:
            self.seg_nup.setVisible(not on)
            self.w_cell.setVisible(on)
            self.l_cell_fit.setVisible(on)
            if on:
                L = self.layout_spec()
                self.l_cell_fit.setText(trf("Влезает: {n} ({c}×{r}), рамка {w}×{h} мм", n=L["cols"] * L["rows"], c=L["cols"], r=L["rows"],
                                            w="%g" % round(L["cw"], 1), h="%g" % round(L["ch"], 1)))
        except (AttributeError, RuntimeError):
            pass

    def border_mm(self):
        try:
            return max(0.0, min(30.0, float(str(self.s["border_mm"]).replace(",", "."))))
        except ValueError:
            return 0.0

    def cell_mm(self):
        """Заданный размер рамки (режим «По размеру»), мм: (ширина, высота)."""
        out = []
        for k in ("cell_w", "cell_h"):
            try:
                out.append(max(10.0, min(1000.0, float(str(self.s[k]).replace(",", ".")))))
            except ValueError:
                out.append(50.0)
        return tuple(out)

    def _fit_cells(self, short, long_, m, g, cw, ch):
        """Сколько рамок cw×ch влезает на лист: пробуем рамку как задана и повёрнутую, берём где больше."""
        best = None
        for w_, h_ in ((cw, ch), (ch, cw)):
            cols = int((short - 2 * m + g + 1e-6) // (w_ + g))
            rows = int((long_ - 2 * m + g + 1e-6) // (h_ + g))
            if cols >= 1 and rows >= 1 and (best is None or cols * rows > best[0] * best[1]):
                best = (cols, rows, w_, h_)
        return best

    def layout_spec(self):
        """Геометрия листа, мм: бумага книжная PW×PH, сетка cols×rows, поле m по краю листа и такое же
        расстояние m между фото (как задано в поле «Рамка, мм»), ячейка cw×ch. В режиме «По размеру» ячейка
        задана, сетка — сколько таких рамок влезает, и она стоит по центру листа."""
        short, long_, tag = pc.FORMATS[self.s["format"]]
        m = self.border_mm() if self.s["borders"] else 0.0
        if self.s.get("cell_mode"):
            cw, ch = self.cell_mm()
            fit = self._fit_cells(short, long_, m, m, cw, ch)
            if fit is None:                                          # рамка больше листа: одна рамка, вписанная в лист
                k = min((short - 2 * m) / cw, (long_ - 2 * m) / ch)
                fit = (1, 1, cw * k, ch * k)
            cols, rows, cw, ch = fit
            x0 = (short - cols * cw - (cols - 1) * m) / 2
            y0 = (long_ - rows * ch - (rows - 1) * m) / 2
            return {"PW": float(short), "PH": float(long_), "cols": cols, "rows": rows, "m": m, "g": m, "cw": cw, "ch": ch, "tag": tag,
                    "x0": x0, "y0": y0}
        cols, rows = nup_grid(self.s["nup"])
        while True:
            g = m
            cw = (short - 2 * m - (cols - 1) * g) / cols
            ch = (long_ - 2 * m - (rows - 1) * g) / rows
            if (cw >= 10 and ch >= 10) or m <= 0:
                break
            m = max(0.0, m - 1.0)                      # поле слишком большое для такого листа — уменьшаем
        return {"PW": float(short), "PH": float(long_), "cols": cols, "rows": rows, "m": m, "g": m, "cw": cw, "ch": ch, "tag": tag}

    def cell_sync(self):
        """В режиме «По размеру» число фото на листе = сколько рамок влезло (его читают остальные части программы)."""
        if self.s.get("cell_mode"):
            L = self.layout_spec()
            self.s["nup"] = max(1, min(NUP_MAX * 4, L["cols"] * L["rows"]))
            try:
                self.seg_nup.set(self.s["nup"] if self.s["nup"] <= NUP_MAX else 1)
            except Exception:
                pass

    def sheet_mode(self):
        """True — результат работы это листы (несколько фото на листе или фото с белыми полями)."""
        return bool(self.s.get("cell_mode")) or self.s["nup"] > 1 or (self.s["borders"] and self.border_mm() > 0)

    def cell_fmt(self):
        """Формат рамки кадрирования: при одном фото без полей — сама бумага, иначе — место этого фото на листе."""
        if not self.sheet_mode():
            return pc.FORMATS[self.s["format"]]
        L = self.layout_spec()
        w, h = L["cw"], L["ch"]
        if self.s["free"] and self.idx >= 0:
            f = self.files[self.idx]
            r = next((x["rect"] for x in self.slots() if x["f"] == f), None)
            if r:
                w, h = r[2], r[3]
        return (min(w, h), max(w, h), "%s_%d" % (L["tag"], self.s["nup"]))

    def slots(self):
        """Места на листах по порядку: [{key, f, sheet, rect (x, y, w, h мм), grid}]. Порядок фото можно менять
        (swap_slots), в свободном режиме у места свой прямоугольник."""
        L = self.layout_spec()
        n = L["cols"] * L["rows"]
        sig = (self.s["format"], self.s["nup"], self.s["borders"], self.border_mm(), self.s["fill"], self.s.get("cell_mode"), self.cell_mm())
        if sig != self._layout_sig:                   # сменили бумагу/сетку/поля — свободная расстановка начинается заново
            self.free, self._layout_sig = {}, sig
        files = self.checked_files()
        if self.s["fill"]:
            keys = [(f, c, j) for f in files for c in range(max(1, self.states[f].copies)) for j in range(n)]
        else:
            want = [(f, c) for f in files for c in range(max(1, self.states[f].copies))]
            ws = set(want)
            order = [k for k in self.slot_order if k in ws]
            have = set(order)
            order += [k for k in want if k not in have]
            keys = order
            if self._only is None:                     # печать одного фото не должна портить порядок остальных
                self.slot_order = order
        out = []
        for i, key in enumerate(keys):
            sheet, j = divmod(i, n)
            r, c = divmod(j, L["cols"])
            grid = (L.get("x0", L["m"]) + c * (L["cw"] + L["g"]), L.get("y0", L["m"]) + r * (L["ch"] + L["g"]), L["cw"], L["ch"])
            out.append({"key": key, "f": key[0], "sheet": sheet, "grid": grid,
                        "rect": self.free.get(key, grid) if self.s["free"] else grid})
        return out

    def slot_paper(self, f, rect):
        """(ширина, высота снимка px, размер кадра мм, лежит ли фото в ячейке боком) для места rect."""
        st = self.states[f]
        W, H = pc.true_size(f, st.rotation)
        w, h = rect[2], rect[3]
        paper = pc.paper_size((min(w, h), max(w, h), ""), st.orient if st.orient else pc.ORIENTS[self.s["orient"]], W, H)
        rot = abs(w - h) > 1e-6 and ((paper[0] < paper[1]) != (w < h))
        return W, H, paper, rot

    def swap_slots(self, a, b):
        if a in self.slot_order and b in self.slot_order:
            i, j = self.slot_order.index(a), self.slot_order.index(b)
            self.slot_order[i], self.slot_order[j] = self.slot_order[j], self.slot_order[i]
        self.redraw()

    def set_free(self, on):
        self.s["free"] = bool(on)
        try:
            self.sheet_view.sw_free.set(bool(on))
        except Exception:
            pass
        self.redraw()

    def reset_layout(self):
        self.slot_order, self.free = [], {}
        self.redraw()

    def snap_rect(self, key, x, y, w, h, on=True):
        """Прилипание места на листе к краям и середине листа и к краям соседних фото (в пределах 2 мм)."""
        if not on:
            return x, y
        L = self.layout_spec()
        sheet = next((s_["sheet"] for s_ in self.slots() if s_["key"] == key), 0)
        xs, ys = [0.0, L["PW"], L["PW"] / 2], [0.0, L["PH"], L["PH"] / 2]
        for o in self.slots():
            if o["sheet"] == sheet and o["key"] != key:
                r = o["rect"]
                xs += [r[0], r[0] + r[2]]
                ys += [r[1], r[1] + r[3]]

        def fix(v, size, lines):
            best = None
            for ln in lines:
                for edge in (v, v + size, v + size / 2):
                    d = ln - edge
                    if abs(d) <= 2.0 and (best is None or abs(d) < abs(best)):
                        best = d
            return v + (best or 0.0)
        return fix(x, w, xs), fix(y, h, ys)

    def sheet_plan(self):
        """Раскладка отмеченных фото по листам -> (план для движка, фото, параметры, геометрия)."""
        L = self.layout_spec()
        o = pc.parse_print_opts({})
        o.update(layout="multi", caption="none", marks=False, border=0.0)
        sides = (0.0, 0.0, 0.0, 0.0) if self.sheet_mode() else self.bleed_mm()
        use_bleed = any(abs(v) > 1e-9 for v in sides)
        if use_bleed:
            o["layout"] = "single"                    # одно фото на листе без полей: работает подрезка принтером
        photos, sheets = [], []
        for x in self.slots():
            try:
                W, H, paper, rot = self.slot_paper(x["f"], x["rect"])
            except Exception:
                continue
            photos.append({"path": x["f"], "st": self.states[x["f"]].copy(), "paper": paper, "copies": 1})
            while len(sheets) <= x["sheet"]:
                sheets.append([])
            r = x["rect"]
            ent = {"photo": len(photos) - 1, "x": r[0], "y": r[1], "w": r[2], "h": r[3], "rot": rot, "iw": paper[0], "ih": paper[1]}
            if use_bleed:
                sl, sT, sr, sb = sides                                   # стороны ЛИСТА -> стороны снимка (боком: поворот на 90° против часовой)
                bl, bt, br, bb = (sb, sl, sT, sr) if rot else (sl, sT, sr, sb)
                photos[-1]["sides"] = (bl, bt, br, bb)
                ent["iw"], ent["ih"] = max(1.0, paper[0] + bl + br), max(1.0, paper[1] + bt + bb)
                ent["x"], ent["y"] = r[0] - sl, r[1] - sT
                ent["w"], ent["h"] = (ent["ih"], ent["iw"]) if rot else (ent["iw"], ent["ih"])
            sheets[x["sheet"]].append(ent)
        geom = pc.virtual_geometry(L["PW"], L["PH"], "portrait")
        plan = {"geom": geom, "area": geom["area"], "sheets": sheets, "warnings": [], "util": 1.0, "gap": L["g"], "orient": "portrait"}
        return plan, photos, o, L

    def sheet_count(self):
        n = self.s["nup"]
        copies = [max(1, self.states[f].copies) for f in self.checked_files()]
        return sum(copies) if self.s["fill"] else -(-sum(copies) // n)

    def set_app_mode(self, mode):
        """ФОТО / ДОКУМЕНТ: в режиме документа слева скрыты миниатюры, справа вместо «Фото» и «Умной рамки» — страница «Документ»."""
        self.app_mode = mode
        doc = mode == "doc"
        self.center_stack.setCurrentIndex(2 if doc else (1 if self.view == "sheet" else 0))
        if hasattr(self, "mode_switch"):
            self.mode_switch.set(mode)
        if hasattr(self, "left_w"):
            self.left_w.setVisible(not doc)
            for i, b in enumerate(self.seg_page.group.buttons()):   # кнопки вкладок: Макет, Цвет, Умная рамка, Принтер, Документ
                b.setVisible((i >= 3) if doc else (i < 4))
            self.b_save.setVisible(not doc)
            for w in self._photo_only:
                w.setVisible(not doc and not (self.compact and w in self._caps))
            self.show_page(4 if doc else 0)

    def set_view(self, v):
        self.view = "sheet" if v == "sheet" else "crop"
        self.center_stack.setCurrentIndex(2 if getattr(self, "app_mode", "photo") == "doc" else (1 if self.view == "sheet" else 0))
        self.seg_view.set(self.view)
        if self.view == "sheet":
            self.sheet_view.refresh()
        else:
            self.canvas.place_pill()
        self.redraw()

    def select_file(self, f):
        if f in self.files and (self.idx < 0 or self.files[self.idx] != f):
            self.show_photo(self.files.index(f))

    def _shortcuts(self):
        def sc(keys, fn):
            for k in keys:
                QShortcut(QKeySequence(k), self, activated=fn)
        sc(("Left", "PgUp"), lambda: self._key(lambda: self.go(-1)))
        sc(("Right", "PgDown"), lambda: self._key(lambda: self.go(1)))
        sc(("R",), lambda: self._key(self.flip_frame))
        sc(("C",), lambda: self._key(lambda: self.show_page(1 - self.pages.currentIndex())))
        sc(("+", "="), lambda: self._key(lambda: self.zoom(1.02)))
        sc(("-",), lambda: self._key(lambda: self.zoom(1 / 1.02)))
        sc(("Ctrl+O",), self.open_any)
        sc(("Ctrl+S",), lambda: self.save(False))
        sc(("Ctrl+Shift+S",), lambda: self.save(True))
        sc(("Ctrl+P",), self.print_now)
        sc(("Ctrl+Shift+P",), self.print_current)
        sc(("Ctrl+Z",), self.undo)
        sc(("Ctrl+Y", "Ctrl+Shift+Z"), self.redo)
        sc(("N",), lambda: self._key(lambda: self.smart_next(1)))
        sc(("Shift+N",), lambda: self._key(lambda: self.smart_next(-1)))
        sc(("V",), lambda: self._key(self.smart_mark_seen))

    def _key(self, fn):
        if isinstance(QApplication.focusWidget(), (QLineEdit, QComboBox)):
            return
        fn()

    def mode(self):
        return pc.MODES[self.s["mode"]]

    def checked_files(self):
        if self._only is not None:
            return [self._only] if self._only in self.files else []
        return [f for f in self.files if f in self.checked]

    def bleed_mm(self):
        vals = dict(pc.PRINT_DEFAULTS)
        vals.update({k: v for k, v in self.settings.get("print", {}).items() if k in pc.PRINT_DEFAULTS})
        try:
            return pc.bleed_sides(pc.parse_print_opts(vals))
        except Exception:
            return (0.0, 0.0, 0.0, 0.0)

    # ---------- подрезка принтером (печать без полей)
    BLEED_KEYS = ("bleed_on", "bleed", "bleed_l", "bleed_t", "bleed_r", "bleed_b")

    def _bleed_card(self):
        v = self.bleed_vals()
        self.sw_bleed = Switch(bool(v["bleed_on"]))
        self.sw_bleed.setToolTip(tr("Выключено — значения ниже сохраняются, но не применяются."))
        self.sw_bleed.toggled.connect(lambda on: self.bleed_set("bleed_on", bool(on)))
        self.e_bleed = {}
        for k, ph in (("bleed", "0"), ("bleed_l", ""), ("bleed_t", ""), ("bleed_r", ""), ("bleed_b", "")):
            e = QLineEdit(str(v[k]))
            e.setFixedWidth(64 if k == "bleed" else 52)
            e.setAlignment(Qt.AlignCenter)
            e.setPlaceholderText(ph or "=")
            e.textEdited.connect(lambda t, k=k: self.bleed_set(k, t))
            self.e_bleed[k] = e
        self.l_bleed = lbl("", "muted", wrap=True)
        sides = hbox(*[w for k, n in (("bleed_l", "Лево"), ("bleed_t", "Верх"), ("bleed_r", "Право"), ("bleed_b", "Низ"))
                       for w in (lbl(n, "muted"), self.e_bleed[k])], None, spacing=4)
        self._bleed_hint = lbl("Если принтер срезает края при печати без полей — введите отрицательные значения (отступ): "
                               "фото уменьшится на эту величину, а принтер дорастит его до края. Положительные — снимок заходит "
                               "за край листа реальным содержимым. Пустое поле = «как общее». Действует при одном фото на листе без белых полей.",
                               "muted", wrap=True)
        c = card("Печать без полей: подрезка принтером",
                 row("Учитывать подрезку", self.sw_bleed),
                 row("Со всех сторон, мм", self.e_bleed["bleed"]),
                 sides, self.l_bleed, self._bleed_hint,
                 btn("Тестовая шкала краёв", self.add_edge_test, ico="plus",
                     tip="Картинка со шкалой: распечатайте её теми же настройками — последняя видимая цифра на каждой стороне покажет, сколько мм срезал принтер."))
        if not hasattr(self, "_bleed_timer"):
            self._bleed_timer = QTimer(self)
            self._bleed_timer.setSingleShot(True)
            self._bleed_timer.setInterval(500)
            self._bleed_timer.timeout.connect(self._bleed_flush)
            self._bleed_dirty = False
        self.bleed_sync()
        return c

    def bleed_vals(self):
        vals = dict(pc.PRINT_DEFAULTS)
        vals.update({k: v for k, v in self.settings.get("print", {}).items() if k in pc.PRINT_DEFAULTS})
        return vals

    def bleed_set(self, key, val):
        self.settings.setdefault("print", {})[key] = val
        self._bleed_dirty = True
        self._bleed_timer.start()
        self.bleed_sync()
        try:
            self.canvas.update()
        except Exception:
            pass

    def _bleed_flush(self):
        """Запись в общий файл настроек (его же читает окно печати) — только ключи подрезки."""
        if not getattr(self, "_bleed_dirty", False):
            return
        self._bleed_dirty = False
        fresh = pc.load_settings()
        cur = self.settings.get("print", {})
        fresh.setdefault("print", {}).update({k: cur[k] for k in self.BLEED_KEYS if k in cur})
        pc.save_settings(fresh)

    def bleed_sync(self):
        """Доступность полей и пояснение: действует ли подрезка прямо сейчас."""
        if not hasattr(self, "sw_bleed"):
            return
        on = bool(self.bleed_vals()["bleed_on"])
        for e in self.e_bleed.values():
            e.setEnabled(on)
        sides = self.bleed_mm()
        if not on:
            t = tr("Выключено: значения сохранены, но печать идёт обычным образом.")
        elif not any(abs(x) > 1e-9 for x in sides):
            t = tr("Все значения нулевые — подрезки нет.")
        elif self.sheet_mode():
            t = tr("Сейчас на листе несколько фото или белые поля — подрезка не применяется.")
        else:
            t = trf("Действует: лево {a}, верх {b}, право {c}, низ {d} мм", a="%g" % sides[0], b="%g" % sides[1], c="%g" % sides[2], d="%g" % sides[3])
        self.l_bleed.setText(t)

    def add_edge_test(self):
        """Шкала краёв размера листа -> в список фото."""
        short, long_, tag = pc.FORMATS[self.s["format"]]
        w, h = (long_, short) if pc.ORIENTS[self.s["orient"]] == "landscape" else (short, long_)
        d = Path(tempfile.gettempdir()) / "PhotoCrop"
        d.mkdir(parents=True, exist_ok=True)
        p = d / ("Шкала_краёв_%s.png" % tag)
        pc.make_edge_test(w, h, 300).save(p, dpi=(300, 300))
        self.load_files([p], add=True)

    def changeEvent(self, e):
        if e.type() == QEvent.ActivationChange and self.isActiveWindow():
            try:                                    # окно печати могло поменять подрезку — перечитать и перерисовать шкалу
                fresh = pc.load_settings()
                for k in ("print", "print_presets"):
                    if k in fresh:
                        self.settings[k] = fresh[k]
                self.canvas.update()
                for k, e_ in getattr(self, "e_bleed", {}).items():
                    v = self.bleed_vals()[k]
                    if str(v) != e_.text() and not e_.hasFocus():
                        e_.setText(str(v))
                if hasattr(self, "sw_bleed"):
                    self.sw_bleed.set(bool(self.bleed_vals()["bleed_on"]))
                self.bleed_sync()
            except Exception:
                pass
        super().changeEvent(e)

    # ---------- файлы
    def start_dir(self):
        st = self.settings
        if st.get("start_dir_mode") == "last" and st.get("last_dir") and Path(st["last_dir"]).is_dir():
            return st["last_dir"]
        return pc.desktop_dir()

    def open_any(self):
        """Одна кнопка на фото, папки и документы: выбрали документ — открывается раздел «Документ»,
        выбрали фото или папку — раздел «Фото»."""
        dlg = OpenDialog(self, self.start_dir())
        if not dlg.exec() or not dlg.choice:
            return
        kind, val, add = dlg.choice
        if kind == "doc":
            self.set_app_mode("doc")
            self.doc_load(Path(val))
            return
        if getattr(self, "app_mode", "photo") == "doc":
            self.set_app_mode("photo")
        if kind == "files":
            self.load_files(val, add)
        else:
            self.load_folder(Path(val), add)

    # ---------- фото можно бросить в окно мышью (из проводника)
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        pos = e.position().toPoint()
        e.acceptProposedAction()
        self.drop_paths(paths, self.sheet_view.mapFrom(self, pos) if self.view == "sheet" else None)

    def drop_paths(self, paths, sheet_pos=None):
        """Добавляет брошенные файлы и папки. Если бросили на лист — первое новое фото встаёт в точку, куда бросили."""
        files = []
        docs = [Path(q) for q in paths if Path(q).suffix.lower() in DOC_EXTS and Path(q).is_file()]
        if docs and not any(Path(q).suffix.lower() in pc.EXTS or Path(q).is_dir() for q in paths):
            self.set_app_mode("doc")                       # бросили только документ — открываем раздел «Документ»
            self.doc_load(docs[0])
            return
        for q in paths:
            q = Path(q)
            if q.is_dir():
                files += pc.scan_folder(q, self.s["recursive"], self.s["out_name"].strip(), self.out_dirs())[0]
            elif q.suffix.lower() in pc.EXTS and q.is_file():
                files.append(q)
        if not files:
            return
        had = set(self.files)
        self.load_files(files, add=bool(self.files))
        fresh = [f for f in files if f not in had and f in self.states]
        sv = self.sheet_view
        if sheet_pos is None or not fresh or self.s["fill"] or not sv.g:
            return
        x0, y0, k = sv.g
        L = self.layout_spec()
        mx, my = (sheet_pos.x() - x0) / k, (sheet_pos.y() - y0) / k
        if 0 <= mx <= L["PW"] and 0 <= my <= L["PH"]:
            key = (fresh[0], 0)
            self.set_free(True)
            self.free[key] = (mx - L["cw"] / 2, my - L["ch"] / 2, L["cw"], L["ch"])
            sv.sel = key
            sv.show_photo_page(fresh[0])
            self.redraw()

    def out_dirs(self):
        """Куда программа сохраняет результат: эти папки при открытии исходников пропускаются (по пути, а не по имени)."""
        d = []
        if self.s["outdir"].strip():
            d.append(self.s["outdir"].strip())
        if self.settings.get("outdir_custom"):
            d.append(self.settings["outdir_custom"])
        return d

    def load_folder(self, src, add=False):
        files, own, other = pc.scan_folder(src, self.s["recursive"], self.s["out_name"].strip(), self.out_dirs())
        if not files:
            info(self, tr("В выбранной папке нет фотографий (JPG, PNG, TIFF, BMP, WEBP).")
                 + ("\n\n" + pc.skipped_note(own, other) if (own or other) else ""))
            return
        self.settings["last_dir"] = str(src)
        if add and self.files:
            self.load_files(files, True)
            return
        states = {f: pc.CropState() for f in files}
        idx = self._restore_autosave(src, files, states)
        self.set_files(src, files, states, idx)
        if own or other:
            info(self, "Загружено фото: %d.\n\n%s" % (len(files), pc.skipped_note(own, other)))

    def load_files(self, paths, add=False):
        new = []
        for q in paths:
            f = Path(q)
            if f.suffix.lower() in pc.EXTS and f.is_file() and f not in new:
                new.append(f)
        if not pc.HEIC_OK and any(Path(q).suffix.lower() in (".heic", ".heif") for q in paths):
            info(self, "Для снимков HEIC нужна библиотека pillow-heif.\nВыполните в командной строке:  pip install pillow-heif\nи запустите программу заново.")
        if not new:
            if pc.HEIC_OK or not any(Path(q).suffix.lower() in (".heic", ".heif") for q in paths):
                info(self, "Среди выбранных нет поддерживаемых фотографий (JPG, PNG, TIFF, BMP, WEBP, HEIC).")
            return
        self.settings["last_dir"] = str(new[0].parent)
        if add and self.files:
            have = set(self.files)
            fresh = [f for f in new if f not in have]
            if not fresh:
                return
            i = len(self.files)
            for f in fresh:
                self.states[f] = pc.CropState()
                self.checked.add(f)
            self.files = self.files + fresh
            self.thumbs_view.model().refresh()
            self.upd_counts()
            self.show_photo(i)
            self.smart_after_open(fresh)
            return
        try:
            src = Path(os.path.commonpath([str(f.parent) for f in new]))
        except ValueError:
            src = new[0].parent
        files = sorted(new, key=pc.natural_key)
        self.set_files(src, files, {f: pc.CropState() for f in files}, 0)

    def set_files(self, src, files, states, idx):
        self.src_dir, self.files, self.states = src, files, states
        self.smart_reset()
        self._undo, self._redo, self._undo_key = [], [], None
        self.checked = set(files)
        self._last_check = None
        self.idx = -1
        self.thumbs_view.model().refresh()
        self.upd_counts()
        self.show_photo(max(0, min(idx, len(files) - 1)))
        self.smart_after_open()

    def _restore_autosave(self, src, files, states):
        self._auto_sig = None
        try:
            d = json.loads(pc.autosave_path(src).read_text(encoding="utf-8"))
            saved = d.get("states", {})
            n = sum(1 for f in files if (saved.get(str(f)) or {}).get("edited"))
        except Exception:
            return 0
        if not n or not ask(self, "Найдены сохранённые рамки для этой папки (изменённых снимков: %d).\n\nВосстановить?" % n):
            return 0
        for f in files:
            for k, v in (saved.get(str(f)) or {}).items():
                if k in pc.CropState.__slots__:
                    setattr(states[f], k, dict(v) if k == "adj" else v)
            pc._sanitize_state(states[f])
        return min(max(int(d.get("idx", 0)), 0), len(files) - 1)

    def _session(self, files=None):
        s = pc.AgentSession(persist=False)
        files = list(self.files) if files is None else files
        s.files, s.states = files, {f: self.states[f] for f in files}
        s.idx = max(0, files.index(self.files[self.idx])) if (self.idx >= 0 and self.files[self.idx] in files) else 0
        s.folder, s.recursive = self.src_dir, self.s["recursive"]
        s.fmt_name, s.orient_name, s.mode_name = self.s["format"], self.s["orient"], self.s["mode"]
        return s

    def _autosave_sig(self):
        return tuple((str(f), tuple(getattr(st, k) for k in pc.CropState.__slots__ if k != "adj"), tuple(sorted(st.adj.items())))
                     for f, st in self.states.items())

    def _autosave_now(self):
        if not self.files or self.src_dir is None:
            return
        sig = self._autosave_sig()
        if sig == self._auto_sig:
            return
        if not any(st.edited for st in self.states.values()):
            self._auto_sig = sig
            try:
                pc.autosave_path(self.src_dir).unlink()
            except OSError:
                pass
            return
        pc.write_json_atomic(pc.autosave_path(self.src_dir), self._session().to_project(full=False))
        self._auto_sig = sig

    def _autosave_tick(self):
        try:
            self._autosave_now()
        except Exception:
            pass

    def save_project(self):
        if not self.files:
            info(self, "Сначала откройте фото.")
            return
        p, _ = QFileDialog.getSaveFileName(self, tr("Сохранить проект (рамки и настройки)"), "photocrop_project.json", "PhotoCrop (*.json)")
        if p:
            try:
                pc.write_json_atomic(p, self._session().to_project(full=False))
            except OSError as ex:
                warn(self, "Не удалось сохранить проект:\n%s" % ex)

    def load_project(self):
        pc.AGENT_DIR.mkdir(parents=True, exist_ok=True)
        p, _ = QFileDialog.getOpenFileName(self, tr("Открыть проект"), str(pc.AGENT_DIR), "PhotoCrop (*.json);;* (*.*)")
        if not p:
            return
        try:
            s = pc.AgentSession(persist=False)
            s.from_project(json.loads(Path(p).read_text(encoding="utf-8")))
        except (OSError, ValueError) as ex:
            warn(self, "Не удалось прочитать проект:\n%s" % ex)
            return
        if not s.files:
            info(self, "В проекте нет доступных файлов фотографий.")
            return
        for key, name, table in (("format", s.fmt_name, pc.FORMATS), ("orient", s.orient_name, pc.ORIENTS), ("mode", s.mode_name, pc.MODES)):
            if name in table:
                self.s[key] = name
        self._building = True
        self.cb_format.setCurrentText(self.s["format"])
        self.seg_orient.set(self.s["orient"])
        self.seg_mode.set(self.s["mode"])
        self.seg_mode2.set(self.s["mode"])
        self._building = False
        self.set_files(s.folder, s.files, s.states, s.idx)

    # ---------- отметки и рабочее поле
    def upd_counts(self):
        n, m = len(self.checked_files()), len(self.files)
        self.l_count.setText(trf("{n} из {m} отмечено", n=n, m=m) if m else "")
        self.update_info()

    def on_tile(self, i):
        if not (0 <= i < len(self.files)):
            return
        f = self.files[i]
        if f not in self.checked:                    # щёлкнул по неотмеченному фото — оно включается в работу
            self.checked.add(f)
            self.upd_counts()
        if i != self.idx:
            self.show_photo(i)
        else:
            self.thumbs_view.viewport().update()

    def toggle_check(self, i, shift=False):
        if not (0 <= i < len(self.files)):
            return
        f = self.files[i]
        on = f not in self.checked
        if shift and self._last_check is not None:   # Shift: отметить диапазон
            a, b = sorted((self._last_check, i))
            for g in self.files[a:b + 1]:
                (self.checked.add if on else self.checked.discard)(g)
        elif on:
            self.checked.add(f)
        else:
            self.checked.discard(f)
        self._last_check = i
        self.upd_counts()
        self.sync_work(f if (on and not shift) else None)

    def check_all(self, on):
        self.checked = set(self.files) if on else set()
        self.upd_counts()
        self.sync_work()

    def sync_work(self, newly=None):
        """Рабочее поле показывает только отмеченные фото."""
        self.thumbs_view.viewport().update()
        if not self.files:
            return
        chk = [i for i, f in enumerate(self.files) if f in self.checked]
        if not chk:
            self.idx = -1
            self.raw = self.preview = self.preview_pm = None
            self.img_size = (0, 0)
            self.redraw()
            return
        if newly is not None and newly in self.checked:
            self.show_photo(self.files.index(newly))
            return
        if self.idx >= 0 and self.files[self.idx] in self.checked and self.preview_pm is not None:
            self.redraw()
            return
        self.show_photo(next((i for i in chk if i > self.idx), chk[-1]))

    def remove_unchecked(self):
        if not self.files:
            return
        keep = self.checked_files()
        if not keep:
            info(self, "Ни одно фото не отмечено. Отметьте нужные («+» в углу превью).")
            return
        if len(keep) == len(self.files):
            return
        if not ask_soft(self, "Убрать из списка %d неотмеченных фото?\nФайлы на диске не удаляются." % (len(self.files) - len(keep))):
            return
        cur = self.files[self.idx] if self.idx >= 0 else None
        self.files = keep
        self.states = {f: self.states[f] for f in keep}
        self._undo, self._redo = [], []
        self.thumbs_view.model().refresh()
        self.upd_counts()
        self.show_photo(keep.index(cur) if cur in keep else 0)

    def go(self, d):
        chk = [i for i, f in enumerate(self.files) if f in self.checked]
        if not chk:
            return
        if self.idx in chk:
            p = max(0, min(len(chk) - 1, chk.index(self.idx) + d))
        else:
            p = 0 if d >= 0 else len(chk) - 1
        if chk[p] != self.idx:
            self.show_photo(chk[p])

    def show_photo(self, i):
        if not self.files:
            return
        self.idx = i
        f = self.files[i]
        st = self.states[f]
        try:
            self.img_size = pc.true_size(f, st.rotation)
            self.raw, self.icc = pc.load_preview(f, st.rotation)
            self.refresh_proof()
        except Exception as ex:
            self.raw = self.preview = self.preview_pm = None
            self.img_size = (0, 0)
            self.l_info.setText("%s: %s (%s)" % (f.name, tr("не удалось открыть"), ex))
        self.thumbs_view.viewport().update()
        self.thumbs_view.see(i)
        self.redraw()
        if self.view == "sheet":
            self.sheet_view.show_photo_page(f)
        if self.pages.currentIndex() == 1:
            self.sync_adj()
        self.smart_sync()

    def cur(self):
        if self.preview_pm is None or self.idx < 0 or self.idx >= len(self.files) or self.files[self.idx] not in self.checked:
            return None
        f = self.files[self.idx]
        st = self.states[f]
        W, H = self.img_size
        if not W or not H:
            return None
        orient = st.orient if st.orient else pc.ORIENTS[self.s["orient"]]
        return f, st, W, H, pc.paper_size(self.cell_fmt(), orient, W, H)

    def redraw(self):
        if self._building:
            return
        self.canvas.update()
        if self.view == "sheet":
            self.sheet_view.refresh()
        self.update_info()

    def update_info(self):
        self.smart_sync()
        cur = self.cur()
        chk = self.checked_files()
        L = self.layout_spec()
        ns = self.sheet_count()
        if self.sheet_mode():
            self.l_sheet.setText(trf("{n} фото на листе, ячейка {w}×{h} мм", n=self.s["nup"], w="%g" % round(L["cw"], 1), h="%g" % round(L["ch"], 1)))
            self.l_sheet2.setText((tr("Без полей, фото вплотную") if L["m"] <= 0 else trf("Белое поле {m} мм вокруг каждого фото", m="%g" % L["m"]))
                                  + ". " + trf("Листов к печати: {n}", n=ns))
        else:
            self.l_sheet.setText(tr("Одно фото на лист, без полей"))
            self.l_sheet2.setText(trf("Листов к печати: {n}", n=ns))
        self.b_save.setText((trf("Сохранить листы · {n}", n=ns) if self.sheet_mode() else trf("Сохранить отмеченные · {n}", n=len(chk)))
                            if self.files else tr("Сохранить отмеченные"))
        self.b_undo.setEnabled(bool(self._undo))
        self.b_redo.setEnabled(bool(self._redo))
        if not cur:
            self.l_pos.setText("0 / %d" % len(chk))
            self.l_pos.setMinimumWidth(self._pos_width("0 / %d" % len(chk)))
            self.l_angle.setText("0,0°")
            self.l_copies.setText("1")
            self.l_dot.setStyleSheet("color: %s;" % T["muted"])
            if not self.files:
                self.l_info.setText(tr("Откройте фото или папку"))
            elif not chk:
                self.l_info.setText(tr("Отмечено фото: 0"))
            return
        f, st, W, H, paper = cur
        mode = self.mode()
        dpi = pc.effective_dpi(W, H, paper, st, mode)
        if mode == "crop":
            g = pc.frame_geom(W, H, paper, st)
            part = tr("кадр") + " %d×%d px" % (round(g[2]), round(g[3]))
            if not pc.frame_inside(W, H, g):
                part += ", " + tr("есть белые поля")
        else:
            part = tr("без обрезки")
        self.l_dot.setStyleSheet("color: %s;" % (T["ok"] if dpi >= 250 else T["warn"] if dpi >= 150 else T["bad"]))
        self.l_info.setText("%s ≈ %d dpi      %s      %d×%d px      %s" % (tr("печать"), round(dpi), f.name, W, H, part))
        txt = "%d / %d" % (chk.index(f) + 1, len(chk))
        self.l_pos.setText(txt)
        self.l_pos.setMinimumWidth(self._pos_width(txt))
        self.l_angle.setText(("%.1f°" % st.angle).replace(".", ","))
        self.l_copies.setText(str(st.copies))

    def _thumbs_ready(self):
        self.thumbs_view.viewport().update()

    # ---------- отмена / повтор
    @staticmethod
    def _st_tuple(st):
        return tuple(getattr(st, k) for k in pc.CropState.__slots__ if k != "adj") + (tuple(sorted(st.adj.items())),)

    def push_undo(self, files, key=None, merge=0.0):
        now = time.time()
        if key is not None and key == self._undo_key and now - self._undo_t < merge:
            self._undo_t = now
            return
        self._undo.append({f: self.states[f].copy() for f in files})
        del self._undo[:-pc.UNDO_LIMIT]
        self._redo.clear()
        self._undo_key, self._undo_t = key, now

    def undo_trim(self, f):
        if self._undo and list(self._undo[-1]) == [f] and self._st_tuple(self._undo[-1][f]) == self._st_tuple(self.states[f]):
            self._undo.pop()
        self.update_info()

    def _apply_snapshot(self, snap):
        rot_changed = False
        for f, st in snap.items():
            if f not in self.states:
                continue
            if self.idx >= 0 and f == self.files[self.idx] and self.states[f].rotation != st.rotation:
                rot_changed = True
            self.states[f] = st.copy()
        first = next((f for f in snap if f in self.states), None)
        if first is None:
            return
        i = self.files.index(first)
        self._undo_key = None
        if first not in self.checked:
            self.checked.add(first)
            self.upd_counts()
        if i != self.idx or rot_changed:
            self.show_photo(i)
        else:
            self.refresh_proof()
            self.thumbs_view.viewport().update()
            self.redraw()
            if self.pages.currentIndex() == 1:
                self.sync_adj()

    def undo(self):
        if not self._undo:
            return
        snap = self._undo.pop()
        self._redo.append({f: self.states[f].copy() for f in snap if f in self.states})
        self._apply_snapshot(snap)

    def redo(self):
        if not self._redo:
            return
        snap = self._redo.pop()
        self._undo.append({f: self.states[f].copy() for f in snap if f in self.states})
        self._apply_snapshot(snap)

    # ---------- действия с рамкой
    def mark(self, f):
        self.states[f].edited = True

    def zoom(self, factor):
        cur = self.cur()
        if not cur or self.mode() != "crop":
            return
        f, st, W, H, paper = cur
        self.push_undo([f], ("zoom", f), 0.8)
        st.scale *= factor
        pc.normalize(st)
        self.mark(f)
        self.redraw()

    def tilt(self, delta):
        cur = self.cur()
        if not cur or self.mode() != "crop":
            return
        f, st, W, H, paper = cur
        self.push_undo([f], ("tilt", f) if delta is not None else None, 0.8)
        st.angle = 0.0 if delta is None else round(st.angle + delta, 3)
        pc.normalize(st)
        self.mark(f)
        self.redraw()

    def flip_frame(self):
        cur = self.cur()
        if not cur:
            return
        f, st, W, H, paper = cur
        self.push_undo([f])
        st.orient = "landscape" if paper[0] < paper[1] else "portrait"
        pc.normalize(st)
        self.mark(f)
        self.redraw()

    def rotate_photo(self, deg):
        if not self.cur():
            return
        f = self.files[self.idx]
        st = self.states[f]
        self.push_undo([f])
        st.rotation = pc.rot_add(st.rotation, deg)
        st.cx = st.cy = 0.5
        st.scale, st.angle, st.orient = 1.0, 0.0, None
        self.mark(f)
        self.show_photo(self.idx)

    def flip_photo(self, axis):
        """Отразить фото по горизонтали («h») или вертикали («v»)."""
        if not self.cur():
            return
        f = self.files[self.idx]
        st = self.states[f]
        self.push_undo([f])
        st.rotation = pc.rot_flip(st.rotation, axis)
        st.cx = st.cy = 0.5
        st.scale, st.angle, st.orient = 1.0, 0.0, None
        self.mark(f)
        self.show_photo(self.idx)

    def reset_frame(self):
        if not self.cur():
            return
        f = self.files[self.idx]
        st = self.states[f]
        self.push_undo([f])
        st.cx = st.cy = 0.5
        st.scale, st.angle, st.orient = 1.0, 0.0, None
        st.edited = bool(st.rotation or st.copies != 1 or st.adj)
        self.thumbs_view.viewport().update()
        self.redraw()

    def reset_all(self):
        if not self.files or not ask_soft(self, "Сбросить рамки, повороты, число копий и цветокоррекцию у всех фотографий?"):
            return
        self.push_undo(self.files)
        self.states = {f: pc.CropState() for f in self.files}
        if self.idx >= 0:
            self.show_photo(self.idx)

    def _orient_changed(self, v):
        if self._building:
            return
        self.s["orient"] = v
        changed = [f for f, st in self.states.items() if st.orient is not None]
        if changed:
            self.push_undo(changed)
        auto_keys = [f for f, r in self.sm_res.items() if f in self.states and r.get("key") == self.sm_key(self.states[f])]
        for st in self.states.values():
            st.orient = None
        for f in auto_keys:                              # рамки, поставленные умной рамкой, остаются «автоматическими»
            self.sm_res[f]["key"] = self.sm_key(self.states[f])
        self.smart_cfg_changed()
        self.redraw()

    def copies_step(self, d):
        if not self.cur():
            return
        f = self.files[self.idx]
        st = self.states[f]
        n = max(1, min(99, st.copies + d))
        if n != st.copies:
            self.push_undo([f], ("copies", f), 1.0)
            st.copies = n
            st.edited = True
            self.thumbs_view.viewport().update()
            self.redraw()

    # ---------- цвет: профиль принтера и экранная имитация
    def cm_build(self):
        return pc.cm_build(self.s["icc"], self.s["intent"], self.s["bpc"], self.s["embed"])

    def _cm_set(self, key, on):
        if self._building:
            return
        self.s[key] = bool(on)
        self.cm_changed()
        if key == "cm_on" and on:
            self._ccor_check()

    def cm_changed(self):
        icc = self.s["icc"].strip()
        if not getattr(self, "_prof_lock", False) and icc != getattr(self, "_pc_icc", icc) and pcr.norm(self.s["pcorr"]) != pcr.default():
            on = self.s["pcorr"]["on"]                       # другой файл ICC: поправка к прежнему профилю не подходит
            self.s["pcorr"] = pcr.default()
            self.s["pcorr"]["on"] = on
            self.pcorr_sync()
        self._pc_icc = icc
        self.profile_save()
        self._icc_info()
        self.refresh_proof()
        self.redraw()
        if self.pages.currentIndex() == 1:
            self.update_hist()

    def _icc_info(self):
        p = self.s["icc"].strip()
        if not p:
            txt = tr("Профиль не выбран")
        else:
            try:
                desc, space, ok = pc.profile_info(p)
                txt = desc
                if space != "RGB":
                    txt += " — " + tr("нужен RGB-профиль!")
                elif self.s["intent"] not in ok:
                    txt += " — " + tr("этот способ рендеринга профилем не поддерживается")
                elif self.s["intent"] == "Абсолютный колориметрический" and self.s["cm_on"]:
                    txt += " — " + tr("белые поля листа напечатаются красителем; для печати обычно берут «Относительный»")
            except Exception:
                txt = tr("Не удалось прочитать файл профиля")
        self.l_icc.setText(txt)
        if getattr(self, "l_icc2", None) is not None:
            try:
                self.l_icc2.setText(txt)
            except RuntimeError:
                pass

    def refresh_proof(self):
        """Экранная картинка: снимок → цветокоррекция → (по желанию) имитация печати и подсветка вне охвата."""
        base = self.raw
        self.adj_img = None
        self.gamut_pct = None
        if base is not None and self.idx >= 0 and not self.show_orig:
            st = self.states[self.files[self.idx]]
            if st.adj:
                try:
                    base = pc.adjust_tile(self.raw, pc.merge_adj({}, st), 100, preview=True)
                except Exception:
                    base = self.raw
        self.adj_img = base
        self.preview = base
        if base is not None and not self.show_orig and self.s["proof"] and self.s["cm_on"]:
            try:
                cm = self.cm_build()
                if self.s["gamut"]:
                    self.preview, self.gamut_pct = pc.gamut_preview(base, self.icc, cm)
                else:
                    self.preview = pc.proof_preview(base, self.icc, cm)
            except Exception:
                self.preview = base
        self.preview_pm = QPixmap.fromImage(pil_to_qimage(self.preview)) if self.preview is not None else None

    def open_cm_dialog(self):
        CmDialog(self).exec()
        self._building = True
        self.sw_cm.set(self.s["cm_on"])
        self.sw_cm2.set(self.s["cm_on"])
        self._building = False
        self.cm_changed()
        self._ccor_check()

    # ---------- цветокоррекция
    def cur_adj(self):
        return self.states[self.files[self.idx]].adj if self.idx >= 0 else {}

    def adj_files(self):
        if self.idx < 0:
            return []
        return self.checked_files() if self.s["adj_scope"] == "all" else [self.files[self.idx]]

    def adj_set(self, upd, files=None, key=None):
        if self.adj_lock or self._building:
            return
        files = files if files is not None else self.adj_files()
        if not files:
            return
        self.push_undo(files, ("adj", files[0] if len(files) == 1 else len(files), key or tuple(sorted(upd))), 1.0)
        for f in files:
            st = self.states[f]
            st.adj = pc.clean_adj({**st.adj, **upd})
            if st.adj:
                st.edited = True
        self._after_adj()

    def adj_replace(self, adj, files):
        if not files:
            return
        self.push_undo(files)
        new = pc.clean_adj(adj)
        for f in files:
            st = self.states[f]
            st.adj = dict(new)
            if new:
                st.edited = True
        self._after_adj()

    def adj_apply_each(self, mapping, drop_keys=()):
        files = list(mapping)
        if not files:
            return
        self.push_undo(files)
        for f in files:
            st = self.states[f]
            keep = {k: v for k, v in st.adj.items() if k not in drop_keys}
            st.adj = pc.clean_adj({**keep, **mapping[f]})
            if st.adj:
                st.edited = True
        self._after_adj()

    def _after_adj(self):
        self.thumbs_view.viewport().update()
        if not self._adj_timer.isActive():            # не чаще раза в ~40 мс при перетаскивании ползунка
            self._adj_timer.start()

    def _adj_redraw(self):
        if self.idx < 0:
            return
        self.refresh_proof()
        self.redraw()
        self._color_win_update()
        self.update_hist()

    def adj_show_original(self, on):
        if self.show_orig != on:
            self.show_orig = on
            self._adj_redraw()

    def _color_editors_enable(self, on):
        """Без открытого фото уровни, кривые и выбор по цветам недоступны (серые), а не молча не реагируют на мышь."""
        for w in (self.sel_panel, *self._levels_editors(), *self._curve_panels()):
            w.setEnabled(on)
            w.setToolTip("" if on else tr("Сначала откройте фото"))

    def sync_adj(self):
        self._color_editors_enable(self.idx >= 0)
        if self.idx < 0:
            return
        self.adj_lock = True
        try:
            full = pc.adj_full(self.cur_adj())
            for k, (s, step) in self.sliders.items():
                s.setValue(int(round(full[k] / step)))
                self.slider_lbl[k].setText(self._adj_fmt(k, full[k]))
            self.sw_bw.set(full["bw"])
            self.sw_sepia.set(full["sepia"])
            self.seg_auto.set(full["auto"])
            for ed in self._levels_editors():
                ed.set_value(full["levels"])
            for pnl in self._curve_panels():
                pnl.set_value(full["curves"])
            self.sel_panel.set_value(full["selcol"])
        finally:
            self.adj_lock = False
        self._color_hist()
        self._color_win_update()
        self.update_hist()

    def _curve_panels(self):
        w = getattr(self, "curves_win", None)
        return [self.curves_panel] + ([w.panel] if w is not None else [])

    def _levels_editors(self):
        w = getattr(self, "curves_win", None)
        return [self.levels_ed] + ([w.levels] if w is not None else [])

    def _color_win_update(self):
        w = getattr(self, "curves_win", None)
        if w is not None and w.isVisible():
            w.preview.set_pixmap(self.preview_pm)

    def _color_hist(self):
        """Гистограмма исходного (ещё не исправленного) кадра — подложка для уровней и кривых."""
        if self.raw is None:
            h = None
        else:
            if getattr(self, "_hist_img", None) is not self.raw:
                small = self.raw
                if max(small.size) > 800:
                    small = small.copy()
                    small.thumbnail((800, 800))
                self._hist_img, self._hist_src = self.raw, pc.hist_rgb(small)[0]
            h = self._hist_src
        for ed in self._levels_editors():
            ed.set_hist(h)
        for pnl in self._curve_panels():
            pnl.set_hist(h)

    def levels_changed(self, val, sender=None):
        self.adj_set({"levels": val}, key=("levels",))
        for ed in self._levels_editors():
            if ed is not sender:
                ed.set_value(val)

    def selcol_changed(self, val):
        self.adj_set({"selcol": val}, key=("selcol",))

    def curves_changed(self, sender, val):
        self.adj_set({"curves": val}, key=("curves",))
        for pnl in self._curve_panels():
            if pnl is not sender:
                pnl.set_value(val)

    def open_curves_window(self):
        self.open_color_window(1)

    def open_color_window(self, tab=1):
        """Большой экран: уровни (0) или кривые (1) слева, редактируемое фото справа."""
        w = getattr(self, "curves_win", None)
        if w is None:
            w = self.curves_win = ColorWindow(self)
            w.panel.changed.connect(lambda v: self.curves_changed(w.panel, v))
            w.levels.changed.connect(lambda v: self.levels_changed(v, w.levels))
            w.levels.auto_requested.connect(self.levels_auto)
        full = pc.adj_full(self.cur_adj()) if self.idx >= 0 else pc.adj_full({})
        w.panel.set_value(full["curves"])
        w.levels.set_value(full["levels"])
        w.show_tab(tab)
        self._color_editors_enable(self.idx >= 0)
        self._color_hist()
        w.show()
        w.preview.set_pixmap(self.preview_pm)
        w.raise_()
        w.activateWindow()

    def levels_auto(self):
        if self.idx < 0 or self.raw is None:
            return
        small = self.raw
        if max(small.size) > 800:
            small = small.copy()
            small.thumbnail((800, 800))
        val = ct.auto_levels_rows(*pc._auto_bounds(small.convert("RGB"), "color"))
        self.adj_set({"levels": val}, key=("levels",))
        for ed in self._levels_editors():
            ed.set_value(val)

    def update_hist(self, note=None):
        img = self.adj_img if self.adj_img is not None else self.raw
        if img is None:
            self.hist.set(None)
            return
        try:
            h, low, high = pc.hist_rgb(img)
        except Exception:
            return
        self.hist.set(h)
        t = note or (tr("В чёрном") + ": %.1f%%   " % low + tr("В белом") + ": %.1f%%" % high)
        if note is None and self.gamut_pct is not None:
            t += "   " + tr("Вне охвата принтера") + ": %.1f%%" % self.gamut_pct
        self.l_hist.setText(t)
        self.l_hist.setStyleSheet("color: %s;" % (T["bad"] if (note is None and (low > 1 or high > 1)) else T["muted"]))

    @staticmethod
    def _small(f):
        with pc.Image.open(f) as im:
            im.draft("RGB", (600, 600))
            im = pc.to_rgb(pc.ImageOps.exif_transpose(im))
            im.thumbnail((500, 500), pc.RESAMPLE_FAST)
            return im

    def enhance(self, level, files=None):
        files = list(files) if files is not None else self.adj_files()
        if not files or getattr(self, "_enh_busy", False):
            return
        name = tr("Супер улучшения") if level >= 2 else tr("Улучшения для Epson")
        if len(files) > 1 and not ask_soft(self, tr("Применить «%s» к %d фото?") % (name, len(files)) + "\n" + tr(
                "Для каждого фото параметры подберутся отдельно, прежняя коррекция будет сброшена. Отменить можно Ctrl+Z.")):
            return
        self._enh_busy = True
        QApplication.setOverrideCursor(Qt.WaitCursor)
        mapping, bad = {}, 0
        try:
            for n, f in enumerate(files):
                try:
                    mapping[f] = pc.enhance_adj(pc.analyze_image(self._small(f)), level)
                except Exception:
                    bad += 1
                if n % 3 == 2:
                    self.l_enh.setText(tr("Анализ") + ": %d / %d…" % (n + 1, len(files)))
                    self.l_enh.show()
                    QApplication.processEvents()
        finally:
            QApplication.restoreOverrideCursor()
            self._enh_busy = False
        notes = []
        cur = self.files[self.idx]
        if cur in mapping and self.raw is not None and self.s["cm_on"]:      # цвета не должны уходить за охват принтера
            try:
                cm = self.cm_build()
                for _ in range(2):
                    probe = type("S", (), {"adj": {**{k: v for k, v in self.states[cur].adj.items() if k not in pc.ADJ_KEYS}, **mapping[cur]}})()
                    test = pc.adjust_tile(self.raw, pc.merge_adj({}, probe), 100, preview=True)
                    pct = pc.gamut_preview(test, self.icc, cm)[1]
                    boost = any(s > 0 for _h, s, _l in ct.selcol_full(mapping[cur].get("selcol")))
                    if pct <= 3.0 or not (mapping[cur].get("vib") or mapping[cur].get("sat") or boost):
                        break
                    half = {"selcol": pc.halve_selcol_sat(mapping[cur]["selcol"])} if boost else {}
                    mapping[cur] = pc.clean_adj({**mapping[cur], **half, "vib": mapping[cur].get("vib", 0) / 2, "sat": 0})
                    notes.append(tr("красочность уменьшена: принтер не передаёт часть цветов"))
            except Exception:
                pass
        self.adj_apply_each(mapping, pc.ADJ_KEYS)          # прежняя коррекция сбрасывается целиком
        if self.s["dpi"].replace(",", ".").strip() not in ("360", "720"):
            self.s["dpi"] = "360"                                           # родное разрешение печати Epson
            notes.append(tr("разрешение сохранения 360 dpi"))
        self.sync_adj()
        msg = tr("Готово") + ": %d" % len(mapping) + ((", " + tr("не удалось") + " %d" % bad) if bad else "")
        self.l_enh.setText(msg + (". " + "; ".join(notes) if notes else "") + ".")
        self.l_enh.show()

    def adj_apply_all(self):
        if self.idx < 0:
            return
        if len(self.files) > 1 and not ask_soft(self, "Применить настройки этого фото ко всем фотографиям?\n"
                                                 "Их собственная коррекция будет заменена. Отменить можно Ctrl+Z."):
            return
        self.adj_replace(self.cur_adj(), list(self.files))

    def adj_copy(self):
        if self.idx < 0:
            return
        self.adj_clipboard = dict(self.cur_adj())
        self.update_hist(tr("Настройки скопированы — перейдите к другому фото и нажмите «Вставить»"))

    def adj_paste(self, to_all):
        if self.idx < 0:
            return
        if self.adj_clipboard is None:
            info(self, "Сначала нажмите «Копировать» на фото с нужными настройками.")
            return
        self.adj_replace(self.adj_clipboard, list(self.files) if to_all else [self.files[self.idx]])
        self.sync_adj()

    def preset_name(self, n):
        name = str(self.settings.get("adj_preset_names", {}).get(str(n), "")).strip()
        return name or tr("Пресет") + " %d" % n

    def _preset_tips(self):
        for n, b in self.b_pre.items():
            full = self.preset_name(n)
            fm = QFontMetrics(b.font())
            b.setText(fm.elidedText(full, Qt.ElideRight, 70))
            saved = str(n) in self.settings.get("adj_presets", {})
            b.setToolTip(full + ": " + (tr("Сохранённые настройки: нажмите, чтобы применить") if saved
                                        else tr("Пресет пуст: настройте ползунки и нажмите «Сохранить» под ним")))

    def preset_rename(self, n, name=None):
        """Своё имя пресета (до 20 символов). Пустое имя возвращает «Пресет n»."""
        if name is None:
            dlg = QInputDialog(self)
            dlg.setWindowTitle(tr("Переименовать пресет"))
            dlg.setLabelText(trf("Название пресета {n}", n=n))
            dlg.setTextValue(self.preset_name(n) if str(n) in self.settings.get("adj_preset_names", {}) else "")
            dlg.setOkButtonText(tr("Готово"))
            dlg.setCancelButtonText(tr("Отмена"))
            if not dlg.exec():
                return
            name = dlg.textValue()
        names = self.settings.setdefault("adj_preset_names", {})
        name = " ".join(str(name).split())[:20]
        if name:
            names[str(n)] = name
        else:
            names.pop(str(n), None)
        self.persist()
        self._preset_tips()

    def preset_pick(self, n):
        """Применяет сохранённый пресет к фото (или к отмеченным, как задано переключателем выше)."""
        data = self.settings.get("adj_presets", {}).get(str(n))
        if data is None:
            self.update_hist(trf("Пресет {n} пока пуст. Настройте ползунки и нажмите «Сохранить» под ним.", n=n))
            return
        if self.idx < 0:
            return
        self.adj_replace(data, self.adj_files())
        self.sync_adj()
        self.update_hist(trf("Применён пресет {n}", n=n))

    def preset_save(self, n):
        """Запоминает текущие настройки этого фото в пресет n, пока их не заменят другими."""
        if self.idx < 0:
            info(self, "Сначала откройте фото.")
            return
        presets = self.settings.setdefault("adj_presets", {})
        old, new = presets.get(str(n)), dict(self.cur_adj())
        old = pc.clean_adj(old) if old is not None else None             # из файла настроек списки возвращаются кортежами
        if old is not None and old != new and not ask(self, trf("Заменить сохранённый пресет {n} текущими настройками?", n=n)):
            return
        presets[str(n)] = new
        self.persist()
        self._preset_tips()
        self.update_hist(trf("Пресет {n} сохранён", n=n))

    def adj_reset(self, all_files):
        if self.idx < 0:
            return
        if all_files and not ask_soft(self, "Сбросить цветокоррекцию у всех фотографий?"):
            return
        self.adj_replace({}, list(self.files) if all_files else [self.files[self.idx]])
        self.sync_adj()

    def auto_bright(self):
        if self.idx < 0 or self.raw is None:
            return
        if self.s["adj_scope"] == "all":
            info(self, "Авто-яркость считается по каждому фото отдельно. Для всех сразу используйте «Авто-уровни».")
            return
        sug = pc.suggest_adjust(pc.analyze_image(self.raw))
        self.adj_set({"bright": sug.get("bright", 0.0), "contrast": sug.get("contrast", 0.0)}, files=[self.files[self.idx]])
        self.sync_adj()

    def sync_inspector(self):
        if self.idx >= 0 and self.pages.currentIndex() == 1:
            self.sync_adj()

    # ---------- сохранение
    def options(self):
        s = self.s
        try:
            dpi = float(s["dpi"].replace(",", "."))
            if not 50 <= dpi <= 2400:
                raise ValueError
        except ValueError:
            warn(self, "Укажите DPI числом от 50 до 2400.")
            return None
        import re
        outdir = s["outdir"].strip()
        out_name = re.sub(r'[\\/:*?"<>|]+', "", s["out_name"]).strip(" .") or pc.OUT_SUBDIR
        if s["out_mode"] == "custom" and not outdir:
            warn(self, "Укажите папку для сохранения или выберите «Рядом с фото».")
            return None
        cm = None
        if s["cm_on"]:
            try:
                cm = self.cm_build()
            except ValueError as ex:
                warn(self, str(ex))
                return None
        return {"fmt": self.cell_fmt(), "orient": pc.ORIENTS[s["orient"]], "mode": pc.MODES[s["mode"]], "dpi": dpi,
                "resize": s["resize"], "filetype": s["filetype"], "quality": int(s["quality"]),
                "outdir": outdir, "out_mode": s["out_mode"], "out_name": out_name, "subfolder": s["subfolder"],
                "copies_in_name": s["copies_name"], "universe": [(f, self.states[f].copies) for f in self.files], "cm": cm}

    def save(self, all_files):
        if self.saving or not self.files:
            return
        o = self.options()
        if not o:
            return
        files = self.checked_files() if all_files else ([self.files[self.idx]] if self.cur() else [])
        if not files:
            info(self, "Ни одно фото не отмечено. Отметьте нужные («+» в углу превью).")
            return
        if all_files and self.sheet_mode():
            self._save_sheets(o, files)
            return
        jobs = [(f, self.states[f].copy()) for f in files]
        low = pc.low_res_list(jobs, o)
        if low:
            lst = "\n".join("%s — %s dpi" % (n, d) for n, d in low[:10]) + ("\n… +%d" % (len(low) - 10) if len(low) > 10 else "")
            if not ask(self, tr("Малое разрешение для печати (меньше 150 dpi), фото: %d") % len(low) + "\n\n" + lst + "\n\n"
                       + tr("Печать будет нерезкой. Всё равно сохранить?")):
                return
        self.saving = True
        self.b_save.setEnabled(False)
        self.progress.setRange(0, len(jobs))
        self.progress.setValue(0)
        self.progress.show()
        self.l_prog.setText(tr("Сохранение…"))
        self.l_prog.show()
        if self.settings.get("anim", True):
            st0 = self.states[files[0]]
            self.overlay.play(self.thumbs.get(files[0], st0.rotation), "save", trf("Сохраняю: {n}", n=len(jobs)))
        threading.Thread(target=self._save_worker, args=(jobs, o), daemon=True).start()

    def _save_worker(self, jobs, o):
        try:
            saved, errors = pc.process_batch(jobs, o, lambda i, n, name: self.sig.progress.emit(i, n, str(name)))
        except Exception as ex:
            saved, errors = [], ["%s: %s" % (ex.__class__.__name__, ex)]
        try:
            dirs = [str(d) for d in pc.out_dirs(jobs, o)]
        except Exception:
            dirs = []
        self.sig.done.emit(len(saved), [str(e) for e in errors], o, dirs)

    # ---------- листы: сохранение в файлы и печать
    def _sheet_job(self, kind_dir, ppi, fmt, cm):
        plan, photos, o, L = self.sheet_plan()
        o["export_fmt"] = fmt
        return {"kind": "export", "o": o, "idxs": list(range(len(plan["sheets"]))), "plan": plan, "photos": photos,
                "ppi": int(round(ppi)), "mode": self.mode(), "cm": cm, "dir": str(kind_dir)}

    def _busy(self, n, text, files, kind):
        self.saving = True
        self.b_save.setEnabled(False)
        self.b_print.setEnabled(kind == "print" and not files)      # во время печати кнопка остаётся яркой: на ней идёт анимация
        self.progress.setRange(0, max(1, n))
        self.progress.setValue(0)
        self.progress.show()
        self.l_prog.setText(text)
        self.l_prog.show()
        if self.settings.get("anim", True) and files:
            self.overlay.play(self.thumbs.get(files[0], self.states[files[0]].rotation), kind, text)

    def _save_sheets(self, o, files):
        outdir = Path(o["outdir"]) if o["out_mode"] == "custom" else Path(self.src_dir or files[0].parent) / o["out_name"]
        try:
            c = self._sheet_job(outdir, o["dpi"], o["filetype"], o["cm"])
        except Exception as ex:
            warn(self, str(ex))
            return
        if not c["idxs"]:
            return
        self._busy(len(c["idxs"]), trf("Сохраняю листы: {n}", n=len(c["idxs"])), files, "save")

        def work():
            errors, n = [], 0
            try:
                res = pc.run_sheets_job(c, lambda j, total, text: self.sig.progress.emit(j, total, str(text)), threading.Event())
                n = len(res[3]) if res[0] == "done" else 0
            except Exception as ex:
                errors = ["%s: %s" % (ex.__class__.__name__, ex)]
            self.sig.done.emit(n, errors, dict(o, outdir=str(outdir)), [str(outdir)])
        threading.Thread(target=work, daemon=True).start()

    def _print_sheets(self, files):
        o = self.options()
        if not o:
            return
        tmp = pc.AGENT_DIR / "print_sheets"
        try:
            if tmp.is_dir():
                for q in tmp.iterdir():
                    if q.is_file():
                        q.unlink()
            c = self._sheet_job(tmp, o["dpi"], "JPEG", None)       # профиль принтера применит само окно печати
        except Exception as ex:
            warn(self, str(ex))
            return
        if not c["idxs"]:
            return
        self._busy(len(c["idxs"]), trf("Готовлю листы к печати: {n}", n=len(c["idxs"])), files, "print")

        def work():
            try:
                res = pc.run_sheets_job(c, lambda j, total, text: self.sig.progress.emit(j, total, str(text)), threading.Event())
                self.sig.sheets_ready.emit([str(x) for x in res[3]] if res[0] == "done" else [], "")
            except Exception as ex:
                self.sig.sheets_ready.emit([], "%s: %s" % (ex.__class__.__name__, ex))
        threading.Thread(target=work, daemon=True).start()

    def _print_sheets_ready(self, files, err):
        self.saving = False
        self.b_save.setEnabled(True)
        self.b_print.setEnabled(True)
        self.progress.hide()
        self.l_prog.hide()
        if err or not files:
            warn(self, tr("Не удалось подготовить листы") + (":\n" + err if err else ""))
            return
        sheets = [Path(f) for f in files]
        ses = pc.AgentSession(persist=False)                      # готовые листы уходят в окно печати как обычные фото «одно на лист»
        ses.files, ses.states, ses.idx = sheets, {f: pc.CropState() for f in sheets}, 0
        ses.folder, ses.recursive = sheets[0].parent, False
        ses.fmt_name, ses.orient_name, ses.mode_name = self.s["format"], next(iter(pc.ORIENTS)), next(iter(pc.MODES))
        self.persist()
        fresh = pc.load_settings()
        pr = dict(fresh.get("print", {}))
        pr.update(layout="Одно фото на листе", copies="1")
        fresh["print"] = pr
        pc.save_settings(fresh)
        self.settings = fresh
        self._launch_print(ses.to_project(full=False))

    def _launch_print(self, project):
        path = pc.AGENT_DIR / "qt_print_project.json"
        try:
            pc.write_json_atomic(path, project)
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, "--print-project", str(path)]
            else:
                cmd = [sys.executable, str(Path(pc.__file__).resolve()), "--print-project", str(path)]
            subprocess.Popen(cmd)
            return True
        except Exception as ex:
            warn(self, tr("Не удалось открыть окно печати") + ":\n%s" % ex)
            return False

    def _save_progress(self, i, n, name):
        self.progress.setValue(i)
        if name.startswith("\x01"):                          # печать: текст движка и анимация на каждый отправленный лист
            name = name[1:]
            self.l_prog.setText(tr(name))
            if not name.startswith("Готовлю"):
                self._sheet_sent(i, n)
            return
        self.l_prog.setText("%d / %d: %s" % (i, n, name))

    def _save_done(self, ok, errors, o, dirs):
        self.saving = False
        self.b_save.setEnabled(True)
        self.b_print.setEnabled(True)
        self.progress.hide()
        out = dirs[0] if dirs else o["outdir"]
        self.l_prog.setText(trf("Готово: {n} файл(ов)", n=ok))
        text = tr("Сохранено файлов") + ": %d\n" % ok + tr("Папка") + ": %s" % out + ("  (+%d)" % (len(dirs) - 1) if len(dirs) > 1 else "")
        if o.get("cm"):
            text += "\n" + tr("Профиль принтера") + ": %s" % o["cm"]["name"]
        if errors:
            warn(self, text + "\n\n" + tr("Ошибки") + " (%d):\n" % len(errors) + "\n".join(errors[:15]))
        elif ask(self, text + "\n\n" + tr("Открыть папку?")) and hasattr(os, "startfile"):
            os.startfile(out)

    # ---------- печать (окно печати — прежнее; получает только отмеченные фото)
    def open_print(self):
        if self.saving:
            return
        files = self.checked_files()
        if not files:
            info(self, "Ни одно фото не отмечено. Отметьте нужные («+» в углу превью).")
            return
        if self.sheet_mode():
            self._print_sheets(files)
            return
        self.persist()
        if self._launch_print(self._session(files).to_project(full=False)) and self.settings.get("anim", True):
            st0 = self.states[files[0]]
            self.overlay.play(self.thumbs.get(files[0], st0.rotation), "print", trf("На печать: {n} фото", n=len(files)))

    # ---------- настройки
    def persist(self):
        s = self.s
        self._bleed_flush()
        fresh = pc.load_settings()                    # окно печати пишет свои разделы в тот же файл — не затираем их
        for k in ("last_dir", "start_dir_mode", "snap_px", "anim", "icc_dir", "check_updates", "skip_update", "doc_paper", "doc_fit", "doc_margin", "doc_cm_on", "doc_icc", "converter_path", "adj_presets", "adj_preset_names", "confirm_actions", "agent_enabled", "agent_badge", "agent_lock", "agent_token", "agent_port", "agent_allow_print", "agent_max_sheets", "agent_confirm_print"):
            if k in self.settings:
                fresh[k] = self.settings[k]
        fresh.update(format=s["format"], orient=s["orient"], mode=s["mode"], recursive=s["recursive"], subfolder=s["subfolder"],
                     copies_in_name=s["copies_name"], resize=s["resize"], filetype=s["filetype"], quality=int(s["quality"]),
                     grid=s["grid"], out_mode=s["out_mode"], out_name=s["out_name"].strip() or pc.OUT_SUBDIR,
                     cm_on=s["cm_on"], icc=s["icc"].strip(), intent=s["intent"], bpc=s["bpc"], embed=s["embed"], pcorr=pcr.norm(s["pcorr"]),
                     snap=s["snap"], language=pc.get_language(), theme=self.theme_name,
                     nup=s["nup"], borders=s["borders"], border_mm=self.border_mm(), sheet_fill=s["fill"], qt_print=dict(self.pr),
                     cell_mode=s["cell_mode"], cell_w=self.cell_mm()[0], cell_h=self.cell_mm()[1],
                     smart=dict(self.sm))
        for k in ("print_devmodes", "print_printer", "print_profiles", "print_quick"):
            if k in self.settings:
                fresh[k] = self.settings[k]
        if s["out_mode"] == "custom":
            fresh["outdir_custom"] = s["outdir"].strip()
        try:
            fresh["dpi"] = float(s["dpi"].replace(",", "."))
        except ValueError:
            pass
        self.settings = fresh
        pc.save_settings(fresh)

    def open_settings(self):
        SettingsDialog(self).exec()

    def apply_look(self, theme=None, lang=None):
        """Смена темы или языка: окно собирается заново, открытые фото и рамки остаются."""
        if theme:
            self.theme_name = theme
            T.clear()
            T.update(THEMES[theme])
        if lang:
            pc.set_language(lang)
        page = self.pages.currentIndex()
        self.setWindowTitle(tr("КопиТехник Принт — кадрирование для фотопечати"))
        self.build()
        self.thumbs_view.model().refresh()
        if self.idx >= 0:
            self.thumbs_view.see(self.idx)
        if page == 1 and self.files:
            self.show_page(1)

    def closeEvent(self, e):
        if self.printing and not ask(self, "Идёт печать. Прервать и выйти?"):
            e.ignore()
            return
        self.cancel.set()
        if self.saving and not self.printing and not ask(self, "Идёт сохранение. Всё равно выйти?"):
            e.ignore()
            return
        enabled = self.settings.get("agent_enabled", False)
        self.agent_stop()                                          # файл с адресом агента удаляется; включённость запоминаем
        self.settings["agent_enabled"] = enabled
        try:
            self._autosave_now()
        except Exception:
            pass
        try:
            self.persist()
        except Exception:
            pass
        e.accept()


class _ResetSlider(QSlider):
    """Ползунок: двойной щелчок возвращает исходное значение."""
    reset = Signal()

    def mouseDoubleClickEvent(self, e):
        self.reset.emit()

    def wheelEvent(self, e):
        e.ignore()                       # колесо прокручивает панель, а не дёргает ползунок случайно


# ---------------------------------------------------------------- окно «Открыть»: фото и папки в одном месте

class OpenDialog(QDialog):
    """Одна кнопка на всё: выделили фото — откроются они; ничего не выделили — откроется вся папка;
    выделили одну папку — она целиком. Результат в self.choice: ("files", [пути], добавить) | ("folder", путь, добавить)."""

    def __init__(self, app, start):
        super().__init__(app)
        self.app, self.choice = app, None
        self.cwd = Path(start) if start and Path(start).is_dir() else Path(pc.desktop_dir())
        self.n_files = 0
        self.setWindowTitle(tr("Открыть фото, документ или папку"))
        self.resize(980, 660)
        self.e_path = QLineEdit(str(self.cwd))
        self.e_path.returnPressed.connect(lambda: self.goto(self.e_path.text()))
        top = hbox(ibtn("up", "На уровень выше", self.up, boxed=True), self.e_path, spacing=8)
        places = vbox(lbl("Места", "title"), spacing=2)
        home = Path.home()
        for text, ico, pth in (("Рабочий стол", "desktop", Path(pc.desktop_dir())), ("Изображения", "image", home / "Pictures"),
                               ("Загрузки", "download", home / "Downloads")):
            if pth.is_dir():
                places.addWidget(self._place(text, ico, pth))
        if sys.platform == "win32":
            import string
            for c in string.ascii_uppercase:
                if os.path.exists(c + ":\\"):
                    places.addWidget(self._place(c + ":", "disk", Path(c + ":\\"), translate=False))
        places.addStretch(1)
        side = QFrame()
        side.setObjectName("card")
        side.setFixedWidth(190)
        places.setContentsMargins(8, 12, 8, 8)
        side.setLayout(places)
        self.list = QListWidget()
        self.list.setViewMode(QListView.IconMode)
        self.list.setResizeMode(QListView.Adjust)
        self.list.setMovement(QListView.Static)
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setIconSize(QSize(104, 104))
        self.list.setGridSize(QSize(128, 146))
        self.list.setWordWrap(True)
        self.list.setUniformItemSizes(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setStyleSheet("QListWidget::item { border-radius: 9px; padding: 4px; color: %s; }"
                                "QListWidget::item:hover { background: %s; }"
                                "QListWidget::item:selected { background: %s; border: 1.5px solid %s; }"
                                % (T["text"], T["raised"], T["hover"], T["select"]))
        self.list.itemSelectionChanged.connect(self.upd)
        self.list.itemDoubleClicked.connect(self._dbl)
        self.sw_rec = Switch(app.s["recursive"])
        self.sw_rec.toggled.connect(lambda on: (app.s.__setitem__("recursive", bool(on)), self.upd()))
        self.sw_add = Switch(False)
        self.l_hint = lbl("", "muted")
        self.b_ok = btn("Открыть", self.accept_choice, "primary", big=True)
        self.b_ok.setMinimumWidth(280)
        self.b_ok.setDefault(True)
        opts = hbox(self.sw_rec, lbl("с подпапками"), 14, spacing=8)
        if app.files:
            opts.addWidget(self.sw_add)
            opts.addWidget(lbl("добавить к уже открытым"))
        opts.addStretch(1)
        opts.addWidget(self.l_hint)
        bottom = hbox(lbl("Ctrl или Shift — выбрать несколько, Ctrl+A — все", "muted"), None, btn("Отмена", self.reject, big=True), self.b_ok, spacing=10)
        right = vbox(top, self.list, opts, spacing=10)
        body = hbox(side, right, spacing=12)
        self.setLayout(vbox(body, bottom, spacing=12, margins=(14, 14, 14, 14)))
        sc = QShortcut(QKeySequence("Backspace"), self.list, activated=self.up)
        sc.setContext(Qt.WidgetShortcut)               # только в списке: в строке пути Backspace стирает символ
        self._pending, self._pending_dirs, self._dir_info = [], [], {}
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._load_visible)
        self._timer.start()
        self._folder_icon = self._big_icon("open", T["select"])
        self._blank_icon = self._big_icon("image", T["muted"])
        self._doc_icon = self._big_icon("doc", T["accent"])
        self.fill()

    def _place(self, text, ico, pth, translate=True):
        b = QPushButton(tr(text) if translate else text)
        b.setProperty("kind", "place")
        b.setIcon(icon(ico, T["muted"]))
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(lambda _=False, q=pth: self.goto(q))
        return b

    @staticmethod
    def _big_icon(name, color):
        pm = QPixmap(104, 104)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T["raised"]))
        p.drawRoundedRect(QRectF(0, 0, 104, 104), 10, 10)
        QSvgRenderer(QByteArray(svg_bytes(name, color, 1.3))).render(p, QRectF(26, 26, 52, 52))
        p.end()
        return QIcon(pm)

    def fill(self):
        self.list.clear()
        self._pending, self._pending_dirs = [], []
        dirs, files = pc.OpenDialog.list_dir(self.cwd)
        self.n_files = len(files)
        for q in dirs:
            it = QListWidgetItem(self._folder_icon, q.name or str(q))
            it.setData(Qt.UserRole, ("d", str(q)))
            self.list.addItem(it)
            self._pending_dirs.append(it)
        for q in files:
            it = QListWidgetItem(self._blank_icon, q.name)
            it.setData(Qt.UserRole, ("f", str(q)))
            it.setToolTip(q.name)
            self.list.addItem(it)
            self._pending.append(it)
        try:                                               # документы (PDF, Word, Excel, ...) тоже видны, миниатюр у них нет
            docs = sorted((q for q in self.cwd.iterdir() if q.suffix.lower() in DOC_EXTS and not q.name.startswith(("~", ".")) and q.is_file()),
                          key=lambda q: q.name.lower())
        except OSError:
            docs = []
        for q in docs:
            it = QListWidgetItem(self._doc_icon, q.name)
            it.setData(Qt.UserRole, ("x", str(q)))
            it.setToolTip(q.name)
            self.list.addItem(it)
        self.e_path.setText(str(self.cwd))
        self.upd()

    def _folder_preview(self, it):
        """Превью папки: мозаика из первых фото внутри и число фото; None — миниатюры ещё грузятся."""
        path = it.data(Qt.UserRole)[1]
        info = self._dir_info.get(path)
        if info is None:
            try:
                _d, files = pc.OpenDialog.list_dir(Path(path))
            except Exception:
                files = []
            info = self._dir_info[path] = [len(files), [str(q) for q in files[:4]]]
        total, first = info
        if not first:
            return False                                      # фото нет: остаётся значок папки
        pms = []
        for f in first:
            pm = self.app.thumbs.get(f, 0, 160)
            if pm is None:
                return None
            if not pm.isNull():
                pms.append(pm)
        S = 104
        out = QPixmap(S, S)
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T["raised"]))
        p.drawRoundedRect(QRectF(0, 0, S, S), 10, 10)
        p.setBrush(QColor(T["select"]))                       # «ушко» папки сверху
        p.drawRoundedRect(QRectF(0, 0, 46, 14), 6, 6)
        n = len(pms)
        cols = 1 if n == 1 else 2
        rows = 1 if n <= 2 else 2
        gap = 4.0
        area = QRectF(6, 12, S - 12, S - 18)
        cw, ch = (area.width() - gap * (cols - 1)) / cols, (area.height() - gap * (rows - 1)) / rows
        for i, pm in enumerate(pms):
            r, c = divmod(i, cols)
            cell = QRectF(area.left() + c * (cw + gap), area.top() + r * (ch + gap), cw, ch)
            clip = QPainterPath()
            clip.addRoundedRect(cell, 5, 5)
            p.save()
            p.setClipPath(clip)
            sc = max(cw / pm.width(), ch / pm.height())              # заполнить ячейку, обрезав лишнее
            w_, h_ = pm.width() * sc, pm.height() * sc
            p.drawPixmap(QRectF(cell.center().x() - w_ / 2, cell.center().y() - h_ / 2, w_, h_), pm, QRectF(pm.rect()))
            p.restore()
        txt = str(total) if total < 1000 else "999+"                 # число фото в папке
        f = QFont(p.font())
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        tw = QFontMetricsF(f).horizontalAdvance(txt) + 12
        badge = QRectF(S - tw - 4, S - 22, tw, 18)
        p.setBrush(QColor(0, 0, 0, 190))
        p.drawRoundedRect(badge, 9, 9)
        p.setPen(QColor(255, 255, 255))
        p.drawText(badge, Qt.AlignCenter, txt)
        p.end()
        it.setToolTip(trf("{n} фото", n=total) + ": " + Path(path).name)
        return QIcon(out)

    def _load_visible(self):
        """Миниатюры подгружаются только для видимых плиток — большие папки открываются сразу."""
        view = self.list.viewport().rect()
        if self._pending_dirs:
            keep, done = [], 0
            for it in self._pending_dirs:
                if done >= 3 or not self.list.visualItemRect(it).intersects(view):
                    keep.append(it)
                    continue
                res = self._folder_preview(it)
                if res is None:
                    keep.append(it)
                elif res is not False:
                    it.setIcon(res)
                done += 1
            self._pending_dirs = keep
        if not self._pending:
            return
        left = []
        for it in self._pending:
            if not self.list.visualItemRect(it).intersects(view):
                left.append(it)
                continue
            pm = self.app.thumbs.get(it.data(Qt.UserRole)[1], 0, 160)
            if pm is None:
                left.append(it)
            elif not pm.isNull():
                it.setIcon(QIcon(self._rounded(pm)))
        self._pending = left

    @staticmethod
    def _rounded(pm):
        out = QPixmap(pm.size())
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(out.rect()), 14, 14)
        p.setClipPath(path)
        p.drawPixmap(0, 0, pm)
        p.end()
        return out

    def goto(self, target):
        q = Path(str(target).strip().strip('"'))
        if q.is_file():
            q = q.parent
        if q.is_dir():
            self.cwd = q
            self.fill()

    def up(self):
        if self.cwd.parent != self.cwd:
            self.goto(self.cwd.parent)

    def _sel(self):
        out = []
        for it in self.list.selectedItems():
            k, q = it.data(Qt.UserRole)
            out.append((k, Path(q)))
        return out

    def _dbl(self, it):
        k, q = it.data(Qt.UserRole)
        if k == "d":
            self.goto(q)
        elif k == "x":
            self.choice = ("doc", Path(q), False)
            self.accept()
        else:
            self.choice = ("files", [Path(q)], self.sw_add.isChecked())
            self.accept()

    def _docs(self):
        sel = self._sel()
        docs = [q for k, q in sel if k == "x"]
        return docs if docs and len(docs) == len(sel) else []     # документ открывается, только если выделены одни документы

    def upd(self):
        sel = [x for x in self._sel() if x[0] != "x"]
        act = pc.OpenDialog.decide(sel, self.cwd, self.n_files)
        rec = self.app.s["recursive"]
        docs = self._docs()
        if docs:
            text, ok = trf("Открыть документ «{name}»", name=docs[0].name), True
        elif act is None:
            text, ok = tr("Открыть"), False
        elif act[0] == "files":
            text, ok = trf("Открыть выбранные фото ({n})", n=len(act[1])), True
        elif sel:
            text, ok = trf("Открыть папку «{name}» целиком", name=act[1].name or str(act[1])), True
        else:
            text = trf("Открыть всю папку ({n} фото)", n=self.n_files) if not rec else tr("Открыть всю папку с подпапками")
            ok = self.n_files > 0 or rec
        self.b_ok.setText(text)
        self.b_ok.setEnabled(ok)
        self.l_hint.setText(trf("В папке фото: {n}", n=self.n_files))

    def accept_choice(self):
        docs = self._docs()
        if docs:
            self.choice = ("doc", docs[0], False)
            self.accept()
            return
        act = pc.OpenDialog.decide([x for x in self._sel() if x[0] != "x"], self.cwd, self.n_files)
        if act is None:
            return
        self.choice = (act[0], act[1], self.sw_add.isChecked())
        self.accept()


# ---------------------------------------------------------------- профиль принтера

class CmDialog(QDialog):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        s = app.s
        self.setWindowTitle(tr("Цветовой профиль печати"))
        self.setMinimumWidth(560)
        self.sw_on = Switch(s["cm_on"])
        self.sw_on.toggled.connect(lambda on: s.__setitem__("cm_on", bool(on)))
        self.e_icc = QLineEdit(s["icc"])
        self.e_icc.textChanged.connect(self._icc_changed)
        self.l_status = lbl("", "muted", wrap=True)
        self.cb_intent = QComboBox()
        self.cb_intent.addItems(list(pc.INTENTS))
        self.cb_intent.setCurrentText(s["intent"])
        self.cb_intent.currentTextChanged.connect(lambda v: (s.__setitem__("intent", v), self._status()))
        sw_bpc, sw_embed = Switch(s["bpc"]), Switch(s["embed"])
        sw_bpc.toggled.connect(lambda on: s.__setitem__("bpc", bool(on)))
        sw_embed.toggled.connect(lambda on: s.__setitem__("embed", bool(on)))
        help_ = lbl("Фото переводится из своего профиля (если его нет — sRGB) в пространство принтера. "
                    "Печатайте готовые файлы через драйвер Epson с отключённым управлением цветом "
                    "(«Без цветокоррекции» / No Color Adjustment), с теми же типом бумаги и качеством печати, "
                    "что были при печати тестовой мишени для профиля.", "muted", wrap=True)
        c = card(None, row("Применять профиль принтера при сохранении", self.sw_on),
                 hbox(self.e_icc, ibtn("open", "Выбрать файл профиля", self.browse, 32, True, isize=16), spacing=6), self.l_status,
                 row("Способ рендеринга", self.cb_intent), row("Компенсация точки чёрного", sw_bpc),
                 row("Встроить профиль в готовый файл", sw_embed))
        self.setLayout(vbox(c, help_, hbox(None, btn("Готово", self.accept, "primary")), spacing=12, margins=(14, 14, 14, 14)))
        self._status()

    def _icc_changed(self, v):
        self.app.s["icc"] = v
        self._status()

    def _status(self):
        self.app._icc_info()
        self.l_status.setText(self.app.l_icc.text())

    def browse(self):
        p, _ = QFileDialog.getOpenFileName(self, tr("Цветовой профиль принтера"), self.app.settings.get("icc_dir") or "",
                                           "ICC (*.icc *.icm);;* (*.*)")
        if p:
            self.app.settings["icc_dir"] = str(Path(p).parent)
            self.e_icc.setText(p)
            self.sw_on.setChecked(True)


# ---------------------------------------------------------------- настройки

class OrnBand(QWidget):
    """Орнаментный пояс под верхней панелью (в темах с национальным оформлением)."""

    def __init__(self):
        super().__init__()
        svg, self.tw, self.th = orn_tile(T["orn"], T)
        k = 3
        self.tile = QPixmap(self.tw * k, self.th * k)
        self.tile.fill(Qt.transparent)
        p = QPainter(self.tile)
        QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(p, QRectF(0, 0, self.tw * k, self.th * k))
        p.end()
        self.tile.setDevicePixelRatio(k)
        self.setFixedHeight(self.th + 2)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T["orn_bg"]))
        n = int(self.width() // self.tw) + 1
        x0 = (self.width() - n * self.tw) / 2.0 if n * self.tw > self.width() else 0
        for i in range(n):
            p.drawPixmap(int(x0 + i * self.tw), 1, self.tile)
        p.setPen(QPen(QColor(T["border"]), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()


class ThemeSwatch(QAbstractButton):
    """Карточка темы: маленькое окно программы в цветах темы."""

    def __init__(self, key):
        super().__init__()
        self.key = key
        self.setCheckable(True)
        self.setFixedSize(150, 112)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, e):
        t = THEMES[self.key]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1.5, 1.5, self.width() - 3, 84)
        p.setPen(QPen(QColor(T["select"] if self.isChecked() else T["border"]), 2.2 if self.isChecked() else 1))
        p.setBrush(QColor(t["bg"]))
        p.drawRoundedRect(r, 10, 10)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["surface"]))
        p.drawRoundedRect(QRectF(9, 22, 26, 56), 4, 4)
        p.drawRoundedRect(QRectF(112, 22, 30, 34), 4, 4)
        p.setBrush(QColor(t["canvas"]))
        p.drawRoundedRect(QRectF(40, 22, 67, 56), 5, 5)
        p.setBrush(QColor(t["accent"]))
        p.drawRoundedRect(QRectF(9, 9, 30, 8), 3, 3)
        p.drawRoundedRect(QRectF(112, 68, 30, 10), 3, 3)
        p.setBrush(QColor(t["raised"]))
        p.drawRoundedRect(QRectF(112, 60, 30, 5), 2, 2)
        if t.get("orn"):                                      # мини-пояс орнамента между верхней планкой и полями
            for i, x in enumerate(range(46, 140, 8)):
                p.setBrush(QColor(t["orn1"] if i % 2 == 0 else t["orn3"]))
                p.drawPolygon(QPolygonF([QPointF(x, 14), QPointF(x + 3, 17.5), QPointF(x, 21), QPointF(x - 3, 17.5)]))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(t["frame"]), 1.6))
        p.drawRect(QRectF(54, 30, 39, 40))
        p.setPen(QColor(T["text"] if self.isChecked() else T["muted"]))
        p.drawText(QRectF(0, 90, self.width(), 20), Qt.AlignCenter, tr(t["title"]))
        p.end()


# ---------------------------------------------------------------- счётчик печати: окно администратора

class SecretDialog(QDialog):
    """Окно с одним-тремя полями для пароля. extra — подпись кнопки «Забыли пароль?» (результат: self.extra_clicked)."""

    def __init__(self, parent, title, prompts, hint="", extra=None):
        super().__init__(parent)
        self.setWindowTitle(tr(title))
        self.setMinimumWidth(380)
        self.extra_clicked = False
        self.edits = []
        v = vbox(spacing=10, margins=(16, 16, 16, 14))
        if hint:
            v.addWidget(lbl(hint, "muted", wrap=True))
        for p in prompts:
            v.addWidget(lbl(p))
            e = QLineEdit()
            e.setEchoMode(QLineEdit.Password)
            e.returnPressed.connect(self.accept)
            self.edits.append(e)
            v.addWidget(e)
        row_ = hbox(spacing=8)
        if extra:
            row_.addWidget(btn(extra, self._extra))
        row_.addStretch(1)
        row_.addWidget(btn("Отмена", self.reject))
        row_.addWidget(btn("OK", self.accept, "primary"))
        v.addLayout(row_)
        self.setLayout(v)
        self.edits[0].setFocus()

    def _extra(self):
        self.extra_clicked = True
        self.accept()

    def values(self):
        return [e.text() for e in self.edits]


def _new_password(parent):
    """Два поля «пароль / повтор» -> пароль или None."""
    hint = trf("Придумайте пароль администратора (не короче {n} символов). Он защищает подробный счётчик печати.", n=ps.MIN_PASSWORD)
    while True:
        dlg = SecretDialog(parent, "Пароль администратора", ["Новый пароль", "Повторите пароль"], hint)
        if dlg.exec() != QDialog.Accepted:
            return None
        a, b = dlg.values()
        if len(a) < ps.MIN_PASSWORD:
            warn(parent, trf("Пароль короче {n} символов.", n=ps.MIN_PASSWORD))
        elif a != b:
            warn(parent, "Пароли не совпадают.")
        else:
            return a


def _show_recovery(parent, key):
    QMessageBox.information(parent, "PhotoCrop", tr("Ключ восстановления (покажется один раз). Запишите его и храните отдельно от компьютера. "
                                                    "С ним можно задать новый пароль, если старый забыт.") + "\n\n" + key)


def admin_login(parent):
    """Вход администратора; в первый раз задаёт пароль. -> True, если вошли."""
    if not ps.has_password():
        pw = _new_password(parent)
        if pw is None:
            return False
        _show_recovery(parent, ps.set_password(pw))
        return True
    while True:
        left = ps.lock_remaining()
        if left > 0:
            warn(parent, trf("Слишком много неверных попыток. Подождите {m} мин {s} с.", m=left // 60, s=left % 60))
            return False
        dlg = SecretDialog(parent, "Вход администратора", ["Пароль"], extra="Забыли пароль?")
        if dlg.exec() != QDialog.Accepted:
            return False
        if dlg.extra_clicked:
            rk = SecretDialog(parent, "Восстановление", ["Ключ восстановления"], tr("Введите ключ, который показала программа при создании пароля."))
            if rk.exec() != QDialog.Accepted:
                continue
            pw = _new_password(parent)
            if pw is None:
                continue
            key = ps.reset_with_recovery(rk.values()[0], pw)
            if key is None:
                warn(parent, "Ключ восстановления не подошёл.")
                continue
            _show_recovery(parent, key)
            return True
        ok, wait = ps.check_password(dlg.values()[0])
        if ok:
            return True
        if wait:
            warn(parent, trf("Слишком много неверных попыток. Подождите {m} мин {s} с.", m=wait // 60, s=wait % 60))
            return False
        warn(parent, "Неверный пароль.")


class AdminStatsDialog(QDialog):
    """Подробный счётчик печати: сводка, журнал, экспорт, смена пароля. Сам закрывается после 5 минут без действий."""
    IDLE_MS = 5 * 60 * 1000

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("Счётчик печати — администратор"))
        self.setMinimumSize(760, 560)
        self.setStyleSheet(
            "QTabWidget::pane{border:1px solid %(border)s;background:%(surface)s;}"
            "QTabBar::tab{background:%(raised)s;color:%(muted)s;padding:7px 18px;border:1px solid %(border)s;border-bottom:0;}"
            "QTabBar::tab:selected{background:%(surface)s;color:%(text)s;}"
            "QScrollArea,QScrollArea > QWidget > QWidget{background:%(surface)s;}"
            "QScrollArea QLabel{background:transparent;color:%(text)s;padding:6px;}"
            "QTableWidget{background:%(surface)s;color:%(text)s;gridline-color:%(border)s;border:0;}"
            "QHeaderView::section{background:%(raised)s;color:%(muted)s;border:0;padding:6px;}" % T)
        self.recs =[r for r in ps.read_all() if not r.get("bad")]
        ok, bad = ps.verify()
        v = vbox(spacing=10, margins=(14, 14, 14, 12))
        if not ok:
            w = lbl(trf("⚠ Журнал изменён или повреждён (строка {n}). Данные ниже могут быть неточными.", n=bad), "muted", wrap=True)
            w.setStyleSheet("color:%s" % T["warn"])
            v.addWidget(w)
        self.l_sum = QLabel()
        self.l_sum.setTextFormat(Qt.RichText)
        self.l_sum.setWordWrap(True)
        self.l_sum.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setWidget(self.l_sum)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([tr(x) for x in ("Время", "Принтер", "Тип", "Бумага", "Режим", "Источник", "Листов", "Файлы")])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.pr_period = QComboBox()
        for k, name in (("today", "Сегодня"), ("week", "7 дней"), ("month", "30 дней"), ("all", "Всё время")):
            self.pr_period.addItem(tr(name), k)
        self.pr_period.setCurrentIndex(3)
        self.pr_printer = QComboBox()
        self.pr_printer.addItem(tr("Все принтеры"), None)
        for name in ps.printer_names(self.recs):
            self.pr_printer.addItem(name, name)
        self.pr_period.currentIndexChanged.connect(lambda *_: self.fill_printers())
        self.pr_printer.currentIndexChanged.connect(lambda *_: self.fill_printers())
        self.l_pr = QLabel()
        self.l_pr.setTextFormat(Qt.RichText)
        self.l_pr.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        sc2 = QScrollArea()
        sc2.setWidgetResizable(True)
        sc2.setFrameShape(QFrame.NoFrame)
        sc2.setWidget(self.l_pr)
        pr_page = QWidget()
        pv = vbox(spacing=8, margins=(8, 8, 8, 8))
        lp, lq = QLabel(tr("Период")), QLabel(tr("Принтер"))
        for w_ in (lp, lq):
            w_.setStyleSheet("color:%s;background:transparent" % T["text"])
        pv.addLayout(hbox(lp, self.pr_period, lq, self.pr_printer,
                          None, btn("Экспорт по принтерам…", self._export_printers), spacing=8))
        pv.addWidget(sc2, 1)
        pr_page.setLayout(pv)
        tabs = QTabWidget()
        tabs.addTab(sc, tr("Сводка"))
        tabs.addTab(pr_page, tr("Принтеры"))
        tabs.addTab(self.table, tr("Журнал"))
        v.addWidget(tabs, 1)
        v.addLayout(hbox(btn("Экспорт в CSV…", self._export), btn("Сменить пароль", self._change), btn("Очистить журнал", self._clear),
                         None, btn("Выйти", self.accept, "primary"), spacing=8))
        self.setLayout(v)
        self.fill()
        self.idle = QTimer(self)
        self.idle.setSingleShot(True)
        self.idle.timeout.connect(self.accept)
        self.idle.start(self.IDLE_MS)
        QApplication.instance().installEventFilter(self)

    def done(self, r):
        QApplication.instance().removeEventFilter(self)
        super().done(r)

    def eventFilter(self, o, e):
        if e.type() in (QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.MouseMove, QEvent.Wheel):
            self.idle.start(self.IDLE_MS)
        return False

    def fill(self):
        s = ps.summary(self.recs)
        td = lambda x, al="left": '<td style="padding:2px 14px 2px 0" align="%s">%s</td>' % (al, x)
        h = ["<h3>%s</h3><table>" % tr("Всего напечатано")]
        h.append("<tr>%s%s%s%s</tr>" % (td("<b>%s</b>" % tr("Период")), td("<b>%s</b>" % tr("Листов"), "right"), td("<b>%s</b>" % tr("Фото"), "right"),
                                        td("<b>%s</b>" % tr("Документы"), "right")))
        for k, name in (("today", "Сегодня"), ("week", "7 дней"), ("month", "30 дней"), ("all", "Всё время")):
            p = s["periods"][k]
            h.append("<tr>%s%s%s%s</tr>" % (td(tr(name)), td(p["sheets"], "right"), td(p["photo"], "right"), td(p["doc"], "right")))
        h.append("</table>")
        for field, title in (("printer", "По принтерам"), ("paper_photo", "Бумага: фото, листов"), ("paper_doc", "Бумага: документы, листов"), ("source", "По источнику (app — окно программы, agent — ИИ-агент)")):
            h.append("<h3>%s</h3><table>" % tr(title))
            for k, n in s[field][:12]:
                h.append("<tr>%s%s</tr>" % (td(k), td(n, "right")))
            h.append("</table>")
        if s["days"]:
            mx = max(n for _, n in s["days"]) or 1
            h.append("<h3>%s</h3><table>" % tr("Последние 14 дней"))
            for d, n in s["days"]:
                h.append("<tr>%s%s%s</tr>" % (td(d), td(n, "right"), td('<span style="color:%s">%s</span>' % (T["accent"], "█" * max(1, round(24 * n / mx))))))
            h.append("</table>")
        self.l_sum.setText("".join(h))
        self.fill_printers()
        rows = list(reversed(self.recs[-500:]))
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, key in enumerate(("t", "printer", "kind", "paper", "mode", "source", "sheets", "files")):
                v = r.get(key, "")
                if key == "kind":
                    v = tr("Документ" if ps.rkind(r) == "doc" else "Фото")
                elif key == "paper":
                    v = ps.paper_label(v)
                self.table.setItem(i, j, QTableWidgetItem(", ".join(v) if isinstance(v, list) else str(v)))
        self.table.resizeColumnsToContents()

    def fill_printers(self):
        data = ps.by_printer(self.recs, self.pr_period.currentData(), self.pr_printer.currentData())
        td = lambda x, al="left": '<td style="padding:2px 14px 2px 0" align="%s">%s</td>' % (al, x)
        if not data:
            self.l_pr.setText("<p>%s</p>" % tr("Нет данных за выбранный период."))
            return
        h = []
        for name, d in data:
            h.append("<h3>%s — %s: %d (%s %d, %s %d)</h3><table>" % (name, tr("листов"), d["sheets"], tr("фото"), d["photo"], tr("документы"), d["doc"]))
            h.append("<tr>%s%s%s</tr>" % (td("<b>%s</b>" % tr("Тип")), td("<b>%s</b>" % tr("Бумага")), td("<b>%s</b>" % tr("Листов"), "right")))
            for kind, paper, n in d["rows"]:
                h.append("<tr>%s%s%s</tr>" % (td(tr("Документ" if kind == "doc" else "Фото")), td(paper), td(n, "right")))
            h.append("</table>")
        self.l_pr.setText("".join(h))

    def _export_printers(self):
        p, _ = QFileDialog.getSaveFileName(self, tr("Экспорт по принтерам…"), "print_by_printer.csv", "CSV (*.csv)")
        if p:
            try:
                info(self, trf("Сохранено строк: {n}", n=ps.export_printers_csv(p, self.pr_period.currentData(), self.pr_printer.currentData(), self.recs)))
            except OSError as ex:
                warn(self, str(ex))

    def _export(self):
        p, _ = QFileDialog.getSaveFileName(self, tr("Экспорт в CSV…"), "print_log.csv", "CSV (*.csv)")
        if p:
            try:
                info(self, trf("Сохранено строк: {n}", n=ps.export_csv(p)))
            except OSError as ex:
                warn(self, str(ex))

    def _change(self):
        dlg = SecretDialog(self, "Сменить пароль", ["Текущий пароль"])
        if dlg.exec() != QDialog.Accepted:
            return
        ok, wait = ps.check_password(dlg.values()[0])
        if not ok:
            warn(self, "Неверный пароль.")
            return
        pw = _new_password(self)
        if pw:
            _show_recovery(self, ps.set_password(pw))

    def _clear(self):
        if not ask(self, "Очистить журнал? Старый журнал сохранится в файл-копию рядом с ним."):
            return
        bak = ps.clear_log()
        self.recs = []
        self.fill()
        if bak:
            info(self, tr("Копия журнала") + ":\n" + str(bak))


class SettingsDialog(QDialog):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        st = app.settings
        self.setWindowTitle(tr("Настройки"))
        self.swatches = QButtonGroup(self)
        themes = hbox(spacing=10)
        for key in THEMES:
            sw = ThemeSwatch(key)
            sw.setChecked(key == app.theme_name)
            sw.clicked.connect(lambda _=False, k=key: self._theme(k))
            self.swatches.addButton(sw)
            themes.addWidget(sw)
        themes.addStretch(1)
        sw_anim = Switch(st.get("anim", True))
        sw_anim.toggled.connect(lambda on: (st.__setitem__("anim", bool(on)), ANIM_ON.__setitem__(0, bool(on))))
        look = card("Оформление", themes, row("Анимация отправки на печать и сохранения", sw_anim))
        seg_lang = QComboBox()                                           # языков много — выпадающий список
        for k, v in pc.LANGS.items():
            seg_lang.addItem(v, k)
        seg_lang.setCurrentIndex(max(0, seg_lang.findData(pc.get_language())))
        seg_lang.activated.connect(lambda i, cb=seg_lang: self._lang(cb.itemData(i)))
        seg_dir = Segmented([("Рабочий стол", "desktop"), ("Последняя использованная", "last")],
                            "last" if st.get("start_dir_mode") == "last" else "desktop")
        seg_dir.changed.connect(lambda v: st.__setitem__("start_dir_mode", v))
        sw_conf = Switch(SOFT[0])
        sw_conf.toggled.connect(lambda on: (st.__setitem__("confirm_actions", bool(on)), SOFT.__setitem__(0, bool(on))))
        general = card("Общие", row("Язык интерфейса", seg_lang), row("Папка, с которой начинается «Открыть»", seg_dir),
                       row("Спрашивать подтверждение обычных действий (сброс, применение ко всем, печать)", sw_conf))
        sw_snap = Switch(app.s["snap"])
        sw_snap.toggled.connect(lambda on: app.s.__setitem__("snap", bool(on)))
        sl = QSlider(Qt.Horizontal)
        sl.setRange(2, 40)
        sl.setValue(int(st.get("snap_px", 10)))
        sl.setFixedWidth(180)
        l_px = lbl(str(sl.value()))
        l_px.setFixedWidth(24)
        sl.valueChanged.connect(lambda v: (st.__setitem__("snap_px", int(v)), l_px.setText(str(v))))
        crop = card("Кадрирование", row("Прилипание рамки к краям и центру фото", sw_snap),
                    row("Сила прилипания, пикселей экрана", hbox(sl, l_px)),
                    lbl("Ctrl при перетаскивании — временно отключает прилипание.", "muted"))
        sw_upd = Switch(st.get("check_updates", True))
        sw_upd.toggled.connect(lambda on: st.__setitem__("check_updates", bool(on)))
        import webbrowser
        link = lambda text, url: btn(text, lambda: webbrowser.open(url), "link")
        upd_card = card("О программе", lbl("KopiTehnik Print"), row("Версия", lbl(APP_VERSION)), row("Автор", lbl(AUTHOR)),
                        hint(LICENSE_TEXT),
                        hbox(link("Страница на GitHub", GITHUB_URL), link("Все выпуски", GITHUB_URL + "/releases"), None, spacing=6),
                        hbox(link("Сообщить об ошибке", GITHUB_URL + "/issues"), link("Текст лицензии", LICENSE_URL), None, spacing=6),
                        row("Проверять обновления при запуске", sw_upd),
                        hbox(None, btn("Проверить обновления", lambda: app.check_updates(True), ico="sparkle")))
        about = lbl(tr("Настройки хранятся в файле") + ": " + str(pc.SETTINGS_PATH) + "\n\n" + tr(
            "Программа не связана с компанией Epson. Epson и названия моделей — торговые марки их владельцев и используются только "
            "для описания совместимости. Управление драйвером принтера и обслуживание (проверка дюз, прочистка) вы используете на свой риск: "
            "прочистка расходует чернила."), "muted", wrap=True)
        # классическая раскладка: слева дерево разделов с подпунктами, справа страница выбранного
        self.stack = QStackedWidget()
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setFixedWidth(230)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.setFocusPolicy(Qt.NoFocus)
        self.tree.setStyleSheet("QTreeWidget { background: %s; border: 1px solid %s; border-radius: 10px; padding: 6px; }"
                                "QTreeWidget::item { height: 30px; border-radius: 7px; padding-left: 2px; }"
                                "QTreeWidget::item:hover { background: %s; }"
                                "QTreeWidget::item:selected { background: %s; color: %s; }"
                                "QTreeWidget::branch { background: %s; }"
                                "QTreeWidget::branch:selected { background: %s; }"
                                % (T["surface"], T["border"], T["raised"], T["hover"], T["text"], T["surface"], T["hover"]))

        def page(*cards):
            self.stack.addWidget(app._scroll(*cards))
            return self.stack.count() - 1

        def section(title, ico, children):
            top = QTreeWidgetItem([tr(title)])
            top.setIcon(0, icon(ico, T["muted"]))
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            self.tree.addTopLevelItem(top)
            first = None
            for name, cards in children:
                it = QTreeWidgetItem([tr(name)])
                it.setData(0, Qt.UserRole, page(*cards))
                top.addChild(it)
                first = first or it
            top.setData(0, Qt.UserRole, first.data(0, Qt.UserRole) if first else 0)
            top.setExpanded(True)
            return first

        first = section("Интерфейс", "settings", [("Оформление", [look]), ("Язык и общие", [general])])
        section("Фото", "image", [("Кадрирование", [crop]), ("Сохранение", [self._save_card()])])
        section("Печать", "print", [("Профили печати", [self._profiles_card()]),
                                    ("Счётчик печати", [self._counter_card()])])
        section("ИИ-агент (MCP)", "sparkle", [("Подключение и права", [self._agent_card()])])
        section("О программе", "doc", [("Версия и обновления", [upd_card])])
        self.tree.currentItemChanged.connect(lambda cur, _prev: self.stack.setCurrentIndex(int(cur.data(0, Qt.UserRole) or 0)) if cur is not None else None)
        self.tree.setCurrentItem(first)
        self.setMinimumSize(900, 600)
        self.resize(960, 660)
        self.setLayout(vbox(hbox(self.tree, self.stack, spacing=12), about, hbox(None, btn("Готово", self.accept, "primary")),
                            spacing=12, margins=(14, 14, 14, 14)))

    def _profiles_card(self):
        """Сохранённые профили печати (принтер + формат + тип бумаги): просмотр и удаление."""
        app = self.app
        self.lw_prof = QListWidget()
        self.lw_prof.setMinimumHeight(220)

        def fill():
            self.lw_prof.clear()
            for key in sorted(app._profiles()):
                prof = app._profiles()[key]
                it = QListWidgetItem(app.profile_title(key) + ("  —  " + (Path(prof.get("icc", "")).name if prof.get("cm_on") and prof.get("icc") else tr("без профиля ICC"))))
                it.setData(Qt.UserRole, key)
                self.lw_prof.addItem(it)

        def delete():
            it = self.lw_prof.currentItem()
            if it and ask(self, "Забыть сохранённые настройки этой связки и вернуть стандартные?"):
                app._profiles().pop(it.data(Qt.UserRole), None)
                app.profile_label(None)
                fill()
        fill()
        return card("Профили печати", lbl("Для каждой связки «принтер + формат + тип бумаги» программа помнит свои цветовой профиль, "
                                          "способ рендеринга, резкость и настройки драйвера. Они сохраняются автоматически при любом изменении.", "muted", wrap=True),
                    self.lw_prof, hbox(btn("Удалить выбранный", delete, ico="trash"), None))

    def _save_card(self):
        """Куда и как сохраняются готовые файлы (раньше было в правой колонке главного окна)."""
        app, s = self.app, self.app.s
        put = lambda k: (lambda v: s.__setitem__(k, v))
        self.rb_orig = QRadioButton(tr("Рядом с фото, в папку"))
        self.rb_custom = QRadioButton(tr("В другую папку"))
        (self.rb_custom if s["out_mode"] == "custom" else self.rb_orig).setChecked(True)
        self.rb_orig.toggled.connect(lambda on: (s.__setitem__("out_mode", "orig" if on else "custom"), self._out_enable()))
        self.e_outname = QLineEdit(s["out_name"])
        self.e_outname.textEdited.connect(put("out_name"))
        self.e_outdir = QLineEdit(s["outdir"])
        self.e_outdir.setPlaceholderText(tr("Папка не выбрана"))
        self.e_outdir.textEdited.connect(put("outdir"))
        self.b_outdir = ibtn("open", "Выбрать папку", self._choose_outdir, 32, True, isize=16)
        e_dpi = QLineEdit(s["dpi"])
        e_dpi.setFixedWidth(84)
        e_dpi.textEdited.connect(put("dpi"))
        seg_type = Segmented([(k, k) for k in pc.FILETYPES], s["filetype"])
        seg_type.changed.connect(lambda v: (s.__setitem__("filetype", v), self._q_enable()))
        self.sl_q = QSlider(Qt.Horizontal)
        self.sl_q.setRange(70, 100)
        self.sl_q.setValue(int(s["quality"]))
        self.l_q = lbl(str(s["quality"]))
        self.l_q.setFixedWidth(26)
        self.sl_q.valueChanged.connect(lambda v: (s.__setitem__("quality", int(v)), self.l_q.setText(str(v))))
        self.l_qcap = lbl("Качество JPEG")
        sw_resize, sw_sub, sw_cn = Switch(s["resize"]), Switch(s["subfolder"]), Switch(s["copies_name"])
        sw_resize.toggled.connect(lambda on: s.__setitem__("resize", bool(on)))
        sw_sub.toggled.connect(lambda on: s.__setitem__("subfolder", bool(on)))
        sw_cn.toggled.connect(lambda on: s.__setitem__("copies_name", bool(on)))
        c = card("Сохранение", self.rb_orig, self.e_outname, self.rb_custom, hbox(self.e_outdir, self.b_outdir, spacing=6),
                 row("Разрешение, dpi", e_dpi), row("Тип файла", seg_type), hbox(self.l_qcap, self.sl_q, self.l_q),
                 row("Точный размер печати", sw_resize), row("Подпапка по формату", sw_sub),
                 row("Число копий в имени файла", sw_cn))
        c.setMinimumWidth(330)
        self._out_enable()
        self._q_enable()
        return c

    def _agent_card(self):
        """ИИ-агент: подключение MCP к этому окну и права агента."""
        app, st = self.app, self.app.settings
        sw_on = Switch(app.agent_server is not None)
        self.l_agent_state = lbl("", "muted", wrap=True)

        def on_toggle(on):
            if on:
                app.agent_start()
            else:
                app.agent_stop()
            self._agent_state()
        sw_on.toggled.connect(on_toggle)
        sw_print, sw_conf = Switch(st.get("agent_allow_print", True)), Switch(st.get("agent_confirm_print", False))
        sw_print.toggled.connect(lambda on: st.__setitem__("agent_allow_print", bool(on)))
        sw_conf.toggled.connect(lambda on: st.__setitem__("agent_confirm_print", bool(on)))
        sw_lock = Switch(st.get("agent_lock", True))
        sw_lock.setToolTip(tr("Пока агент работает, окно только для просмотра: вы видите, что он делает, но не можете случайно ему помешать. Кнопка «Забрать управление» снимает блокировку."))
        sw_lock.toggled.connect(lambda on: (st.__setitem__("agent_lock", bool(on)), app._agent_hint()))
        sw_badge = Switch(st.get("agent_badge", True))
        sw_badge.toggled.connect(lambda on: (st.__setitem__("agent_badge", bool(on)), app._agent_hint()))
        e_max = QLineEdit(str(st.get("agent_max_sheets", 0) or 0))
        e_max.setFixedWidth(56)
        e_max.textEdited.connect(lambda v: st.__setitem__("agent_max_sheets", int(v) if v.strip().isdigit() else 0))
        self._agent_state()
        import agent_clients as ac
        self.cb_client = QComboBox()
        for k, t in ac.titles().items():
            self.cb_client.addItem(t, k)
        return card("ИИ-агент (MCP)", row("Агент может работать с этим окном", sw_on), self.l_agent_state,
                    row("Разрешить агенту печатать", sw_print), row("Макс. листов за одну печать (0 — без ограничения)", e_max),
                    row("Спрашивать меня перед печатью агента", sw_conf),
                    row("Блокировать окно, пока агент работает (только просмотр)", sw_lock),
                    row("Показывать плашку «ИИ-агент работает»", sw_badge),
                    row("Программа-агент", self.cb_client),
                    hbox(btn("Подключить", self._agent_connect), btn("Скопировать настройку", self._agent_copy),
                         btn("Адрес для HTTP-клиентов", self._agent_http), spacing=6),
                    lbl("Агент видит те же фото и настройки, что и вы, и всё, что он делает, отменяется Ctrl+Z. "
                        "Подключение только с этого компьютера.", "muted", wrap=True))

    def _agent_state(self):
        a = self.app
        self.l_agent_state.setText(trf("Включено, порт {p}", p=a.agent_server.port) if a.agent_server else tr("Выключено"))

    def _agent_client(self):
        return self.cb_client.currentData()

    def _agent_connect(self):
        import agent_clients as ac
        client = self._agent_client()
        ok, msg = ac.install(client, pc.mcp_server_entry())
        if ok:
            self.app.agent_start()
            self._agent_state()
        elif ac.CLIENTS[client]["kind"] != "json" or "не найден" not in msg:
            QApplication.clipboard().setText(ac.snippet(client, pc.mcp_server_entry()))        # настройка уже в буфере обмена
            msg += "\n\n" + tr("Настройка скопирована в буфер обмена.")
        (info if ok else warn)(self, msg)

    def _agent_copy(self):
        import agent_clients as ac
        QApplication.clipboard().setText(ac.snippet(self._agent_client(), pc.mcp_server_entry()))
        info(self, "Настройка скопирована. Вставьте её в конфигурацию клиента MCP.")

    def _agent_http(self):
        a = self.app
        if a.agent_server is None:
            info(self, "Сначала включите «Агент может работать с этим окном».")
            return
        QApplication.clipboard().setText("URL: http://127.0.0.1:%d/mcp\nAuthorization: Bearer %s" % (a.agent_server.port, a.settings["agent_token"]))
        info(self, "Адрес и ключ скопированы. Для клиентов, которые подключаются по HTTP (Streamable HTTP), а не запуском программы.")

    def _counter_card(self):
        """Общий счётчик за день (виден всем) и вход в подробный счётчик для администратора."""
        self.l_today = lbl("")
        self._refresh_today()
        return card("Счётчик печати", self.l_today,
                    hbox(btn("Подробный счётчик (администратор)…", self._admin), None),
                    lbl("Подробный журнал, экспорт и сброс доступны по паролю администратора.", "muted", wrap=True))

    def _refresh_today(self):
        t = ps.today()
        self.l_today.setText(trf("Напечатано сегодня: {s} листов (фото {p}, документы {d})", s=t["sheets"], p=t["photo"], d=t["doc"]))

    def _admin(self):
        if admin_login(self):
            AdminStatsDialog(self).exec()
        self._refresh_today()

    def _out_enable(self):
        custom = self.app.s["out_mode"] == "custom"
        self.e_outname.setEnabled(not custom)
        self.e_outdir.setEnabled(custom)
        self.b_outdir.setEnabled(custom)

    def _q_enable(self):
        on = self.app.s["filetype"] == "JPEG"
        for w in (self.sl_q, self.l_q, self.l_qcap):
            w.setVisible(on)

    def _choose_outdir(self):
        d = QFileDialog.getExistingDirectory(self, tr("Куда сохранять"), self.app.s["outdir"] or self.app.start_dir())
        if d:
            self.app.s["outdir"] = d
            self.e_outdir.setText(d)

    def _theme(self, key):
        if key != self.app.theme_name:
            self.app.apply_look(theme=key)
            for b in self.swatches.buttons():
                b.update()

    def _lang(self, code):
        if code != pc.get_language():
            self.app.apply_look(lang=code)
            self.accept()
            QTimer.singleShot(0, self.app.open_settings)       # окно настроек открывается заново — уже на новом языке


# ---------------------------------------------------------------- перевод новых надписей

pc.EN.update({
    "Формат": "Format", "Фото": "Photos", "Сетка третей": "Rule-of-thirds grid", "Настройки": "Settings",
    "Проект: открыть или сохранить рамки и настройки": "Project: open or save frames and settings",
    "Открыть проект…": "Open project…", "Сохранить проект…": "Save project…", "Открыть проект": "Open project",
    "Открыть фото или папку (Ctrl+O)": "Open photos or a folder (Ctrl+O)",
    "Наклонить рамку влево на 0,1° (Shift+колесо — на 1°)": "Tilt frame left 0.1° (Shift+wheel — 1°)",
    "Наклонить рамку вправо на 0,1°": "Tilt frame right 0.1°", "Выровнять рамку (0°)": "Level the frame (0°)",
    "Сбросить рамку этого фото": "Reset this photo's frame", "Сохранить отмеченные": "Save checked", "Печать": "Print",
    "Ctrl+Shift+S; Ctrl+S — только текущее фото": "Ctrl+Shift+S; Ctrl+S — current photo only",
    "Это фото": "This photo", "Копий": "Copies", "Меньше копий": "Fewer copies", "Больше копий": "More copies",
    "Коррекция цвета": "Colour adjustments", "Сохранение": "Saving", "Рядом с фото, в папку": "Next to photos, in folder",
    "В другую папку": "To another folder", "Папка не выбрана": "No folder chosen", "Выбрать папку": "Choose folder",
    "Разрешение, dpi": "Resolution, dpi", "Тип файла": "File type", "Качество JPEG": "JPEG quality",
    "Точный размер печати": "Exact print size", "Подпапка по формату": "Subfolder per format", "Число копий в имени файла": "Copies count in file name",
    "Цвет": "Colour", "Уровни и кривые": "Levels and curves", "Нет фото": "No photo", "Показать оригинал (удерживайте)": "Show original (hold)", "Сначала откройте фото": "Open a photo first", "Уровни": "Levels", "Кривые": "Curves", "По цветам": "By colour", "На весь экран…": "Full screen…",
    "Все каналы сразу": "All channels together", "Красный канал": "Red channel", "Зелёный канал": "Green channel", "Синий канал": "Blue channel",
    "Чёрная точка (вход)": "Black point (input)", "Гамма (середина)": "Gamma (midtones)", "Белая точка (вход)": "White point (input)",
    "Выход: чёрный": "Output: black", "Вход: чёрный": "Input: black", "гамма": "gamma", "белый": "white",
    "Двойной щелчок по бегунку — сбросить его.": "Double-click a marker to reset it.", "Авто": "Auto", "Сбросить": "Reset",
    "Сбросить канал": "Reset channel", "Сбросить всё": "Reset all", "Сбросить цвет": "Reset colour", "Контраст S": "S contrast",
    "Светлее": "Lighter", "Темнее": "Darker", "Мягкая S-кривая: больше контраста": "Soft S-curve: more contrast",
    "Поднять средние тона": "Raise the midtones", "Опустить средние тона": "Lower the midtones",
    "Щелчок по кривой — новая точка, двойной щелчок или правая кнопка — удалить точку.": "Click the curve to add a point; double-click or right-click a point to remove it.",
    "Кривые: перетаскивайте точки, результат сразу виден в главном окне. Канал RGB меняет все цвета, R, G, B — по одному.": "Curves: drag the points, the result shows at once in the main window. RGB changes all colours; R, G, B one at a time.",
    "Красный": "Red", "Жёлтый": "Yellow", "Зелёный": "Green", "Голубой": "Cyan", "Синий": "Blue", "Пурпурный": "Magenta",
    "Поправка принтера": "Printer correction", "Включить для этой бумаги": "Enable for this paper",
    "Подгоняет отпечаток под экран. На экране не видна, действует только при печати фото и документов, с профилем принтера и без него.": "Matches the print to the screen. Not shown on screen, applied only when printing photos and documents, with or without a printer profile.",
    "Нейтраль (серый)": "Neutral (grey)", "По цветам": "By colour", "Общее": "General", "Тени": "Shadows", "Средние": "Midtones", "Света": "Highlights",
    "Тепло": "Warmth", "Пурпур": "Magenta", "Оттенок": "Hue", "Насыщ.": "Sat.", "Яркость": "Brightness", "Гамма": "Gamma", "Цвета": "Colours",
    "холоднее": "cooler", "теплее": "warmer", "зеленее": "greener", "пурпурнее": "more magenta", "темнее": "darker", "светлее": "lighter", "бледнее": "paler", "ярче": "more vivid",
    "Двойной щелчок — сбросить": "Double-click to reset", "Сбросить": "Reset", "Тестовая страница": "Test page", "Тестовый лист": "Test sheet",
    "Поправка включена и будет применена при печати.": "The correction is on and will be applied when printing.",
    "Включено, но все значения нулевые.": "On, but all values are zero.", "Выключена: печать без поправки.": "Off: printing without correction.",
    "Поправка принтера: включена": "Printer correction: on",
    "Принтер не выбран: поправка запомнится за связкой «принтер + формат + бумага» после выбора принтера.": "No printer selected: the correction will be stored for the printer + size + paper combination once a printer is chosen.",
    "Оттенок": "Hue", "Насыщенность": "Saturation", "Яркость": "Brightness",
    "Серые и нейтральные цвета не затрагиваются.": "Greys and neutral colours are left alone.",
    "Обновить сейчас": "Update now", "Программа сама скачает обновление, закроется, обновится и запустится снова.": "The program will download the update, close, update itself and start again.",
    "Скачиваю версию {v}…": "Downloading version {v}…", "Скачиваю версию {v}: {a} из {b} МБ": "Downloading version {v}: {a} of {b} MB", "Обновление": "Update",
    "Скачайте новую версию вручную:": "Download the new version manually:", "Не удалось запустить обновление: {e}": "Could not start the update: {e}",
    "Пресет 1": "Preset 1", "Пресет 2": "Preset 2", "Пресет 3": "Preset 3", "Переименовать пресет": "Rename preset", "Сохранить": "Save", "Сохранённые настройки: нажмите, чтобы применить": "Saved settings: click to apply", "Пресет пуст: настройте ползунки и нажмите «Сохранить» под ним": "Preset is empty: set the sliders and press Save under it", "Запомнить текущие настройки ползунков в этот пресет. Он хранится, пока вы не сохраните в него другие.": "Store the current slider values in this preset. It stays until you save other values into it.", "Цвет на экране": "Colour on screen", "Профиль принтера": "Printer profile", "Выбрать профиль…": "Choose profile…",
    "Имитация печати на экране": "Simulate print on screen", "Показать цвета вне охвата": "Show out-of-gamut colours",
    "Параметры": "Settings", "это фото": "this photo", "все отмеченные": "all checked", "Это фото": "This photo", "Куда применять коррекцию: только к текущему фото или ко всем отмеченным галочкой": "Where to apply the correction: the current photo only, or all photos ticked with a checkmark", "Менять": "Apply to",
    "Татарская": "Tatar", "Марийская": "Mari", "Основное": "Basic", "Детали": "Detail", "нет": "off", "контраст": "contrast", "цвет": "colour", "Ч/Б": "B/W", "Авто-уровни": "Auto levels",
    "Яркость": "Brightness", "Контраст": "Contrast", "Гамма (средние тона)": "Gamma (midtones)", "Тени (осветлить +)": "Shadows (lighten +)",
    "Света (вернуть −)": "Highlights (recover −)", "Насыщенность": "Saturation", "Красочность (бледные цвета)": "Vibrance (pale colours)",
    "Температура (холоднее ← → теплее)": "Temperature (cooler ← → warmer)", "Оттенок (зелёный ← → пурпурный)": "Tint (green ← → magenta)",
    "Красный": "Red", "Зелёный": "Green", "Синий": "Blue", "Шум цвета": "Colour noise", "Резкость при печати, %": "Print sharpening, %",
    "Радиус резкости (при 300 ppi)": "Sharpening radius (at 300 ppi)", "Порог резкости": "Sharpening threshold",
    "Улучшение для печати на Epson": "Enhancement for Epson printing", "Улучшить": "Enhance", "Супер": "Super",
    "Показать оригинал (удерживайте)": "Show original (hold)", "Настройки фото": "Photo settings", "Сбросить": "Reset",
    "Сбросить у всех": "Reset for all", "Двойной щелчок по ползунку — сбросить его.": "Double-click a slider to reset it.",
    "Сначала откройте фото.": "Open photos first.", "Нажмите «Открыть» и выберите фото или папку": "Click “Open” and choose photos or a folder",
    "Откройте фото или папку": "Open photos or a folder", "кадр": "frame", "есть белые поля": "white margins",
    "без обрезки": "no cropping", "печать": "print", "не удалось открыть": "could not open", "Профиль не выбран": "No profile chosen",
    "нужен RGB-профиль!": "an RGB profile is required!", "этот способ рендеринга профилем не поддерживается": "this rendering intent is not supported by the profile",
    "Не удалось прочитать файл профиля": "Could not read the profile file", "В чёрном": "Clipped black", "В белом": "Clipped white",
    "Вне охвата принтера": "Out of printer gamut", "Супер улучшения": "Super enhance", "Улучшения для Epson": "Epson enhance",
    "Применить «%s» к %d фото?": "Apply “%s” to %d photos?",
    "Для каждого фото параметры подберутся отдельно, прежняя коррекция будет сброшена. Отменить можно Ctrl+Z.": "Settings are chosen for each photo separately, the previous correction is reset. Undo with Ctrl+Z.",
    "Анализ": "Analysing", "Готово": "Done", "не удалось": "failed", "Куда сохранять": "Where to save",
    "красочность уменьшена: принтер не передаёт часть цветов": "vibrance reduced: the printer cannot reproduce some colours",
    "разрешение сохранения 360 dpi": "save resolution set to 360 dpi", "включена компенсация точки чёрного": "black point compensation turned on",
    "Малое разрешение для печати (меньше 150 dpi), фото: %d": "Low print resolution (below 150 dpi), photos: %d",
    "Печать будет нерезкой. Всё равно сохранить?": "The print will be soft. Save anyway?",
    "Сохранено файлов": "Files saved", "Папка": "Folder", "Ошибки": "Errors", "Открыть папку?": "Open the folder?",
    "Не удалось открыть окно печати": "Could not open the print window", "Места": "Places", "Рабочий стол": "Desktop",
    "Изображения": "Pictures", "Загрузки": "Downloads", "добавить к уже открытым": "add to the photos already open",
    "Ctrl или Shift — выбрать несколько, Ctrl+A — все": "Ctrl or Shift — select several, Ctrl+A — all",
    "Выбрать файл профиля": "Choose a profile file", "Способ рендеринга": "Rendering intent",
    "Применять профиль принтера при сохранении": "Apply the printer profile when saving", "Цветовой профиль принтера": "Printer colour profile",
    "Анимация отправки на печать и сохранения": "Animate sending to print and saving", "Язык интерфейса": "Interface language",
    "О программе": "About", "Программа-агент": "Agent application", "Подключить": "Connect", "Скопировать настройку": "Copy settings", "Адрес для HTTP-клиентов": "Address for HTTP clients", "Настройка скопирована в буфер обмена.": "The settings were copied to the clipboard.", "Автор": "Author", "Версия": "Version", "Лицензия: PolyForm Noncommercial 1.0.0. Бесплатно для личного и некоммерческого использования; для коммерческого нужно разрешение автора.": "Licence: PolyForm Noncommercial 1.0.0. Free for personal and non-commercial use; commercial use needs the author's permission.", "Текст лицензии": "Licence text",
    "Страница на GitHub": "Project page on GitHub", "Все выпуски": "All releases", "Сообщить об ошибке": "Report a problem",
    
    "Спрашивать подтверждение обычных действий (сброс, применение ко всем, печать)": "Ask for confirmation of everyday actions (reset, apply to all, print)",
    "Папка, с которой начинается «Открыть»": "Folder that “Open” starts in", "Последняя использованная": "Last used",
    "Кадрирование": "Cropping", "Сила прилипания, пикселей экрана": "Snap strength, screen pixels", "Общие": "General",
    "Настройки хранятся в файле": "Settings are stored in", "Оформление": "Appearance",
    "Сохранить проект (рамки и настройки)": "Save project (frames and settings)",
})
pc.EN.update({
    "Бумага": "Paper", "Фото на листе": "Photos per sheet", "Рамка и поля": "Frame and borders", "Поля": "Borders", "мм": "mm", "Кадр": "Crop", "Макет": "Layout", "Лист": "Sheet",
    "Сколько фото печатать на одном листе": "How many photos to print on one sheet",
    "Выключено — печать без полей, фото вплотную. Включено — белое поле по краю листа и между фото.": "Off — borderless, photos edge to edge. On — a white margin at the sheet edge and between photos.",
    "Поле по краю листа и расстояние между фото, мм": "Sheet margin and distance between photos, mm",
    "Ориентация рамки": "Frame orientation", "Как фото ложится в рамку": "How the photo fits the frame", "Копий этого фото": "Copies of this photo",
    "Весь лист — копии одного фото": "Whole sheet — copies of one photo", "Показать лист": "Show sheet",
    "Одно фото на лист, без полей": "One photo per sheet, borderless", "Без полей, фото вплотную": "Borderless, photos edge to edge",
    "Предыдущий лист": "Previous sheet", "Следующий лист": "Next sheet",
    "Отметьте фото слева — они разложатся по листам": "Check photos on the left — they will be laid out on sheets",
    "Не удалось подготовить листы": "Could not prepare the sheets",
})
pc.EN.update({
    "КопиТехник Принт": "KopiTehnik Print", "КопиТехник Принт — кадрирование для фотопечати": "KopiTehnik Print — cropping for photo printing",
    "Своё число": "Custom", "Режим «Документ» скоро": "Document mode is coming", "Печать Word и PDF с профилем бумаги для документов, редактирование и распознавание текста.": "Printing Word and PDF with a document paper profile, text editing and recognition.", "Своё число фото на листе": "Custom number of photos per sheet",
    "Обновление": "Updates", "Версия программы": "Program version", "Проверять обновления при запуске": "Check for updates at start",
    "Проверить обновления": "Check for updates", "Доступно обновление": "Update available", "Вышла новая версия:": "A new version is out:",
    "Открыть страницу загрузки": "Open the download page", "Пропустить эту версию": "Skip this version", "Позже": "Later",
    "У вас последняя версия:": "You have the latest version:",
    "Не удалось проверить обновления. Проверьте подключение к интернету.": "Could not check for updates. Check your internet connection.",
})
pc.EN_FMT.update({"Относится к профилю печати: {t}": "Belongs to the print profile: {t}", "Пресет {n}": "Preset {n}", "Название пресета {n}": "Name of preset {n}", "Вход {a} → выход {b}": "Input {a} → output {b}", "Пресет {n} пока пуст. Настройте ползунки и нажмите «Сохранить» под ним.": "Preset {n} is empty. Set the sliders and press Save under it.", "Заменить сохранённый пресет {n} текущими настройками?": "Replace saved preset {n} with the current settings?", "Применён пресет {n}": "Preset {n} applied", "Пресет {n} сохранён": "Preset {n} saved", "Страниц: {n}": "Pages: {n}", "Открыть документ «{name}»": "Open document “{name}”"})
pc.EN.update({"Бумага: фото, листов": "Paper: photos, sheets", "Бумага: документы, листов": "Paper: documents, sheets", "Тип": "Type"})
pc.EN.update({
    "Документ": "Document", "PDF, Word, Excel, PowerPoint и другие офисные файлы": "PDF, Word, Excel, PowerPoint and other office files",
    "Открыть документ…": "Open document…", "Открыть документ": "Open document", "Открыть фото, документ или папку": "Open photos, a document or a folder", "Документ не открыт": "No document open",
    "Редактировать PDF": "Edit PDF", "Распознать текст": "Recognise text",
    "Откроется в программе «КопиТехник Конвертор»": "Opens in KopiTehnik Converter", "Распознавание в «КопиТехник Конвертор»": "Recognition in KopiTehnik Converter",
    "Печать документа": "Document printing", "Как страница ложится на лист": "How the page sits on the sheet", "По листу": "Fit to sheet",
    "Только уменьшить": "Shrink only", "Как есть": "Actual size", "Поля, мм": "Margins, mm", "Страницы": "Pages", "Копий": "Copies",
    "все, или 1-3, 5, 8-": "all, or 1-3, 5, 8-", "Профиль для документов": "Document profile",
    "Использовать профиль принтера": "Use printer profile",
    "У документов своя бумага и свой профиль, он не связан с профилем фото.": "Documents have their own paper and profile, separate from the photo profile.",
    "Документы": "Documents", "Этот тип файла не поддерживается.": "This file type is not supported.",
    "Не удалось перевести документ в PDF": "Could not convert the document to PDF", "Не удалось открыть PDF.": "Could not open the PDF.",
    "переведён в PDF": "converted to PDF", "Сначала откройте документ.": "Open a document first.",
    "Правка PDF и распознавание делаются в программе «КопиТехник Конвертор». Она не найдена на этом компьютере.": "PDF editing and recognition are done in KopiTehnik Converter. It was not found on this computer.",
    "Скачать конвертер": "Download the converter", "Указать Converter.exe…": "Choose Converter.exe…", "Отмена": "Cancel",
    "Открыт конвертер: закончите правку и сохраните.": "The converter is open: finish editing and save.",
    "Не удалось запустить конвертер": "Could not start the converter", "изменён в конвертере": "edited in the converter",
    "Неверный диапазон страниц": "Invalid page range", "копий": "copies", "Отправляю в печать страницу": "Sending page to print",
    "Не удалось открыть PDF для печати.": "Could not open the PDF for printing.",
})
pc.EN.update({
    "Умная рамка": "Smart frame", "ИИ-агент работает: окно только для просмотра": "AI agent is working: the window is view-only", "Забрать управление": "Take control", "Блокировать окно, пока агент работает (только просмотр)": "Lock the window while the agent works (view only)", "Изменить…": "Change…", "Бумага в драйвере: подбирается автоматически по размеру листа ({f})": "Driver paper: chosen automatically from the sheet size ({f})", "Бумага в драйвере: {p} (выбрана вручную)": "Driver paper: {p} (set manually)", "Профили печати": "Print profiles", "Удалить выбранный": "Delete selected", "без профиля ICC": "no ICC profile", "Сбросить к стандарту": "Reset to defaults", "Профиль: {t}. Изменения сохраняются автоматически.": "Profile: {t}. Changes are saved automatically.", "Скрыть рамки ИИ": "Hide AI boxes", "Убрать с фото все рамки, которые рисует ИИ (люди, лица, части тела, скелет). Сама умная рамка кадра остаётся.": "Hide every box the AI draws on the photo (people, faces, body parts, skeleton). The smart crop frame itself stays.", "Показывать плашку «ИИ-агент работает»": "Show the “AI agent is working” badge", "Макет": "Layout", "Пресет": "Preset", "Переименовать пресет": "Rename preset", "Название пресета (пусто — вернуть стандартное)": "Preset name (empty — restore default)", "Анализ": "Analysis", "Дополнительно": "Advanced", "Результат": "Result", "Все": "All", "Отмеченные": "Checked",
    "Умная рамка: поиск людей (SmartCrop), вердикты ok/note/check/manual, маркеры на миниатюрах, очередь проверки.": "Smart frame: people detection (SmartCrop), ok/note/check/manual verdicts, thumbnail markers, review queue.",
    "Включить режим": "Enable smart frame",
    "Подбирает рамку так, чтобы не отрезать людей и питомцев; сомнительные кадры помечает для проверки.": "Picks a frame that does not cut off people or pets; marks doubtful shots for review.",
    "Автоматически при открытии фото и смене формата": "Automatically when photos are opened or the format changes",
    "Рамки ставятся сами, как только открыты фото или изменён лист": "Frames are set as soon as photos are opened or the sheet changes",
    "Новые фото открыты — анализ запускается сам (если режим включён).": "New photos are opened — analysis starts by itself (if the mode is on).",
    "Ставить найденные рамки": "Apply the frames found", "Выключено — только проверять и помечать кадры, рамки не менять": "Off — only check and mark shots, leave frames unchanged",
    "Не трогать рамки, правленные вручную": "Keep frames I adjusted by hand", "Если вы подвинули рамку сами, автоматика её не перезапишет": "If you moved a frame yourself, it will not be overwritten",
    "Что анализировать": "What to analyse", "Слева показывать только кадры для проверки": "Show only shots to review on the left", "Остальные миниатюры скрываются": "Other thumbnails are hidden",
    "Найти людей и поставить рамки": "Find people and set frames", "Анализировать": "Analyse", "Остановить": "Stop", "Ищу людей…": "Looking for people…",
    "Готово: {n} фото. К проверке: {b}": "Done: {n} photos. To review: {b}", "(остановлено)": "(stopped)", "Нужно посмотреть: {n}": "To review: {n}",
    "Нет отмеченных фото для анализа.": "No checked photos to analyse.", "Для этого фото анализа ещё нет.": "No analysis for this photo yet.",
    "Сначала выполните анализ.": "Run the analysis first.", "Кадров для проверки нет.": "No shots to review.",
    "Следующий": "Next", "Следующий кадр, который стоит проверить (N)": "Next shot worth checking (N)", "Предыдущий кадр для проверки (Shift+N)": "Previous shot to check (Shift+N)",
    "Проверено": "Reviewed", "Снять отметку": "Clear mark", "Отметить кадр проверенным (V)": "Mark the shot as reviewed (V)", "После «Проверено» — к следующему": "After “Reviewed” go to the next one",
    "Вернуть умную рамку": "Restore the smart frame", "Другая ориентация": "Other orientation", "Вписать целиком": "Fit whole", "С белыми полями": "With white margins",
    "белых полей около {p}%": "about {p}% white margins", "всё равно режется: {n}, до {c}%": "still cut: {n}, up to {c}%", "людей: {n}": "people: {n}",
    "всё цело": "all intact", "цело": "intact", "заметка": "note", "проверить": "check", "вручную": "manual", "проверено": "reviewed", "правлено вручную": "edited by hand",
    "нужно пересчитать": "needs recalculation", "Люди и питомцы целы.": "People and pets are intact.",
    "Рамка поправлена вручную — автоматически не меняется.": "Frame adjusted by hand — not changed automatically.",
    "Формат, ориентация или настройки изменились — нужен пересчёт.": "Format, orientation or settings changed — recalculation needed.",
    "Размер места фото на листе, мм (короткая, длинная сторона): целый лист или ячейка при нескольких фото на листе.": "Size of the photo slot on the sheet, mm (short, long side): the whole sheet or a cell when several photos are on a sheet.",
    "Что беречь в первую очередь (сверху — важнее)": "What to protect first (top is more important)", "Важнее": "More important", "Менее важно": "Less important",
    "Голова": "Head", "Тело": "Body", "Питомец": "Pet", "Кисти рук": "Hands", "Руки": "Arms", "Ноги": "Legs", "Стопы": "Feet", "Прочее": "Other",
    "Строгость к важному": "Strictness for the important", "Во сколько раз каждая следующая часть важнее: чем выше, тем сильнее рамка бережёт головы за счёт мелочей": "How many times each next part matters more: the higher, the more the frame protects heads at the expense of details",
    "Запас вокруг головы": "Headroom around the head", "Насколько оставлять место вокруг головы, % от её размера": "How much room to leave around the head, % of its size",
    "Чувствительность поиска людей": "People detection sensitivity", "Выше — находит больше людей, но чаще ошибается; ниже — пропускает неуверенных": "Higher — finds more people but errs more; lower — skips uncertain ones",
    "Групповое фото — от, чел.": "Group photo — from, people", "Начиная с этого числа людей кадр всегда стоит проверить": "From this many people the shot is always worth checking",
    "белые поля листа напечатаются красителем; для печати обычно берут «Относительный»": "the white margins of the sheet will be printed with ink; “Relative” is normally used for printing",
    "Включено управление цветом Windows (ICM) при включённом профиле принтера — цвет обработается дважды. Включите «Цвет Windows (ICM) отключён» на вкладке «Принтер».": "Windows colour management (ICM) is on together with the printer profile — colour would be processed twice. Turn on “Windows colour (ICM) off” on the Printer tab.",
    "Печать фото": "Print photo", "До / После": "Before / After", "До": "Before", "После": "After", "Сравнить: слева снимок без правок, справа с правками. Проведите линию мышью по фото": "Compare: the original on the left, the edited photo on the right. Drag the line over the photo", "Напечатать только это фото (Ctrl+Shift+P)": "Print only this photo (Ctrl+Shift+P)",
    "Нет открытого фото для печати.": "No open photo to print.",
    "Мелкие люди на дальнем плане": "Small people in the background", "Люди мельче этой доли от самого крупного (с лицом) считаются дальним планом": "People smaller than this share of the largest (with a face) count as background",
    "Не учитывать мелких людей": "Ignore small people", "Люди дальнего плана вообще не влияют на рамку и не дают замечаний; выключено — они лишь менее важны": "Background people do not affect the frame or raise warnings; off — they are just less important",
    "Люди без лица — наинизший приоритет": "People without a visible face — lowest priority", "Стоящие спиной и те, у кого в кадр попала только часть тела: если рядом есть человек с лицом, ему ничего не режется, а такому — в последнюю очередь": "People facing away or only partly in the shot: if someone with a face is in the frame, nothing of theirs is cut, and these people are cut last",
    "Ориентация кадра": "Frame orientation", "Как у фото": "As in the photo", "Человек": "Person",
    "Человек: ИИ сам выбирает книжную или альбомную ориентацию и срезает лишнее, оставляя людей крупно, как на портрете, с небольшим запасом фона (фото может «повернуться» на 90°).": "Person: the AI picks portrait or landscape and trims the excess, keeping people large like a portrait with a little background (the photo may turn by 90°).",
    "Шире": "Wider",
    "Как у фото: горизонтальное остаётся горизонтальным, вертикальное — вертикальным. Другую ориентацию можно выбрать вручную для одного кадра.": "As in the photo: landscape stays landscape, portrait stays portrait. You can pick the other orientation by hand for a single shot.",
    "Предупреждать о разрешении ниже, dpi": "Warn below resolution, dpi", "Если из-за рамки разрешение печати ниже, кадр помечается": "If the frame lowers print resolution below this, the shot is marked",
    "Выборочно проверять «цело»": "Spot-check “intact” shots", "Часть безупречных кадров тоже попадает в очередь проверки — так видно, пропустил ли детектор людей молча": "Some flawless shots also go to the review queue — shows whether the detector silently missed people",
    "Обводить найденных людей на фото": "Outline detected people on the photo", "Рамки людей и лиц поверх фото; пунктир — детектор не уверен": "People and face boxes over the photo; dashed — the detector is unsure",
    "Использовать видеокарту (CUDA)": "Use the GPU (CUDA)", "Ускоряет поиск людей, если установлен onnxruntime-gpu": "Speeds up detection if onnxruntime-gpu is installed",
    "видеокарта (CUDA)": "GPU (CUDA)", "процессор": "CPU",
    "Скачать модели": "Download models", "Скачиваю модели…": "Downloading models…", "Проверить установку": "Check installation",
    "Лица (YuNet) и люди (YOLOX), около 42 МБ, один раз": "Faces (YuNet) and people (YOLOX), about 42 MB, once",
    "Нужно скачать модели распознавания (лица и люди, около 42 МБ) — кнопка ниже. Без них люди не находятся.": "Detection models must be downloaded (faces and people, about 42 MB) — button below. Without them people are not found.",
    "Не хватает библиотек: ": "Missing libraries: ", "Готово: лица YuNet + люди YOLOX · ": "Ready: YuNet faces + YOLOX people · ",
    "Файл smart_crop.py не найден рядом с программой.": "smart_crop.py was not found next to the program.",
    "Очистить кэш": "Clear cache", "Кэш распознавания очищен. Следующий анализ найдёт людей заново.": "Detection cache cleared. The next analysis will find people again.",
    "Сбросить настройки": "Reset settings", "Двойной щелчок — вернуть исходное значение.": "Double-click — restore the default.",
    "Контактный лист…": "Contact sheet…", "Контактный лист для проверки": "Contact sheet for review", "Картинка со всеми кадрами для проверки": "An image with all the shots to review",
    "Контактный лист сохранён: ": "Contact sheet saved: ", "Проблемных кадров нет — лист не нужен.": "No problem shots — no sheet needed.",
    "Решения (JSON)…": "Decisions (JSON)…", "Сохранить решения": "Save decisions", "Не удалось сохранить файл:\n%s": "Could not save the file:\n%s",
    "Не удалось обработать файл: %s": "Could not process the file: %s", "Умная рамка: %s": "Smart frame: %s",
    "Найденные люди поверх фото: рамка человека, на лице — яркая рамка; неуверенные — пунктиром.": "Detected people over the photo: a box per person, a bright box on the face; uncertain ones dashed.",
    "Не удалось скачать модели:\n%s\n\nСкачайте вручную: python smart_crop.py setup": "Could not download the models:\n%s\n\nDownload manually: python smart_crop.py setup",
    "Модели распознавания не скачаны: без них люди не находятся (только лица по каскадам Хаара).\n\nСкачать сейчас (около 42 МБ)?": "Detection models are not downloaded: without them people are not found (only faces by Haar cascades).\n\nDownload now (about 42 MB)?",
    "Не найден smart_crop.py:\n%s": "smart_crop.py not found:\n%s",
    ". Выполните: pip install numpy opencv-python onnxruntime": ". Run: pip install numpy opencv-python onnxruntime",
})
pc.EN_FMT.update({
    "Готово: {n} фото. К проверке: {b}": "Done: {n} photos. To review: {b}", "Нужно посмотреть: {n}": "To review: {n}", "людей: {n}": "people: {n}",
    "белых полей около {p}%": "about {p}% white margins", "всё равно режется: {n}, до {c}%": "still cut: {n}, up to {c}%",
})
pc.EN.update({
    "Метод": "Method", "Простой": "Simple", "Улучшенный": "Enhanced",
    "Улучшенный: части тела считаются от размера головы, а важность идёт строго по очереди — голова → тело → кисти → руки → ноги → стопы (порядок меняется ниже). Нижняя ступень никогда не вытесняет верхнюю.": "Enhanced: body parts are sized from the head and importance goes strictly in order — head → body → hands → arms → legs → feet (change the order below). A lower tier never displaces a higher one.",
    "Простой: части тела по пропорциям рамки человека, срезы складываются с весами ступеней («Строгость к важному»).": "Simple: body parts from the person's box proportions; cuts are added up with tier weights (“Strictness for the important”).",
    "Допуск между ступенями": "Tolerance between tiers",
    "Улучшенный метод: разница срезов меньше этой считается ничьёй — тогда решает следующая ступень (тело, кисти, руки…)": "Enhanced method: a difference in cuts smaller than this is a tie — then the next tier decides (body, hands, arms…)",
    "Печать без полей: подрезка принтером": "Borderless printing: printer crop", "Учитывать подрезку": "Apply the printer crop",
    "Выключено — значения ниже сохраняются, но не применяются.": "Off — the values below are kept but not applied.",
    "Со всех сторон, мм": "All sides, mm", "Лево": "Left", "Верх": "Top", "Право": "Right", "Низ": "Bottom",
    "Если принтер срезает края при печати без полей — введите отрицательные значения (отступ): фото уменьшится на эту величину, а принтер дорастит его до края. Положительные — снимок заходит за край листа реальным содержимым. Пустое поле = «как общее». Действует при одном фото на листе без белых полей.": "If the printer crops the edges in borderless printing, enter negative values (inset): the photo shrinks by that amount and the printer grows it to the edge. Positive values extend real photo content past the sheet edge. An empty field = “same as general”. Works with one photo per sheet and no white margins.",
    "Тестовая шкала краёв": "Edge test scale",
    "Картинка со шкалой: распечатайте её теми же настройками — последняя видимая цифра на каждой стороне покажет, сколько мм срезал принтер.": "A scale image: print it with the same settings — the last visible number on each side shows how many mm the printer cropped.",
    "Выключено: значения сохранены, но печать идёт обычным образом.": "Off: values are kept but printing goes the usual way.",
    "Все значения нулевые — подрезки нет.": "All values are zero — no crop.",
    "Сейчас на листе несколько фото или белые поля — подрезка не применяется.": "There are several photos or white margins on the sheet now — the crop is not applied.",
})
pc.EN_FMT.update({"{n} фото": "{n} photos", "Действует: лево {a}, верх {b}, право {c}, низ {d} мм": "Active: left {a}, top {b}, right {c}, bottom {d} mm"})
pc.EN.update({
    "После анализа сортировать фото: красные первыми": "After analysis sort photos: red first",
    "Красные и жёлтые кадры — в начало списка, зелёные — в конец. Поправленные вручную становятся зелёными.": "Red and yellow shots go to the top of the list, green to the end. Shots you fix by hand turn green.",
    "Отсортировать": "Sort", "Исходный порядок": "Original order", "Красные кадры — в начало списка, зелёные — в конец": "Red shots to the top of the list, green to the end",
    "исправить вручную": "fix by hand", "посмотреть": "take a look", "в порядке или поправлено": "fine or fixed",
    "Исправьте кадр вручную": "Fix this shot by hand", "Посмотрите кадр": "Take a look at this shot", "Поправлено вручную": "Fixed by hand", "Кадр в порядке": "Shot is fine",
})
pc.EN.update({
    "Показывать части тела и скелет": "Show body parts and skeleton",
    "Цветные рамки частей (Г голова, Т тело, К кисти, Р руки, Н ноги, С стопы) и скелет нейросети позы в улучшенном методе": "Coloured boxes of the parts (Г head, Т body, К hands, Р arms, Н legs, С feet) and the pose network skeleton in the enhanced method",
    "Конечности: по размеру головы (скелет нейросети не найден или нет модели)": "Limbs: from head size (no network skeleton found or no model)",
    "Конечности: по пропорциям рамки человека (простой метод)": "Limbs: from the person's box proportions (simple method)",
    "Улучшенный метод: нужна модель позы (скелет, около 5,5 МБ) — кнопка ниже. Пока её нет, руки и ноги оцениваются по размеру головы, а не нейросетью.": "Enhanced method: the pose model (skeleton, about 5.5 MB) is needed — button below. Until then arms and legs are estimated from head size, not by the network.",
    "Готово: лица YuNet + люди YOLOX + скелет MediaPipe · ": "Ready: YuNet faces + YOLOX people + MediaPipe skeleton · ",
})
pc.EN_FMT.update({"Конечности: нейросеть позы (скелет найден у {n} из {m} чел.), остальные — по размеру головы": "Limbs: pose network (skeleton found for {n} of {m} people), the rest from head size"})
pc.EN.update({
    "Улучшение для печати на Epson: светлее, чуть контрастнее и резче. Подбирается под каждый снимок. Прежняя коррекция сбрасывается.": "Enhancement for Epson printing: lighter, slightly more contrast and sharpness. Tuned for each photo. The previous correction is reset.",
    "Более сильное улучшение: ярче, сочнее, резче": "Stronger enhancement: brighter, more vivid, sharper",
    "Авто-яркость": "Auto brightness", "Копировать настройки этого фото": "Copy this photo's settings", "Вставить настройки в это фото": "Paste settings into this photo",
    "Применить настройки этого фото ко всем": "Apply this photo's settings to all", "Сбросить коррекцию этого фото": "Reset this photo's adjustments",
    "Сбросить коррекцию у всех фото": "Reset adjustments for all photos",
    "Ширина фото на листе, мм": "Photo width on the sheet, mm", "Высота фото на листе, мм": "Photo height on the sheet, mm", "Ш": "W", "В": "H",
    "Сохранять пропорции при изменении размера": "Keep proportions when resizing", "Повернуть место на листе: ширина ⇄ высота": "Rotate the slot: width ⇄ height",
    "Наклонить фото влево": "Tilt photo left", "Наклонить фото вправо": "Tilt photo right", "Крупнее": "Zoom in", "Мельче": "Zoom out",
    "Вернуть это фото в сетку": "Put this photo back on the grid", "Убрать фото с листа": "Remove the photo from the sheet",
    "Принтер": "Printer", "Принтер и бумага": "Printer and paper", "Тип бумаги": "Media type", "Размер бумаги": "Paper size", "Подача": "Source",
    "Свойства драйвера…": "Driver properties…", "Обновить список принтеров": "Refresh the printer list", "Обработка": "Processing",
    "Все настройки печати": "All print settings", "Проверка дюз": "Nozzle check", "Узор из дюз": "Nozzle pattern",
    "Прочистка головки": "Head cleaning", "Если есть полосы": "If you see banding",
    "Разрешение печати, ppi": "Print resolution, ppi", "Резкость": "Sharpen", "Метки реза": "Cut marks", "Уменьшить лист, %": "Shrink sheet, %",
    "Насколько уменьшить лист, чтобы принтер не срезал края при печати без полей. 0 — не менять.": "How much to shrink the sheet so the printer does not trim the edges in borderless printing. 0 — no change.",
    "Цвет Windows (ICM) отключён": "Windows colour (ICM) off", "Задание": "Job", "Копий каждого листа": "Copies of each sheet",
    "Каждый лист — отдельным заданием": "Each sheet as a separate job", "Пауза между листами, сек": "Pause between sheets, s",
    "Очередь печати": "Print queue", "Нажмите «Обновить», чтобы увидеть очередь.": "Click “Refresh” to see the queue.", "Обновить": "Refresh",
    "Очистить": "Clear", "Старое окно печати…": "Old print window…", "Авто — по размеру листа": "Auto — match the sheet size",
    "Принтеры не найдены. Листы можно сохранить в файлы.": "No printers found. Sheets can be saved to files.",
    "Не удалось получить настройки драйвера этого принтера.": "Could not get this printer's driver settings.",
    "Тип бумаги, качество и печать без полей этот драйвер отдаёт только через «Свойства драйвера». Настройки запоминаются.": "This driver exposes media type, quality and borderless only through “Driver properties”. Settings are remembered.",
    "Качество и печать без полей задаются в «Свойствах драйвера». Настройки запоминаются.": "Quality and borderless are set in “Driver properties”. Settings are remembered.",
    "Принтер не выбран или недоступен.": "No printer selected or printer unavailable.",
    "Принтер не выбран или недоступен. Выберите принтер на вкладке «Принтер».": "No printer selected. Choose one on the “Printer” tab.",
    "Не удалось открыть свойства принтера": "Could not open printer properties", "Не удалось подготовить печать": "Could not prepare printing",
    "Бумага в драйвере": "Paper in driver", "Листов к печати": "Sheets to print", "Начать печать?": "Start printing?",
    "Подготовка…": "Preparing…", "Отменить печать": "Cancel printing", "Ошибка печати": "Print error", "Запрашиваю очередь…": "Reading the queue…",
    "Очередь пуста.": "The queue is empty.", "Удалить все задания из очереди этого принтера?": "Remove all jobs from this printer's queue?",
    "Идёт печать. Прервать и выйти?": "Printing is in progress. Stop and quit?",
    "Копий каждого листа при печати": "Copies of every sheet when printing", "Меньше копий листа": "Fewer sheet copies",
    "Больше копий листа": "More sheet copies",
    "Свободно": "Free", "Свободный режим: фото можно ставить куда угодно и менять их размер": "Free mode: place photos anywhere and resize them",
    "Вернуть раскладку по сетке и исходный порядок": "Restore the grid layout and original order",
    "Печать без полей": "Borderless printing",
    "Лево": "Left", "Верх": "Top", "Право": "Right", "Низ": "Bottom",
})
pc.EN_FMT.update({
    "Печать: лист {a} из {b}": "Printing: sheet {a} of {b}",
    "Отправлено на печать листов: {n}": "Sheets sent to the printer: {n}", "Печать отменена, отправлено листов: {n}": "Printing cancelled, sheets sent: {n}",
    "Лист в программе {a}×{b} мм, а в драйвере другая бумага. Изображение будет растянуто на бумагу драйвера.": "The sheet is {a}×{b} mm but the driver uses a different paper. The image will be stretched to the driver's paper.",
    "{n} фото на листе, ячейка {w}×{h} мм": "{n} photos per sheet, cell {w}×{h} mm", "Белое поле {m} мм вокруг каждого фото": "White border {m} mm around each photo",
    "Листов к печати: {n}": "Sheets to print: {n}", "Сохранить листы · {n}": "Save sheets · {n}", "Сохраняю листы: {n}": "Saving sheets: {n}",
    "Готовлю листы к печати: {n}": "Preparing sheets for print: {n}",
    "{n} из {m} отмечено": "{n} of {m} checked", "Сохранить отмеченные · {n}": "Save checked · {n}",
    "Сохраняю: {n}": "Saving: {n}", "Готово: {n} файл(ов)": "Done: {n} file(s)", "На печать: {n} фото": "To print: {n} photos",
})


# ---------------------------------------------------------------- запуск

def _excepthook(et, ev, tb):
    text = "".join(traceback.format_exception(et, ev, tb))
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + text + "\n")
    except Exception:
        pass
    sys.stderr.write(text)
    try:
        if QApplication.instance() is not None:
            box = QMessageBox(QMessageBox.Critical, "PhotoCrop", "Ошибка в программе. Текст сохранён в файле:\n%s" % LOG_PATH)
            box.setDetailedText(text)
            box.exec()
    except Exception:
        pass


def selftest(app):
    """Собирает окно, загружает пробные снимки, нажимает основные кнопки и сохраняет снимок экрана и отчёт."""
    import tempfile
    out = pc.SETTINGS_PATH.parent
    out.mkdir(parents=True, exist_ok=True)
    report, shots = [], []
    tmp = Path(tempfile.mkdtemp(prefix="photocrop_test_"))
    for i, col in enumerate(((120, 160, 110), (200, 150, 110), (100, 130, 190), (190, 170, 90))):
        pc.Image.new("RGB", (1800, 1200) if i % 2 == 0 else (1200, 1800), col).save(tmp / ("test_%d.jpg" % i))
    win = MainWindow()
    win.show()

    def step(name, fn):
        try:
            fn()
            app.processEvents()
            report.append("OK   " + name)
        except Exception:
            report.append("FAIL " + name + "\n" + traceback.format_exc())

    def shot(name):
        app.processEvents()
        time.sleep(0.3)
        app.processEvents()
        p = out / ("selftest_%s.png" % name)
        win.grab().save(str(p))
        shots.append(str(p))

    def color_tab_empty():
        win.show_page(1)                                     # без фото вкладка «Цвет» открывается: пресеты видны сразу
        app.processEvents()
        if win.pages.currentIndex() != 1 or not win.b_pre[1].isVisible():
            raise RuntimeError("вкладка «Цвет» без фото не открылась или нет кнопок пресетов")
        if win.levels_ed.isEnabled() or win.curves_panel.isEnabled() or win.sel_panel.isEnabled():
            raise RuntimeError("без фото уровни, кривые и выбор цвета должны быть недоступны")
        win.preset_pick(1)
        win.show_page(0)
    step("вкладка «Цвет» открывается без фото", color_tab_empty)
    step("открыть папку", lambda: win.load_folder(tmp))
    step("снимок окна", lambda: shot("main"))
    step("следующее фото", lambda: win.go(1))
    step("поворот", lambda: win.rotate_photo(90))
    step("наклон", lambda: win.tilt(1.5))
    step("масштаб", lambda: win.zoom(0.9))
    step("книжная/альбомная", win.flip_frame)

    def bleed_overlay_rotates():
        class Rec:
            def __init__(self):
                self.texts = []

            def font(self):
                return QFont()

            def drawText(self, _r, _fl, s):
                self.texts.append(s)

            def __getattr__(self, _n):
                return lambda *a, **k: None
        old_print = dict(win.settings.get("print", {}))
        win.settings.setdefault("print", {}).update(bleed_on=True, bleed="0", bleed_l="-2", bleed_t="-2", bleed_r="-3", bleed_b="-6")
        try:
            P = [(0, 0), (100, 0), (100, 60), (0, 60)]
            for rot, want in ((False, ["Л -2", "В -2", "П -3", "Н -6"]), (True, ["Н -6", "Л -2", "В -2", "П -3"])):
                r = Rec()
                win.canvas._bleed(r, P, 100.0, rot)
                if r.texts != want:
                    raise RuntimeError("подрезка у %s кадра: %r, ожидалось %r" % ("лежащего боком" if rot else "прямого", r.texts, want))
        finally:
            win.settings["print"] = old_print
    step("подрезка на рамке поворачивается вместе с кадром", bleed_overlay_rotates)
    step("отмена и повтор", lambda: (win.undo(), win.redo()))
    step("снять отметку", lambda: win.toggle_check(0))
    step("снять все", lambda: win.check_all(False))
    step("отметить все", lambda: win.check_all(True))
    step("страница цвета", lambda: win.show_page(1))
    step("ползунок яркости", lambda: win.sliders["bright"][0].setValue(20))
    def enhance_resets():
        win.adj_set({"temp": 30.0, "sepia": True, "bright": 25.0})
        win.enhance(1)
        a = win.cur_adj()
        if a.get("temp") or a.get("sepia") or a.get("bright"):
            raise RuntimeError("улучшение не сбросило прежнюю коррекцию")
    step("улучшение Epson", lambda: win.enhance(1))
    step("улучшение сбрасывает прежнюю коррекцию", enhance_resets)
    def presets_flow():
        win.settings["adj_presets"] = {}                      # пресеты прошлых запусков спросили бы подтверждение замены
        win.adj_replace({}, [win.files[win.idx]])
        win.adj_set({"bright": 17.0, "sat": 9.0})
        win.preset_pick(1)                                   # пресет пуст: ничего не применяется, настройки на месте
        if win.cur_adj().get("bright") != 17.0:
            raise RuntimeError("пустой пресет изменил настройки")
        win.preset_save(1)
        win.adj_replace({}, [win.files[win.idx]])
        win.preset_pick(1)
        if win.cur_adj().get("bright") != 17.0 or win.cur_adj().get("sat") != 9.0:
            raise RuntimeError("пресет 1 не применился")
        win.adj_set({"bright": -5.0})
        win.preset_save(2)
        win.preset_pick(1)
        if win.cur_adj().get("bright") != 17.0 or pc.load_settings().get("adj_presets", {}).get("2", {}).get("bright") != -5.0:
            raise RuntimeError("пресеты перепутались или не сохранились в файл")
        win.adj_set({"bright": 3.0})
        win.preset_save(3)
        win.preset_rename(3, "  Тёплый   тон ")
        if win.preset_name(3) != "Тёплый тон" or not win.b_pre[3].text().startswith("Тёпл") or pc.load_settings().get("adj_preset_names", {}).get("3") != "Тёплый тон":
            raise RuntimeError("пресет 3 не переименовался")
        win.preset_rename(3, "")
        if not win.preset_name(3).startswith(win.b_pre[3].text().rstrip("…")) or "Тёпл" in win.b_pre[3].text():
            raise RuntimeError("пустое имя должно вернуть «Пресет 3»")
        win.adj_replace({}, [win.files[win.idx]])
        win.sync_adj()
    step("пресеты коррекции: сохранить и применить", presets_flow)
    def printer_correction_flow():
        win.s["pcorr"] = pcr.default()
        win.pcorr_sync()
        if win.w_pcorr_body.isEnabled():
            raise RuntimeError("выключенная поправка не должна давать менять ползунки")
        win.sw_pcorr.set(True)
        win.sw_pcorr.toggled.emit(True)
        if not win.w_pcorr_body.isEnabled() or not win.s["pcorr"]["on"]:
            raise RuntimeError("поправка не включилась")
        win._pc_rows[0][0].setValue(40)                       # тепло, зона «средние»
        win.seg_pc_zone.changed.emit("lights")
        win._pc_rows[1][0].setValue(-25)                      # пурпур, зона «света»
        win.seg_pc_sel.changed.emit(5)
        win._pc_rows[3][0].setValue(-30)                      # насыщенность пурпурного
        c = win.s["pcorr"]
        if c["tone"]["mids"][0] != 40 or c["tone"]["lights"][1] != -25 or c["sel"][5][1] != -30 or c["tone"]["lights"][0] != 0:
            raise RuntimeError("значения попали не в те зоны: %r" % c)
        win.seg_pc_zone.changed.emit("mids")
        if win._pc_rows[0][0].value() != 40:
            raise RuntimeError("ползунок не показал значение выбранной зоны")
        win.persist()
        if pcr.norm(pc.load_settings().get("pcorr"))["tone"]["mids"][0] != 40:
            raise RuntimeError("поправка не сохранилась в настройках")
        before = len(win.files)
        win.add_pcorr_test()
        if len(win.files) != before + 1:
            raise RuntimeError("тестовая страница не добавилась")
        win.w_pcorr_body.parent().grab().save(str(out / "selftest_pcorr.png"))
        win.pcorr_reset()
        if not pcr.is_neutral(win.s["pcorr"]) or not win.s["pcorr"]["on"]:
            raise RuntimeError("сброс должен обнулить значения и оставить переключатель")
        win.s["pcorr"] = pcr.default()
        win.pcorr_sync()
        # поправка живёт в профиле печати связки «принтер + формат + бумага» и переключается вместе с ним
        fmts = list(pc.FORMATS)
        old_pr, old_fmt, old_profs = win.pr["printer"], win.s["format"], dict(win.settings.get("print_profiles", {}))
        try:
            win.pr["printer"] = "Тестовый принтер"
            win.settings["print_profiles"] = {}
            win.s["format"] = fmts[0]
            win.s["pcorr"] = pcr.norm({"on": True, "tone": {"mids": [11, 0]}})
            win.profile_save()
            win.s["format"] = fmts[1]
            win.s["pcorr"] = pcr.norm({"on": True, "tone": {"mids": [-7, 0]}})
            win.profile_save()
            win.s["format"] = fmts[0]
            win.profile_apply()
            if win.s["pcorr"]["tone"]["mids"][0] != 11 or win._pc_rows[0][0].value() != 11:
                raise RuntimeError("поправка не вернулась вместе с профилем первого формата: %r" % win.s["pcorr"])
            win.s["format"] = fmts[1]
            win.profile_apply()
            if win.s["pcorr"]["tone"]["mids"][0] != -7:
                raise RuntimeError("поправка не переключилась вместе с профилем второго формата")
            win.pr["printer"] = "Другой принтер"                   # связка без профиля: прежняя поправка не переносится
            win.s["pcorr"] = pcr.norm({"on": True, "tone": {"mids": [30, 0]}})
            win.profile_apply()
            if win.s["pcorr"]["on"] or not pcr.is_neutral(win.s["pcorr"]) or win._pc_rows[0][0].value() != 0:
                raise RuntimeError("у связки без профиля поправка должна быть выключена и обнулена: %r" % win.s["pcorr"])
            win.pr["printer"] = "Тестовый принтер"
            win.profile_apply()
            win.cm_changed()                                      # тот же ICC: поправка на месте
            win.s["icc"] = "другой_профиль.icc"                   # другой файл ICC: поправка обнуляется, переключатель остаётся
            win.cm_changed()
            if not pcr.is_neutral(win.s["pcorr"]) or not win.s["pcorr"]["on"] or win._pc_rows[0][0].value() != 0:
                raise RuntimeError("при смене файла ICC поправка должна обнулиться: %r" % win.s["pcorr"])
            if pcr.norm(win._profiles()[win.profile_key()]["pcorr"])["tone"]["mids"][0] != 0:
                raise RuntimeError("обнулённая поправка не сохранилась в профиле печати")
        finally:
            win.s["icc"] = ""
            win._pc_icc = ""

            win.pr["printer"], win.s["format"] = old_pr, old_fmt
            win.settings["print_profiles"] = old_profs
            win.s["pcorr"] = pcr.default()
            win.pcorr_sync()
    step("поправка принтера: ползунки, зоны, сохранение, тестовая страница", printer_correction_flow)
    def levels_curves_selcol():
        win.adj_replace({}, [win.files[win.idx]])
        win.sync_adj()
        if not (win.levels_ed.isEnabled() and win.curves_panel.isEnabled() and win.sel_panel.isEnabled()):
            raise RuntimeError("с фото уровни, кривые и выбор цвета должны быть доступны")
        win.levels_ed.rows[0] = [20.0, 1.2, 235.0, 0.0, 255.0]
        win.levels_ed._emit()
        if not win.cur_adj().get("levels"):
            raise RuntimeError("уровни не записались в коррекцию")
        win.curves_panel.shape(((0, 0), (64, 48), (192, 208), (255, 255)))
        if not win.cur_adj().get("curves"):
            raise RuntimeError("кривые не записались в коррекцию")
        win.sel_panel.pick(0)
        win.sel_panel.sl[1].setValue(40)
        if not win.cur_adj().get("selcol"):
            raise RuntimeError("выборочный цвет не записался в коррекцию")
        win.levels_auto()
        win.sync_adj()
        win.open_curves_window()
        app.processEvents()
        win.curves_win.grab().save(str(out / "selftest_curves.png"))
        win.curves_win.close()
        a = dict(win.cur_adj())
        win.settings["adj_presets"] = {}                      # занятый пресет спросил бы подтверждение
        win.preset_save(2)                                   # структурные параметры проходят через пресеты и JSON
        win.adj_replace({}, [win.files[win.idx]])
        win.preset_pick(2)
        if win.cur_adj() != a:
            raise RuntimeError("пресет потерял уровни, кривые или выборочный цвет")
        win.adj_replace({}, [win.files[win.idx]])
        win.sync_adj()
    step("уровни, кривые, выборочный цвет", levels_curves_selcol)
    step("снимок: цвет", lambda: shot("color"))
    step("12 фото на листе", lambda: (win._layout_set("nup", 12), win.seg_nup.set(12)))
    step("7 фото на листе (своё число)", lambda: (win._layout_set("nup", 7), win.seg_nup.set(7), win.layout_spec()))
    step("4 фото на листе", lambda: win._layout_set("nup", 4))
    step("вид «Лист»", lambda: (win.set_view("sheet"), win.sheet_view.update()))
    step("снимок: лист 4", lambda: (time.sleep(1.5), shot("sheet4")))
    step("2 фото на листе с полями", lambda: (win._layout_set("nup", 2), win._layout_set("borders", True), win.sheet_view.update()))
    step("снимок: лист 2 с полями", lambda: (time.sleep(1.5), shot("sheet2")))
    step("вид «Кадр»", lambda: (win._layout_set("borders", False), win._layout_set("nup", 1), win.set_view("crop")))
    step("режим «вписать»", lambda: win.seg_mode.group.buttons()[1].click())
    step("режим «кадрировать»", lambda: win.seg_mode.group.buttons()[0].click())
    for name in THEMES:
        step("тема " + name, lambda n=name: win.apply_look(theme=n))
        step("снимок темы " + name, lambda n=name: shot("theme_" + n))
    step("язык English", lambda: win.apply_look(lang="en"))
    step("язык русский", lambda: win.apply_look(lang="ru"))
    step("окно настроек", lambda: SettingsDialog(win).grab().save(str(out / "selftest_settings.png")))
    step("окно профиля", lambda: CmDialog(win).grab().save(str(out / "selftest_profile.png")))

    def agent_flow():
        import agent_bridge as ab
        import urllib.error
        win.settings["agent_allow_print"] = True
        port = win.agent_start()
        if not port or ab.read_endpoint() is None:
            raise RuntimeError("сервер агента не запустился")
        ep = ab.read_endpoint()

        def call(method, params=None, endpoint=None):
            res = {}

            def run():
                try:
                    res["r"] = ab.post(endpoint or ep, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}, timeout=60)
                except Exception as ex:                      # noqa: BLE001
                    res["e"] = ex
            t = threading.Thread(target=run)
            t.start()
            while t.is_alive():                               # окно обрабатывает запросы агента в этом потоке
                app.processEvents()
                time.sleep(0.01)
            if "e" in res:
                raise res["e"]
            return res["r"]

        def tool(name, **args):
            r = call("tools/call", {"name": name, "arguments": args})
            return json.loads(r["result"]["content"][0]["text"])
        r = call("initialize", {"protocolVersion": "2025-06-18"})
        if "PhotoCrop" not in r["result"]["instructions"] or "resources" not in r["result"]["capabilities"]:
            raise RuntimeError("initialize: нет инструкции или ресурсов")
        names = {t["name"] for t in call("tools/list")["result"]["tools"]}
        need = {"app_state", "app_guide", "enhance", "set_adjust", "open_folder", "print_photos", "set_layout", "doc_open", "color_preset_apply", "undo"}
        if need - names:
            raise RuntimeError("нет инструментов: %s" % sorted(need - names))
        if "# PhotoCrop" not in call("resources/read", {"uri": "photocrop://guide/overview"})["result"]["contents"][0]["text"]:
            raise RuntimeError("справка не читается")
        st = tool("app_state")
        if not st["ok"] or st["result"]["photos"] != len(win.files):
            raise RuntimeError("app_state: %s" % st)
        win.adj_replace({}, [win.files[win.idx]])
        r = tool("set_adjust", bright=21.0)
        if not r["ok"] or win.cur_adj().get("bright") != 21.0:
            raise RuntimeError("set_adjust агента не дошёл до окна: %s" % r)
        win.undo()
        if win.cur_adj().get("bright"):
            raise RuntimeError("Ctrl+Z окна не отменил команду агента")
        r = tool("enhance", level=2)
        if not r["ok"] or not win.cur_adj():
            raise RuntimeError("enhance: %s" % r)
        r = tool("set_layout", nup=4, borders=True, border_mm=3)
        if not r["ok"] or win.s["nup"] != 4 or not win.s["borders"]:
            raise RuntimeError("set_layout: %s" % r)
        tool("set_layout", nup=1, borders=False)
        r = tool("printer_correction", on=True, tone={"mids": [30, -10]}, sat=15)
        if not r["ok"] or win.s["pcorr"]["tone"]["mids"] != [30.0, -10.0] or not win.sw_pcorr.isChecked() or win._pc_rows[0][0].value() != 30:
            raise RuntimeError("printer_correction агента не дошла до окна: %s" % r)
        r = tool("printer_correction", tone={"nowhere": [1, 1]})
        if r["ok"]:
            raise RuntimeError("неверная зона поправки должна давать ошибку")
        tool("printer_correction", reset=True, on=False)
        if not pcr.is_neutral(win.s["pcorr"]) or win.s["pcorr"]["on"]:
            raise RuntimeError("сброс поправки агентом не сработал")
        r = tool("set_format", format="13x18")
        if not r["ok"] or not win.s["format"].startswith("13"):
            raise RuntimeError("set_format агента не изменил формат окна: %s" % r)
        tool("set_format", format="10x15")
        r = tool("check_photos", photo="all", on=False)
        if not r["ok"] or win.checked_files():
            raise RuntimeError("check_photos: %s" % r)
        tool("check_photos", photo="all", on=True)
        r = tool("open_folder", path=str(tmp))
        if not r["ok"] or len(win.files) != 4:
            raise RuntimeError("open_folder агента не открыл фото в окне: %s" % r)
        win.settings["agent_allow_print"] = False
        r = tool("print_photos")
        if r["ok"] or r["error"]["code"] != "print_not_allowed":
            raise RuntimeError("запрет печати не сработал: %s" % r)
        win.settings["agent_allow_print"] = True
        try:
            call("tools/list", endpoint={"port": ep["port"], "token": "wrong"})
            raise RuntimeError("запрос с чужим ключом принят")
        except urllib.error.HTTPError as ex:
            if ex.code != 401:
                raise
        win.agent_stop()
        if ab.read_endpoint() is not None:
            raise RuntimeError("файл адреса агента остался после остановки")
    step("ИИ-агент в окне: MCP по HTTP, инструменты, права", agent_flow)
    def open_dlg():
        d = OpenDialog(win, str(tmp))
        d.show()
        app.processEvents()
        time.sleep(0.6)
        app.processEvents()
        d._load_visible()
        app.processEvents()
        d.grab().save(str(out / "selftest_open.png"))
        d.close()
    step("окно «Открыть»", open_dlg)

    def drop_doc():
        from PIL import Image
        pdf = tmp / "бросили.pdf"
        Image.new("RGB", (300, 400), (240, 240, 240)).save(pdf)
        win.drop_paths([str(pdf)])
        app.processEvents()
        if win.app_mode != "doc" or win.pages.currentIndex() != 4:
            raise RuntimeError("документ не открыл раздел «Документ»")
        win.set_app_mode("photo")
    step("документ, брошенный в окно, открывает раздел «Документ»", drop_doc)
    step("вкладка «Принтер»", lambda: (win.show_page(2), shot("printer"), win.show_page(0)))
    step("параметры сохранения", lambda: win.options() or (_ for _ in ()).throw(RuntimeError("options() вернул пусто")))
    text = "PhotoCrop Qt selftest  %s\nPySide6 %s, Python %s\n\n%s\n" % (
        time.strftime("%Y-%m-%d %H:%M:%S"), __import__("PySide6").__version__, sys.version.split()[0], "\n".join(report))
    (out / "selftest_report.txt").write_text(text, encoding="utf-8")
    print(text)
    print("Файлы самопроверки:", out)
    return 1 if any(r.startswith("FAIL") for r in report) else 0


pc.EN.update({
    "Счётчик печати": "Print counter", "Счётчик печати — администратор": "Print counter — administrator",
    "Подробный счётчик (администратор)…": "Detailed counter (administrator)…",
    "Подробный журнал, экспорт и сброс доступны по паролю администратора.": "The detailed journal, export and reset need the administrator password.",
    "Пароль администратора": "Administrator password", "Новый пароль": "New password", "Повторите пароль": "Repeat the password",
    "Пароли не совпадают.": "The passwords do not match.", "Вход администратора": "Administrator login", "Пароль": "Password",
    "Забыли пароль?": "Forgot the password?", "Восстановление": "Recovery", "Ключ восстановления": "Recovery key",
    "Введите ключ, который показала программа при создании пароля.": "Enter the key the program showed when the password was created.",
    "Ключ восстановления не подошёл.": "The recovery key does not match.", "Неверный пароль.": "Wrong password.",
    "Ключ восстановления (покажется один раз). Запишите его и храните отдельно от компьютера. С ним можно задать новый пароль, если старый забыт.":
        "Recovery key (shown only once). Write it down and keep it away from this computer. It lets you set a new password if the old one is forgotten.",
    "Сменить пароль": "Change password", "Текущий пароль": "Current password", "Отмена": "Cancel",
    "Экспорт в CSV…": "Export to CSV…", "Очистить журнал": "Clear the journal", "Выйти": "Log out",
    "Очистить журнал? Старый журнал сохранится в файл-копию рядом с ним.": "Clear the journal? The old journal is kept in a backup file next to it.",
    "Копия журнала": "Journal backup", "Сводка": "Summary", "Журнал": "Journal",
    "Время": "Time", "Бумага, мм": "Paper, mm", "Файлов на листе": "Files on the sheet", "Файлы": "Files", "Напечатано файлов": "Files printed", "Режим": "Mode", "Источник": "Source", "Листов": "Sheets",
    "Всего напечатано": "Total printed", "Период": "Period", "Фото": "Photos", "Сегодня": "Today", "7 дней": "7 days", "30 дней": "30 days",
    "Всё время": "All time", "По принтерам": "By printer", "Принтеры": "Printers", "Все принтеры": "All printers", "Принтер": "Printer",
    "Экспорт по принтерам…": "Export by printer…", "Нет данных за выбранный период.": "No data for the selected period.", "листов": "sheets", "фото": "photos", "документы": "documents", "Период": "Period", "По формату бумаги": "By paper size",
    "По источнику (app — окно программы, agent — ИИ-агент)": "By source (app — program window, agent — AI agent)",
    "Последние 14 дней": "Last 14 days",
})
pc.EN_FMT.update({
    "Придумайте пароль администратора (не короче {n} символов). Он защищает подробный счётчик печати.":
        "Choose an administrator password (at least {n} characters). It protects the detailed print counter.",
    "Пароль короче {n} символов.": "The password is shorter than {n} characters.",
    "Слишком много неверных попыток. Подождите {m} мин {s} с.": "Too many wrong attempts. Wait {m} min {s} s.",
    "⚠ Журнал изменён или повреждён (строка {n}). Данные ниже могут быть неточными.": "⚠ The journal was changed or damaged (line {n}). The figures below may be inaccurate.",
    "Сохранено строк: {n}": "Rows saved: {n}",
    "Напечатано сегодня: {s} листов (фото {p}, документы {d})": "Printed today: {s} sheets (photos {p}, documents {d})",
})


def make_app_icon():
    """Значок программы для панели задач, окна и Alt+Tab: тот же знак «К», что и в шапке, без анимации."""
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(s, s)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        bd.draw_mark(p, QRectF(0, 0, s, s), True)
        p.end()
        icon.addPixmap(pm)
    return icon


def main():
    sys.excepthook = _excepthook
    try:                                             # свой идентификатор, чтобы в панели задач был наш значок, а не python
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("KopiTehnik.Print.PhotoCrop")
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("PhotoCrop")
    app.setWindowIcon(make_app_icon())
    app.setStyle("Fusion")
    if "--selftest" in sys.argv:
        sys.exit(selftest(app))
    win = MainWindow()
    win.showMaximized()

    def fit():                                       # окно не должно быть шире экрана, даже если панели просят больше
        try:
            av = win.screen().availableGeometry()
            if win.width() > av.width() or win.height() > av.height():
                win.setGeometry(av)
        except Exception:
            pass
    QTimer.singleShot(300, fit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
