# -*- coding: utf-8 -*-
"""Связь ИИ-агента с окном программы: адрес сервера в окне, HTTP-сервер (только этот компьютер) и мост «stdio ↔ окно».

Окно PhotoCropQt поднимает сервер и пишет адрес с ключом в agent_endpoint.json. Клиент MCP (например Claude Desktop) запускает
`PhotoCropQt.exe mcp`: он читает этот файл и пересылает запросы в окно, поэтому агент работает с теми же фото, что видит человек.
Если окна нет, тот же `mcp` работает сам по себе, без окна (см. photo_crop.agent_main).
Модуль без Qt: его импортирует и консольный режим.
"""
import json
import app_dirs
import os
import secrets
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ENDPOINT_NAME = "agent_endpoint.json"
MAX_BODY = 64 * 1024 * 1024


def settings_dir():
    return app_dirs.data_dir()


def endpoint_path():
    return settings_dir() / ENDPOINT_NAME


def read_endpoint():
    """{'port', 'token', 'pid'} или None."""
    try:
        d = json.loads(endpoint_path().read_text(encoding="utf-8"))
        return d if isinstance(d.get("port"), int) and d.get("token") else None
    except (OSError, ValueError):
        return None


def new_token():
    return secrets.token_hex(24)


# ---------------------------------------------------------------- сервер в окне

class AgentHttpServer:
    """POST /mcp с телом JSON-RPC (один запрос или массив) -> JSON. Только 127.0.0.1, заголовок Authorization: Bearer <ключ>.
    handle(msg) -> ответ (dict) или None для уведомлений; вызывается из рабочих потоков сервера."""

    def __init__(self, handle, token, port=0):
        self.handle, self.token, self.want_port = handle, token, port
        self.httpd = None
        self.thread = None
        self.port = 0
        self.on_request = None                                   # вызывается при каждом запросе (индикатор «агент работает»)

    def start(self):
        server = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code, body=b"", ctype="application/json; charset=utf-8"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def _auth(self):
                host = (self.headers.get("Host") or "").split(":")[0].lower()
                if host not in ("127.0.0.1", "localhost", "[::1]"):
                    return False                                 # защита от DNS rebinding
                if self.headers.get("Origin"):
                    return False                                 # запросы со страниц браузера не пускаем
                got = (self.headers.get("Authorization") or "").strip()
                return secrets.compare_digest(got, "Bearer " + server.token)

            def do_GET(self):
                self._send(405, b'{"error":"use POST"}')

            def do_POST(self):
                if self.path.split("?")[0] != "/mcp":
                    return self._send(404, b'{"error":"not found"}')
                if not self._auth():
                    return self._send(401, b'{"error":"unauthorized"}')
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > MAX_BODY:
                        return self._send(413, b'{"error":"too large"}')
                    msg = json.loads(self.rfile.read(n).decode("utf-8"))
                except (ValueError, OSError):
                    return self._send(400, b'{"jsonrpc":"2.0","id":null,"error":{"code":-32700,"message":"Parse error"}}')
                if server.on_request:
                    try:
                        server.on_request()
                    except Exception:
                        pass
                if isinstance(msg, list):
                    rs = [r for r in (server.handle(m) for m in msg if isinstance(m, dict)) if r is not None]
                    out = rs if rs else None
                elif isinstance(msg, dict):
                    out = server.handle(msg)
                else:
                    out = {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
                if out is None:
                    return self._send(202)
                self._send(200, json.dumps(out, ensure_ascii=False, default=str).encode("utf-8"))

        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.want_port), H)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="photocrop-agent", daemon=True)
        self.thread.start()
        self.write_endpoint()
        return self.port

    def write_endpoint(self):
        p = endpoint_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({"port": self.port, "token": self.token, "pid": os.getpid()}), encoding="utf-8")
        os.replace(tmp, p)
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        ep = read_endpoint()
        if ep and ep.get("pid") == os.getpid():
            try:
                endpoint_path().unlink()
            except OSError:
                pass


# ---------------------------------------------------------------- клиент: запрос в окно

def post(ep, msg, timeout=900):
    """Отправляет JSON-RPC в окно. Возвращает ответ (dict/list) или None (ответа нет, 202). Исключение — окно недоступно."""
    req = urllib.request.Request("http://127.0.0.1:%d/mcp" % ep["port"], data=json.dumps(msg).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + ep["token"]})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))        # локальный адрес, системный прокси не нужен
    with opener.open(req, timeout=timeout) as r:
        body = r.read()
        if r.status == 202 or not body:
            return None
        return json.loads(body.decode("utf-8"))


def window_alive():
    """Есть ли запущенное окно, которое отвечает на запросы."""
    ep = read_endpoint()
    if not ep:
        return None
    try:
        r = post(ep, {"jsonrpc": "2.0", "id": 0, "method": "ping"}, timeout=5)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return ep if isinstance(r, dict) and "result" in r else None


# ---------------------------------------------------------------- stdio в оконном exe

def open_stdio():
    """В exe без консоли (PyInstaller, windowed) sys.stdin/stdout равны None, хотя клиент передал каналы при запуске. Открываем их
    по дескрипторам Windows. Возвращает (stdin, stdout) в UTF-8."""
    stdin, stdout = sys.stdin, sys.stdout
    if (stdin is None or stdout is None) and sys.platform == "win32":
        try:
            import ctypes
            import msvcrt
            k32 = ctypes.windll.kernel32
            k32.GetStdHandle.restype = ctypes.c_void_p
            h_in, h_out = k32.GetStdHandle(-10), k32.GetStdHandle(-11)
            if stdin is None and h_in not in (None, 0, ctypes.c_void_p(-1).value):
                stdin = os.fdopen(msvcrt.open_osfhandle(h_in, os.O_RDONLY), "r", encoding="utf-8", newline="\n")
            if stdout is None and h_out not in (None, 0, ctypes.c_void_p(-1).value):
                stdout = os.fdopen(msvcrt.open_osfhandle(h_out, os.O_WRONLY), "w", encoding="utf-8", newline="\n")
        except Exception:
            pass
    for st in (stdin, stdout):
        try:
            st.reconfigure(encoding="utf-8")
        except Exception:
            pass
    return stdin, stdout
