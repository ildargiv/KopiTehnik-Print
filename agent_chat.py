# -*- coding: utf-8 -*-
"""Встроенный чат-агент «Печатник» (бета): цикл «модель -> инструмент -> результат».

Модуль без Qt и без сети по умолчанию. Модель подключается адаптером с методом chat(messages, tools) -> {"content", "tool_calls"}.
Инструменты берутся только из белого списка (ToolGate): чего нет в списке, того для модели не существует.
Выполняет вызовы переданная функция execute(req) (в программе это GuiAgent.execute), поэтому права печати, журнал и откат общие
с внешним MCP-агентом.
"""
import json
import time
import urllib.error
import urllib.request

MAX_STEPS = 30
TURN_LIMIT = 15 * 60                                             # секунд на один ход (задание человека), потом остановка
RESULT_LIMIT = 3000                                              # знаков ответа инструмента, которые видит модель

# Группы инструментов: модели отдаём только набор под текущую задачу (малой локальной модели 100 команд много).
GROUPS = {
    "prepare": ["app_state", "prepare_series", "find_problem_photos", "check_photos", "select_photo", "open_folder", "open_files", "list_photos", "photo_info",
                "set_format", "list_formats", "set_orientation", "set_mode", "set_layout", "set_copies", "remove_unchecked", "set_app_mode",
                "doc_open", "doc_info", "doc_set", "doc_convert"],
    "color": ["preview_photo", "analyze_photo", "analyze_photos", "set_crop", "move_crop", "reset_crop", "set_view", "zoom_photo", "rotate_photo", "flip_photo", "set_adjust", "white_balance",
              "color_presets", "color_preset_apply", "copy_adjust", "paste_adjust", "compare_photo", "contact_sheet", "fix_print", "undo", "redo"],
    "profiles": ["list_icc_profiles", "set_color_profile", "get_color_profile", "printer_correction", "list_printers", "select_printer",
                 "driver_capabilities", "set_print_options", "get_print_options", "add_edge_test", "list_presets", "load_preset"],
    "print": ["plan_print", "render_sheet", "preflight", "print_photos", "doc_print", "print_status", "print_stats"],
    "save": ["set_save_options", "save_files", "export_sheets"],   # сохранить готовые файлы или листы в папку
    "auto": ["auto_crop", "auto_adjust", "auto_levels", "enhance"],          # автоматика: только по кнопкам «Улучшить», «Кадрировать» и по просьбе
    "queue": ["printer_status", "queue", "jobs", "job_status", "wait_queue", "cancel_job"],
    "admin": [],                                                 # инструменты администратора: их даёт окно (ToolGate.local), только после входа
}
CONTROL = ["ask_user", "need_tools"]                             # всегда доступно

# Слова запроса -> группы инструментов (маршрутизатор: малой модели отдаём 10–25 инструментов, а не все).
ROUTES = {
    "color": ("цвет", "ярк", "контраст", "светл", "темн", "тёмн", "розов", "синев", "жёлт", "желт", "зелен", "зелён", "баланс", "оттен", "насыщ",
              "кривы", "уровн", "отпечат", "бледн", "ч/б", "чёрно", "черно", "color", "bright", "contrast", "dark", "tint", "balance", "curve",
              "pink", "green", "yellow", "pale", "black and white", "b/w"),
    "profiles": ("профил", "icc", "принтер", "бумаг", "поле", "края", "драйвер", "printer", "paper", "profile", "border"),
    "print": ("печат", "распечат", "print", "лист", "sheet"),
    "save": ("сохран", "экспорт", "запиши", "save", "export"),
    "admin": ("кнопк", "вкладк", "интерфейс", "местами", "перестав", "шаблон", "скрой", "спрячь", "button", "tab", "interface", "template", "hide"),
    "queue": ("очеред", "задани", "отмен", "застр", "queue", "job", "cancel"),
}
DEFAULT_GROUPS = ("prepare",)

PRINT_TOOLS = {"print_photos", "doc_print", "print"}
HISTORY_LIMIT = 60                                               # сообщений диалога, которые уходят модели (старое отбрасывается)

