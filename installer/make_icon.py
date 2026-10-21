# -*- coding: utf-8 -*-
"""Рисует assets/app.ico (значок программы для exe и установщика) тем же кодом, что и значок окна.
Запуск: QT_QPA_PLATFORM=offscreen python installer/make_icon.py"""
import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("APPDATA", str(ROOT / "build" / "appdata"))      # не трогать настройки пользователя

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication
from PIL import Image

import photo_crop_qt as q

app = QApplication([])
frames = []
for n in (16, 24, 32, 48, 64, 128, 256):
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    q.brand_icon_pixmap(n).save(buf, "PNG")
    frames.append(Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA"))
out = ROOT / "assets" / "app.ico"
out.parent.mkdir(exist_ok=True)
frames[-1].save(out, format="ICO", sizes=[(f.width, f.height) for f in frames], append_images=frames[:-1])
print("OK", out, out.stat().st_size)
