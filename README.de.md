[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | **Deutsch** | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Татарча](README.tt.md)

# PhotoCrop (КопиТехник PRINT)

Ein Windows-Programm zum Zuschneiden und Drucken von Fotos (10×15 cm und weitere Formate) mit intelligentem Zuschnitt, Farbkorrektur, Farbprofilen, Druckaufteilung und KI-Agent-Modus.

**License: not selected (keine Lizenz gewählt).**

## Funktionen

- Druckformate: 10×15, 9×13, 13×18, 15×21, 20×30, 30×40 cm, A5, A4, A3, A3+, A2 (Blatt füllend zuschneiden oder ganzes Foto einpassen).
- Intelligenter Zuschnitt: Gesichtserkennung (YuNet), Personen und Haustiere (YOLOX), Posenmodell; der Rahmen lässt sich auch manuell setzen.
- Farbkorrektur je Foto: Helligkeit, Kontrast, Gamma, Schatten/Lichter, Sättigung, Temperatur/Farbton, RGB, Auto, Schwarzweiß, Sepia, Rauschminderung, Schärfe.
- Farbmanagement: ICC-Profil des Druckers und Windows-ICM-Schalter.
- Druckplanung: mehrere Fotos pro Blatt, Beschnitt je Seite, ein Auftrag pro Blatt mit Pause, Prüfungen vor dem Druck (dpi, Passung).
- Export als JPEG, TIFF, PNG und PDF.
- KI-Agent-Modus: Jeder Schritt ist ein Befehl mit JSON-Antwort (Kommandozeile oder MCP-Server für Claude Desktop). Siehe [AGENT.md](AGENT.md) (auf Russisch).
- Oberflächensprachen der Qt-Version: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча (Auswahl in den Einstellungen; Standard ist die Systemsprache; Arabisch läuft von rechts nach links). Die Übersetzungen decken die Hauptbildschirme ab, sind maschinell erstellt und noch nicht von Muttersprachlern geprüft; nicht übersetzte Texte erscheinen auf Englisch.

## Installation

- Windows mit Python 3.9+ („Add python.exe to PATH“) oder `install.bat` ausführen: installiert Python (falls fehlend), die Pakete und legt Verknüpfungen an. Internet erforderlich.
- Manuell: `pip install -r requirements.txt`.

## Qt-Version starten

Doppelklick auf `run_qt.bat` (installiert Pillow, pillow-heif, PySide6 und startet `photo_crop_qt.py`). Selbsttest: `selftest_qt.bat`. Das ältere Tkinter-Fenster: `python photo_crop.py`.

### Erkennungsmodelle

Die Modelle YuNet / YOLOX (~36 MB) sind nicht im Repository; sie werden bei der ersten Nutzung (oder mit `python smart_crop.py setup`) nach `%APPDATA%\PhotoCrop\models` heruntergeladen.

## Agent-Modus und MCP

`mcp_config.bat` (oder `python photo_crop.py mcp-config`) ausführen, um den Konfigurationsblock zu erhalten, ihn in `claude_desktop_config.json` (`%APPDATA%\Claude\`) eintragen und Claude Desktop neu starten. Für die gebaute exe sieht der Block `mcpServers.photocrop` so aus:

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

Wichtige Befehle: `open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

Kommandozeile: `python photo_crop.py agent set_format format=10x15`; `python photo_crop.py agent --list` listet alle Befehle. Der Zustand liegt in `%APPDATA%\PhotoCrop\agent_state.json`. `PHOTOCROP_AGENT_DRYRUN=1` verbietet echten Druck.

## exe-Dateien bauen

`build_exe.bat` baut mit PyInstaller `PhotoCrop.exe` (Tkinter-Fenster) und `PhotoCropAgent.exe` (Konsole, für MCP). Achtung: Das Skript löscht danach `build\` und die `.spec`-Dateien. Die Qt-Version wird mit `pyinstaller PhotoCropQt.spec` gebaut → `dist\PhotoCropQt.exe`. Ein Tag `v*` startet den GitHub-Actions-Workflow (`.github/workflows/build.yml`), der `PhotoCropQt.exe` und `PhotoCropAgent.exe` baut und an ein GitHub Release anhängt.

## Lizenz

License: not selected (keine Lizenz gewählt).