# Параметры, которых нет в общем описании команд, но которые нужны модели: уровни, кривые, выборочный цвет (по каналам).
EXTRA_PARAMS = {
    "set_adjust": [
        ("levels", "object", "Levels per channel: keys all, r, g, b; each [black 0..254, gamma 0.1..10 (1 = none), white 1..255], "
                             "e.g. {\"all\": [8, 1.1, 245], \"b\": [0, 0.92, 255]}. Replaces earlier levels."),
        ("curves", "object", "Tone curves per channel: keys all, r, g, b; each a list of [input, output] points 0..255, "
                             "e.g. {\"all\": [[0, 0], [64, 56], [192, 200], [255, 255]]}. Replaces earlier curves."),
        ("selcol", "object", "Selective colour: keys red, yellow, green, cyan, blue, magenta; each [hue, saturation, lightness] -100..100, "
                             "e.g. {\"red\": [0, -10, 0], \"green\": [5, 10, 0]}. Replaces earlier values."),
        ("relative", "boolean", "Add the numbers to the current values instead of replacing them."),
    ],
}
_CH = ("all", "r", "g", "b")
_CH_ALIAS = {"rgb": "all", "common": "all", "master": "all", "red": "r", "green": "g", "blue": "b"}
_SEL = ("red", "yellow", "green", "cyan", "blue", "magenta")
_SEL_ALIAS = {"r": "red", "y": "yellow", "g": "green", "c": "cyan", "b": "blue", "m": "magenta"}


def channel_rows(v, neutral):
    """{"all": …, "r": …} -> четыре строки (общий, R, G, B) для движка. Готовый список не трогаем."""
    if not isinstance(v, dict):
        return v
    d = {_CH_ALIAS.get(str(k).lower(), str(k).lower()): x for k, x in v.items()}
    bad = [k for k in d if k not in _CH]
    if bad:
        raise ValueError("unknown channel '%s'; use all, r, g, b" % bad[0])
    return [d.get(c, neutral) for c in _CH]


def selcol_rows(v):
    if not isinstance(v, dict):
        return v
    d = {_SEL_ALIAS.get(str(k).lower(), str(k).lower()): x for k, x in v.items()}
    bad = [k for k in d if k not in _SEL]
    if bad:
        raise ValueError("unknown colour '%s'; use %s" % (bad[0], ", ".join(_SEL)))
    return [d.get(c, [0, 0, 0]) for c in _SEL]


def friendly_args(name, args):
    """Удобную для модели запись (по именам каналов) переводит в формат движка."""
    if name == "set_adjust":
        if "levels" in args:
            rows = channel_rows(args["levels"], [0, 1, 255])
            args["levels"] = [list(r)[:3] + [0, 255] if isinstance(r, (list, tuple)) and len(r) == 3 else r for r in rows] if isinstance(rows, list) else rows
        if "curves" in args:
            args["curves"] = channel_rows(args["curves"], [[0, 0], [255, 255]])
        if "selcol" in args:
            args["selcol"] = selcol_rows(args["selcol"])
    return args
# Макро-инструменты: один вызов вместо пяти (малой модели так проще). Выполняются через тот же execute, печать не запускают.
MACRO_SPEC = {
    "prepare_series": ("Open a folder of photos, set the print format and copies per photo, then run the pre-print check. Does NOT print. "
                       "Returns how many photos were opened, sheets to print, and any problems.",
                       [("folder", "string", "Folder with photos."), ("format", "string", "Print format, e.g. 10x15, A4."),
                        ("copies", "integer", "Copies of each photo (default 1).")]),
    "fix_print": ("Correct the PRINT (not the screen) after the person complains about a printed photo: too pink, too green, too yellow, "
                  "too blue, too dark, too light, too pale, too vivid; also a colour tint in black-and-white prints. Adjusts the printer correction for "
                  "the current printer and paper in a small fixed step and switches it on. Pass the complaint in the person's words.",
                  [("problem", "string", "The complaint, e.g. 'розовит', 'темнее экрана', 'too green'."),
                   ("strength", "string", "slight | normal | strong (default normal).")]),
    "find_problem_photos": ("Look over the whole open series and list photos that stand out: too dark, too bright, blurry, clipped, low resolution. "
                            "Returns photo numbers with reasons. Changes nothing.", []),
}
MACROS = set(MACRO_SPEC)

