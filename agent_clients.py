# -*- coding: utf-8 -*-
"""Подключение PhotoCrop как MCP-сервера к программам-агентам: Claude Desktop, Claude Code, Cursor, Windsurf, OpenCode, OpenClaw,
Hermes Agent, VS Code и любой другой клиент с запуском сервера командой (stdio).

Сервер у всех один: `PhotoCropQt.exe mcp` (он сам соединяется с окном программы). Различается только место и формат настройки клиента.
Файлы JSON правим сами (с копией .bak и без затрагивания чужих серверов), для остальных даём команду клиента или готовый текст.
Модуль без Qt."""
import json
import os
import shutil
import subprocess
from pathlib import Path

NAME = "photocrop"


def _home():
    return Path(os.path.expanduser("~"))


def _appdata():
    return Path(os.environ.get("APPDATA") or str(_home() / "AppData" / "Roaming"))


def _std(cmd):
    return {"command": cmd["command"], "args": list(cmd["args"])}


def _opencode(cmd):
    return {"type": "local", "command": [cmd["command"], *cmd["args"]], "enabled": True}


def _vscode(cmd):
    return {"type": "stdio", "command": cmd["command"], "args": list(cmd["args"])}


# kind: json — правим файл; cli — запускаем команду клиента; text — только показываем настройку
CLIENTS = {
    "claude_desktop": {"title": "Claude Desktop", "kind": "json", "path": lambda: _appdata() / "Claude" / "claude_desktop_config.json",
                       "key": "mcpServers", "shape": _std, "create_dir": True, "restart": "Закройте Claude Desktop полностью (и значок в трее) и откройте снова."},
    "claude_code": {"title": "Claude Code", "kind": "cli", "exe": "claude",
                    "add": lambda c: ["claude", "mcp", "add", "--scope", "user", NAME, "--", c["command"], *c["args"]],
                    "remove": lambda c: ["claude", "mcp", "remove", "--scope", "user", NAME]},
    "cursor": {"title": "Cursor", "kind": "json", "path": lambda: _home() / ".cursor" / "mcp.json", "key": "mcpServers", "shape": _std,
               "restart": "Перезапустите Cursor."},
    "windsurf": {"title": "Windsurf", "kind": "json", "path": lambda: _home() / ".codeium" / "windsurf" / "mcp_config.json",
                 "key": "mcpServers", "shape": _std, "restart": "Нажмите «Refresh» в панели MCP или перезапустите Windsurf."},
    "opencode": {"title": "OpenCode", "kind": "json", "path": lambda: _home() / ".config" / "opencode" / "opencode.json", "key": "mcp",
                 "shape": _opencode, "schema": "https://opencode.ai/config.json", "restart": "Перезапустите OpenCode."},
    "openclaw": {"title": "OpenClaw", "kind": "cli", "exe": "openclaw",
                 "add": lambda c: ["openclaw", "mcp", "add", NAME, "--command", c["command"], *sum((["--arg", a] for a in c["args"]), [])],
                 "remove": None},
    "hermes": {"title": "Hermes Agent", "kind": "text", "where": "~/.hermes/config.yaml",
               "restart": "Добавьте блок в ~/.hermes/config.yaml, затем в Hermes выполните /reload-mcp."},
    "vscode": {"title": "VS Code (Copilot)", "kind": "text", "where": ".vscode/mcp.json или «MCP: Open User Configuration»", "restart": ""},
    "other": {"title": "Другой клиент (JSON)", "kind": "text", "where": "настройки MCP вашего клиента", "restart": ""},
}


def titles():
    return {k: v["title"] for k, v in CLIENTS.items()}


def snippet(client, cmd):
    """Готовая настройка для клиента (текст, который можно вставить)."""
    c = CLIENTS[client]
    j = lambda o: json.dumps(o, ensure_ascii=False, indent=2)
    if client == "hermes":
        return ("mcp_servers:\n  %s:\n    command: %s\n    args: %s\n"
                % (NAME, json.dumps(cmd["command"], ensure_ascii=False), json.dumps(cmd["args"])))
    if client == "vscode":
        return j({"servers": {NAME: _vscode(cmd)}})
    if client == "claude_code":
        return " ".join(_quote(a) for a in c["add"](cmd))
    if client == "openclaw":
        return " ".join(_quote(a) for a in c["add"](cmd))
    if c["kind"] == "json":
        return j({c["key"]: {NAME: c["shape"](cmd)}})
    return j({"mcpServers": {NAME: _std(cmd)}})


