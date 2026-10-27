# -*- coding: utf-8 -*-
"""Частные настройки драйвера Epson внутри DEVMODE: «без полей», цветокоррекция, качество.

Смещения приватной зоны зависят от модели и версии драйвера, поэтому живут в таблице PROFILES.
Для незнакомой модели функции ничего не меняют (supported() == False), а не пишут наугад.
Свои смещения можно добавить в файл epson_profiles.json рядом с настройками программы.
Модуль не зависит от Windows: работает с готовым blob DEVMODE (bytes).
"""
import json
import struct

try:
    from epson_recipes import RECIPES        # модели, снятые по снимкам DEVMODE (tools/make_epson_recipes.py)
except ImportError:                          # pragma: no cover
    RECIPES = {}

SRC_NORMAL, SRC_BORDERLESS = 261, 262      # dmDefaultSource: без этого драйвер сбрасывает флаг «без полей»
DM_DEFAULTSOURCE_OFFSET = 88               # DEVMODEW.dmDefaultSource
DM_FIELDS_OFFSET = 72
DM_DEFAULTSOURCE_FLAG = 0x200
CCOR_AUTO, CCOR_MANUAL = 1, 2              # «Автоматический» / «Настройка» (нейтральная = драйвер цвет не правит)

# ключи: border (байт, бит 0), ccor (байт), quality (байт; значения в "quality_values")
PROFILES = {
    "L8050": {"border": 7700, "ccor": 188, "maint": 1, "quality": 7788},
    # L18050: качество (0/1/2) найдено по снимкам драйвера, «без полей» и цветокоррекция сняты вручную через диалог — совпадают с L8050
    "L18050": {"quality": 7788, "border": 7700, "ccor": 188, "maint": 1},
}

DM_MEDIATYPE_OFFSET = 196   # DEVMODEW.dmMediaType: 1 — простая бумага, остальное (396 и др.) — фото.
                            # priv+2088 для этого не годится: он зависит и от размера (на A5 всегда 0x10).

# байты режима качества (priv+offset: значение) и публичные поля (dmPrintQuality/dmYResolution @90/96),
# снятые с драйвера через его диалог. Ключ: (бумага, значение селектора priv+7788).
_PHOTO = {
    (("photo", 1)): {"priv": {124: 0x03, 150: 0x03, 154: 0x20, 2200: 0x00, 7765: 0x00, 7766: 0x00}},
    (("photo", 2)): {"priv": {124: 0x05, 150: 0x04, 154: 0x21, 2200: 0x00, 7765: 0x00, 7766: 0x00}},
}
_PLAIN = {   # простая бумага (dmMediaType=1); на L18050 «Черновик» на простой бумаге не найден
    ("plain", 1): {"priv": {124: 0x02, 150: 0x03, 154: 0x2B, 2200: 0x01, 7765: 0xC0, 7766: 0x01}},
    ("plain", 2): {"priv": {124: 0x03, 150: 0x04, 154: 0x22, 2200: 0x00, 7765: 0x00, 7766: 0x00}},
}
QUALITY_SETS = {
    "L8050": {**_PHOTO, **_PLAIN},
    "L18050": {**_PHOTO, **_PLAIN, **{
        ("photo", 0): {"priv": {124: 0x02, 150: 0x01, 154: 0x01, 2200: 0x00, 7765: 0x40, 7766: 0x00},
                       "pub": {90: 0x68, 91: 0x01, 96: 0x68, 97: 0x01}},
    }},
}

# носители (dmMediaType), на которых драйвер не принимает режим и сам возвращает «Стандарт»:
# проверено перебором 10 носителей × 28 размеров на L8050 — «Высокое» не работает на «Бланк письма» (828),
# «Photo Quality Ink Jet» (318), «Photo Stickers» (338) и «Конверты» (353).
OLD_FAMILY = {"T50", "P50", "TX650", "R290", "1410"}      # приватная зона 796 байт; фотобумага снята полностью на T50