# Запрещено всегда, даже если окажется в группе: права, ключи, обновления, очистка чужой очереди.
NEVER = {"app_settings", "clear_queue", "pause_printer", "resume_printer", "job_control", "check_update", "save_project", "load_project"}


# Жалобы на отпечаток -> поправка принтера (printer_correction). Знак: tone = [тёплый(+)/холодный(-), пурпур(+)/зелень(-)].
COMPLAINTS = (
    (("розов", "пурпур", "малинов", "магент", "pink", "magenta", "purple"), "tone", (0, -1)),
    (("зелен", "зелён", "green"), "tone", (0, 1)),
    (("желт", "жёлт", "оранж", "yellow", "orange"), "tone", (-1, 0)),
    (("синев", "сини", "синий", "голуб", "blue", "cyan"), "tone", (1, 0)),
    (("темн", "тёмн", "dark"), "gamma", 1),
    (("светл", "засвеч", "белес", "белёс", "light", "washed"), "gamma", -1),
    (("бледн", "тускл", "блекл", "блёкл", "pale", "dull"), "sat", 1),
    (("кислотн", "пересыщ", "слишком ярк", "vivid", "garish", "oversaturated"), "sat", -1),
)
STEPS = {"slight": 5, "normal": 10, "strong": 20}
# «сделай темнее» — это просьба, а не жалоба: направление обратное («темнее экрана» — жалоба)
_WISH = ("сделай", "сделать", "надо", "нужно", "хочу", "make it", "want", "should be")
_VS_SCREEN = ("экран", "чем", "screen", "than")


def parse_complaint(text):
    """Что поправить по жалобе на отпечаток: список (вид, направление). Пустой список — жалобу не поняли."""
    t = (text or "").lower()
    flip = -1 if any(w in t for w in _WISH) and not any(w in t for w in _VS_SCREEN) else 1
    out, kinds = [], set()
    for words, kind, sign in COMPLAINTS:
        axis = kind if kind != "tone" else ("tone0" if sign[0] else "tone1")
        if axis in kinds or not any(w in t for w in words):
            continue
        kinds.add(axis)
        out.append((kind, tuple(flip * x for x in sign) if kind == "tone" else flip * sign))
    return out


