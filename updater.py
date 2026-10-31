"""Автообновление: скачивает новую версию из релиза GitHub, проверяет её и запускает замену программы.

Обновление ставит установщик релиза (KopiTehnikPrint-Setup-*.exe) в тихом режиме поверх текущей установки.
Это делает маленький bat-файл: он ждёт, пока программа закроется, запускает установщик и потом сам открывает программу. Без Qt: проверяется отдельно в tests/test_updater.py.
"""
import hashlib
import ntpath
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


def _program_files_dirs():
    out = []
    for k in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        v = os.environ.get(k)
        if v:
            out.append(os.path.normcase(os.path.abspath(v)))
    return out


def needs_admin(app_exe):
    """Программа стоит в «Program Files»: обновить её можно только с правами администратора (отдельный запрос UAC)."""
    d = os.path.normcase(os.path.abspath(str(app_exe)))
    return any(d == p or d.startswith(p + os.sep) for p in _program_files_dirs())


def result_path():
    import app_dirs
    return app_dirs.data_dir() / "update_result.txt"


def log_path():
    import app_dirs
    return app_dirs.data_dir() / "update_install.log"


def consume_result():
    """Итог прошлой установки обновления: (код выхода установщика, путь к журналу) или None. Файл итога удаляется."""
    p = result_path()
    try:
        txt = p.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return None
    try:
        p.unlink()
    except OSError:
        pass
    try:
        return int(txt.split()[0]), str(log_path())
    except (ValueError, IndexError):
        return None


def build_script(setup_file, app_exe, pid=None, admin=None, result=None, log=None):
    """Текст bat-файла: дождаться закрытия программы, поставить обновление (с запросом UAC, если программа в Program Files),
    записать код результата и запустить программу снова.
    Ждём все процессы с именем программы (в том числе зависший фоновый), через 8 секунд завершаем оставшиеся: иначе установщик
    просит «закрыть старую версию»."""
    admin = needs_admin(app_exe) if admin is None else admin
    exe_name = ntpath.basename(str(app_exe))       # пути Windows: basename платформы здесь не подходит (тесты идут и на Linux)
    scope = "/ALLUSERS" if admin else "/CURRENTUSER"
    args = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", scope]
    if log:
        args.append('/LOG="%s"' % log)
    lines = ["@echo off",
             "chcp 65001 >nul",
             "set N=0",
             ":wait",
             r'%%SystemRoot%%\System32\tasklist.exe /FI "IMAGENAME eq %s" 2>nul | %%SystemRoot%%\System32\find.exe /I "%s" >nul' % (exe_name, exe_name),
             "if errorlevel 1 goto go",
             "set /a N+=1",
             "if %N% geq 8 goto kill",
             "timeout /t 1 /nobreak >nul",
             "goto wait",
             ":kill",
             r'%%SystemRoot%%\System32\taskkill.exe /F /IM "%s" >nul 2>&1' % exe_name,
             "timeout /t 2 /nobreak >nul",
             ":go"]
    if admin:
        ps_args = ",".join("'%s'" % a.replace("'", "''") for a in args)
        ps = ("$p = Start-Process -FilePath '%s' -ArgumentList %s -Verb RunAs -Wait -PassThru; exit $p.ExitCode"
              % (str(setup_file).replace("'", "''"), ps_args))
        lines.append('powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "%s"' % ps.replace('"', '\\"'))
    else:
        lines.append('start "" /wait "%s" %s' % (setup_file, " ".join('"%s"' % a if (" " in a and '"' not in a) else a for a in args)))
    lines.append("set RC=%errorlevel%")
    if result:
        lines.append('echo %%RC%%> "%s"' % result)
    lines += ['start "" "%s"' % app_exe, '(goto) 2>nul & del "%~f0"']
    return "\r\n".join(lines) + "\r\n"


def launch(setup_file, app_exe=None, pid=None):
    """Запускает замену в отдельном процессе; после этого программа должна сразу закрыться."""
    app_exe = app_exe or sys.executable
    script = Path(tempfile.mkdtemp(prefix="kopitehnik_apply_")) / "apply_update.bat"
    try:
        result, log = result_path(), log_path()
        result.parent.mkdir(parents=True, exist_ok=True)
        result.unlink(missing_ok=True)
    except Exception:
        result = log = None
    script.write_text(build_script(setup_file, app_exe, pid or os.getpid(), result=result, log=log), encoding="utf-8")
    flags = 0x00000008 | 0x00000200 | 0x08000000          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    subprocess.Popen(["cmd.exe", "/c", str(script)], creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return script
