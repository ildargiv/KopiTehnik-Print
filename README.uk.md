[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | **Українська** | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Татарча](README.tt.md)

# PhotoCrop (КопиТехник PRINT)

Програма для Windows: кадрування та друк фотографій (10×15 см та інші формати), розумне кадрування, корекція кольору, колірні профілі, розкладка друку та режим ШІ-агента.

**License: not selected (ліцензію не обрано).**

## Screenshots

<p align="center"><img src="docs/promo.gif" alt="PhotoCrop animated overview" width="760"></p>

![PhotoCrop main window: crop frame on a demo photo](docs/screenshots/main-window.png)

![Colour adjustments page](docs/screenshots/color-adjustments.png)

![Print sheet with 4 photos per sheet](docs/screenshots/print-sheet.png)

| Arabic (right-to-left) | Japanese |
|---|---|
| ![Arabic interface](docs/screenshots/main-window-arabic-rtl.png) | ![Japanese interface](docs/screenshots/main-window-japanese.png) |
## Можливості

- Формати друку: 10×15, 9×13, 13×18, 15×21, 20×30, 30×40 см, A5, A4, A3, A3+, A2 (кадрувати із заповненням аркуша або вписати повністю).
- Розумне кадрування: обличчя (YuNet), люди й тварини (YOLOX), модель пози; рамку можна задати й вручну.
- Корекція кольору кожного фото: яскравість, контраст, гама, тіні/світла, насиченість, температура/відтінок, RGB, авто, чорно-біле, сепія, шумозаглушення, різкість.
- Керування кольором: ICC-профіль принтера та перемикач Windows ICM.
- Планування друку: кілька фото на аркуші, випуск за кожен бік, окреме завдання на кожен аркуш із паузою, перевірки перед друком (dpi, розміщення).
- Збереження у JPEG, TIFF, PNG і PDF.
- Режим ШІ-агента: кожен етап доступний командою з відповіддю у JSON (командний рядок або MCP-сервер для Claude Desktop). Див. [AGENT.md](AGENT.md) (російською).
- Мови інтерфейсу Qt-версії: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча (вибір у Налаштуваннях; типово мова системи; арабська — справа наліво). Переклади охоплюють основні екрани, зроблені машинно й ще не перевірені носіями мови; неперекладені написи показуються англійською.

## Встановлення

- Windows і Python 3.9+ («Add python.exe to PATH») або запустіть `install.bat`: він встановить Python (якщо немає), пакети й створить ярлики. Потрібен інтернет.
- Вручну: `pip install -r requirements.txt`.

## Запуск Qt-версії

Двічі клацніть `run_qt.bat` (встановлює Pillow, pillow-heif, PySide6 і запускає `photo_crop_qt.py`). Самоперевірка: `selftest_qt.bat`. Попереднє вікно на Tkinter: `python photo_crop.py`.

### Моделі розпізнавання

Моделі YuNet / YOLOX (~36 МБ) не входять до репозиторію; вони завантажуються під час першого запуску (або командою `python smart_crop.py setup`) до `%APPDATA%\PhotoCrop\models`.

## Режим агента та MCP

Запустіть `mcp_config.bat` (або `python photo_crop.py mcp-config`), щоб отримати блок налаштувань, додайте його до `claude_desktop_config.json` (`%APPDATA%\Claude\`) і перезапустіть Claude Desktop. Для готового exe блок `mcpServers.photocrop` виглядає так:

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

Основні команди: `open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

З командного рядка: `python photo_crop.py agent set_format format=10x15`; `python photo_crop.py agent --list` — список усіх команд. Стан зберігається в `%APPDATA%\PhotoCrop\agent_state.json`. Змінна `PHOTOCROP_AGENT_DRYRUN=1` забороняє реальний друк.

## Збирання exe

`build_exe.bat` збирає через PyInstaller `PhotoCrop.exe` (вікно на Tkinter) і `PhotoCropAgent.exe` (консольний, для MCP). Увага: після збирання скрипт видаляє `build\` і файли `.spec`. Qt-версія збирається командою `pyinstaller PhotoCropQt.spec` → `dist\PhotoCropQt.exe`. Тег `v*` запускає GitHub Actions (`.github/workflows/build.yml`): він збирає `PhotoCropQt.exe` і `PhotoCropAgent.exe` та додає їх до GitHub Release.

## Ліцензія

License: not selected (ліцензію не обрано).
