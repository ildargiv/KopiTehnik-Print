"""Узкая панель (316 px): подписи кнопок не обрезаются; английские строки для «По числу / По размеру» и др."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget  # noqa: E402

import photo_crop as pc  # noqa: E402
import photo_crop_qt as q  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def host(app, width, *buttons):
    """Кнопки с жёстко заданной шириной: как в узкой панели, где ряд тесен и лейаут отдаёт кнопке меньше, чем ей нужно."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    for b in buttons:
        b.setFixedWidth(width)
        lay.addWidget(b)
    w.show()
    app.processEvents()
    return w


def set_width(app, w, b, width):
    b.setFixedWidth(width)
    app.processEvents()


def need(b):
    return b.sizeHint().width()


def test_fit_button_shrinks_instead_of_clipping(app):
    wide = q.FitButton("Очень длинная подпись кнопки").fit_text()
    narrow = q.FitButton("Ок").fit_text()
    w = host(app, 90, wide)
    narrow.setParent(w)
    narrow.setFixedWidth(200)
    narrow.show()
    app.processEvents()
    assert wide.styleSheet() and "font-size" in wide.styleSheet()              # не влезала: поля и шрифт уменьшены
    assert not narrow.styleSheet()                                             # влезала: ничего не трогаем
    px = int(wide.styleSheet().split("font-size:")[1].split("px")[0])
    assert q.FitButton.fit_min <= px < 13
    w.close()


def test_fit_button_untouched_when_it_fits(app):
    b = q.FitButton("Печать").fit_text()
    w = host(app, 300, b)
    assert not b.styleSheet()
    w.close()


def test_fit_button_not_enabled_by_default(app):
    b = q.FitButton("Очень длинная подпись кнопки без включённой подгонки")
    w = host(app, 100, b)
    assert not b.styleSheet()
    w.close()


def test_fit_restores_when_wider(app):
    b = q.FitButton("Очень длинная подпись кнопки").fit_text()
    w = host(app, 90, b)
    assert b.styleSheet()
    set_width(app, w, b, 600)
    assert not b.styleSheet()
    w.close()


def test_segmented_and_btn_buttons_use_fit(app):
    seg = q.Segmented([("Макет", 0), ("Умная рамка", 1)], 0)
    assert all(isinstance(b, q.FitButton) and b._fit_on for b in seg.group.buttons())
    assert q.btn("Улучшить")._fit_on


def test_english_for_layout_cell_modes_and_hints():
    pc.set_language("en")
    try:
        assert pc.tr("По числу") == "By count" and pc.tr("По размеру") == "By size"
        assert pc.tr("Увеличение этого фото") == "Zoom of this photo"
        assert pc.tr("Оригинал") != "Оригинал" and pc.tr("Поместить") != "Поместить"
        assert not any(c.isalpha() and ord(c) > 0x400 for c in pc.tr("Обрезать"))
    finally:
        pc.set_language("ru")


def test_fit_leaves_buttons_with_their_own_style_alone(app):
    b = q.FitButton("Очень длинная подпись кнопки").fit_text()
    b.setStyleSheet("QPushButton { background: green; }")
    w = host(app, 90, b)
    assert b.styleSheet() == "QPushButton { background: green; }"
    w.close()
