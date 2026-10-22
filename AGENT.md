# Управление PhotoCrop с помощью ИИ-агента

Агент управляет **всеми** этапами без окна и «без зрения»: каждая команда возвращает JSON с цифрами
(размеры, dpi, положение рамки, раскладка листов, статистика яркости/резкости, состояние принтера и очереди).
Картинку можно запросить при желании (`preview_photo` / `render_sheet` с `inline=true`).

## Как подключить

**1. Claude Desktop (MCP) — рекомендуется. Агент работает с самим окном программы.**
Установщик `KopiTehnikPrint-Setup-<версия>.exe` предлагает пункт «Подключить ИИ-агента (MCP) к Claude Desktop» (отмечен по умолчанию):
он записывает сервер `photocrop` в `%APPDATA%\Claude\claude_desktop_config.json` (рядом остаётся копия `.bak`) и включает приём
подключений в окне. Перезапустите Claude Desktop. Всё то же можно сделать позже: Настройки → «ИИ-агент (MCP)» → «Подключить к Claude Desktop».
Для другого клиента MCP: кнопка «Скопировать настройку MCP» или `PhotoCropQt.exe mcp-config`; запуск сервера: `PhotoCropQt.exe mcp`.

Как это устроено: окно программы поднимает сервер на `127.0.0.1` (только этот компьютер, ключ в `%APPDATA%\PhotoCrop\agent_endpoint.json`), а
`PhotoCropQt.exe mcp` пересылает в него запросы клиента. Агент видит и меняет то же, что человек: открытые фото, рамки, коррекцию, формат,
раскладку листа, принтер, документ. Изменения видны в окне сразу, Ctrl+Z их отменяет, вверху виден значок «ИИ-агент работает».
Если окно не запущено, `PhotoCropQt.exe mcp` работает само по себе, без окна, со своим состоянием (`agent_state.json`), как раньше.
Права агента задаёт человек в Настройках: печатать или нет, максимум листов за одну печать, спрашивать ли подтверждение перед печатью.
По умолчанию права полные.

**Быстрая работа:** `batch` (несколько команд за вызов), `contact_sheet` и `compare_photo` (картинки), `analyze_photos` (сводка по серии), `white_balance` (по эталону, точка или область), `set_adjust` с `relative=true`, `flip_photo` (отражение), `list_icc_profiles` (имя профиля вместо пути).

**Правило владельца:** по возможности настраивайте всё вручную (`set_crop`, `set_adjust`, параметры листа и печати), а автоматику
(`enhance`, `auto_adjust`, `auto_levels`, `auto_crop`, умная рамка) используйте только если владелец сам об этом попросил.

Инструменты окна (сверх команд движка): `app_state`, `app_guide`, `open_files`, `check_photos`, `remove_unchecked`, `enhance`
(«Улучшить» и «Супер»), `auto_levels`, `color_presets` / `color_preset_save` / `color_preset_apply`, `copy_adjust` / `paste_adjust`,
`set_layout`, `set_view`, `set_app_mode`, `add_edge_test`, `print_photos` / `print_status`, `doc_open` / `doc_info` / `doc_set` /
`doc_print` / `doc_convert`, `app_settings`, `print_stats`, `check_update`. Справка для самого агента: `app_guide` и ресурс `photocrop://guide`.

**2. Командная строка / любой агент с доступом к shell:**

    python photo_crop.py agent open_folder path="C:\Фото"
    python photo_crop.py agent set_format format=10x15
    python photo_crop.py agent '{"cmd":"set_crop","photo":0,"cx":0.4,"scale":0.8}'
    python photo_crop.py agent --file сценарий.json      # список команд
    python photo_crop.py agent --serve                    # JSON-строка на входе -> JSON-строка на выходе
    python photo_crop.py agent --list                     # все команды

