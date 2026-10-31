"""Обработчик сетевой печати на ПК, где стоит принтер (исполнитель). Без Qt.

Клиент присылает нейтральный лист (sRGB, PNG/JPEG, вся бумага целиком) вместе с метаданными; здесь он:
  1. проверяется (это картинка, размер в пикселях ограничен, пропорции совпадают с бумагой в драйвере);
  2. получает цвет принтера ИЗ ЕГО ПРОФИЛЯ НА ЭТОМ ПК (ICC, поправка принтера, подрезка), клиентские профили не используются;
  3. уходит на принтер через PrinterJob с настройками драйвера из профиля;
  4. записывается в журнал печати.
Ядро photo_crop (pc) и поправка принтера (pcr) передаются в конструктор: так модуль проверяется тестами без Windows.
"""
import base64
import hashlib
import io
import json

MAX_PIXELS = 400_000_000          # защита от «бомбы» распаковки: A3 при 600 dpi ≈ 140 Мпикс
ASPECT_TOL = 0.02                 # допустимое расхождение пропорций листа и бумаги в драйвере

PROF_COLOR = ("cm_on", "icc", "intent", "bpc", "embed", "pcorr")
PROF_PR = ("icm_off", "ppi", "sharp", "shrink")
DEFAULT_COLOR = {"cm_on": False, "icc": "", "intent": "", "bpc": False, "embed": False, "pcorr": None}
DEFAULT_PR = {"icm_off": True, "ppi": "Авто", "sharp": 0, "shrink": "0"}


class PrintRefused(Exception):
    pass


def profile_revision(profile):
    """Короткая ревизия профиля: клиент проверяет, что настройки не поменялись между просмотром и печатью."""
    p = {k: v for k, v in (profile or {}).items() if k != "blob"}
    s = json.dumps(p, sort_keys=True, ensure_ascii=False, default=str) + str((profile or {}).get("blob", ""))
    return hashlib.sha1(s.encode()).hexdigest()[:10]


class NetPrinting:
    def __init__(self, pc, pcr, get_settings, image_open=None, print_stats=None):
        """get_settings() -> актуальный dict настроек программы (ключи print_profiles, print_devmodes, net_shared)."""
        self.pc, self.pcr, self.get_settings = pc, pcr, get_settings
        self._open = image_open
        self.print_stats = print_stats

    # ---- какие принтеры отдаются по сети ----
    def shared_printers(self):
        """None в net_shared = все установленные принтеры; иначе список разрешённых."""
        allowed = self.get_settings().get("net_shared")
        names = self.pc.list_printers()
        return names if allowed is None else [n for n in names if n in allowed]

    def handler_printers(self, meta, data, peer):
        out = []
        profs = self.get_settings().get("print_profiles", {})
        for name in self.shared_printers():
            keys = [k for k in profs if k.split(" | ")[0] == name]
            out.append({"name": name, "profiles": [{"key": k, "rev": profile_revision(profs[k])} for k in keys]})
        return {"printers": out}

    # ---- профиль ----
    def find_profile(self, printer, key=None, fmt=None):
        profs = self.get_settings().get("print_profiles", {})
        if key and key in profs and key.split(" | ")[0] == printer:
            return key, profs[key]
        keys = [k for k in profs if k.split(" | ")[0] == printer]
        keys.sort(key=lambda k: (len(k.split(" | ")) < 2 or k.split(" | ")[1] != fmt))
        return (keys[0], profs[keys[0]]) if keys else (None, None)

    def _blob(self, printer, prof):
        stored = (prof or {}).get("blob") or self.get_settings().get("print_devmodes", {}).get(printer)
        if not stored:
            raise PrintRefused("Для принтера нет сохранённых настроек драйвера на этом ПК. Откройте его в программе и сохраните настройки.")
        b = base64.b64decode(stored)
        if not self.pc.devmode_valid(b):
            raise PrintRefused("Сохранённые настройки драйвера повреждены.")
        return b

    def context(self, printer, key=None, fmt=None):
        pk, prof = self.find_profile(printer, key, fmt)
        color = {k: (prof or {}).get(k, v) for k, v in DEFAULT_COLOR.items()}
        pr = {k: (prof or {}).get(k, v) for k, v in DEFAULT_PR.items()}
        blob = self.pc.prepare_blob(printer, self._blob(printer, prof), "portrait", {"paper": self.pc.PAPER_DRIVER, "icm_off": bool(pr["icm_off"])})
        geom = self.pc.printer_geometry(printer, blob, "portrait")
        cm = None
        if color["cm_on"]:
            cm = self.pc.cm_build(color["icc"], color["intent"], color["bpc"], color["embed"])
        pcorr = self.pcr.norm(color["pcorr"]) if color["pcorr"] and self.pcr.active(color["pcorr"]) else None
        return {"key": pk, "rev": profile_revision(prof), "blob": blob, "geom": geom, "cm": cm, "pcorr": pcorr, "pr": pr}

    def handler_snapshot(self, meta, data, peer):
        """Снимок принтера для клиента: бумага, ppi, ревизия профиля (план листов строится по нему)."""
        printer = meta.get("printer")
        self._check_shared(printer)
        c = self.context(printer, meta.get("profile"), meta.get("format"))
        gw, gh = c["geom"]["paper"]
        ppi = self.pc.resolve_ppi({"ppi": c["pr"]["ppi"]}, c["geom"])
        return {"printer": printer, "profile": c["key"], "rev": c["rev"], "paper_mm": [round(gw, 1), round(gh, 1)], "ppi": ppi,
                "color": bool(c["cm"]), "pcorr": bool(c["pcorr"])}

    def _check_shared(self, printer):
        if printer not in self.shared_printers():
            raise PrintRefused("Принтер недоступен по сети.")

    # ---- печать листа ----
    def _decode(self, data):
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        im = (self._open or Image.open)(io.BytesIO(data))
        if im.width * im.height > MAX_PIXELS:
            raise PrintRefused("Слишком большое изображение.")
        im.load()
        return im.convert("RGB")

    def print_sheet(self, meta, data):
        """Передаётся в net_link.Node(print_sheet=...). Бросает исключение при отказе или сбое."""
        printer = meta["printer"]
        self._check_shared(printer)
        c = self.context(printer, meta.get("profile"), meta.get("format"))
        if meta.get("rev") and meta["rev"] != c["rev"]:
            raise PrintRefused("Профиль принтера на этом ПК изменился, обновите настройки.")
        img = self._decode(data)
        gw, gh = c["geom"]["paper"]
        if abs(img.width / img.height - gw / gh) > ASPECT_TOL * max(gw / gh, 1):
            raise PrintRefused("Пропорции листа (%dx%d) не совпадают с бумагой в драйвере (%gx%g мм)." % (img.width, img.height, gw, gh))
        if c["cm"]:
            img = self.pc.apply_printer_profile(img, None, c["cm"])
        if c["pcorr"]:
            img = self.pcr.apply(img, c["pcorr"])
        title = "PhotoCrop сеть: %s" % str(meta.get("from", ""))[:40]
        with self.pc.PrinterJob(printer, c["blob"], title) as job:
            job.page(img)
            job.finish()
        if self.print_stats:
            try:
                self.print_stats.record(printer, int(meta.get("photos", 1)), "%gx%g" % (round(gw, 1), round(gh, 1)), "network",
                                        "network", 1, [], kind="photo")
            except Exception:
                pass
        return {"printed": True}

    def handlers(self):
        """Команды для net_link.Node(handlers=...)."""
        return {"printers": self.handler_printers, "printer_snapshot": self.handler_snapshot}