QUALITY_UNSUPPORTED = {
    "L8050": {2: {828, 318, 338, 353}},
    # остальное — матрица через DocumentProperties на ПК пользователя (носители из драйвера × режимы), 27.10.2026
    "L18050": {0: {1, 318, 326, 338, 352, 353, 828}, 2: {318}},
    "L805": {1: {318, 326, 338, 352}},
    "L1800": {1: {275, 318, 325, 326, 338, 352, 396}},
    "PX660": {1: {260, 271, 272, 275, 283, 335, 338, 352, 359, 379}, 2: {272, 275, 353, 359, 379}},
}

# режимы качества по моделям: (значение байта, название). У L8050 в драйвере нет «Черновика».
QUALITY_MODES = {
    "L8050": [(1, "Стандарт"), (2, "Высокое")],
    "L18050": [(0, "Черновик"), (1, "Стандарт"), (2, "Высокое")],
}


def model_of(printer_name):
    """«EPSON L8050 Series (копия 1)» -> «L8050»; не Epson -> None."""
    up = (printer_name or "").upper()
    if "EPSON" not in up:
        return None
    toks = up.replace("(", " ").replace(")", " ").split()
    if "1410" in toks:                                       # Stylus Photo 1410: в названии одни цифры
        return "1410"
    for tok in toks:
        if tok != "EPSON" and any(c.isdigit() for c in tok) and any(c.isalpha() for c in tok):
            return tok
    return None


def load_profiles(extra_path=None):
    prof = {k: dict(v) for k, v in PROFILES.items()}
    if extra_path:
        try:
            with open(extra_path, encoding="utf-8") as f:
                for k, v in json.load(f).items():
                    if isinstance(v, dict):
                        prof.setdefault(k.upper(), {}).update({a: int(b) for a, b in v.items() if isinstance(b, int)})
        except (OSError, ValueError):
            pass
    return prof


