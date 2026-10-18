[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | **Татарча**

# PhotoCrop (КопиТехник PRINT)

Windows өчен программа: фотоларны кадрлау һәм бастыру (10×15 см һәм башка форматлар), акыллы кадрлау, төс төзәтү, төс профильләре, басма урнаштыру һәм ИИ-агент режимы.

**License: not selected (лицензия сайланмаган).**

## Screenshots

<p align="center"><img src="docs/promo.gif" alt="PhotoCrop animated overview" width="760"></p>

![PhotoCrop main window: crop frame on a demo photo](docs/screenshots/main-window.png)

![Colour adjustments page](docs/screenshots/color-adjustments.png)

![Print sheet with 4 photos per sheet](docs/screenshots/print-sheet.png)

| Arabic (right-to-left) | Japanese |
|---|---|
| ![Arabic interface](docs/screenshots/main-window-arabic-rtl.png) | ![Japanese interface](docs/screenshots/main-window-japanese.png) |
## Мөмкинлекләр

- Басма форматлары: 10×15, 9×13, 13×18, 15×21, 20×30, 30×40 см, A5, A4, A3, A3+, A2 (битне тутырып кадрлау яки фотоны тулысынча сыйдыру).
- Акыллы кадрлау: йөзләр (YuNet), кешеләр һәм өй хайваннары (YOLOX), поза модуле; рамканы кул белән дә бирергә була.
- Һәр фото өчен төс төзәтү: яктылык, контраст, гамма, күләгәләр/яктылар, туендырылганлык, температура/төсмер, RGB, авто, ак-кара, сепия, шау-шуны киметү, ачыклык.
- Төс белән идарә итү: принтерның ICC профиле һәм Windows ICM күчергече.
- Басма планлаштыру: бер биттә берничә фото, һәр як өчен чыгым, һәр бит өчен аерым эш (эшләр арасында пауза), бастырыр алдыннан тикшерүләр (dpi, сыю).
- JPEG, TIFF, PNG һәм PDF форматларына саклау.
- ИИ-агент режимы: һәр этап JSON кайтаручы боерык булып тора (боерык юлы яки Claude Desktop өчен MCP-сервер). Карагыз: [AGENT.md](AGENT.md) (русча).
- Qt-версиянең интерфейс телләре: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча (көйләүләрдә сайлана; килешенгәнчә — система теле; гарәп теле уңнан сулга). Тәрҗемәләр төп экраннарны каплый, машина ярдәмендә эшләнгән һәм туган тел ияләре тарафыннан тикшерелмәгән; тәрҗемә ителмәгән язмалар инглизчә күрсәтелә.

## Урнаштыру

- Windows һәм Python 3.9+ («Add python.exe to PATH») яки `install.bat` эшләтегез: ул Python (булмаса), пакетларны урнаштыра һәм ярлыклар ясый. Интернет кирәк.
- Кул белән: `pip install -r requirements.txt`.

## Qt-версияне эшләтү

`run_qt.bat` өстенә ике тапкыр басыгыз (Pillow, pillow-heif, PySide6 урнаштыра һәм `photo_crop_qt.py` эшләтә). Үз-үзен тикшерү: `selftest_qt.bat`. Элекке Tkinter тәрәзәсе: `python photo_crop.py`.

### Танып белү модельләре

YuNet / YOLOX модельләре (~36 МБ) репозиторийга кермиләр; алар беренче эшләтүдә (яки `python smart_crop.py setup` белән) `%APPDATA%\PhotoCrop\models` папкасына йөкләнә.

## Агент режимы һәм MCP

Көйләү блогын алу өчен `mcp_config.bat` (яки `python photo_crop.py mcp-config`) эшләтегез, аны `claude_desktop_config.json` (`%APPDATA%\Claude\`) файлына өстәгез һәм Claude Desktop'ны яңадан кабызыгыз. Әзер exe өчен `mcpServers.photocrop` блогы болай күренә:

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

Төп боерыклар: `open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

Боерык юлыннан: `python photo_crop.py agent set_format format=10x15`; `python photo_crop.py agent --list` барлык боерыкларны күрсәтә. Хәл `%APPDATA%\PhotoCrop\agent_state.json` файлында саклана. `PHOTOCROP_AGENT_DRYRUN=1` үзгәрешлесе чын бастыруны тыя.

## exe төзү

`build_exe.bat` PyInstaller аша `PhotoCrop.exe` (Tkinter тәрәзәсе) һәм `PhotoCropAgent.exe` (консольле, MCP өчен) төзи. Игътибар: скрипт аннан соң `build\` папкасын һәм `.spec` файлларын бетерә. Qt-версия `pyinstaller PhotoCropQt.spec` → `dist\PhotoCropQt.exe` боерыгы белән төзелә. `v*` тегы GitHub Actions эшен (`.github/workflows/build.yml`) кабыза: ул `PhotoCropQt.exe` һәм `PhotoCropAgent.exe` төзи һәм аларны GitHub Release'ка беркетә.

## Лицензия

License: not selected (лицензия сайланмаган).