Состояние (папка, рамки, настройки) сохраняется между вызовами в `%APPDATA%\PhotoCrop\agent_state.json`;
`--fresh` — начать с нуля. Окно программы открывает это же состояние кнопкой «📂 Открыть проект».
Журнал команд: `%APPDATA%\PhotoCrop\agent.log` (команда `get_log`).

## Типовой сценарий

    open_folder → set_format → auto_crop / set_crop / set_adjust (analyze_photo, preview_photo — проверка числами)
    → set_color_profile → select_printer → set_driver_settings → set_print_options
    → plan_print → render_sheet → preflight → print (wait=false) → job_status / wait_queue / queue

## Безопасность

* `print` сам вызывает проверки; `dry_run=true` — только проверка; `max_sheets` (по умолчанию 200) ограничивает расход бумаги;
  `strict=true` — отказ при любых предупреждениях.
* Переменная `PHOTOCROP_AGENT_DRYRUN=1` запрещает реальную печать (всё считается, но на принтер не уходит).
* `PHOTOCROP_AGENT_ROOTS=C:\Фото;D:\Out` — агент работает только внутри этих папок.
* `PHOTOCROP_AGENT_DEBUG=1` — в ошибках `internal` добавляется трассировка.

## Важное про драйвер принтера

Через `set_driver_settings` доступны общедоступные поля Windows (ориентация, бумага, качество, цвет, тип носителя,
ICM и т.д.). Частные опции драйвера Epson (например, «Без цветокоррекции / No Color Adjustment») агент менять не может —
их один раз выставляют в окне «Свойства принтера» программы; настройки сохраняются и дальше подхватываются агентом.
`driver_capabilities` показывает, какие бумаги, лотки и типы носителей поддерживает драйвер.

## Цветокоррекция и папка вывода (добавлено)
- `set_adjust` (photo = ссылка, список или `"all"`): bright, contrast, gamma, shadows, highlights, sat, vib, temp, tint, r, g, b, auto (`contrast|color|bw|off`; `bw` — автоматически чёрно-белое с улучшением), bw, sepia, denoise, sharp, sharp_radius, sharp_thr, а также `levels`, `curves`, `selcol`; `reset=true` очищает.
  - `levels`: JSON-список из 4 строк (общий, R, G, B) по 5 чисел `[чёрная точка 0-254, гамма 0.1-10, белая точка 1-255, выход от, выход до]`; нейтрально `[0,1,255,0,255]`.
  - `curves`: 4 списка точек `[[вход, выход], ...]` (общий, R, G, B), вход и выход 0-255; нейтрально `[[0,0],[255,255]]`.
  - `selcol`: 6 строк (красный, жёлтый, зелёный, голубой, синий, пурпурный) по 3 числа `[оттенок, насыщенность, яркость]` от −100 до 100.
- `set_save_options`: `out_mode` = `orig` (рядом с каждым оригиналом, в подпапку `out_name`, по умолчанию «Готовые») или `custom` (папка `outdir`).
- `open_folder` пропускает только готовые результаты программы (папки «Готовые»/«Печать» + имя вида `_10x15`) и сообщает `skipped`; `save_files` возвращает `low_res_under_150dpi`.

## Печать по одному листу и подрезка по сторонам (новое)

В `print_options` (`set_print_options`, `list_formats`) добавлены параметры:

- `one_by_one` (по умолчанию `true`) — каждый лист (и каждая копия листа) уходит отдельным заданием печати, как в Epson Photo+.
- `job_pause` — пауза между заданиями, секунды (0–60, по умолчанию 2). Отмена работает и во время паузы.
- `bleed_l`, `bleed_t`, `bleed_r`, `bleed_b` — вылет/отступ по каждой стороне, мм (-10…10). Пусто — берётся общий `bleed`.
  Положительное значение продолжает фото за край листа настоящим содержимым; отрицательное — отступ (фото меньше листа,
  белое поле), им компенсируют принтер, который при печати без полей подрезает края.
