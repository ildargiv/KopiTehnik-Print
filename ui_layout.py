# -*- coding: utf-8 -*-
"""Расположение кнопок окна, которое администратор может менять (сам или через агента): порядок и скрытие.

Хранится в настройках: settings["ui_layout"] = {зона: {"order": [id, …], "hidden": [id, …]}}. Код программы не меняется,
«Сбросить» возвращает исходный вид. Зоны:
  tabs   — вкладки правой панели (порядок и скрытие);
  bottom — нижний ряд «Сохранить / Печать / …» (только порядок: видимость кнопок зависит от режима и сети);
  quick  — быстрые кнопки агента (порядок и скрытие).
Первая половина модуля без Qt (её проверяют тесты), вторая применяет расположение к окну.
"""

ZONES = {
    "tabs": {"items": ["layout", "color", "smart", "printer", "doc", "agent", "plot"], "hide": True,
             "title": "Tabs of the right panel"},
    "bottom": {"items": ["save", "print", "remote", "multi"], "hide": False, "title": "Bottom row of buttons"},
    "quick": {"items": ["improve", "crop", "prepare", "print"], "hide": True, "title": "Quick buttons of the agent"},
}
TITLES = {
    "tabs": {"layout": "Макет", "color": "Цвет", "smart": "Умная рамка", "printer": "Принтер", "doc": "Документ", "agent": "Агент", "plot": "Плоттер"},
    "bottom": {"save": "Сохранить", "print": "Печать", "remote": "Печать на другом ПК", "multi": "Несколько принтеров"},
    "quick": {"improve": "Улучшить", "crop": "Кадрировать", "prepare": "Подготовить", "print": "Печать"},
}
TAB_INDEX = {"layout": 0, "color": 1, "smart": 2, "printer": 3, "doc": 4, "agent": 5, "plot": 6}     # номер кнопки в seg_page (порядок создания)


def norm(cfg, zone):
    """(порядок, скрытые) зоны: сохранённое расположение, дополненное новыми кнопками и очищенное от неизвестных."""
    items = ZONES[zone]["items"]
    z = (cfg or {}).get(zone) if isinstance(cfg, dict) else None
    z = z if isinstance(z, dict) else {}
    order = [i for i in z.get("order") or [] if i in items]
    order = list(dict.fromkeys(order))
    for pos, i in enumerate(items):                              # кнопки, появившиеся в новой версии, встают на своё обычное место
        if i not in order:
            order.insert(min(pos, len(order)), i)
    hidden = [i for i in z.get("hidden") or [] if i in items] if ZONES[zone]["hide"] else []
    return order, list(dict.fromkeys(hidden))


def change(cfg, zone, order=None, hide=None, show=None):
    """Новое расположение зоны. order — желаемый порядок (можно часть: названные встают первыми), hide/show — списки id.
    Возвращает новый cfg; ошибки — ValueError с текстом для агента."""
    if zone not in ZONES:
        raise ValueError("unknown zone '%s'; zones: %s" % (zone, ", ".join(ZONES)))
    items = ZONES[zone]["items"]
    for name, lst in (("order", order), ("hide", hide), ("show", show)):
        if lst is None:
            continue
        if not isinstance(lst, (list, tuple)):
            raise ValueError("%s must be a list of ids" % name)
        bad = [i for i in lst if i not in items]
        if bad:
            raise ValueError("unknown item '%s' in zone %s; items: %s" % (bad[0], zone, ", ".join(items)))
    cur, hidden = norm(cfg, zone)
    if order:
        first = list(dict.fromkeys(order))
        cur = first + [i for i in cur if i not in first]
    if hide or show:
        if not ZONES[zone]["hide"]:
            raise ValueError("items of zone %s cannot be hidden, only reordered" % zone)
        hidden = [i for i in hidden if i not in (show or [])]
        hidden += [i for i in (hide or []) if i not in hidden]
        if zone == "tabs" and not [i for i in ("layout", "color", "smart", "printer") if i not in hidden]:
            raise ValueError("at least one of the tabs layout, color, smart, printer must stay visible")
    out = dict(cfg) if isinstance(cfg, dict) else {}
    out[zone] = {"order": cur, "hidden": hidden}
    return out


def describe(cfg):
    """Текущее расположение всех зон для агента."""
    out = {}
    for zone, z in ZONES.items():
        order, hidden = norm(cfg, zone)
        out[zone] = {"about": z["title"], "can_hide": z["hide"],
                     "items": [{"id": i, "title": TITLES[zone][i], "hidden": i in hidden} for i in order]}
    return out


# ---------------------------------------------------------------- применение к окну (Qt)

def _reorder(layout, widgets):
    """Ставит виджеты в layout в заданном порядке (остальные элементы layout не трогаем: они остаются впереди)."""
    for w in widgets:
        layout.removeWidget(w)
    for w in widgets:
        layout.addWidget(w)


def apply(win):
    """Расставляет кнопки окна по настройке. Вызывается после сборки окна и после каждого изменения."""
    cfg = win.settings.get("ui_layout")
    seg = getattr(win, "seg_page", None)
    if seg is not None:
        order, _hidden = norm(cfg, "tabs")
        btns = [seg.group.button(TAB_INDEX[i]) for i in order]
        _reorder(seg.layout(), btns)
        for b in btns:
            seg.layout().setStretchFactor(b, 1)
    row = getattr(win, "bottom_row", None)
    if row is not None:
        order, _h = norm(cfg, "bottom")
        ws = {"save": win.b_save, "print": win.b_print, "remote": win.b_remote, "multi": win.b_multi}
        _reorder(row, [ws[i] for i in order])
        for i in order:
            row.setStretchFactor(ws[i], 1 if i == "print" else 0)
    qc = getattr(win, "quick_chat", None)
    if qc is not None and getattr(qc, "chips_row", None) is not None:
        order, hidden = norm(cfg, "quick")
        _reorder(qc.chips_row, [qc.chips[i] for i in order])
        for i in order:
            qc.chips_row.setStretchFactor(qc.chips[i], len(qc.chips[i].text()))
            qc.chips[i].setVisible(i not in hidden)
    hide_tabs(win)


def hide_tabs(win):
    """Прячет вкладки, скрытые администратором. Только прячет: показом вкладок управляет режим окна (set_app_mode)."""
    seg = getattr(win, "seg_page", None)
    if seg is None:
        return
    _order, hidden = norm(win.settings.get("ui_layout"), "tabs")
    for i in hidden:
        seg.group.button(TAB_INDEX[i]).setVisible(False)


def set_layout(win, cfg):
    """Сохраняет новое расположение и сразу показывает его."""
    win.settings["ui_layout"] = cfg
    win.persist()
    mode = getattr(win, "app_mode", "photo")
    page = win.seg_page.value()                                  # открытая страница: вернём её, если её вкладка не скрыта
    win.set_app_mode(mode)                                       # вернуть обычную видимость вкладок, затем спрятать скрытые
    dock = getattr(win, "chat_dock", None)
    if dock is not None:
        dock.sync()
    apply(win)
    if page is not None and not win.seg_page.group.button(win.seg_page.values.index(page)).isHidden():
        win.show_page(page)
