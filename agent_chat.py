# -*- coding: utf-8 -*-
"""Встроенный чат-агент (ЭКСПЕРИМЕНТ, ветка experiment/embedded-agent): цикл «модель -> инструмент -> результат».

Модуль без Qt и без сети по умолчанию. Модель подключается адаптером с методом chat(messages, tools) -> {"content", "tool_calls"}.
Инструменты берутся только из белого списка (ToolGate): чего нет в списке, того для модели не существует.
Выполняет вызовы переданная функция execute(req) (в программе это GuiAgent.execute), поэтому права печати, журнал и откат общие
с внешним MCP-агентом.
"""
import json
import urllib.error
import urllib.request

MAX_STEPS = 30
RESULT_LIMIT = 3000                                              # знаков ответа инструмента, которые видит модель

# Группы инструментов: модели отдаём только набор под текущую задачу (малой локальной модели 100 команд много).
GROUPS = {
    "prepare": ["app_state", "prepare_series", "find_problem_photos", "check_photos", "select_photo", "open_folder", "open_files", "list_photos", "photo_info", "set_format", "set_orientation", "set_layout", "set_copies", "doc_open", "doc_info", "doc_set"],
    "color": ["analyze_photo", "analyze_photos", "set_crop", "move_crop", "rotate_photo", "flip_photo", "set_adjust", "white_balance",
              "color_presets", "color_preset_apply", "copy_adjust", "paste_adjust", "compare_photo", "contact_sheet", "undo", "redo"],
    "profiles": ["list_icc_profiles", "set_color_profile", "get_color_profile", "printer_correction", "list_printers", "select_printer",
                 "driver_capabilities", "set_print_options", "get_print_options", "add_edge_test"],
    "print": ["plan_print", "render_sheet", "preflight", "print_photos", "doc_print", "print_status", "print_stats"],
    "queue": ["printer_status", "queue", "jobs", "job_status", "wait_queue", "cancel_job"],
}
CONTROL = ["ask_user", "need_tools"]                             # всегда доступно

# Слова запроса -> группы инструментов (маршрутизатор: малой модели отдаём 10–25 инструментов, а не все).
ROUTES = {
    "color": ("цвет", "ярк", "контраст", "светл", "темн", "тёмн", "розов", "синев", "жёлт", "желт", "баланс", "оттен", "насыщ", "кривы", "уровн",
              "color", "bright", "contrast", "dark", "tint", "balance", "curve"),
    "profiles": ("профил", "icc", "принтер", "бумаг", "поле", "края", "драйвер", "printer", "paper", "profile", "border"),
    "print": ("печат", "распечат", "print", "лист", "sheet"),
    "queue": ("очеред", "задани", "отмен", "застр", "queue", "job", "cancel"),
}
DEFAULT_GROUPS = ("prepare",)

PRINT_TOOLS = {"print_photos", "doc_print", "print"}
# Макро-инструменты: один вызов вместо пяти (малой модели так проще). Выполняются через тот же execute, печать не запускают.
MACRO_SPEC = {
    "prepare_series": ("Open a folder of photos, set the print format and copies per photo, then run the pre-print check. Does NOT print. "
                       "Returns how many photos were opened, sheets to print, and any problems.",
                       [("folder", "string", "Folder with photos."), ("format", "string", "Print format, e.g. 10x15, A4."),
                        ("copies", "integer", "Copies of each photo (default 1).")]),
    "find_problem_photos": ("Look over the whole open series and list photos that stand out: too dark, too bright, blurry, clipped, low resolution. "
                            "Returns photo numbers with reasons. Changes nothing.", []),
}
MACROS = set(MACRO_SPEC)

# Запрещено всегда, даже если окажется в группе: права, ключи, обновления, очистка чужой очереди.
NEVER = {"app_settings", "clear_queue", "pause_printer", "resume_printer", "job_control", "check_update", "save_project", "load_project"}


