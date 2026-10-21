"""Печатает версию программы из photo_crop_qt.py (одно место правды для установщика и релиза)."""
import re
import sys
from pathlib import Path

src = (Path(__file__).resolve().parent.parent / "photo_crop_qt.py").read_text(encoding="utf-8")
m = re.search(r'^APP_VERSION = "([^"]+)"', src, re.M)
if not m:
    sys.exit("APP_VERSION не найден")
print(m.group(1))