class EpsonPriv:
    def __init__(self, printer_name, profiles=None, driver_name=None):
        # очередь могли переименовать («Принтер в цехе»): модель берём по имени драйвера, по имени очереди — запасной вариант
        self.model = model_of(driver_name) or model_of(printer_name)
        self.map = (profiles or PROFILES).get(self.model or "", {})
        # модели без смещений в PROFILES: рецепт из снимков драйвера (байты целиком, потом merge)
        self.recipe = RECIPES.get(self.model or "") if not self.map else None

    def supported(self, feature):
        if self.recipe is not None:
            return feature in ("quality", "maint") or (feature == "border" and "border" in self.recipe)
        return feature in self.map

    # --- модели по рецептам ---------------------------------------------------------------------------
    _DPI_LEVEL = {180: 0, 360: 1, 720: 2}

    @staticmethod
    def _put(ba, part):
        start = struct.unpack_from("<H", ba, 68)[0]
        for off, val in part["pub"].items():
            ba[off] = val
        for off, val in part["priv"].items():
            if start + off < len(ba):
                ba[start + off] = val

    def set_media(self, blob, code):
        """Тип бумаги: у моделей по рецептам драйвер хранит его и в публичном dmMediaType, и в зеркале приватной зоны;
        если записать только публичное поле, merge откатывает носитель на «простую» (проверено на T50, P50, TX650, R290, 1410, PX660, L805)."""
        ba = bytearray(blob)
        struct.pack_into("<I", ba, DM_MEDIATYPE_OFFSET, int(code))
        m = (self.recipe or {}).get("media_mirror")
        if m:
            pos = self._private_start(blob) + m
            if pos + 1 < len(ba):
                struct.pack_into("<H", ba, pos, int(code) & 0xFFFF)
        flags = struct.unpack_from("<I", ba, DM_FIELDS_OFFSET)[0] | 0x2000000        # DM_MEDIATYPE
        struct.pack_into("<I", ba, DM_FIELDS_OFFSET, flags)
        return bytes(ba)

    def _recipe_get(self, blob, feature):
        if feature == "quality":
            return self._DPI_LEVEL.get(struct.unpack_from("<H", blob, 90)[0])
        return struct.unpack_from("<H", blob, DM_DEFAULTSOURCE_OFFSET)[0] == self.recipe["border"]["src_on"]

    def _recipe_set(self, blob, feature, value):
        ba = bytearray(blob)
        if feature == "quality":
            q = self.recipe["quality"].get(int(value))
            if q:
                self._put(ba, q)
            return bytes(ba)
        b = self.recipe["border"]
        self._put(ba, b["on"] if value else b["off"])
        struct.pack_into("<H", ba, DM_DEFAULTSOURCE_OFFSET, b["src_on"] if value else b["src_off"])
        if value and b["media"] and struct.unpack_from("<I", ba, DM_MEDIATYPE_OFFSET)[0] == 1:
            ba = bytearray(self.set_media(bytes(ba), b["media"]))           # без полей — только на фотобумаге
        struct.pack_into("<I", ba, DM_FIELDS_OFFSET, struct.unpack_from("<I", ba, DM_FIELDS_OFFSET)[0] | DM_DEFAULTSOURCE_FLAG)
        return bytes(ba)

    def _quality_patch(self, blob, value):
        """Набор байтов режима качества из реальных снимков драйвера: драйвер выводит байт 7788 из зеркальных
        байтов (+124, +150, +154 ...), поэтому одного селектора мало — иначе merge вернёт прежнее качество."""
        sets = QUALITY_SETS.get(self.model, {})
        media = struct.unpack_from("<I", blob, DM_MEDIATYPE_OFFSET)[0]
        paper = "plain" if media == 1 else "photo"
        return sets.get((paper, value)) or sets.get(("photo", value)) or {}

    def quality_modes(self, blob=None):
        """Режимы качества модели; с blob — только те, для которых известен набор байтов на текущем носителе."""
        if self.recipe is not None:
            names = {0: "Черновик", 1: "Стандарт", 2: "Высокое"}
            media = struct.unpack_from("<I", blob, DM_MEDIATYPE_OFFSET)[0] if blob else None
            bad = QUALITY_UNSUPPORTED.get(self.model, {})
            out = [(k, names[k]) for k in sorted(self.recipe["quality"]) if media not in bad.get(k, ())]
            if self.model in OLD_FAMILY and media not in (None, 1):
                # на фотобумаге драйвер T50 поднимает «Стандарт» до 720 dpi; «Черновик» остаётся только на простой
                out = [(k, n) for k, n in out if k == 2]
            return out
        modes = QUALITY_MODES.get(self.model, []) if self.supported("quality") else []
        if blob is None:
            return modes
        media = struct.unpack_from("<I", blob, DM_MEDIATYPE_OFFSET)[0]
        paper = "plain" if media == 1 else "photo"
        sets = QUALITY_SETS.get(self.model, {})
        bad = QUALITY_UNSUPPORTED.get(self.model, {})
        return [(v, n) for v, n in modes if (paper, v) in sets and media not in bad.get(v, ())]

    def maintenance_verified(self):
        """Команды обслуживания проверены на железе только для L8050; на остальных моделях — стандартные команды Epson."""
        return self.model == "L8050"

    def maintenance(self, printer_name, action):
        """Проверка дюз / прочистка. Только для моделей с ключом maint."""
        if not self.supported("maint"):
            raise ValueError("Для этой модели обслуживание из программы не проверено")
        send_raw(printer_name, maintenance_job(action))

    @staticmethod
    def _private_start(blob):
        return struct.unpack_from("<H", blob, 68)[0]

    def _pos(self, blob, feature):
        pos = self._private_start(blob) + self.map[feature]
        if pos >= len(blob):
            raise ValueError("DEVMODE короче, чем ожидает профиль %s (версия драйвера?)" % self.model)
        return pos

    def get(self, blob, feature):
        if not self.supported(feature):
            return None
        if self.recipe is not None:
            return self._recipe_get(blob, feature)
        pos = self._pos(blob, feature)
        return bool(blob[pos] & 1) if feature == "border" else blob[pos]

    def set(self, blob, feature, value):
        """Возвращает новый blob. Нужно потом пропустить его через merge_devmode (драйвер досчитает поля)."""
        if not self.supported(feature):
            return bytes(blob)
        if self.recipe is not None:
            return self._recipe_set(blob, feature, value)
        ba = bytearray(blob)
        pos = self._pos(blob, feature)
        if feature == "border":
            if value:
                ba[pos] |= 1
            else:
                ba[pos] &= 0xFE
            struct.pack_into("<H", ba, DM_DEFAULTSOURCE_OFFSET, SRC_BORDERLESS if value else SRC_NORMAL)
            struct.pack_into("<I", ba, DM_FIELDS_OFFSET, struct.unpack_from("<I", ba, DM_FIELDS_OFFSET)[0] | DM_DEFAULTSOURCE_FLAG)
        else:
            if feature == "quality":
                start = self._private_start(blob)
                patch = self._quality_patch(blob, int(value))
                for off, val in patch.get("priv", {}).items():
                    if start + off < len(ba):
                        ba[start + off] = val
                for off, val in patch.get("pub", {}).items():
                    ba[off] = val
            ba[pos] = int(value) & 0xFF
        return bytes(ba)

    def set_color_correction_off(self, blob, off=True):
        """Выключить цветокоррекцию драйвера (программа сама ведёт цвет по ICC)."""
        return self.set(blob, "ccor", CCOR_MANUAL if off else CCOR_AUTO)

    def color_correction_off(self, blob):
        v = self.get(blob, "ccor")
        return None if v is None else v == CCOR_MANUAL


