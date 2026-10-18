[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | **Polski** | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Татарча](README.tt.md)

# PhotoCrop (КопиТехник PRINT)

Program dla Windows do kadrowania i drukowania zdjęć (10×15 cm i inne formaty) z inteligentnym kadrowaniem, korekcją kolorów, profilami barwnymi, układem wydruku i trybem agenta AI.

**License: not selected (nie wybrano licencji).**

## Screenshots

<p align="center"><img src="docs/promo.gif" alt="PhotoCrop animated overview" width="760"></p>

![PhotoCrop main window: crop frame on a demo photo](docs/screenshots/main-window.png)

![Colour adjustments page](docs/screenshots/color-adjustments.png)

![Print sheet with 4 photos per sheet](docs/screenshots/print-sheet.png)

| Arabic (right-to-left) | Japanese |
|---|---|
| ![Arabic interface](docs/screenshots/main-window-arabic-rtl.png) | ![Japanese interface](docs/screenshots/main-window-japanese.png) |
## Funkcje

- Formaty wydruku: 10×15, 9×13, 13×18, 15×21, 20×30, 30×40 cm, A5, A4, A3, A3+, A2 (kadrowanie z wypełnieniem arkusza lub dopasowanie całego zdjęcia).
- Inteligentne kadrowanie: wykrywanie twarzy (YuNet), osób i zwierząt (YOLOX), model pozy; ramkę można też ustawić ręcznie.
- Korekcja kolorów dla każdego zdjęcia: jasność, kontrast, gamma, cienie/światła, nasycenie, temperatura/odcień, RGB, auto, czerń i biel, sepia, redukcja szumu, wyostrzanie.
- Zarządzanie kolorem: profil ICC drukarki i przełącznik Windows ICM.
- Planowanie wydruku: wiele zdjęć na arkuszu, spad z każdej strony, osobne zadanie dla każdego arkusza z przerwą, kontrole przed wydrukiem (dpi, dopasowanie).
- Eksport do JPEG, TIFF, PNG i PDF.
- Tryb agenta AI: każdy krok to polecenie zwracające JSON (wiersz poleceń lub serwer MCP dla Claude Desktop). Zobacz [AGENT.md](AGENT.md) (po rosyjsku).
- Języki interfejsu wersji Qt: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча (wybór w Ustawieniach; domyślnie język systemu; arabski od prawej do lewej). Tłumaczenia obejmują główne ekrany, są maszynowe i nie zostały jeszcze sprawdzone przez native speakerów; nieprzetłumaczone teksty pojawiają się po angielsku.

## Instalacja

- Windows z Pythonem 3.9+ („Add python.exe to PATH”) lub uruchom `install.bat`: instaluje Pythona (jeśli brak), pakiety i tworzy skróty. Wymagany internet.
- Instalacja ręczna: `pip install -r requirements.txt`.

## Uruchamianie wersji Qt

Kliknij dwukrotnie `run_qt.bat` (instaluje Pillow, pillow-heif, PySide6 i uruchamia `photo_crop_qt.py`). Autotest: `selftest_qt.bat`. Starsze okno Tkinter: `python photo_crop.py`.

### Modele detekcji

Modele YuNet / YOLOX (~36 MB) nie są w repozytorium; pobierane są przy pierwszym użyciu (lub poleceniem `python smart_crop.py setup`) do `%APPDATA%\PhotoCrop\models`.

## Tryb agenta i MCP

Uruchom `mcp_config.bat` (lub `python photo_crop.py mcp-config`), aby uzyskać blok konfiguracji, dodaj go do `claude_desktop_config.json` (`%APPDATA%\Claude\`) i uruchom ponownie Claude Desktop. Dla zbudowanego exe blok `mcpServers.photocrop` wygląda tak:

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

Główne polecenia: `open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

Wiersz poleceń: `python photo_crop.py agent set_format format=10x15`; `python photo_crop.py agent --list` wypisuje wszystkie polecenia. Stan jest zapisany w `%APPDATA%\PhotoCrop\agent_state.json`. `PHOTOCROP_AGENT_DRYRUN=1` blokuje prawdziwe drukowanie.

## Budowanie plików exe

`build_exe.bat` buduje przez PyInstaller `PhotoCrop.exe` (okno Tkinter) i `PhotoCropAgent.exe` (konsola, dla MCP). Uwaga: skrypt potem usuwa `build\` i pliki `.spec`. Wersję Qt buduje się poleceniem `pyinstaller PhotoCropQt.spec` → `dist\PhotoCropQt.exe`. Wypchnięcie tagu `v*` uruchamia workflow GitHub Actions (`.github/workflows/build.yml`), który buduje `PhotoCropQt.exe` i `PhotoCropAgent.exe` i dołącza je do GitHub Release.

## Licencja

License: not selected (nie wybrano licencji).
