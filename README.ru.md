[English](README.md) | **Русский** | [Español](README.es.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Татарча](README.tt.md)

# PhotoCrop (КопиТехник PRINT)

Программа для Windows: кадрирование и печать фотографий (10×15 см и другие форматы), умное кадрирование, цветокоррекция, цветовые профили, раскладка печати и режим ИИ-агента.

**License: not selected (лицензия не выбрана).**

## Screenshots

<p align="center"><img src="docs/promo.gif" alt="PhotoCrop animated overview" width="760"></p>

![PhotoCrop main window: crop frame on a demo photo](docs/screenshots/main-window.png)

![Colour adjustments page](docs/screenshots/color-adjustments.png)

![Print sheet with 4 photos per sheet](docs/screenshots/print-sheet.png)

| Arabic (right-to-left) | Japanese |
|---|---|
| ![Arabic interface](docs/screenshots/main-window-arabic-rtl.png) | ![Japanese interface](docs/screenshots/main-window-japanese.png) |
## Возможности

- Форматы для печати: 10×15, 9×13, 13×18, 15×21, 20×30, 30×40 см, A5, A4, A3, A3+, A2 (кадрировать с заполнением листа или вписать целиком).
- Умное кадрирование: лица (YuNet), люди и питомцы (YOLOX), модель позы; рамку можно задать и вручную.
- Цветокоррекция каждого фото: яркость, контраст, гамма, тени/света, насыщенность, температура/оттенок, RGB, авто, чёрно-белое, сепия, шумоподавление, резкость.
- Управление цветом: ICC-профиль принтера и переключатель Windows ICM.
- Планирование печати: несколько фото на листе, вылет по каждой стороне, отдельное задание на каждый лист с паузой, проверки перед печатью (dpi, размещение).
- Сохранение в JPEG, TIFF, PNG и PDF.
- Режим «Документ» (переключатель ФОТО / ДОКУМЕНТ вверху): печать PDF, Word, Excel и PowerPoint со своим профилем принтера и настройками бумаги, диапазоном страниц, копиями, вписыванием или заполнением. Редактирование и распознавание текста (OCR) открываются в отдельной программе «КопиТехник Конвертер» (ставится отдельно, программа находит её сама).
- Фото на листе: от 1 до 30 (быстрые кнопки 1, 2, 3, 4, 6, 8, 9, 12, 16, 24 или любое число вручную); ориентация каждого фото определяется автоматически.
- Обновления: программа проверяет последний релиз на GitHub (отключается в настройках) и предлагает открыть страницу загрузки.
- Счётчик печати (Настройки): листы за сегодня видны всем (фото и документы отдельно); подробный журнал (по принтерам, размеру бумаги отдельно для фото и документов, источнику, 14 дней, экспорт в CSV) открывается по паролю администратора с ключом восстановления. Изменение журнала заметно. Считаются листы, отправленные на принтер из программы и ИИ-агентом.
- Тестовый лист для печати без рамок с подписями на пяти языках.
- Режим ИИ-агента: каждый этап доступен командой с ответом в JSON (командная строка или MCP-сервер для Claude Desktop). См. [AGENT.md](AGENT.md).
- Языки интерфейса Qt-версии: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча (выбираются в настройках; по умолчанию язык системы: для русского — русский, иначе английский; арабский — справа налево). Переводы охватывают основные экраны, сделаны машинно и не проверены носителями; непереведённые надписи показываются по-английски.

## Установка

- Windows и Python 3.9+ (отметьте «Add python.exe to PATH») либо запустите `install.bat`: он установит Python (если нет), пакеты и создаст ярлыки. Нужен интернет.
- Вручную: `pip install -r requirements.txt`.

## Запуск Qt-версии

Дважды щёлкните `run_qt.bat` (ставит Pillow, pillow-heif, PySide6 и запускает `photo_crop_qt.py`). Самопроверка: `selftest_qt.bat`. Прежнее окно на Tkinter: `python photo_crop.py`.

### Модели распознавания

Модели YuNet / YOLOX (~36 МБ) в репозиторий не входят; они скачиваются при первом запуске (или командой `python smart_crop.py setup`) в `%APPDATA%\PhotoCrop\models`.

## Режим агента и MCP

Запустите `mcp_config.bat` (или `python photo_crop.py mcp-config`), чтобы получить блок настроек, вставьте его в `claude_desktop_config.json` (`%APPDATA%\Claude\`) и перезапустите Claude Desktop. Для готового exe блок `mcpServers.photocrop` выглядит так:

```json
{
  "mcpServers": {
    "photocrop": {
      "command": "C:\\path\\to\\PhotoCropAgent.exe",
      "args": ["mcp"]
    }
  }
}
```

Основные команды: `open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

Из командной строки: `python photo_crop.py agent set_format format=10x15`; `python photo_crop.py agent --list` — список всех команд. Состояние хранится в `%APPDATA%\PhotoCrop\agent_state.json`. Переменная `PHOTOCROP_AGENT_DRYRUN=1` запрещает реальную печать.

## Сборка exe

`build_exe.bat` собирает через PyInstaller `PhotoCrop.exe` (окно на Tkinter) и `PhotoCropAgent.exe` (консольный, для MCP). Внимание: после сборки скрипт удаляет `build\` и файлы `.spec`. Qt-версия собирается командой `pyinstaller PhotoCropQt.spec` → `dist\PhotoCropQt.exe`. Тег `v*` запускает GitHub Actions (`.github/workflows/build.yml`): он собирает `PhotoCropQt.exe` и `PhotoCropAgent.exe` и прикладывает их к GitHub Release.

## Лицензия

License: not selected (лицензия не выбрана).