class ToolGate:
    """Белый список + проверка папок + режим печати. policy: print_mode 'ask'|'auto'|'off', allow_print, max_sheets."""

    def __init__(self, spec, groups=None, roots=(), policy=None, required=None):
        self.spec = spec
        self.required = required or {}
        self.groups = []
        self.names = set()
        self.set_groups(groups if groups is not None else list(GROUPS))
        self.roots = [r for r in roots if r]
        self.policy = {"print_mode": "ask", "allow_print": True, "max_sheets": 0, **(policy or {})}

    def set_groups(self, groups):
        self.groups = [g for g in groups if g in GROUPS]
        names = set(CONTROL)
        for g in self.groups:
            names.update(GROUPS[g])
        self.names = {n for n in names if n not in NEVER and (n in self.spec or n in CONTROL or n in MACROS)}

    def add_group(self, g):
        if g in GROUPS and g not in self.groups:
            self.set_groups(self.groups + [g])
            return True
        return False

    def route(self, text):
        """Выбирает группы по словам запроса (всегда есть «prepare»)."""
        t = (text or "").lower()
        gs = list(DEFAULT_GROUPS) + [g for g, words in ROUTES.items() if any(w in t for w in words)]
        if "print" in gs and "profiles" not in gs:
            gs.append("profiles")                                 # печать без выбора принтера и профиля не обходится
        self.set_groups(gs)
        return self.groups

    def tools(self):
        """Описания инструментов в формате OpenAI (function calling)."""
        out = []
        for n in sorted(self.names):
            if n == "ask_user":
                out.append(_fn(n, "Ask the person a question when something is unclear instead of guessing.",
                               [("question", "string", "The question."), ("options", "array", "Optional answer choices.")], ["question"]))
                continue
            if n == "need_tools":
                out.append(_fn(n, "Get more tools when the ones you have are not enough. Groups: %s." % ", ".join(GROUPS),
                               [("group", "string", "Group name.")], ["group"]))
                continue
            if n in MACROS:
                desc, params = MACRO_SPEC[n]
                out.append(_fn(n, desc, params, ["folder", "format"] if n == "prepare_series" else []))
                continue
            desc, params = self.spec[n]
            out.append(_fn(n, desc, params, self.required.get(n, [])))
        return out

    def check(self, name, args):
        """None если можно, иначе текст отказа для модели."""
        if name not in self.names:
            return "tool '%s' is not available" % name
        if name in PRINT_TOOLS:
            if not self.policy["allow_print"] or self.policy["print_mode"] == "off":
                return "printing by the agent is disabled in settings"
        bad = self.path_violation(args)
        if bad:
            return "path '%s' is outside the allowed folders" % bad[0]
        return None

    def path_violation(self, args):
        """Пути из аргументов, которые лежат вне разрешённых папок."""
        out = []
        for k in ("path", "paths", "folder", "outdir", "icc", "icc_path"):
            v = args.get(k)
            for p in ([v] if isinstance(v, str) else v if isinstance(v, list) else []):
                if isinstance(p, str) and (k not in ("icc", "icc_path") or "/" in p or "\\" in p) and not self.in_roots(p):
                    out.append(p)
        return out

    def in_roots(self, path):
        import os
        if not self.roots:
            return False                                         # без разрешённых папок файлы недоступны
        p = os.path.normcase(os.path.realpath(path))
        for r in self.roots:
            r = os.path.normcase(os.path.realpath(r))
            if p == r or p.startswith(r.rstrip(os.sep) + os.sep):
                return True
        return False


def _fn(name, desc, params, required):
    props = {}
    for n, t, d in params:
        pr = {"description": d}
        if t != "any":                                           # any: тип не ограничиваем (число, строка или список)
            pr["type"] = t
        if t == "array":
            pr["items"] = {"type": "string"}
        props[n] = pr
    return {"type": "function", "function": {"name": name, "description": desc,
                                              "parameters": {"type": "object", "properties": props, "required": list(required)}}}


