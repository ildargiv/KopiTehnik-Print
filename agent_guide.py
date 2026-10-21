# -*- coding: utf-8 -*-
"""Справка для ИИ-агента: что умеет программа и каким инструментом это делается. Отдаётся как инструкция MCP, ресурс
photocrop://guide и инструмент app_guide. Дополняя программу новой функцией, добавляйте её сюда и в GUI_SPEC (gui_agent.py)."""

INSTRUCTIONS = (
    "PhotoCrop («КопиТехник Принт»): programme for cropping, colour-correcting and printing photos (and printing documents) on a "
    "Windows PC. You are connected to the programme's OWN window: you see and change the same photos, frames, colour settings and "
    "print settings as the person at the screen, and they see your changes live (Ctrl+Z in the window undoes them). "
    "Start with app_state (what is open, current settings, your permissions) and app_guide (full list of features and which "
    "tool does what; topics: overview, photos, color, sheet, print, documents, settings, tips). Every command returns numbers, so "
    "you can check work without seeing the screen; preview_photo / render_sheet with inline=true return a picture. "
    "Typical flow: open_folder → set_format / set_layout → auto_crop or set_crop → enhance or set_adjust → set_color_profile → "
    "print_photos (the window's own print, same as the Print button) or the lower-level plan_print → render_sheet → preflight → print. "
    "You have full rights, including printing; the owner may limit printing in the programme settings (app_state shows the limits). "
    "Paper is loaded by the owner as needed: do not print test pages unprompted, and prefer one real print over many trials.")

OVERVIEW = """# PhotoCrop — обзор

Программа: кадрирование и печать фотографий и документов. Окно: сверху переключатель ФОТО / ДОКУМЕНТ, формат бумаги, вид «Кадр» / «Лист»;
слева миниатюры (отметка «+» — какие фото идут в печать и сохранение); справа вкладки: **Фото**, **Цвет**, **Умная рамка**, **Принтер**
(и **Документ** в режиме документов).

Вы работаете с тем же состоянием, что и человек у экрана. Любое ваше изменение видно сразу и отменяется кнопкой Ctrl+Z в окне.
Инструменты делятся на три группы:
1. Команды движка (open_folder, set_crop, set_adjust, set_color_profile, plan_print, print, queue, …) — подробности в `help`.
2. Инструменты окна (app_state, enhance, color presets, set_layout, print_photos, документы, настройки) — см. темы справки.
3. Справка: app_guide(topic) и ресурс photocrop://guide.

Темы: photos, color, sheet, print, documents, settings, tips.
"""

PHOTOS = """# Фото: открыть, выбрать, кадрировать

* **Открыть**: open_folder(path) — вся папка (recursive — с подпапками); open_files(paths, add) — отдельные файлы или добавить к открытым.
  Форматы: JPG, PNG, TIFF, BMP, WEBP, HEIC (нужна pillow-heif). Папки с результатами программы («Готовые», «Печать») пропускаются.
* **Выбрать**: select_photo(photo) — какое фото показано; check_photos(photos, on) — отметки «+» (что печатать и сохранять);
  remove_unchecked — убрать неотмеченные из списка (файлы на диске не трогаются). photo — индекс с 0, имя файла или его часть.
* **Рамка**: set_crop(cx, cy, scale, angle, orient, rotation, copies), move_crop, reset_crop, rotate_photo(90/180/270), set_copies.
  cx, cy — центр рамки в долях фото; scale — размер относительно наибольшей вписанной рамки; angle — наклон в градусах.
* **Автоматическая рамка**: auto_crop(method=center|focus|fill|smart). smart — умная рамка: находит лица, людей, питомцев и не режет их;
  результат по каждому фото: ok / note / check / manual и причины. Модели (~36 МБ) скачиваются при первом использовании.
* **Анализ**: analyze_photo (яркость, перекрытые света и тени, контраст, насыщенность, резкость, точка фокуса), photo_info (размеры, dpi
  при печати, часть рамки вне фото), preview_photo (картинка результата). Малое разрешение (< 150 dpi) — предупреждение в проверках.
* **Формат бумаги и ориентация**: set_format (10×15, 9×13, 13×18, 15×21, 20×30, 30×40, A5, A4, A3, A3+, A2), set_orientation, set_mode
  (crop — заполнить лист; fit — вписать целиком с белыми полями).
* **Отмена**: undo / redo — те же, что Ctrl+Z / Ctrl+Y в окне.
"""

