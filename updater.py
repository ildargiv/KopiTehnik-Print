"""Автообновление: скачивает новую версию из релиза GitHub, проверяет её и запускает замену программы.

Обновление ставит установщик релиза (KopiTehnikPrint-Setup-*.exe) в тихом режиме поверх текущей установки.
Это делает маленький bat-файл: он ждёт, пока программа закроется, запускает установщик и потом сам открывает программу. Без Qt: проверяется отдельно в tests/test_updater.py.
"""
import hashlib
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

SETUP_PREFIX = "KopiTehnikPrint-Setup-"
CHUNK = 256 * 1024


class UpdateError(Exception):
    pass


def assets_from_release(release):
    """Установщик релиза: {"setup": {...}} с name, url, size, sha256 (если GitHub её отдал); пусто, если установщика нет."""
    out = {}
    for a in (release or {}).get("assets") or []:
        name = str(a.get("name", ""))
        url = a.get("browser_download_url")
        if not url:
            continue
        if name.startswith(SETUP_PREFIX) and name.lower().endswith(".exe") and "setup" not in out:
            digest = str(a.get("digest") or "")
            out["setup"] = {"name": name, "url": str(url), "size": int(a.get("size") or 0),
                         "sha256": digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else ""}
    return out


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def install_kind():
    """"setup" — собранная программа под Windows (обновляется установщиком), None — запуск из исходников (самообновление недоступно)."""
    return "setup" if is_frozen() and sys.platform == "win32" else None


def pick_asset(assets):
    """Какой файл качать для этой копии программы или None, если самообновление недоступно."""
    return assets.get("setup") if install_kind() else None


def download(asset, dest_dir=None, progress=None, cancelled=None, timeout=30):
    """Скачивает файл во временную папку и проверяет размер и SHA-256. Возвращает путь.
    progress(получено, всего) вызывается по ходу; cancelled() -> True прерывает загрузку (UpdateError)."""
    dest_dir = Path(dest_dir or tempfile.mkdtemp(prefix="kopitehnik_update_"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / asset["name"]
    part = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    got = 0
    try:
        rq = urllib.request.Request(asset["url"], headers={"User-Agent": "KopiTehnikPrint"})
        with urllib.request.urlopen(rq, timeout=timeout) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or asset.get("size") or 0)
            while True:
                if cancelled and cancelled():
                    raise UpdateError("Загрузка отменена.")
                chunk = r.read(CHUNK)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                got += len(chunk)
                if progress:
                    progress(got, total)
    except UpdateError:
        part.unlink(missing_ok=True)
        raise
    except Exception as ex:
        part.unlink(missing_ok=True)
        raise UpdateError("Не удалось скачать обновление: %s" % ex)
    size = int(asset.get("size") or 0)
    if size and got != size:
        part.unlink(missing_ok=True)
        raise UpdateError("Файл скачан не полностью (%d из %d байт)." % (got, size))
    want = asset.get("sha256") or ""
    if want and h.hexdigest().lower() != want:
        part.unlink(missing_ok=True)
        raise UpdateError("Контрольная сумма файла не совпала: загрузка повреждена, обновление отменено.")
    os.replace(part, dest)
    return dest


def build_script(setup_file, app_exe, pid):
    """Текст bat-файла: дождаться закрытия программы, тихо поставить обновление, запустить программу снова."""
    lines = ["@echo off",
             "chcp 65001 >nul",
             ":wait",
             r'%%SystemRoot%%\System32\tasklist.exe /FI "PID eq %d" 2>nul | %%SystemRoot%%\System32\find.exe "%d" >nul' % (pid, pid),
             "if not errorlevel 1 (",
             "  timeout /t 1 /nobreak >nul",
             "  goto wait",
             ")",
             'start "" /wait "%s" /SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS' % setup_file,
             'start "" "%s"' % app_exe,
             '(goto) 2>nul & del "%~f0"']
    return "\r\n".join(lines) + "\r\n"


def launch(setup_file, app_exe=None, pid=None):
    """Запускает замену в отдельном процессе; после этого программа должна сразу закрыться."""
    app_exe = app_exe or sys.executable
    script = Path(tempfile.mkdtemp(prefix="kopitehnik_apply_")) / "apply_update.bat"
    script.write_text(build_script(setup_file, app_exe, pid or os.getpid()), encoding="utf-8")
    flags = 0x00000008 | 0x00000200 | 0x08000000          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    subprocess.Popen(["cmd.exe", "/c", str(script)], creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return script
