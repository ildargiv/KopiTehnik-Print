"""Папка данных программы: %APPDATA%\\KopiTehnik Print (раньше PhotoCrop). Старая папка при первом запуске переносится целиком."""
import os
from pathlib import Path

NAME, OLD_NAME = "KopiTehnik Print", "PhotoCrop"


def data_dir():
    root = Path(os.environ.get("APPDATA", str(Path.home())))
    new, old = root / NAME, root / OLD_NAME
    if not new.exists() and old.is_dir():
        try:
            old.rename(new)
        except OSError:                       # папка занята другой копией программы: работаем со старой, перенос в следующий раз
            return old
    return new
