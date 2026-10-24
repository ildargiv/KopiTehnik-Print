# -*- coding: utf-8 -*-
"""Встроенный чат-агент (ЭКСПЕРИМЕНТ, ветка experiment/embedded-agent): цикл «модель -> инструмент -> результат».

Модуль без Qt и без сети по умолчанию. Модель подключается адаптером с методом chat(messages, tools) -> {"content", "tool_calls"}.
Инструменты берутся только из белого списка (ToolGate): чего нет в списке, того для модели не существует.
Выполняет вызовы переданная функция execute(req) (в программе это GuiAgent.execute), поэтому права печати, журнал и откат общие
с внешним MCP-агентом.
"""
import json
import urllib.request

MAX_STEPS = 30

# Группы инструментов: модели отдаём только набор под текущую задачу (малой локальной модели 100 команд много).
GROUPS = {
    "prepare": ["app_state", "open_folder", "open_files", "list_photos", "photo_info", "set_format", "set_orientation", "set_layout", "set_copies", "doc_open", "doc_info", "doc_set"],
    "color": ["analyze_photo", "analyze_photos", "set_crop", "move_crop", "rotate_photo", "flip_photo", "set_adjust", "white_balance",
              "color_presets", "color_preset_apply", "copy_adjust", "paste_adjust", "compare_photo", "contact_sheet", "undo", "redo"],
    "profiles": ["list_icc_profiles", "set_color_profile", "get_color_profile", "printer_correction", "list_printers", "select_printer",
                 "driver_capabilities", "set_print_options", "get_print_options", "add_edge_test"],
    "print": ["plan_print", "render_sheet", "preflight", "print_photos", "doc_print", "print_status", "print_stats"],
    "queue": ["printer_status", "queue", "jobs", "job_status", "wait_queue", "cancel_job"],
}
CONTROL = ["ask_user"]                                           # всегда доступно

PRINT_TOOLS = {"print_photos", "doc_print", "print"}
# Запрещено всегда, даже если окажется в группе: права, ключи, обновления, очистка чужой очереди.
NEVER = {"app_settings", "clear_queue", "pause_printer", "resume_printer", "job_control", "check_update", "save_project", "load_project"}


class ToolGate:
    """Белый список + проверка папок + режим печати. policy: print_mode 'ask'|'auto'|'off', allow_print, max_sheets."""

    def __init__(self, spec, groups=None, roots=(), policy=None):
        self.spec = spec
        names = set(CONTROL)
        for g in (groups or GROUPS):
            names.update(GROUPS.get(g, ()))
        self.names = {n for n in names if n not in NEVER and (n in spec or n in CONTROL)}
        self.roots = [r for r in roots if r]
        self.policy = {"print_mode": "ask", "allow_print": True, "max_sheets": 0, **(policy or {})}

    def tools(self):
        """Описания инструментов в формате OpenAI (function calling)."""
        out = []
        for n in sorted(self.names):
            if n == "ask_user":
                out.append(_fn(n, "Ask the person a question when something is unclear instead of guessing.",
                               [("question", "string", "The question."), ("options", "array", "Optional answer choices.")], ["question"]))
                continue
            desc, params = self.spec[n]
            out.append(_fn(n, desc, params, []))
        return out

    def check(self, name, args):
        """None если можно, иначе текст отказа для модели."""
        if name not in self.names:
            return "tool '%s' is not available" % name
        if name in PRINT_TOOLS:
            if not self.policy["allow_print"] or self.policy["print_mode"] == "off":
                return "printing by the agent is disabled in settings"
        for k in ("path", "paths", "folder"):
            v = args.get(k)
            for p in ([v] if isinstance(v, str) else v if isinstance(v, list) else []):
                if isinstance(p, str) and not self.in_roots(p):
                    return "path '%s' is outside the allowed folders" % p
        return None

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
    props = {n: {"type": {"any": "string"}.get(t, t), "description": d} for n, t, d in params}
    return {"type": "function", "function": {"name": name, "description": desc,
                                              "parameters": {"type": "object", "properties": props, "required": list(required)}}}


class Agent:
    """Один диалог. confirm(text) -> bool вызывается перед печатью в режиме 'ask'; ask(question, options) -> str для ask_user."""

    def __init__(self, provider, gate, execute, system="", confirm=None, ask=None, max_steps=MAX_STEPS, log=None):
        self.provider, self.gate, self.execute = provider, gate, execute
        self.confirm, self.ask, self.max_steps, self.log = confirm, ask, max_steps, log
        self.messages = [{"role": "system", "content": system}] if system else []
        self.stopped = False
        self.printed_ok = 0

    def stop(self):
        self.stopped = True

    def say(self, text):
        """Реплика человека -> ответ агента (текст). Выполняет вызовы инструментов, пока модель их просит."""
        self.stopped = False
        self.messages.append({"role": "user", "content": text})
        tools = self.gate.tools()
        for _ in range(self.max_steps):
            if self.stopped:
                return "(stopped)"
            reply = self.provider.chat(self.messages, tools)
            calls = reply.get("tool_calls") or []
            self.messages.append({"role": "assistant", "content": reply.get("content") or "", **({"tool_calls": calls} if calls else {})})
            if not calls:
                return reply.get("content") or ""
            for c in calls:
                self.messages.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": self._run(c)})
        return "(step limit reached)"

    def _run(self, call):
        f = call.get("function") or {}
        name = f.get("name", "")
        try:
            args = json.loads(f.get("arguments") or "{}") if isinstance(f.get("arguments"), str) else dict(f.get("arguments") or {})
        except ValueError:
            return json.dumps({"ok": False, "error": "arguments must be valid JSON"})
        if not isinstance(args, dict):
            return json.dumps({"ok": False, "error": "arguments must be an object"})
        denied = self.gate.check(name, args)
        if denied:
            self._log(name, args, "denied: " + denied)
            return json.dumps({"ok": False, "error": denied})
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
        return json.dumps(res, ensure_ascii=False, default=str)[:20000]

    def _log(self, name, args, what):
        if self.log:
            self.log(name, args, what)


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
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d["choices"][0]["message"]
