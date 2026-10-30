# -*- coding: utf-8 -*-
"""Быстрый старт печати: до восьми кнопок с сохранёнными настройками принтера, бумаги и цвета.

Чистая логика без Qt: вид ячейки (пустая / привязана к принтеру / без привязки), нормализация
сохранённых данных, совместимость с другим принтером. Окно и применение — в photo_crop_qt.py.
"""

MAX_SLOTS = 8                                # столько ячеек хранится; сколько из них видно, выбирает пользователь (по умолчанию DEFAULT_VISIBLE)
SLOTS = MAX_SLOTS
DEFAULT_VISIBLE = 3
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


def norm_store(raw, printer=""):
    """Ячейки по принтерам: {имя очереди: [3 ячейки]}. Старый формат (один список на всех) переносится:
    привязанные ячейки — к своему принтеру, остальные — к текущему; занятое место не затирается."""
    store = {}
    if isinstance(raw, dict):
        for name, lst in raw.items():
            if isinstance(name, str) and isinstance(lst, list):
                store[name] = norm_slots(lst)
    elif isinstance(raw, list):
        for i, s in enumerate(norm_slots(raw)):
            if s.get("empty"):
                continue
            name = s["printer"] if s.get("bound") and s.get("printer") else printer
            s["bound"], s["printer"] = True, name
            row = store.setdefault(name, norm_slots(None))
            j = i if row[i].get("empty") else next((k for k, x in enumerate(row) if x.get("empty")), None)
            if j is not None:
                row[j] = s
    store.setdefault(printer, norm_slots(None))
    return store


def status(slot, printers):
    """Цвет кнопки: green — настройка привязана к принтеру и он есть; orange — без привязки к принтеру;
    red — привязан, но принтер не найден; gray — ячейка пуста."""
    if slot.get("empty"):
        return GRAY
    if not slot.get("bound"):
        return ORANGE
    return GREEN if slot.get("printer") in (printers or []) else RED


def driver_compatible(slot, printer, model_of, current_model=None):
    """Можно ли применить сохранённые настройки драйвера (blob) к текущему принтеру: та же очередь или та же модель.
    current_model — модель текущего принтера по драйверу (очередь могли переименовать)."""
    if slot.get("empty") or not printer:
        return False
    if slot.get("printer") == printer:
        return True
    m = slot.get("model") or model_of(slot.get("printer", ""))
    cur = current_model or model_of(printer)
    return bool(m) and m == cur
