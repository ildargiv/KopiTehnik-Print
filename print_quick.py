# -*- coding: utf-8 -*-
"""Быстрый старт печати: три кнопки с сохранёнными настройками принтера, бумаги и цвета.

Чистая логика без Qt: вид ячейки (пустая / привязана к принтеру / без привязки), нормализация
сохранённых данных, совместимость с другим принтером. Окно и применение — в photo_crop_qt.py.
"""

SLOTS = 3
GREEN, ORANGE, GRAY, RED = "green", "orange", "gray", "red"


def empty_slot(n):
    return {"name": "Быстрый старт %d" % (n + 1), "empty": True}


def norm_slots(raw):
    """Список ровно из SLOTS ячеек; мусор и недостающие заменяются пустыми."""
    out = []
    raw = raw if isinstance(raw, list) else []
    for i in range(SLOTS):
        s = raw[i] if i < len(raw) and isinstance(raw[i], dict) else None
        if not s or s.get("empty") or not isinstance(s.get("state"), dict):
            out.append(empty_slot(i))
            continue
        name = " ".join(str(s.get("name") or "").split())[:24] or "Быстрый старт %d" % (i + 1)
        out.append({"name": name, "bound": bool(s.get("bound")), "printer": str(s.get("printer") or ""),
                    "model": str(s.get("model") or ""), "state": s["state"]})
    return out


def status(slot, printers):
    """Цвет кнопки: green — настройка привязана к принтеру и он есть; orange — без привязки к принтеру;
    red — привязан, но принтер не найден; gray — ячейка пуста."""
    if slot.get("empty"):
        return GRAY
    if not slot.get("bound"):
        return ORANGE
    return GREEN if slot.get("printer") in (printers or []) else RED


def driver_compatible(slot, printer, model_of):
    """Можно ли применить сохранённые настройки драйвера (blob) к текущему принтеру: тот же принтер или та же модель."""
    if slot.get("empty") or not printer:
        return False
    if slot.get("printer") == printer:
        return True
    m = model_of(slot.get("printer", "")) or slot.get("model")
    return bool(m) and m == model_of(printer)
