# -*- coding: utf-8 -*-
"""ИИ-агент внутри окна PhotoCropQt.

GuiAgent даёт MCP-клиенту те же команды, что и режим без окна (photo_crop.AgentSession), но над состоянием самого окна:
перед командой окно копируется в сеанс (фото, рамки и коррекция — те же объекты), после неё изменения возвращаются в окно.
Сверх того есть инструменты окна (GUI_SPEC): «Улучшить/Супер», пресеты цвета, раскладка листа, печать кнопкой окна, документы,
настройки, справка. Всё выполняется в потоке окна, поэтому пользователь видит изменения сразу, а Ctrl+Z их отменяет.
"""
import json
import threading
import time
from concurrent.futures import Future
from pathlib import Path

import agent_bridge as ab
import agent_guide as guide
import photo_crop as pc

# Диалоги окна во время команды агента не показываются: сообщения копятся здесь и возвращаются в ответе (notes).
CTX = {"active": False, "notes": []}

GUI_SPEC = {
    "app_state": ("Everything about the programme window right now: mode (photo/document), page, open photos and checked ones, current photo, "
                  "format, sheet layout, colour profile, printer, adjustments of the current photo, document, your permissions and limits.", []),
    "app_guide": ("Full guide to the programme: what it can do and which tool does it. Topics: overview, photos, color, sheet, print, documents, "
                  "settings, tips, all.", [("topic", "string", "overview | photos | color | sheet | print | documents | settings | tips | all")]),
    "open_files": ("Open photo files (or add them to the open ones).", [("paths", "any", "List of file paths or one path."),
                                                                      ("add", "boolean", "Add to the open photos instead of replacing them.")]),
    "check_photos": ("Tick or untick photos (the «+» in the corner of a thumbnail): only ticked photos are saved and printed.",
                     [("photo", "any", "Photo ref, list of refs or \"all\"."), ("on", "boolean", "Default true."),
                      ("only", "boolean", "Untick everything else first.")]),
    "remove_unchecked": ("Remove unticked photos from the list (files on disk are not touched).", []),
    "enhance": ("The «Enhance» (level 1) and «Super» (level 2) buttons: choose levels, curve, selective colour, vibrance, noise reduction "
                "and sharpness for each photo separately, tuned for Epson photo printing. The photo's previous colour correction is reset. "
                "The owner prefers manual set_adjust: use this only when the owner asks for it.",
                [("level", "integer", "1 = Enhance, 2 = Super (default 1)."),
                 ("photo", "any", "Photo ref, list of refs, \"all\" or \"checked\". Default: the current photo.")]),
    "auto_levels": ("«Auto» in the levels editor: stretch levels of the current photo to the edges of its histogram.", []),
    "color_presets": ("The three colour presets («Preset 1/2/3» buttons): which are saved and what they contain.", []),
    "color_preset_save": ("Remember the current photo's colour correction in preset n until it is replaced.", [("n", "integer", "1, 2 or 3.")]),
    "color_preset_apply": ("Apply colour preset n.", [("n", "integer", "1, 2 or 3."),
                                                     ("photo", "any", "Photo ref, list, \"all\" or \"checked\". Default: the current photo.")]),
    "copy_adjust": ("Copy the colour correction of the current photo.", []),
    "paste_adjust": ("Paste the copied colour correction.", [("photo", "any", "Photo ref, list, \"all\" or \"checked\". Default: the current photo.")]),
    "set_layout": ("Sheet layout of the window: photos per sheet 1..30, white borders and their width, fill cells.",
                   [("nup", "integer", "Photos per sheet 1..30."), ("borders", "boolean", "White margin at the edge and between photos."),
                    ("border_mm", "number", "Margin in mm."), ("fill", "boolean", "Fill cells by cropping."),
                    ("cell_w", "number", "Frame width in mm: switches the sheet to «by size» mode (as many such frames as fit)."),
                    ("cell_h", "number", "Frame height in mm (use together with cell_w)."),
                    ("by_size", "boolean", "false — back to «by number» (nup).")]),
    "set_view": ("Window view: crop (one photo with its frame) or sheet (layout of the sheets).", [("view", "string", "crop | sheet")]),
    "set_app_mode": ("PHOTO / DOCUMENT switch.", [("mode", "string", "photo | doc")]),
    "add_edge_test": ("Add the edge-test sheet (for borderless printing) of the current paper size to the open photos.", []),
    "print_photos": ("Print like the «Print photo» button: sheets are built from the window's settings (format, photos per sheet, margins, "
                     "printer profile, Printer tab) and sent to the selected printer.",
                     [("which", "string", "current | checked (default checked)"), ("photo", "any", "Print only these photos (ref or list)."),
                      ("copies", "integer", "Copies of each sheet."), ("wait", "boolean", "Wait until all sheets are sent (default true)."),
                      ("timeout", "number", "Seconds to wait (default 300).")]),
    "print_status": ("Is the window printing or saving now, and the result of the last print.", []),
    "doc_open": ("Open a document (PDF, Word, Excel, PowerPoint) and switch the window to document mode.", [("path", "string", "File path.")]),
    "doc_info": ("Open document and its print settings.", []),
    "doc_set": ("Document print settings.", [("paper", "string", "Paper, e.g. A4."), ("fit", "string", "fit | shrink | actual"),
                                           ("margin", "number", "mm"), ("range", "string", "e.g. 1-3, 5, 8- ; empty = all"),
                                           ("copies", "integer", ""), ("cm_on", "boolean", "Use printer profile."), ("icc", "string", "ICC file.")]),
    "doc_print": ("Print the open document on the selected printer.", [("wait", "boolean", "Default true."), ("timeout", "number", "Seconds, default 300.")]),
    "doc_convert": ("Open the document in «KopiTehnik Converter» (PDF editing, OCR) if it is installed.", [("ocr", "boolean", "Text recognition.")]),
    "app_settings": ("Read or change safe programme settings (language, theme, animation, confirmations, update check, save folder and "
                     "options). Agent permissions can be changed only by the person in the Settings window.",
                     [("set", "object", "Fields to change, e.g. {\"confirm_actions\": false}. Omit to only read.")]),
    "print_stats": ("Sheets printed today (photos and documents).", []),
    "check_update": ("Is there a newer version of the programme on GitHub.", []),
}
GUI_READONLY = {"app_state", "app_guide", "color_presets", "print_status", "doc_info", "print_stats", "check_update"}
GUI_REQUIRED = {"open_files": ["paths"], "color_preset_save": ["n"], "color_preset_apply": ["n"], "set_view": ["view"],
                "set_app_mode": ["mode"], "doc_open": ["path"]}