def _quote(a):
    return '"%s"' % a if (" " in a or "\\" in a) else a


def config_path(client, override=None):
    c = CLIENTS[client]
    return Path(override) if override else (c["path"]() if c["kind"] == "json" else None)


def _read_json(path):
    """(данные, ошибка). Нет файла — пустой объект."""
    if not path.is_file():
        return {}, None
    try:
        cfg = json.loads(path.read_text(encoding="utf-8") or "{}")
    except ValueError:
        return None, "Файл %s не является корректным JSON (комментарии и висячие запятые не поддерживаются): правьте вручную." % path
    if not isinstance(cfg, dict):
        return None, "Файл %s: ожидался JSON-объект." % path
    return cfg, None


def _write_json(path, cfg):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def installed(client):
    """Похоже ли, что клиент установлен: есть папка настроек (JSON) или команда в PATH (CLI)."""
    c = CLIENTS[client]
    if c["kind"] == "json":
        return c.get("create_dir", False) or c["path"]().parent.is_dir()
    if c["kind"] == "cli":
        return shutil.which(c["exe"]) is not None
    return False


def install(client, cmd, path=None, run=subprocess.run):
    """Подключает PhotoCrop к клиенту. Возвращает (успех, сообщение). Если автоматически нельзя, сообщение содержит готовую настройку."""
    c = CLIENTS[client]
    text = snippet(client, cmd)
    if c["kind"] == "text":
        return False, "Автоматической настройки для «%s» нет. Добавьте в %s:\n\n%s\n%s" % (c["title"], c["where"], text, c.get("restart", ""))
    if c["kind"] == "cli":
        if not shutil.which(c["exe"]):
            return False, "Команда «%s» не найдена. Установите %s или выполните вручную:\n\n%s" % (c["exe"], c["title"], text)
        try:
            r = run(c["add"](cmd), capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as ex:
            return False, "Не удалось запустить %s: %s\n\nВыполните вручную:\n\n%s" % (c["exe"], ex, text)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        if r.returncode != 0:
            return False, "%s вернул ошибку: %s\n\nМожно вручную:\n\n%s" % (c["title"], out[:400], text)
        return True, "Готово: PhotoCrop подключён к %s. %s" % (c["title"], out[:300])
    p = config_path(client, path)
    if path is None and not c.get("create_dir") and not p.parent.is_dir():
        return False, "%s не найден (нет папки %s). Установите его или добавьте вручную в %s:\n\n%s" % (c["title"], p.parent, p, text)
    cfg, err = _read_json(p)
    if err:
        return False, err + "\n\nДобавьте вручную:\n\n" + text
    servers = cfg.setdefault(c["key"], {})
    if not isinstance(servers, dict):
        return False, "Файл %s: «%s» должен быть объектом.\n\n%s" % (p, c["key"], text)
    if not p.is_file() and c.get("schema"):
        cfg = {"$schema": c["schema"], **cfg}
    servers[NAME] = c["shape"](cmd)
    if p.is_file():
        shutil.copyfile(p, p.with_name(p.name + ".bak"))
    _write_json(p, cfg)
    return True, "Готово: PhotoCrop записан в %s. %s" % (p, c.get("restart", ""))


def uninstall(client, path=None, run=subprocess.run):
    """Убирает PhotoCrop из настройки клиента (чужие серверы не трогает). Возвращает (убрано, сообщение)."""
    c = CLIENTS[client]
    if c["kind"] == "cli":
        if not c.get("remove") or not shutil.which(c["exe"]):
            return False, ""
        try:
            r = run(c["remove"]({"command": "", "args": []}), capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return False, ""
        return r.returncode == 0, ""
    if c["kind"] != "json":
        return False, ""
    p = config_path(client, path)
    cfg, err = _read_json(p)
    if err or not cfg or not isinstance(cfg.get(c["key"]), dict) or NAME not in cfg[c["key"]]:
        return False, ""
    shutil.copyfile(p, p.with_name(p.name + ".bak"))
    del cfg[c["key"]][NAME]
    _write_json(p, cfg)
    return True, "PhotoCrop убран из %s" % p