class ToolGate:
    """Белый список + проверка папок + режим печати. policy: print_mode 'ask'|'auto'|'off', allow_print, max_sheets."""

    def __init__(self, spec, groups=None, roots=(), policy=None, required=None, local=None, admin=False):
        self.spec = spec
        self.local = dict(local or {})                            # инструменты окна: {имя: (описание, параметры, обязательные, функция)}
        self.admin = bool(admin)                                  # вошёл администратор: доступна группа «admin»
        self.required = required or {}
        self.groups = []
        self.names = set()
        self.block_print = False                                  # на время «Подготовить к печати»: печатать нельзя
        self.set_groups(groups if groups is not None else list(GROUPS))
        self.roots = [r for r in roots if r]
        self.policy = {"print_mode": "ask", "allow_print": True, "max_sheets": 0, **(policy or {})}

    def set_groups(self, groups):
        self.groups = [g for g in groups if g in GROUPS and (g != "admin" or (self.admin and self.local))]
        names = set(CONTROL)
        for g in self.groups:
            names.update(self.local if g == "admin" else GROUPS[g])
        self.names = {n for n in names if n not in NEVER and (n in self.spec or n in CONTROL or n in MACROS or n in self.local)}
        if self.block_print:
            self.names -= PRINT_TOOLS

    def add_group(self, g):
        if g in GROUPS and g not in self.groups:
            self.set_groups(self.groups + [g])
            return g in self.groups
        return False

    def group_names(self):
        return [g for g in GROUPS if g != "admin" or (self.admin and self.local)]

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
                out.append(_fn(n, "Get more tools when the ones you have are not enough. Groups: %s." % ", ".join(self.group_names()),
                               [("group", "string", "Group name.")], ["group"]))
                continue
            if n in MACROS:
                desc, params = MACRO_SPEC[n]
                out.append(_fn(n, desc, params, ["folder", "format"] if n == "prepare_series" else []))
                continue
            if n in self.local:
                desc, params, req = self.local[n][:3]
                out.append(_fn(n, desc, params, req))
                continue
            desc, params = self.spec[n]
            have = {p[0] for p in params}
            params = list(params) + [p for p in EXTRA_PARAMS.get(n, []) if p[0] not in have]
            out.append(_fn(n, desc, params, self.required.get(n, [])))
        return out

    def check(self, name, args):
        """None если можно, иначе текст отказа для модели."""
        if name not in self.names:
            return "tool '%s' is not available" % name
        if name in PRINT_TOOLS:
            if self.block_print:
                return "printing is not part of this task"
            if not self.policy["allow_print"]:
                return ("trial mode is on, so nothing is printed; tell the person to switch off 'Trial mode: do not print' "
                        "in Settings -> AI agent if they want real printing")
            if self.policy["print_mode"] == "off":
                return "printing by the agent is disabled in settings"
        bad = self.path_violation(args)
        if bad:
            return "path '%s' is outside the allowed folders" % bad[0]
        return None

    def path_violation(self, args):
        """Пути из аргументов, которые лежат вне разрешённых папок."""
        out = []
        for k in ("path", "paths", "folder", "outdir", "dir", "file", "files", "icc", "icc_path"):
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
                 undo_depth=None, route=True, vision=False):
        self.provider, self.gate, self.execute = provider, gate, execute
        self.confirm, self.ask, self.max_steps, self.log = confirm, ask, max_steps, log
        self.allow_path = allow_path                             # allow_path(path) -> bool: человек разрешает новую папку
        self.messages = [{"role": "system", "content": system}] if system else []
        self.stopped = False
        self.printed_ok = 0
        self.undo_depth, self.undo_base = undo_depth, None      # undo_depth() -> число шагов отмены окна: по ним откатываем действия агента
        self.route = route
        self.vision = vision                                     # модель видит картинки: превью из ответов инструментов уходят ей изображением
        self.pending_images = []
        self.user_text = ""                                      # всё, что человек написал в этом диалоге: отсюда «свои» пути
        self.turn_limit = TURN_LIMIT
        self.call_seq = 0
        self.asked_paths = 0

    def stop(self):
        """Останавливает диалог сразу: обрывает ожидание ответа модели (если провайдер умеет) и не даёт выполнить следующий шаг."""
        self.stopped = True
        cancel = getattr(self.provider, "cancel", None)
        if cancel:
            cancel()

    def say(self, text, groups=None, block_print=False):
        """Реплика человека -> ответ агента (текст). Выполняет вызовы инструментов, пока модель их просит.
        groups: набор инструментов для быстрой кнопки вместо маршрутизатора; block_print: запретить печать на этот запрос."""
        self.stopped = False
        self.gate.block_print = block_print
        if self.undo_base is None and self.undo_depth:
            self.undo_base = self.undo_depth()
        if groups:
            self.gate.set_groups(groups)
        elif self.route:
            self.gate.route(text)
        else:
            self.gate.set_groups(self.gate.groups)                   # применить block_print
        self.user_text += "\n" + (text or "")
        self.messages.append({"role": "user", "content": text})
        recent = []
        self.asked_paths = 0                                     # «Разрешить папку?» — не больше одного вопроса за ход
        deadline = time.monotonic() + self.turn_limit
        for _ in range(self.max_steps):
            if self.stopped:
                return "(stopped)"
            if time.monotonic() > deadline:
                return "(the task took too long and was stopped; please split it into smaller steps)"
            self._compact()
            try:
                reply = self.provider.chat(self.messages, self.gate.tools())
            except Cancelled:
                return "(stopped)"
            calls = reply.get("tool_calls") or []
            if not calls:
                calls = parse_text_calls(reply.get("content") or "")       # Qwen часто пишет вызов в текст
                if calls:
                    reply = {**reply, "content": ""}
            for c in calls:                                      # строгие серверы требуют id у каждого вызова и ответ на каждый
                if not c.get("id"):
                    self.call_seq += 1
                    c["id"] = "call_%d" % self.call_seq
            self.messages.append({"role": "assistant", "content": reply.get("content") or "", **({"tool_calls": calls} if calls else {})})
            if not calls:
                return strip_think(reply.get("content") or "")
            for i, c in enumerate(calls):
                why = None
                if self.stopped:
                    why = "(stopped)"
                else:
                    key = json.dumps(c.get("function"), sort_keys=True, default=str)
                    recent.append(key)
                    if (len(recent) >= 3 and recent[-1] == recent[-2] == recent[-3]) or recent.count(key) >= 4:
                        why = "(the agent kept repeating the same steps and was stopped; please rephrase the task)"
                if why:
                    for rest in calls[i:]:                       # закрываем все вызовы пачки, иначе следующий запрос получит ошибку 400
                        self.messages.append({"role": "tool", "tool_call_id": rest["id"], "content": json.dumps({"ok": False, "error": "not run: " + why})})
                    self.pending_images = []
                    return why
                self.messages.append({"role": "tool", "tool_call_id": c["id"], "content": self._run(c)})
            for name, b64 in self.pending_images:                # картинки отдельным сообщением: в ответе инструмента их не везде принимают
                self.messages.append({"role": "user", "content": [
                    {"type": "text", "text": "Picture returned by %s. Look at it to decide." % name},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}]})
            self.pending_images = []
        return "(step limit reached)"

    def user_gave(self, path):
        """Путь (или папка, в которой он лежит), который человек написал в чате: возвращает написанный путь, иначе None.
        Корень диска («C:\\», «/») не считается."""
        import os
        import re
        norm = lambda x: x.replace("/", "\\").rstrip("\\").casefold()
        said = norm(self.user_text)
        p = os.path.abspath(path)
        while True:
            n = norm(p)
            # путь должен стоять в сообщении целиком (за ним пробел, кавычка, знак или конец), а не быть началом другого пути
            if len(n) > 3 and re.search(re.escape(n) + r"\\?(?=$|[\s\"'»,;.)\]])", said):
                return p
            up = os.path.dirname(p)
            if up == p:
                return None
            p = up

    def _compact(self, keep=4, limit=300):
        """Старые ответы инструментов сжимаем до первых символов: малой модели хватает окна на вчерашние разговоры."""
        tools = [m for m in self.messages if m.get("role") == "tool"]
        for m in tools[:-keep]:
            if len(m["content"]) > limit:
                m["content"] = m["content"][:limit] + "…"
        if len(self.messages) > HISTORY_LIMIT:                   # длинный диалог: старое отбрасываем по границе реплики человека
            head = self.messages[:1] if self.messages[0].get("role") == "system" else []
            cut = len(self.messages) - HISTORY_LIMIT
            while cut < len(self.messages) and not (self.messages[cut].get("role") == "user" and isinstance(self.messages[cut].get("content"), str)):
                cut += 1
            if cut < len(self.messages):
                self.messages = head + self.messages[cut:]
        pics = [m for m in self.messages if isinstance(m.get("content"), list)]
        for m in pics[:-2]:                                      # в истории держим только две последние картинки
            m["content"] = "(earlier picture removed)"

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
        if name in self.gate.names:
            import os
            for p in self.gate.path_violation(args):
                # путь, который человек сам написал в чате (или то, что внутри него), разрешаем без вопроса, на этот диалог.
                # Разрешается ровно написанное: файл — только этот файл, папка — эта папка, но не соседние.
                given = self.user_gave(p)
                if given:
                    self.gate.roots.append(given)
                elif self.allow_path and self.asked_paths < 1:
                    self.asked_paths += 1
                    if self.allow_path(p):
                        self.gate.roots.append(p)
        denied = self.gate.check(name, args)
        if denied:
            self._log(name, args, "denied: " + denied)
            return json.dumps({"ok": False, "error": denied})
        if name in self.gate.local:
            self._log(name, args, "run")
            try:
                res = self.gate.local[name][3](args)
            except Exception as ex:                              # noqa: BLE001: текст ошибки нужен модели
                res = {"ok": False, "error": str(ex)}
            return json.dumps(res, ensure_ascii=False, default=str)[:RESULT_LIMIT]
        try:
            args = friendly_args(name, args)
        except ValueError as ex:
            return json.dumps({"ok": False, "error": str(ex)})
        if name in MACROS:
            self._log(name, args, "run")
            return json.dumps(_slim(self._macro(name, args)), ensure_ascii=False, default=str)[:RESULT_LIMIT]
        if name == "need_tools":
            ok = self.gate.add_group(str(args.get("group", "")))
            return json.dumps({"ok": ok, "groups": self.gate.groups} if ok else {"ok": False, "error": "unknown or already added group"})
        if name == "ask_user":
            ans = self.ask(args.get("question", ""), args.get("options")) if self.ask else ""
            return json.dumps({"ok": True, "answer": ans}, ensure_ascii=False)
        if name == "print_photos":                               # проверка перед печатью обязательна в любом режиме, до вопроса человеку
            bad = self._preflight_problems()
            if bad:
                self._log(name, args, "refused: preflight")
                return json.dumps({"ok": False, "error": "pre-print check found errors; fix them or tell the person", "problems": bad},
                                  ensure_ascii=False, default=str)[:RESULT_LIMIT]
        if name in PRINT_TOOLS and self.gate.policy["print_mode"] == "ask":
            if not (self.confirm and self.confirm("%s %s" % (name, json.dumps(args, ensure_ascii=False)))):
                self._log(name, args, "declined by person")
                return json.dumps({"ok": False, "error": "the person declined printing"})
            self.printed_ok += 1
        limit = int(self.gate.policy.get("max_sheets") or 0)
        if name == "print_photos" and limit > 0:                 # лимит листов из настроек агента: модель его не поднимет
            try:
                asked = int(args.get("max_sheets") or limit)
            except (TypeError, ValueError):
                asked = limit
            args["max_sheets"] = min(asked, limit)
        self._log(name, args, "run")
        try:
            res = self.execute({"cmd": name, **args})
        except Exception as ex:                                  # noqa: BLE001
            res = {"ok": False, "error": "%s: %s" % (ex.__class__.__name__, ex)}
        if self.vision:
            b64 = _take_image(res)
            if b64:
                self.pending_images.append((name, b64))
        return json.dumps(_slim(res), ensure_ascii=False, default=str)[:RESULT_LIMIT]

    def _preflight_problems(self):
        """Ошибки проверки перед печатью (preflight). Пустой список — можно печатать."""
        try:
            out = self.execute({"cmd": "preflight"})
        except Exception as ex:                                  # noqa: BLE001
            return ["preflight failed: %s" % ex]
        if not isinstance(out, dict):
            return []
        if out.get("ok") is False:
            return [out.get("error")]
        pre = out.get("result", out)
        errs = [c for c in pre.get("checks", []) if isinstance(c, dict) and c.get("level") == "error"]
        if errs or pre.get("ready") is False:
            return errs[:10] or ["not ready to print"]
        return []

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
            if name == "fix_print":
                return self._fix_print(args)
            ph = self._call("analyze_photos", photo="all").get("photos", [])
            pre = self._call("preflight")
            return {"ok": True, "checked": len(ph), "problem_photos": find_outliers(ph),
                    "print_warnings": [c for c in pre.get("checks", []) if c.get("level") in ("error", "warning")][:10]}
        except (RuntimeError, KeyError, ValueError) as ex:
            return {"ok": False, "error": str(ex)}

    def _fix_print(self, args):
        todo = parse_complaint(args.get("problem", ""))
        if not todo:
            return {"ok": False, "error": "could not understand the complaint; ask the person what exactly is wrong with the print "
                                          "(pinker, greener, yellower, bluer, darker, lighter, paler or more vivid than the screen)"}
        step = STEPS.get(str(args.get("strength") or "normal").lower(), 10)
        cur = self._call("printer_correction").get("printer_correction", {})
        tone = {z: list(v) for z, v in (cur.get("tone") or {}).items()} or {z: [0, 0] for z in ("shadows", "mids", "lights")}
        new = {"on": True}
        clamp = lambda v: max(-100, min(100, v))
        changed = []
        for kind, sign in todo:
            if kind == "tone":
                for z in tone:
                    tone[z] = [clamp(tone[z][0] + sign[0] * step), clamp(tone[z][1] + sign[1] * step)]
                new["tone"] = tone
            else:
                new[kind] = clamp((cur.get(kind) or 0) + sign * step)
            changed.append(kind)
        res = self._call("printer_correction", **new)
        return {"ok": True, "changed": changed, "step": step, "before": {k: cur.get(k) for k in ("tone", "gamma", "sat", "on")},
                "now": res.get("printer_correction"), "for": res.get("for"),
                "next": "tell the person what changed and suggest printing one photo again to check; the correction is kept for this printer and paper"}

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