class Agent:
    """Один диалог. confirm(text) -> bool вызывается перед печатью в режиме 'ask'; ask(question, options) -> str для ask_user."""

    def __init__(self, provider, gate, execute, system="", confirm=None, ask=None, max_steps=MAX_STEPS, log=None, allow_path=None,
                 undo_depth=None, route=True):
        self.provider, self.gate, self.execute = provider, gate, execute
        self.confirm, self.ask, self.max_steps, self.log = confirm, ask, max_steps, log
        self.allow_path = allow_path                             # allow_path(path) -> bool: человек разрешает новую папку
        self.messages = [{"role": "system", "content": system}] if system else []
        self.stopped = False
        self.printed_ok = 0
        self.undo_depth, self.undo_base = undo_depth, None      # undo_depth() -> число шагов отмены окна: по ним откатываем действия агента
        self.route = route

    def stop(self):
        self.stopped = True

    def say(self, text):
        """Реплика человека -> ответ агента (текст). Выполняет вызовы инструментов, пока модель их просит."""
        self.stopped = False
        if self.undo_base is None and self.undo_depth:
            self.undo_base = self.undo_depth()
        if self.route:
            self.gate.route(text)
        self.messages.append({"role": "user", "content": text})
        recent = []
        for _ in range(self.max_steps):
            if self.stopped:
                return "(stopped)"
            self._compact()
            reply = self.provider.chat(self.messages, self.gate.tools())
            calls = reply.get("tool_calls") or []
            if not calls:
                calls = parse_text_calls(reply.get("content") or "")       # Qwen часто пишет вызов в текст
                if calls:
                    reply = {**reply, "content": ""}
            self.messages.append({"role": "assistant", "content": reply.get("content") or "", **({"tool_calls": calls} if calls else {})})
            if not calls:
                return reply.get("content") or ""
            for c in calls:
                key = json.dumps(c.get("function"), sort_keys=True, default=str)
                recent.append(key)
                if len(recent) >= 3 and recent[-1] == recent[-2] == recent[-3]:
                    return "(the agent repeated the same step three times and was stopped; please rephrase the task)"
                self.messages.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": self._run(c)})
        return "(step limit reached)"

    def _compact(self, keep=4, limit=300):
        """Старые ответы инструментов сжимаем до первых символов: малой модели хватает окна на вчерашние разговоры."""
        tools = [m for m in self.messages if m.get("role") == "tool"]
        for m in tools[:-keep]:
            if len(m["content"]) > limit:
                m["content"] = m["content"][:limit] + "…"

    def rollback(self):
        """Откатывает всё, что агент изменил в окне с начала диалога (шаги Ctrl+Z). Возвращает число шагов."""
        if not self.undo_depth or self.undo_base is None:
            return 0
        n = self.undo_depth() - self.undo_base
        if n > 0:
            self.execute({"cmd": "undo", "steps": n})
        self.undo_base = self.undo_depth()
        return max(n, 0)

    def _run(self, call):
        f = call.get("function") or {}
        name = f.get("name", "")
        try:
            args = json.loads(f.get("arguments") or "{}") if isinstance(f.get("arguments"), str) else dict(f.get("arguments") or {})
        except ValueError:
            return json.dumps({"ok": False, "error": "arguments must be valid JSON"})
        if not isinstance(args, dict):
            return json.dumps({"ok": False, "error": "arguments must be an object"})
        if self.allow_path and name in self.gate.names:
            for p in self.gate.path_violation(args):
                if self.allow_path(p):
                    import os
                    self.gate.roots.append(p if os.path.isdir(p) else os.path.dirname(p))
        denied = self.gate.check(name, args)
        if denied:
            self._log(name, args, "denied: " + denied)
            return json.dumps({"ok": False, "error": denied})
        if name in MACROS:
            self._log(name, args, "run")
            return json.dumps(_slim(self._macro(name, args)), ensure_ascii=False, default=str)[:RESULT_LIMIT]
        if name == "need_tools":
            ok = self.gate.add_group(str(args.get("group", "")))
            return json.dumps({"ok": ok, "groups": self.gate.groups} if ok else {"ok": False, "error": "unknown or already added group"})
        if name == "ask_user":
            ans = self.ask(args.get("question", ""), args.get("options")) if self.ask else ""
            return json.dumps({"ok": True, "answer": ans}, ensure_ascii=False)
        if name in PRINT_TOOLS and self.gate.policy["print_mode"] == "ask":
            if not (self.confirm and self.confirm("%s %s" % (name, json.dumps(args, ensure_ascii=False)))):
                self._log(name, args, "declined by person")
                return json.dumps({"ok": False, "error": "the person declined printing"})
            self.printed_ok += 1
        self._log(name, args, "run")
        try:
            res = self.execute({"cmd": name, **args})
        except Exception as ex:                                  # noqa: BLE001
            res = {"ok": False, "error": "%s: %s" % (ex.__class__.__name__, ex)}
        return json.dumps(_slim(res), ensure_ascii=False, default=str)[:RESULT_LIMIT]

    def _call(self, cmd, **args):
        """Вложенная команда макроса: тот же execute, результат или ошибка текстом."""
        out = self.execute({"cmd": cmd, **args})
        if isinstance(out, dict) and out.get("ok") is False:
            raise RuntimeError("%s: %s" % (cmd, (out.get("error") or {}).get("message", out)))
        return (out or {}).get("result", out) if isinstance(out, dict) else out

    def _macro(self, name, args):
        try:
            if name == "prepare_series":
                opened = self._call("open_folder", path=args["folder"])
                self._call("set_format", format=args["format"])
                copies = int(args.get("copies") or 1)
                if copies != 1:
                    self._call("set_copies", photo="all", copies=copies)
                pre = self._call("preflight")
                checks = [c for c in pre.get("checks", []) if c.get("level") in ("error", "warning")]
                return {"ok": True, "opened": opened.get("photo_count", opened.get("count")), "format": args["format"], "copies": copies,
                        "sheets_to_print": pre.get("sheets_to_print"), "ready": pre.get("ready"), "problems": checks[:10]}
            ph = self._call("analyze_photos", photo="all").get("photos", [])
            pre = self._call("preflight")
            return {"ok": True, "checked": len(ph), "problem_photos": find_outliers(ph),
                    "print_warnings": [c for c in pre.get("checks", []) if c.get("level") in ("error", "warning")][:10]}
        except (RuntimeError, KeyError, ValueError) as ex:
            return {"ok": False, "error": str(ex)}

    def _log(self, name, args, what):
        if self.log:
            self.log(name, args, what)


