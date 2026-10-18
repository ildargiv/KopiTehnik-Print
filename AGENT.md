# Управление PhotoCrop с помощью ИИ-агента

Агент управляет **всеми** этапами без окна и «без зрения»: каждая команда возвращает JSON с цифрами
(размеры, dpi, положение рамки, раскладка листов, статистика яркости/резкости, состояние принтера и очереди).
Картинку можно запросить при желании (`preview_photo` / `render_sheet` с `inline=true`).

## Как подключить

**1. Claude Desktop (MCP) — рекомендуется.** Запустите `mcp_config.bat` (или `python photo_crop.py mcp-config`),
вставьте выведенный блок `mcpServers` в `%APPDATA%\Claude\claude_desktop_config.json`, перезапустите Claude Desktop.
Для готового exe: `PhotoCropAgent.exe mcp` (собирается `build_exe.bat`; оконный PhotoCrop.exe stdio не имеет).

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
- `set_adjust` (photo = ссылка, список или `"all"`): bright, contrast, gamma, shadows, highlights, sat, vib, temp, tint, r, g, b, auto (`contrast|color|bw|off`; `bw` — автоматически чёрно-белое с улучшением), bw, sepia, denoise, sharp, sharp_radius, sharp_thr; `reset=true` очищает.
- `set_save_options`: `out_mode` = `orig` (рядом с каждым оригиналом, в подпапку `out_name`, по умолчанию «Готовые») или `custom` (папка `outdir`).
- `open_folder` пропускает только готовые результаты программы (папки «Готовые»/«Печать» + имя вида `_10x15`) и сообщает `skipped`; `save_files` возвращает `low_res_under_150dpi`.

## Печать по одному листу и подрезка по сторонам (новое)

В `print_options` (`set_print_options`, `list_formats`) добавлены параметры:

- `one_by_one` (по умолчанию `true`) — каждый лист (и каждая копия листа) уходит отдельным заданием печати, как в Epson Photo+.
- `job_pause` — пауза между заданиями, секунды (0–60, по умолчанию 2). Отмена работает и во время паузы.
- `bleed_l`, `bleed_t`, `bleed_r`, `bleed_b` — вылет/отступ по каждой стороне, мм (-10…10). Пусто — берётся общий `bleed`.
  Положительное значение продолжает фото за край листа настоящим содержимым; отрицательное — отступ (фото меньше листа,
  белое поле), им компенсируют принтер, который при печати без полей подрезает края.
