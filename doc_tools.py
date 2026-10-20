# -*- coding: utf-8 -*-
"""Режим «Документ»: разбор диапазона страниц, раскладка страницы на бумаге, поиск и запуск конвертера.

Без Qt и без PyMuPDF (лицензия AGPL): правка PDF и распознавание делаются в отдельной программе «КопиТехник Конвертор».
"""
import os
import subprocess
import sys
from pathlib import Path

PAPERS = {"A4": (210.0, 297.0), "A5": (148.0, 210.0), "A3": (297.0, 420.0), "Letter": (215.9, 279.4), "Legal": (215.9, 355.6)}
CONVERTER_RELEASES = "https://github.com/ildargiv/kopitehnik-converter/releases/latest"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def parse_range(text, total):
    """'1-3, 5, 8-' -> [0, 1, 2, 4, 7, ...] (номера страниц с нуля, по порядку, без повторов). Пусто — все страницы.
    Ошибка в записи -> ValueError."""
    text = (text or "").strip()
    if not text:
        return list(range(total))
    out, seen = [], set()
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        a, sep, b = part.partition("-")
        try:
            lo = int(a) if a.strip() else 1
            hi = (int(b) if b.strip() else total) if sep else lo
        except ValueError:
            raise ValueError(part)
        if lo < 1 or hi < lo or hi > total:
            raise ValueError(part)
        for n in range(lo - 1, hi):
            if n not in seen:
                seen.add(n)
                out.append(n)
    if not out:
        raise ValueError(text)
    return out


def place_page(page_w, page_h, paper_w, paper_h, mode="fit", margin=0.0):
    """Где на бумаге стоит страница (все размеры в одних единицах). mode: 'fit' — вписать целиком по центру
    (увеличивая и уменьшая), 'shrink' — только уменьшать, 'actual' — в натуральную величину по центру.
    Возвращает (x, y, w, h, повернуть_на_90)."""
    rot = (page_w > page_h) != (paper_w > paper_h)             # книжная страница на альбомном листе и наоборот
    if rot:
        page_w, page_h = page_h, page_w
    aw, ah = max(1.0, paper_w - 2 * margin), max(1.0, paper_h - 2 * margin)
    k = min(aw / page_w, ah / page_h)
    if mode == "actual":
        k = 1.0
    elif mode == "shrink":
        k = min(k, 1.0)
    w, h = page_w * k, page_h * k
    return (paper_w - w) / 2, (paper_h - h) / 2, w, h, rot


def converter_candidates(custom=""):
    """Где может лежать Converter.exe."""
    out = [Path(custom)] if custom else []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        out.append(Path(local) / "Programs" / "KopiTehnik Converter" / "Converter.exe")
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        if base:
            out.append(Path(base) / "KopiTehnik Converter" / "Converter.exe")
    if sys.platform == "win32":
        try:
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\KopiTehnikConverter") as k:
                        loc = winreg.QueryValueEx(k, "InstallLocation")[0]
                        out.append(Path(loc) / "Converter.exe")
                except OSError:
                    pass
        except ImportError:
            pass
    return out


def find_converter(custom=""):
    for p in converter_candidates(custom):
        try:
            if p.is_file():
                return str(p)
        except OSError:
            pass
    return None


def edit_command(exe, src, ocr=False, out=None):
    """Командная строка конвертера: Converter.exe --edit <файл> [--ocr] [--out <результат.pdf>]."""
    cmd = [str(exe), "--edit", str(src)]
    if ocr:
        cmd.append("--ocr")
    if out:
        cmd += ["--out", str(out)]
    return cmd


def run_edit(exe, src, ocr=False, out=None):
    """Запускает редактор конвертера и ждёт его закрытия. Возвращает путь сохранённого PDF или None (закрыли без сохранения)."""
    r = subprocess.run(edit_command(exe, src, ocr, out), capture_output=True, text=True, creationflags=_NO_WINDOW)
    if r.returncode != 0:
        return None
    lines = [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]
    return lines[-1] if lines and Path(lines[-1]).is_file() else None
