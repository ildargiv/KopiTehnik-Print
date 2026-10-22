**English** | [Русский](README.ru.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Татарча](README.tt.md)

# KopiTehnik Print

**Print software for small copy centers, photo desks and professional printers.** Customer photos and documents to paper in a minute: smart crop to any format, colour matched to your printer, PDF/Word/Excel/PowerPoint printing, and a tamper-evident sheet counter.

**Free, legal, no cracks, no malware.** A modern alternative to cracked photo-print tools: free for personal use and for a single workstation: copy shop, studio, workshop or independent printer. [Download for Windows](https://github.com/ildargiv/KopiTehnik-Print/releases/latest) · 20 interface languages · no Python needed

- **One window for photo and document jobs**, each with its own printer profile and paper.
- **Fast orders**: 10×15 cm to A2, up to 30 photos per sheet, automatic orientation, pre-flight check (dpi, fit).
- **Colour you can trust**: per-photo corrections, printer ICC profiles, printer correction, borderless edge test.
- **Know your numbers**: sheets printed per day, by printer and paper size, CSV export, admin password.
- **AI helper (optional)**: every step is a JSON command, and an MCP server lets Claude Desktop prepare and print a customer's folder.

License: free for personal use and for a business with one workstation at one location; more workstations, chains and resale need a commercial licence. See [LICENSE](LICENSE).

## Screenshots

<p align="center"><img src="docs/promo.gif" alt="PhotoCrop animated overview" width="760"></p>

![PhotoCrop main window: crop frame on a demo photo](docs/screenshots/main-window.png)

![Colour adjustments page](docs/screenshots/color-adjustments.png)

![Print sheet with 4 photos per sheet](docs/screenshots/print-sheet.png)

| Arabic (right-to-left) | Japanese |
|---|---|
| ![Arabic interface](docs/screenshots/main-window-arabic-rtl.png) | ![Japanese interface](docs/screenshots/main-window-japanese.png) |
## Features

- Print formats: 10×15, 9×13, 13×18, 15×21, 20×30, 30×40 cm, A5, A4, A3, A3+, A2 (crop to fill the sheet or fit the whole photo).
- Smart crop: face detection (YuNet), people and pets (YOLOX), pose model; the frame can also be set by hand.
- Per-photo colour correction: brightness, contrast, gamma, shadows/highlights, saturation, temperature/tint, RGB, auto, black-and-white, sepia, denoise, sharpening.
- Colour management: printer ICC profile and a Windows ICM switch.
- Print planning: several photos per sheet, per-side bleed, one job per sheet with a pause between jobs, pre-print checks (dpi, fit).
- Export to JPEG, TIFF, PNG and PDF.
- Document mode (the PHOTO / DOCUMENT switch at the top): print PDF, Word, Excel and PowerPoint files with their own printer profile and paper settings, page range, copies, fit or fill. Editing and text recognition (OCR) open in the separate KopiTehnik Converter (install it separately; the program finds it by itself).
- Photos per sheet: 1 to 30 (quick buttons for 1, 2, 3, 4, 6, 8, 9, 12, 16, 24 or type any number); orientation of each photo is detected automatically.
- Updates: the program checks the latest GitHub release (switchable in Settings) and offers to open the download page.
- Print counter (Settings): printed sheets today for everyone (photos and documents separately); a detailed journal (by printer, paper size for photos and documents separately, source, last 14 days, CSV export) behind an administrator password with a recovery key. The journal is tamper-evident. It counts sheets sent to the printer from the program and by the AI agent.
- Edge-to-edge test sheet (borderless print check) with captions in five languages.
- AI-agent mode: every step is a command returning JSON (command line or MCP server for Claude Desktop). See [AGENT.md](AGENT.md) (in Russian).
- Interface languages in the Qt version: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча (chosen in Settings; by default the system language, Russian for ru, otherwise English; Arabic is right-to-left). The translations cover the main screens and are machine-made, not yet reviewed by native speakers; untranslated strings appear in English.

## Installation

- Easiest: download `PhotoCropQt.exe` (GUI) or `PhotoCropAgent.exe` (AI-agent / MCP) from the [Releases page](https://github.com/ildargiv/KopiTehnik-Print/releases/latest) and run it. No Python needed.
- Windows with Python 3.9+ ("Add python.exe to PATH"), or run `install.bat`: it installs Python (if missing), the packages and creates shortcuts. Internet is required.
- Manual install: `pip install -r requirements.txt`.

## Running the Qt version

Double-click `run_qt.bat` (installs Pillow, pillow-heif, PySide6 and starts `photo_crop_qt.py`). Self-test: `selftest_qt.bat`. The older Tkinter window: `python photo_crop.py`.

### Detection models

The YuNet / YOLOX models (~36 MB) are not included in the repository; they are downloaded on first use (or with `python smart_crop.py setup`) to `%APPDATA%\PhotoCrop\models`.

## AI-agent mode and MCP

Run `mcp_config.bat` (or `python photo_crop.py mcp-config`) to get the config block, add it to `claude_desktop_config.json` (`%APPDATA%\Claude\`), then restart Claude Desktop. For the built exe the `mcpServers.photocrop` block looks like this:

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

Main commands: `open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

Command line: `python photo_crop.py agent set_format format=10x15`; `python photo_crop.py agent --list` lists all commands. State is stored in `%APPDATA%\PhotoCrop\agent_state.json`. Setting `PHOTOCROP_AGENT_DRYRUN=1` forbids real printing.

## Building exe files

`build_exe.bat` builds `PhotoCrop.exe` (Tkinter window) and `PhotoCropAgent.exe` (console, for MCP) with PyInstaller. Note: the script deletes `build\` and the `.spec` files afterwards. The Qt version is built with `pyinstaller PhotoCropQt.spec` → `dist\PhotoCropQt.exe`. Pushing a tag `v*` runs the GitHub Actions workflow (`.github/workflows/build.yml`), which builds `PhotoCropQt.exe` and `PhotoCropAgent.exe` and attaches them to a GitHub Release.

## License

License: [KopiTehnik Print Free-Use License](LICENSE) (draft): free for personal use and for a business with one workstation at one location; more workstations, chains and resale need a commercial licence.