# --- обслуживание: проверка дюз и прочистка головки (служебные команды Epson remote mode) ---------------
# Формат как у escputil/Gutenprint: ESC @, ESC ( R «REMOTE1» + команда, выход из remote mode, ESC @.
# Для конкретной модели команды надо проверить на принтере, поэтому кнопки показываются только когда
# в профиле модели есть ключ "maint" (на неизвестных моделях их нет).
# Проверено на железе: L8050 (USB), 27.10.2026 — тест дюз и прочистка напечатали ожидаемое.
MAINT_COMMANDS = {"nozzle_check": b"NC\x02\x00\x00\x00", "clean": b"CH\x02\x00\x00\x00"}


def maintenance_job(action):
    """Байты задания для проверки дюз ("nozzle_check") или прочистки ("clean")."""
    cmd = MAINT_COMMANDS[action]
    return b"\x1b@" + b"\x1b(R" + struct.pack("<H", 8) + b"\x00REMOTE1" + cmd + b"\x1b\x00\x00\x00" + b"\x1b@"


def send_raw(printer_name, data):
    """Отправляет байты принтеру как RAW-задание через spooler (только Windows)."""
    import ctypes
    import ctypes.wintypes as wt

    class DocInfo(ctypes.Structure):
        _fields_ = [("pDocName", wt.LPWSTR), ("pOutputFile", wt.LPWSTR), ("pDatatype", wt.LPWSTR)]
    wp = ctypes.WinDLL("winspool.drv", use_last_error=True)
    wp.OpenPrinterW.argtypes = [wt.LPWSTR, ctypes.POINTER(wt.HANDLE), ctypes.c_void_p]
    wp.StartDocPrinterW.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p]
    wp.WritePrinter.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
    wp.ClosePrinter.argtypes = [wt.HANDLE]
    h = wt.HANDLE()
    if not wp.OpenPrinterW(printer_name, ctypes.byref(h), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not wp.StartDocPrinterW(h, 1, ctypes.byref(DocInfo("Обслуживание принтера", None, "RAW"))):
            raise ctypes.WinError(ctypes.get_last_error())
        wp.StartPagePrinter(h)
        n = wt.DWORD(0)
        buf = ctypes.create_string_buffer(data, len(data))
        ok = wp.WritePrinter(h, buf, len(data), ctypes.byref(n))
        wp.EndPagePrinter(h)
        wp.EndDocPrinter(h)
        if not ok or n.value != len(data):
            raise OSError("Принтер принял %d из %d байт" % (n.value, len(data)))
    finally:
        wp.ClosePrinter(h)