COLOR = """# Цвет

Коррекция хранится у каждого фото отдельно. Порядок обработки: уровни и кривые идут после основных ползунков; выборочный цвет — после
насыщенности и красочности, до чёрно-белого.

* **set_adjust** (photo = ссылка, список или "all"): bright, contrast, gamma, shadows, highlights, sat, vib (красочность: тянет
  приглушённые цвета, кожу бережёт), temp (холоднее ← → теплее), tint, r, g, b, auto (contrast | color | bw | off), bw, sepia,
  denoise, sharp, sharp_radius, sharp_thr, а также:
  - **levels** — 4 строки (общий, R, G, B) по 5 чисел [чёрная точка 0–254, гамма 0.1–10, белая точка 1–255, выход от, выход до];
    нейтрально [0,1,255,0,255]. Сначала применяется канал, потом общая строка.
  - **curves** — 4 списка точек [[вход, выход], …] (общий, R, G, B); нейтрально [[0,0],[255,255]]; плавная монотонная кривая.
  - **selcol** — 6 строк (красный, жёлтый, зелёный, голубой, синий, пурпурный) по [оттенок, насыщенность, яркость] от −100 до 100;
    оттенок ±100 = ±30°; серые тона почти не меняются.
  reset=true очищает коррекцию.
* **enhance(level, photos)** — кнопки «Улучшить» (1) и «Супер» (2): подбирает коррекцию под фотопечать на струйном принтере Epson для
  каждого фото отдельно. Уровни (чёрная и белая точки по краям гистограммы, гамма вместо яркости), мягкая S-кривая, выборочный цвет
  по составу кадра (небо, зелень, кожа), красочность, шумоподавление, резкость. **Прежняя коррекция фото сбрасывается целиком.**
  Если цвета выходят за охват принтера, красочность уменьшается. После enhance можно донастроить set_adjust, а увидеть результат —
  analyze_photo / preview_photo.
* auto_levels — «Авто» в уровнях (растяжение по краям гистограммы). auto_adjust — осторожные яркость и контраст по статистике.
* **Пресеты цвета** (три кнопки «Пресет 1/2/3», у каждой можно задать своё имя): color_preset_save(n) запоминает текущую коррекцию, color_preset_apply(n) применяет,
  color_presets показывает. Хранятся в настройках программы до следующего сохранения.
* copy_adjust / paste_adjust(all) — скопировать коррекцию с фото и вставить в другое или во все отмеченные.
* **Цветовой профиль принтера (ICC)**: set_color_profile(on, icc, intent, bpc, embed), get_color_profile. Экранная имитация печати в окне
  включается человеком; вам она не нужна — используйте цифры.
* Область действия коррекции в окне — «это фото» или «все отмеченные»; ваши команды сами задают photo.
"""

SHEET = """# Лист: сколько фото на листе, поля

* set_layout(nup 1–30, borders, border_mm, fill, free): фото на листе, белое поле по краю и между фото (borders + border_mm),
  fill — заполнять ячейки кадрированием. Ориентация каждого фото на листе определяется автоматически.
* set_view(crop|sheet) — вид «Кадр» или «Лист» (в «Листе» видно раскладку). В режиме листа фото можно переставлять; число листов
  показывает app_state.sheets_to_print.
* add_edge_test — тестовый лист для печати без рамок (подписи на пяти языках): проверить, обрезает ли принтер край.
* Вылеты (bleed) по сторонам и подрезка: set_print_options (bleed_*, margin_*) в движке.
"""

