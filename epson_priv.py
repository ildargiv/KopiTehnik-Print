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
    "L8050": {"border": 7700, "ccor": 188},
    # L18050: качество найдено по снимкам драйвера «Черновик/Стандарт/Высокое» (0/1/2); остальные смещения не сняты
    "L18050": {"quality": 7788},
}

# значения байта качества: порядок = порядок в списке программы
QUALITY_MODES = {"quality": [(0, "Черновик"), (1, "Стандарт"), (2, "Высокое")]}


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
            ba[pos] = int(value) & 0xFF
        return bytes(ba)

    def set_color_correction_off(self, blob, off=True):
        """Выключить цветокоррекцию драйвера (программа сама ведёт цвет по ICC)."""
        return self.set(blob, "ccor", CCOR_MANUAL if off else CCOR_AUTO)

    def color_correction_off(self, blob):
        v = self.get(blob, "ccor")
        return None if v is None else v == CCOR_MANUAL