def find_outliers(photos, dark=60, bright=205, clip_pct=8.0, blur_ratio=0.5):
    """Кадры серии, которые выбиваются: тёмные, светлые, с клиппингом, нерезкие (по analyze_photos). Пороги эвристические."""
    import statistics
    sharp = [p.get("sharpness") for p in photos if isinstance(p.get("sharpness"), (int, float))]
    med = statistics.median(sharp) if sharp else 0
    out = []
    for p in photos:
        why = []
        luma = p.get("mean_luma")
        if isinstance(luma, (int, float)):
            if luma < dark:
                why.append("dark")
            elif luma > bright:
                why.append("bright")
        if (p.get("shadow_clip_pct") or 0) > clip_pct:
            why.append("shadows clipped")
        if (p.get("highlight_clip_pct") or 0) > clip_pct:
            why.append("highlights clipped")
        if med and isinstance(p.get("sharpness"), (int, float)) and p["sharpness"] < med * blur_ratio:
            why.append("blurry compared with the series")
        if why:
            out.append({"index": p.get("index"), "name": p.get("name"), "why": why})
    return out


def _slim(o):
    """Убирает из ответа картинки в base64 (модель их текстом не прочитает, а окно переполнится)."""
    if isinstance(o, dict):
        return {k: ("<image omitted>" if "image" in str(k).lower() and "b64" in str(k).lower() else _slim(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [_slim(v) for v in o]
    return o


_TEXT_CALL = None


def parse_text_calls(content):
    """Вызовы инструментов, которые модель написала в тексте: <tool_call>{"name":…, "arguments":{…}}</tool_call>."""
    import re
    global _TEXT_CALL
    if _TEXT_CALL is None:
        _TEXT_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
    out = []
    for i, m in enumerate(_TEXT_CALL.finditer(content or "")):
        try:
            d = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(d, dict) and isinstance(d.get("name"), str):
            args = d.get("arguments", d.get("parameters", {}))
            out.append({"id": "t%d" % i, "type": "function",
                        "function": {"name": d["name"], "arguments": args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)}})
    return out


class OpenAICompatible:
    """Провайдер для любого OpenAI-совместимого адреса (локальные llama.cpp/Ollama/vLLM, облако). Без ключа заголовок не шлётся."""

    def __init__(self, base_url, model="", api_key="", timeout=300):
        self.base_url, self.model, self.api_key, self.timeout = base_url.rstrip("/"), model, api_key, timeout

    def chat(self, messages, tools):
        body = {"model": self.model, "messages": messages, "temperature": 0.2}
        if tools:
            body["tools"] = tools
        hdr = {"Content-Type": "application/json"}
        if self.api_key:
            hdr["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(body).encode("utf-8"), headers=hdr, method="POST")
        # Модель обычно в своей сети (имя без точек или частный адрес): системный прокси для неё не нужен и часто рвёт соединение.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if _is_local(self.base_url) else urllib.request.build_opener()
        try:
            with opener.open(req, timeout=self.timeout) as r:
                d = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as ex:
            raise RuntimeError("model server answered HTTP %d: %s" % (ex.code, ex.read().decode("utf-8", "replace")[:500])) from None
        try:
            return d["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("unexpected model reply: %s" % json.dumps(d, ensure_ascii=False)[:500]) from None


def _is_local(url):
    import ipaddress
    import urllib.parse
    host = urllib.parse.urlparse(url).hostname or ""
    if "." not in host:
        return True                                              # localhost, имя из локальной сети
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return host.endswith((".local", ".lan", ".home", ".internal"))
