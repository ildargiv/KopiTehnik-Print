# -*- coding: utf-8 -*-
"""Частные настройки драйвера Epson внутри DEVMODE: «без полей», цветокоррекция, качество.

Смещения приватной зоны зависят от модели и версии драйвера, поэтому живут в таблице PROFILES.
Для незнакомой модели функции ничего не меняют (supported() == False), а не пишут наугад.
Свои смещения можно добавить в файл epson_profiles.json рядом с настройками программы.
Модуль не зависит от Windows: работает с готовым blob DEVMODE (bytes).
"""
import json
import struct

SRC_NORMAL, SRC_BORDERLESS = 261, 262      # dmDefaultSource: без этого драйвер сбрасывает флаг «без полей»
DM_DEFAULTSOURCE_OFFSET = 88               # DEVMODEW.dmDefaultSource
DM_FIELDS_OFFSET = 72
DM_DEFAULTSOURCE_FLAG = 0x200
CCOR_AUTO, CCOR_MANUAL = 1, 2              # «Автоматический» / «Настройка» (нейтральная = драйвер цвет не правит)

# ключи: border (байт, бит 0), ccor (байт), quality (байт; значения в "quality_values")
PROFILES = {
    "L8050": {"border": 7700, "ccor": 188, "maint": 1, "quality": 7788},
    # L18050: качество (0/1/2) найдено по снимкам драйвера, «без полей» и цветокоррекция сняты вручную через диалог — совпадают с L8050
    "L18050": {"quality": 7788, "border": 7700, "ccor": 188},
}

DM_MEDIATYPE_OFFSET = 196   # DEVMODEW.dmMediaType: 1 — простая бумага, остальное (396 и др.) — фото.
                            # priv+2088 для этого не годится: он зависит и от размера (на A5 всегда 0x10).

# байты режима качества (priv+offset: значение) и публичные поля (dmPrintQuality/dmYResolution @90/96),
# снятые с драйвера через его диалог. Ключ: (бумага, значение селектора priv+7788).
_PHOTO = {
    (("photo", 1)): {"priv": {124: 0x03, 150: 0x03, 154: 0x20, 2200: 0x00, 7765: 0x00, 7766: 0x00}},
    (("photo", 2)): {"priv": {124: 0x05, 150: 0x04, 154: 0x21, 2200: 0x00, 7765: 0x00, 7766: 0x00}},
}
QUALITY_SETS = {
    "L8050": {**_PHOTO, **{
        ("plain", 1): {"priv": {124: 0x02, 150: 0x03, 154: 0x2B, 2200: 0x01, 7765: 0xC0, 7766: 0x01}},
        ("plain", 2): {"priv": {124: 0x03, 150: 0x04, 154: 0x22, 2200: 0x00, 7765: 0x00, 7766: 0x00}},
    }},
    "L18050": {**_PHOTO, **{
        ("photo", 0): {"priv": {124: 0x02, 150: 0x01, 154: 0x01, 2200: 0x00, 7765: 0x40, 7766: 0x00},
                       "pub": {90: 0x68, 91: 0x01, 96: 0x68, 97: 0x01}},
    }},
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
    for tok in up.replace("(", " ").replace(")", " ").split():
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
    def __init__(self, printer_name, profiles=None):
        self.model = model_of(printer_name)
        self.map = (profiles or PROFILES).get(self.model or "", {})

    def supported(self, feature):
        return feature in self.map

    def _quality_patch(self, blob, value):
        """Набор байтов режима качества из реальных снимков драйвера: драйвер выводит байт 7788 из зеркальных
        байтов (+124, +150, +154 ...), поэтому одного селектора мало — иначе merge вернёт прежнее качество."""
        sets = QUALITY_SETS.get(self.model, {})
        media = struct.unpack_from("<I", blob, DM_MEDIATYPE_OFFSET)[0]
        paper = "plain" if media == 1 else "photo"
        return sets.get((paper, value)) or sets.get(("photo", value)) or {}

    def quality_modes(self):
        return QUALITY_MODES.get(self.model, []) if self.supported("quality") else []

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
        pos = self._pos(blob, feature)
        return bool(blob[pos] & 1) if feature == "border" else blob[pos]

    def set(self, blob, feature, value):
        """Возвращает новый blob. Нужно потом пропустить его через merge_devmode (драйвер досчитает поля)."""
        if not self.supported(feature):
            return bytes(blob)
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