GUI_DESTRUCTIVE = ("print", "save_files", "export_sheets", "clear_queue", "cancel_job", "job_control", "print_photos", "doc_print")

SETTABLE = {"language": str, "theme": str, "anim": bool, "confirm_actions": bool, "check_updates": bool, "dpi": str, "filetype": str,
            "quality": int, "out_mode": str, "out_name": str, "outdir": str, "subfolder": bool, "resize": bool, "copies_name": bool}


def policy(settings):
    """Права агента (задаёт человек в настройках окна). По умолчанию полные."""
    return {"allow_print": bool(settings.get("agent_allow_print", True)),
            "max_sheets": max(0, int(settings.get("agent_max_sheets", 0) or 0)),
            "confirm_print": bool(settings.get("agent_confirm_print", False))}


class GuiAgent:
    def __init__(self, win):
        self.win = win
        self.ses = pc.AgentSession(persist=False)
        self.lock = threading.RLock()
        self.invoke = None                                       # callable(fn) -> результат, выполняет fn в потоке окна
        self.spec = {**pc.SPEC, **GUI_SPEC}
        self.readonly = set(pc.READONLY) | GUI_READONLY
        self.required = {**pc.REQUIRED, **GUI_REQUIRED}
        self.destructive = GUI_DESTRUCTIVE
        self.instructions = guide.INSTRUCTIONS
        self.last_request = 0.0
        self.native = {"app_state": self.c_app_state, "app_guide": self.c_app_guide, "open_files": self.c_open_files,
                       "check_photos": self.c_check_photos, "remove_unchecked": self.c_remove_unchecked, "enhance": self.c_enhance,
                       "auto_levels": self.c_auto_levels, "color_presets": self.c_color_presets, "color_preset_save": self.c_preset_save,
                       "color_preset_apply": self.c_preset_apply, "copy_adjust": self.c_copy_adjust, "paste_adjust": self.c_paste_adjust,
                       "set_layout": self.c_set_layout, "set_view": self.c_set_view, "set_app_mode": self.c_set_app_mode,
                       "add_edge_test": self.c_edge_test, "print_status": self.c_print_status, "doc_open": self.c_doc_open,
                       "doc_info": self.c_doc_info, "doc_set": self.c_doc_set, "doc_convert": self.c_doc_convert,
                       "app_settings": self.c_app_settings, "print_stats": self.c_print_stats, "check_update": self.c_check_update,
                       "undo": self.c_undo, "redo": self.c_redo}

    # ---------- ресурсы MCP: справка
    def resources(self):
        return [("photocrop://guide", "PhotoCrop guide", "What the programme can do and which tool does it")] + \
               [("photocrop://guide/" + k, "Guide: " + k, "") for k in guide.TOPICS]

    def read_resource(self, uri):
        return guide.guide(uri.rsplit("/", 1)[-1] if uri != "photocrop://guide" else "all")

    # ---------- выполнение в потоке окна
    def on_gui(self, fn):
        """Результат fn(), выполненной в потоке окна, и сообщения диалогов, которые окно хотело показать."""
        def run():
            CTX["active"], CTX["notes"] = True, []
            try:
                return fn(), list(CTX["notes"])
            finally:
                CTX["active"], CTX["notes"] = False, []
        if self.invoke is None:
            return run()
        return self.invoke(run)

    def execute(self, req):
        t0 = time.time()
        name = ""
        notes = []
        try:
            if not isinstance(req, dict):
                raise pc.AgentError("Запрос должен быть JSON-объектом {\"cmd\": …}", "bad_request")
            req = dict(req)
            name = str(req.pop("cmd", None) or req.pop("command", "") or "")
            if name not in self.spec:
                raise pc.AgentError(f"Неизвестная команда «{name}». Список: app_guide", "unknown_command")
            self.last_request = time.time()
            if name == "batch":
                return self.run_batch(req, t0)
            with self.lock:
                if name in self.native:
                    res, notes = self.on_gui(lambda: self.native[name](req))
                    out = {"ok": True, "cmd": name, "result": res}
                elif name in ("print_photos", "doc_print"):
                    fn = self.print_photos if name == "print_photos" else self.doc_print
                    res, notes = self.on_gui(lambda: fn(req))
                    if res.get("started") and req.get("wait", True):
                        res = self.print_wait(req, res)
                    out = {"ok": True, "cmd": name, "result": res}
                else:
                    out, notes = self.engine(name, req)
        except pc.AgentError as ex:
            out = {"ok": False, "cmd": name, "error": {"code": ex.code, "message": str(ex), **ex.extra}}
        except Exception as ex:
            out = {"ok": False, "cmd": name, "error": {"code": "internal", "message": f"{ex.__class__.__name__}: {ex}"}}
        if notes:
            out["notes"] = notes
        try:
            self.ses._log(req if isinstance(req, dict) else {}, name, out, time.time() - t0)
        except Exception:
            pass
        return out

    def run_batch(self, req, t0):
        """batch: несколько команд (и движка, и окна) за один вызов; каждая выполняется как обычная."""
        items = req.get("commands")
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except ValueError:
                items = None
        if not isinstance(items, list) or not items or len(items) > 60:
            return {"ok": False, "cmd": "batch", "error": {"code": "bad_value", "message": "commands: непустой список [{cmd, ...}], не больше 60"}}
        stop = req.get("stop_on_error", True) not in (False, "false", 0, "0")
        res, stopped = [], None
        for i, it in enumerate(items):
            if isinstance(it, (list, tuple)) and it:
                it = {"cmd": it[0], **(it[1] if len(it) > 1 and isinstance(it[1], dict) else {})}
            if not isinstance(it, dict) or str(it.get("cmd") or "") in ("", "batch"):
                out = {"ok": False, "error": {"code": "bad_request", "message": "элемент: {cmd, ...}, вложенный batch нельзя"}}
            else:
                out = self.execute(dict(it))
                if isinstance(out.get("result"), dict):
                    out["result"] = {k: v for k, v in out["result"].items() if k != "_image_b64"}
            res.append(out)
            if not out.get("ok") and stop:
                stopped = i
                break
        return {"ok": True, "cmd": "batch", "result": {"done": len(res), "of": len(items), "stopped_at": stopped, "results": res}}

    # ---------- команды движка над состоянием окна
    def states_key(self):
        w = self.win
        return tuple((str(f), w._st_tuple(st), tuple(sorted(st.adj.items()))) for f, st in w.states.items())

    def pull(self, name):
        """Окно -> сеанс. Возвращает снимок для сравнения после команды."""
        w, s = self.win, self.ses
        s.files, s.states, s.idx = list(w.files), w.states, w.idx
        s.folder, s.recursive = w.src_dir, w.s["recursive"]
        s.fmt_name, s.orient_name, s.mode_name = w.s["format"], w.s["orient"], w.s["mode"]
        st = w.s
        try:
            dpi = float(str(st["dpi"]).replace(",", "."))
        except ValueError:
            dpi = s.save["dpi"]
        s.save.update(dpi=dpi, resize=st["resize"], filetype=st["filetype"], quality=int(st["quality"]), subfolder=st["subfolder"],
                      out_mode=st["out_mode"], out_name=st["out_name"], outdir=st["outdir"], copies_in_name=st["copies_name"])
        s.cm = {"on": st["cm_on"], "icc": st["icc"], "intent": st["intent"], "bpc": st["bpc"], "embed": st["embed"]}
        if w.pr.get("printer"):
            s.printer = w.pr["printer"]
        if w.blob is not None:
            s.blob = w.blob
        if w.printers:
            s.printers = list(w.printers)
        snap = {"key": self.states_key(), "idx": w.idx, "rot": w.states[w.files[w.idx]].rotation if w.idx >= 0 else 0,
                "files": list(w.files), "save": dict(s.save), "cm": dict(s.cm), "printer": s.printer, "blob": s.blob,
                "fmt": (s.fmt_name, s.orient_name, s.mode_name), "undo": False}
        if name in pc.UNDOABLE and w.files:
            w.push_undo(list(w.files))                          # шаг отмены окна: Ctrl+Z откатит команду агента
            snap["undo"] = True
        return snap

    def push(self, name, snap):
        """Сеанс -> окно: что команда изменила, то окно показывает."""
        w, s = self.win, self.ses
        if list(s.files) != snap["files"]:
            w.set_files(s.folder, list(s.files), s.states, s.idx)
            return
        w.states = s.states
        if snap["undo"]:
            if self.states_key() == snap["key"] and w._undo:
                w._undo.pop()                                   # команда ничего не изменила: пустого шага отмены не оставляем
        fmt = (s.fmt_name, s.orient_name, s.mode_name)
        if fmt != snap["fmt"]:
            if s.fmt_name != w.s["format"]:
                w.cb_format.setCurrentText(s.fmt_name)
            if s.orient_name != w.s["orient"]:
                w.seg_orient.set(s.orient_name)
                w._orient_changed(s.orient_name)
            if s.mode_name != w.s["mode"]:
                w.seg_mode.set(s.mode_name)
                w._set("mode", s.mode_name)
        st = w.s
        if s.save != snap["save"]:
            st.update(dpi="%g" % s.save["dpi"], resize=s.save["resize"], filetype=s.save["filetype"], quality=int(s.save["quality"]),
                      subfolder=s.save["subfolder"], out_mode=s.save["out_mode"], out_name=s.save["out_name"], outdir=s.save["outdir"],
                      copies_name=s.save["copies_in_name"])
        if s.cm != snap["cm"]:
            st.update(cm_on=bool(s.cm["on"]), icc=s.cm["icc"], intent=s.cm["intent"], bpc=s.cm["bpc"], embed=s.cm["embed"])
            w.cm_changed()
        if s.printer != snap["printer"] and s.printer and s.printer != w.pr.get("printer"):
            w.cb_printer.setCurrentText(s.printer)              # окно загрузит драйвер этого принтера
        if s.blob is not None and s.blob != snap["blob"]:
            w.blob = s.blob
            w._save_blob()
            w._fill_driver()
        if 0 <= s.idx < len(w.files) and s.idx != w.idx:
            w.show_photo(s.idx)
        elif w.idx >= 0 and (w.states[w.files[w.idx]].rotation != snap["rot"]):
            w.show_photo(w.idx)
        elif self.states_key() != snap["key"]:
            w.refresh_proof()
            w.redraw()
            w.thumbs_view.viewport().update()
            w.upd_counts()
            if w.pages.currentIndex() == 1:
                w.sync_adj()
            w._after_adj()

    def engine(self, name, req):
        pol = policy(self.win.settings)
        if name == "print":
            if not pol["allow_print"]:
                raise pc.AgentError("Владелец запретил агенту печать в настройках программы.", "print_not_allowed")
            if pol["max_sheets"]:
                req["max_sheets"] = min(int(req.get("max_sheets") or pol["max_sheets"]), pol["max_sheets"])
        snap, notes = self.on_gui(lambda: self.pull(name))
        out = self.ses.execute({**req, "cmd": name})
        _r, notes2 = self.on_gui(lambda: self.push(name, snap))
        return out, notes + notes2

    # ---------- вспомогательное для инструментов окна
    def files_of(self, req, key="photo", default="current"):
        """Список файлов по ссылке агента (индекс, имя, список, "all", "checked", "current")."""
        w = self.win
        if not w.files:
            raise pc.AgentError("Фото не открыты. Сначала open_folder или open_files.", "no_folder")
        v = req.get(key)
        if v is None:
            v = default
        if isinstance(v, str) and v.strip().lower() == "checked":
            return w.checked_files()
        if isinstance(v, str) and v.strip().lower() == "current":
            if w.idx < 0:
                raise pc.AgentError("Нет открытого фото.", "bad_photo")
            return [w.files[w.idx]]
        s = self.ses
        s.files, s.states, s.idx = list(w.files), w.states, w.idx
        return s._many({key: v}, key)

    def _scoped(self, files, fn):
        """Выполняет fn(), пока область действия коррекции окна — именно эти файлы."""
        w = self.win
        keep_scope, keep_checked, keep_idx = w.s["adj_scope"], set(w.checked), w.idx
        try:
            if len(files) == 1 and files[0] == w.files[w.idx]:
                w.s["adj_scope"] = "one"
            else:
                w.s["adj_scope"] = "all"
                w.checked = set(files)
            return fn()
        finally:
            w.s["adj_scope"], w.checked = keep_scope, keep_checked
            w.upd_counts()
            w.thumbs_view.viewport().update()

    def _adj_summary(self):
        w = self.win
        return pc._jsonable(dict(w.cur_adj())) if w.idx >= 0 else {}

    # ---------- инструменты окна
    def c_app_state(self, req):
        w = self.win
        cur = None
        if w.idx >= 0:
            f = w.files[w.idx]
            st = w.states[f]
            cur = {"index": w.idx, "name": f.name, "path": str(f), "rotation": pc.rot_deg(st.rotation), "flip_h": bool(pc.rot_flips(st.rotation)[0]), "flip_v": bool(pc.rot_flips(st.rotation)[1]), "copies": st.copies, "edited": st.edited,
                   "size": list(w.img_size), "adjust": self._adj_summary()}
        try:
            sheets = w.sheet_count() if w.files else 0
        except Exception:
            sheets = None
        try:
            from photo_crop_qt import APP_VERSION
        except Exception:
            APP_VERSION = None
        return {"version": APP_VERSION, "mode": getattr(w, "app_mode", "photo"), "view": w.view, "page": w.pages.currentIndex(),
                "folder": str(w.src_dir) if w.src_dir else None, "photos": len(w.files), "checked": len(w.checked_files()),
                "current": cur, "format": w.s["format"], "orientation": w.s["orient"], "frame_mode": w.s["mode"],
                "layout": {"nup": w.s["nup"], "borders": w.s["borders"], "border_mm": w.border_mm(), "fill": w.s["fill"]},
                "sheets_to_print": sheets,
                "save": {k: w.s[k] for k in ("dpi", "filetype", "quality", "out_mode", "out_name", "outdir", "subfolder", "resize")},
                "color_profile": {"on": w.s["cm_on"], "icc": w.s["icc"], "intent": w.s["intent"], "bpc": w.s["bpc"], "embed": w.s["embed"]},
                "printer": w.pr.get("printer") or None, "printing": bool(w.printing), "saving": bool(w.saving),
                "print_copies_per_sheet": w.pr.get("copies"), "document": self.c_doc_info({}) if w.doc.get("src") else None,
                "color_presets_saved": sorted(w.settings.get("adj_presets", {})),
                "undo_steps": len(w._undo), "agent_permissions": policy(w.settings)}

    def c_app_guide(self, req):
        return {"topic": req.get("topic") or "overview", "text": guide.guide(req.get("topic"))}

    def c_open_files(self, req):
        w = self.win
        paths = req.get("paths")
        paths = [paths] if isinstance(paths, str) else list(paths or [])
        if not paths:
            raise pc.AgentError("paths: нужен путь или список путей", "bad_value")
        for p in paths:
            if not Path(str(p)).expanduser().exists():
                raise pc.AgentError(f"Файл не найден: {p}", "not_found")
        before = len(w.files)
        w.load_files([Path(str(p)).expanduser() for p in paths], add=bool(req.get("add", False)))
        return {"photos": len(w.files), "added": len(w.files) - before if req.get("add") else None}

    def c_check_photos(self, req):
        w = self.win
        files = self.files_of(req, default="all")
        on = bool(req.get("on", True))
        if req.get("only"):
            w.checked = set()
        for f in files:
            (w.checked.add if on else w.checked.discard)(f)
        w.upd_counts()
        w.thumbs_view.viewport().update()
        w.redraw()
        return {"checked": len(w.checked_files()), "photos": len(w.files)}

    def c_remove_unchecked(self, req):
        w = self.win
        n = len(w.files)
        w.remove_unchecked()
        return {"removed": n - len(w.files), "photos": len(w.files)}

    def c_enhance(self, req):
        w = self.win
        level = 2 if int(req.get("level") or 1) >= 2 else 1
        files = self.files_of(req)
        w.enhance(level, files)
        w.sync_adj()
        return {"level": level, "photos": [f.name for f in files], "adjust": self._adj_summary(), "note": w.l_enh.text()}

    def c_auto_levels(self, req):
        w = self.win
        if w.idx < 0:
            raise pc.AgentError("Нет открытого фото.", "bad_photo")
        w.levels_auto()
        return {"levels": pc._jsonable(w.cur_adj().get("levels"))}

    def c_color_presets(self, req):
        return {"presets": pc._jsonable(self.win.settings.get("adj_presets", {})),
                "names": {str(n): self.win.preset_name(n) for n in (1, 2, 3)}}

    def c_preset_save(self, req):
        w = self.win
        n = int(req.get("n") or 0)
        if n not in (1, 2, 3):
            raise pc.AgentError("n: 1, 2 или 3", "bad_value")
        w.preset_save(n)
        return {"saved": n in [int(k) for k in w.settings.get("adj_presets", {})]}

    def c_preset_apply(self, req):
        w = self.win
        n = int(req.get("n") or 0)
        if n not in (1, 2, 3):
            raise pc.AgentError("n: 1, 2 или 3", "bad_value")
        if str(n) not in w.settings.get("adj_presets", {}):
            raise pc.AgentError(f"Пресет {n} пуст.", "preset_empty")
        files = self.files_of(req)
        self._scoped(files, lambda: w.preset_pick(n))
        w.sync_adj()
        return {"applied": n, "photos": [f.name for f in files]}

    def c_copy_adjust(self, req):
        w = self.win
        w.adj_copy()
        return {"copied": True}

    def c_paste_adjust(self, req):
        w = self.win
        if w.adj_clipboard is None:
            raise pc.AgentError("Сначала copy_adjust.", "nothing_copied")
        files = self.files_of(req)
        w.adj_replace(w.adj_clipboard, files)
        w.sync_adj()
        return {"pasted_to": [f.name for f in files]}

    def c_set_layout(self, req):
        w = self.win
        if "nup" in req:
            n = int(req["nup"])
            if not 1 <= n <= 30:
                raise pc.AgentError("nup: 1..30", "bad_value")
            w.seg_nup.set(n)
            w._layout_set("nup", n)
        if "cell_w" in req or "cell_h" in req:
            for k in ("cell_w", "cell_h"):
                if k in req:
                    v = float(req[k])
                    if not 10 <= v <= 1000:
                        raise pc.AgentError(f"{k}: 10..1000 мм", "bad_value")
                    w.e_cell[k].setText("%g" % v)
                    w.s[k] = "%g" % v
            w.seg_cell.set(True)
            w._layout_set("cell_mode", True)
        if "by_size" in req and not req["by_size"]:
            w.seg_cell.set(False)
            w._layout_set("cell_mode", False)
        if "borders" in req:
            on = bool(req["borders"])
            w.sw_borders.setChecked(on)
            w._layout_set("borders", on)
        if "border_mm" in req:
            v = "%g" % float(req["border_mm"])
            w.e_border.setText(v)
            w._layout_set("border_mm", v)
        if "fill" in req:
            w.s["fill"] = bool(req["fill"])
            w.redraw()
        return {"nup": w.s["nup"], "borders": w.s["borders"], "border_mm": w.border_mm(), "fill": w.s["fill"], "sheets": w.sheet_count(),
                "by_size": bool(w.s.get("cell_mode")), "cell_mm": list(w.cell_mm())}

    def c_set_view(self, req):
        v = str(req.get("view") or "").lower()
        if v not in ("crop", "sheet"):
            raise pc.AgentError("view: crop | sheet", "bad_value")
        self.win.set_view(v)
        return {"view": self.win.view}

    def c_set_app_mode(self, req):
        m = str(req.get("mode") or "").lower()
        if m not in ("photo", "doc"):
            raise pc.AgentError("mode: photo | doc", "bad_value")
        self.win.set_app_mode(m)
        return {"mode": self.win.app_mode}

    def c_edge_test(self, req):
        w = self.win
        w.add_edge_test()
        return {"photos": len(w.files), "added": w.files[-1].name if w.files else None}

    def c_undo(self, req):
        w = self.win
        n = max(1, int(req.get("steps") or 1))
        done = 0
        while done < n and w._undo:
            w.undo()
            done += 1
        if not done:
            raise pc.AgentError("Откатывать нечего.", "nothing_to_undo")
        return {"undone": done, "can_undo": len(w._undo), "can_redo": len(w._redo)}

    def c_redo(self, req):
        w = self.win
        n = max(1, int(req.get("steps") or 1))
        done = 0
        while done < n and w._redo:
            w.redo()
            done += 1
        if not done:
            raise pc.AgentError("Повторять нечего.", "nothing_to_redo")
        return {"redone": done, "can_undo": len(w._undo), "can_redo": len(w._redo)}

    # ---------- печать окна
    def c_print_status(self, req):
        w = self.win
        return {"printing": bool(w.printing), "saving": bool(w.saving), "last": getattr(w, "last_print", None)}

    def print_photos(self, req):
        """Запуск печати окна (в потоке окна). Возвращает None, если печать не началась."""
        w = self.win
        pol = policy(w.settings)
        if not pol["allow_print"]:
            raise pc.AgentError("Владелец запретил агенту печать в настройках программы.", "print_not_allowed")
        if w.printing or w.saving:
            raise pc.AgentError("Окно уже печатает или сохраняет.", "busy")
        if getattr(w, "app_mode", "photo") == "doc":
            raise pc.AgentError("Окно в режиме документа: используйте doc_print или set_app_mode photo.", "wrong_mode")
        which = str(req.get("which") or "checked").lower()
        if req.get("photo") is not None:
            files = self.files_of(req)
        elif which == "current":
            files = self.files_of({"photo": "current"})
        else:
            files = w.checked_files()
        if not files:
            raise pc.AgentError("Нет фото для печати (ни одно не отмечено).", "no_photos")
        if req.get("copies") is not None:
            w.pr["copies"] = max(1, min(99, int(req["copies"])))
        try:
            total = len(files) if w.s["fill"] else -(-sum(max(1, w.states[f].copies) for f in files) // w.s["nup"])
        except Exception:
            total = None
        if pol["max_sheets"] and total is not None and total * int(w.pr.get("copies", 1)) > pol["max_sheets"]:
            raise pc.AgentError(f"К печати {total * int(w.pr.get('copies', 1))} листов, а лимит агента {pol['max_sheets']} (настройки программы).",
                                "too_many_sheets")
        keep = set(w.checked)
        try:
            w.checked = set(files)
            w.last_print = None
            if pol["confirm_print"] and not w.agent_confirm_print(files, total):
                raise pc.AgentError("Печать не подтверждена человеком в окне.", "print_declined")
            w.print_now()
        finally:
            w.checked = keep
            w.upd_counts()
        return {"sheets": total, "printer": w.pr.get("printer"), "started": bool(w.printing)}

    def print_wait(self, req, started):
        timeout = float(req.get("timeout") or 300)
        t_end = time.time() + timeout
        w = self.win
        while time.time() < t_end:
            if not self.on_gui(lambda: bool(w.printing))[0]:
                break
            time.sleep(0.4)
        last = self.on_gui(lambda: getattr(w, "last_print", None))[0]
        started["finished"] = last is not None
        started["last"] = last
        return started

    # ---------- документы
    def c_doc_open(self, req):
        w = self.win
        p = Path(str(req.get("path") or "")).expanduser()
        if not p.is_file():
            raise pc.AgentError(f"Файл не найден: {p}", "not_found")
        w.set_app_mode("doc")
        w.doc_load(str(p))
        return self.c_doc_info({})

    def c_doc_info(self, req):
        w = self.win
        d = dict(w.d)
        return {"open": bool(w.doc.get("src")), "name": w.doc["src"].name if w.doc.get("src") else None,
                "pages": w.doc.get("pages", 0), "printer": w.pr.get("printer") or None,
                "settings": {"paper": d["paper"], "fit": d["fit"], "margin": d["margin"], "range": d["range"], "copies": d["copies"],
                             "cm_on": d["cm_on"], "icc": d["icc"]}}

    def c_doc_set(self, req):
        w = self.win
        d = w.d
        import doc_tools as dt
        if "paper" in req:
            if req["paper"] not in dt.PAPERS:
                raise pc.AgentError("paper: " + ", ".join(dt.PAPERS), "bad_value")
            d["paper"] = req["paper"]
            w.settings["doc_paper"] = req["paper"]
        if "fit" in req:
            if req["fit"] not in ("fit", "shrink", "actual"):
                raise pc.AgentError("fit: fit | shrink | actual", "bad_value")
            d["fit"] = w.settings["doc_fit"] = req["fit"]
        if "margin" in req:
            d["margin"] = w.settings["doc_margin"] = "%g" % float(req["margin"])
        if "range" in req:
            d["range"] = str(req["range"] or "")
        if "copies" in req:
            d["copies"] = max(1, min(99, int(req["copies"])))
        if "cm_on" in req:
            d["cm_on"] = w.settings["doc_cm_on"] = bool(req["cm_on"])
        if "icc" in req:
            d["icc"] = w.settings["doc_icc"] = str(req["icc"] or "")
        w.persist()
        return self.c_doc_info({})

    def doc_print(self, req):
        w = self.win
        pol = policy(w.settings)
        if not pol["allow_print"]:
            raise pc.AgentError("Владелец запретил агенту печать в настройках программы.", "print_not_allowed")
        if not w.doc.get("src"):
            raise pc.AgentError("Документ не открыт: doc_open.", "no_document")
        if w.printing or w.saving:
            raise pc.AgentError("Окно уже печатает или сохраняет.", "busy")
        try:
            import doc_tools as dt
            pages = dt.parse_range(w.d["range"], w.doc["pages"])
        except Exception as ex:
            raise pc.AgentError(f"Страницы: {ex}", "bad_value")
        total = len(pages) * w.d["copies"]
        if pol["max_sheets"] and total > pol["max_sheets"]:
            raise pc.AgentError(f"К печати {total} листов, а лимит агента {pol['max_sheets']} (настройки программы).", "too_many_sheets")
        w.last_print = None
        w.print_doc()
        return {"sheets": total, "printer": w.pr.get("printer"), "started": bool(w.printing)}

    def c_doc_convert(self, req):
        w = self.win
        if not w.doc.get("src"):
            raise pc.AgentError("Документ не открыт: doc_open.", "no_document")
        w.doc_convert(bool(req.get("ocr", False)))
        return {"started": True, "note": "Откроется программа «КопиТехник Конвертер»; результат вернётся в окно."}

    # ---------- настройки, счётчик, обновления
    def c_app_settings(self, req):
        w = self.win
        ch = req.get("set")
        if isinstance(ch, str):
            try:
                ch = json.loads(ch)
            except ValueError:
                raise pc.AgentError("set: нужен JSON-объект", "bad_value")
        applied = {}
        for k, v in (ch or {}).items():
            if k not in SETTABLE:
                raise pc.AgentError(f"Поле «{k}» агент менять не может. Доступно: {', '.join(SETTABLE)}", "not_allowed")
            v = SETTABLE[k](v)
            if k in ("language",):
                w.apply_look(lang=v)
            elif k == "theme":
                w.apply_look(theme=v)
            elif k == "confirm_actions":
                w.settings[k] = v
                import photo_crop_qt as q
                q.SOFT[0] = v
            elif k in ("anim", "check_updates"):
                w.settings[k] = v
            else:
                w.s[k] = ("%g" % float(v)) if k == "dpi" else v
            applied[k] = v
        if applied:
            w.persist()
        s = w.settings
        return {"applied": applied, "language": pc.get_language(), "theme": w.theme_name, "anim": bool(s.get("anim", True)),
                "confirm_actions": bool(s.get("confirm_actions", False)), "check_updates": bool(s.get("check_updates", True)),
                "save": {k: w.s[k] for k in ("dpi", "filetype", "quality", "out_mode", "out_name", "outdir", "subfolder", "resize", "copies_name")},
                "agent_permissions": policy(s)}

    def c_print_stats(self, req):
        import print_stats as ps
        return ps.today()

    def c_check_update(self, req):
        import photo_crop_qt as q
        latest = q.fetch_latest_release()
        return {"current": q.APP_VERSION, "latest": latest[0] if latest else None, "page": latest[1] if latest else None,
                "newer": q.update_available(latest), "checked": latest is not None}