def _take_image(res):
    """Достаёт картинку (_image_b64) из ответа команды: {"result": {..., "_image_b64": …}} или сам результат."""
    if not isinstance(res, dict):
        return None
    inner = res.get("result") if isinstance(res.get("result"), dict) else res
    v = inner.pop("_image_b64", None)
    return v if isinstance(v, str) and v else None


def _slim(o):
    """Убирает из ответа картинки в base64 (модель их текстом не прочитает, а окно переполнится)."""
    if isinstance(o, dict):
        return {k: ("<image omitted>" if "image" in str(k).lower() and "b64" in str(k).lower() else _slim(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [_slim(v) for v in o]
    return o


_TEXT_CALL = None
_THINK = None


def strip_think(text):
    """Убирает рассуждения модели (<think>…</think>) из ответа человеку."""
    import re
    global _THINK
    if _THINK is None:
        _THINK = re.compile(r"<think>.*?(</think>|$)", re.S)
    return _THINK.sub("", text or "").strip()


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


class Cancelled(Exception):
    """Запрос к модели прерван кнопкой «Стоп»."""


class OpenAICompatible:
    """Провайдер для любого OpenAI-совместимого адреса (локальные llama.cpp/Ollama/vLLM, облако). Без ключа заголовок не шлётся."""

    def __init__(self, base_url, model="", api_key="", timeout=300):
        import threading
        self.base_url, self.model, self.api_key, self.timeout = base_url.rstrip("/"), model, api_key, timeout
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def chat(self, messages, tools):
        """Запрос идёт в отдельном потоке: «Стоп» не ждёт, пока модель допишет ответ (поток доработает и его ответ выбросится)."""
        import threading
        self._cancel.clear()
        box = {}

        def run():
            try:
                box["ok"] = self._chat(messages, tools)
            except BaseException as ex:                          # noqa: BLE001: передаём в вызывающий поток
                box["err"] = ex
        t = threading.Thread(target=run, daemon=True)
        t.start()
        while t.is_alive():
            if self._cancel.wait(0.1):
                raise Cancelled()
        if "err" in box:
            raise box["err"]
        return box["ok"]

    def ping(self):
        """Проверка связи: список моделей (/models) или короткий ответ. Возвращает текст для человека, ошибки — исключением."""
        try:
            req = urllib.request.Request(self.base_url + "/models", headers={"Authorization": "Bearer " + self.api_key} if self.api_key else {})
            with self._opener().open(req, timeout=15) as r:
                d = json.loads(r.read().decode("utf-8"))
            names = [m.get("id") for m in d.get("data", []) if isinstance(m, dict)]
            if names:
                return names
        except (urllib.error.URLError, ValueError, OSError):
            pass
        self._chat([{"role": "user", "content": "ping"}], [])
        return []

    def _opener(self):
        # Модель обычно в своей сети (имя без точек или частный адрес): системный прокси для неё не нужен и часто рвёт соединение.
        return urllib.request.build_opener(urllib.request.ProxyHandler({})) if _is_local(self.base_url) else urllib.request.build_opener()

    def _chat(self, messages, tools):
        body = {"model": self.model, "messages": messages, "temperature": 0.2}
        if tools:
            body["tools"] = tools
        hdr = {"Content-Type": "application/json"}
        if self.api_key:
            hdr["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(body).encode("utf-8"), headers=hdr, method="POST")
        try:
            with self._opener().open(req, timeout=self.timeout) as r:
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
        return not ip.is_global                                   # частные, loopback и Tailscale (100.64.0.0/10)
    except ValueError:
        return host.endswith((".local", ".lan", ".home", ".internal"))