PRINT = """# Печать

Два пути:
1. **print_photos(which=current|checked, copies)** — как кнопка «Печать фото» в окне: листы собираются по настройкам окна (формат,
   фото на листе, поля, профиль принтера, вкладка «Принтер») и уходят на выбранный принтер. wait=true (по умолчанию) ждёт окончания
   отправки; print_status — печатает ли окно сейчас и чем закончилась последняя печать.
2. Команды движка: select_printer, set_driver_settings, set_print_options, plan_print (план листов), render_sheet (картинка листа),
   preflight (проверки: dpi, размещение, профиль), print (с max_sheets, dry_run, strict), queue / job_status / wait_queue /
   cancel_job / clear_queue / pause_printer — очередь и состояние принтера.

Принтер и драйвер общие для окна и агента: list_printers, select_printer(name) переключают принтер в окне; set_driver_settings
меняет бумагу, качество, тип носителя (общедоступные поля Windows). Частные опции драйвера Epson (например «No Color Adjustment»)
выставляются один раз человеком в окне «Свойства принтера», дальше подхватываются.
Печать учитывается в счётчике (источник «agent»). Если владелец ограничил печать (запрет, лимит листов), app_state и ошибка
покажут это; не пытайтесь обойти ограничение.
Физическое завершение печати — queue / wait_queue; «done» означает, что листы переданы в очередь.
"""

DOCUMENTS = """# Документы (режим ДОКУМЕНТ)

PDF, Word, Excel, PowerPoint: печать со своей бумагой и своим профилем принтера.
* doc_open(path) — открыть документ (переключает окно в режим документа); doc_info — состояние (страниц, бумага, поля, профиль).
* doc_set(paper, fit=fit|shrink|actual, margin, range, copies, cm_on, icc) — настройки печати документа. range: "1-3, 5, 8-" или пусто (все).
* doc_print — печать открытого документа на выбранный принтер (принтер тот же, что на вкладке «Принтер»).
* doc_convert(ocr) — открыть в программе «КопиТехник Конвертер» (редактирование PDF, распознавание текста), если она установлена.
* set_app_mode(photo|doc) — переключатель ФОТО / ДОКУМЕНТ.
"""

SETTINGS = """# Настройки, счётчик, обновления, права агента

* app_settings(get / set): язык, тема, анимация, подтверждения обычных действий (confirm_actions), проверка обновлений — только
  безопасные поля. Права агента (agent_allow_print, agent_max_sheets, agent_confirm_print) может менять только человек в окне:
  вы их читаете в app_state, но не меняете.
* print_stats — сколько листов напечатано сегодня (фото и документы). Подробный журнал защищён паролем администратора и вам недоступен.
* check_update — есть ли новая версия на GitHub.
* Сохранение файлов: set_save_options (dpi, тип JPEG/PNG/TIFF, качество, папка: рядом с фото в «Готовые» или своя), save_files.
  Проекты: save_project / load_project (рамки и настройки в JSON).
"""

TIPS = """# Советы

* Начинайте с app_state: он показывает режим, открытые фото, текущий формат, права и ограничения.
* Результат проверяйте числами (analyze_photo, photo_info, preflight), картинкой — реже (preview_photo inline=true).
* Любую серию правок человек может отменить Ctrl+Z; это обычные шаги отмены окна.
* Не меняйте то, о чём не просили: если человек правил фото руками, enhance сбросит его коррекцию — предупредите.
* Печать расходует бумагу и чернила: сначала plan_print / preflight, потом печать; для проверки раскладки хватит render_sheet.
* Ошибки команд имеют код и сообщение; ответ ok=false не означает сбой программы.
"""

TOPICS = {"overview": OVERVIEW, "photos": PHOTOS, "color": COLOR, "sheet": SHEET, "print": PRINT, "documents": DOCUMENTS,
          "settings": SETTINGS, "tips": TIPS}


def guide(topic=None):
    t = (topic or "overview").strip().lower()
    if t in ("all", "full"):
        return "\n\n".join(TOPICS.values())
    return TOPICS.get(t) or ("Unknown topic. Topics: " + ", ".join(TOPICS) + ", all")
