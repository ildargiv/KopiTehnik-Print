[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | **Italiano** | [Polski](README.pl.md) | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Татарча](README.tt.md)

# PhotoCrop (КопиТехник PRINT)

Programma Windows per ritagliare e stampare foto (10×15 cm e altri formati), con ritaglio intelligente, correzione del colore, profili colore, impaginazione di stampa e modalità agente IA.

**License: [KopiTehnik Print Licence](LICENSE)**

## Screenshots

<p align="center"><img src="docs/promo.gif" alt="PhotoCrop animated overview" width="760"></p>

![PhotoCrop main window: crop frame on a demo photo](docs/screenshots/main-window.png)

![Colour adjustments page](docs/screenshots/color-adjustments.png)

![Print sheet with 4 photos per sheet](docs/screenshots/print-sheet.png)

| Arabic (right-to-left) | Japanese |
|---|---|
| ![Arabic interface](docs/screenshots/main-window-arabic-rtl.png) | ![Japanese interface](docs/screenshots/main-window-japanese.png) |
## Funzionalità

- Formati di stampa: 10×15, 9×13, 13×18, 15×21, 20×30, 30×40 cm, A5, A4, A3, A3+, A2 (ritaglia per riempire il foglio o adatta l'intera foto).
- Ritaglio intelligente: rilevamento dei volti (YuNet), persone e animali (YOLOX), modello di posa; il riquadro si può impostare anche a mano.
- Correzione colore per foto: luminosità, contrasto, gamma, ombre/alteluci, saturazione, temperatura/tinta, RGB, auto, bianco e nero, seppia, riduzione del rumore, nitidezza.
- Gestione del colore: profilo ICC della stampante e interruttore Windows ICM.
- Pianificazione della stampa: più foto per foglio, abbondanza per lato, un lavoro per foglio con pausa, controlli prima della stampa (dpi, adattamento).
- Esportazione in JPEG, TIFF, PNG e PDF.
- Modalità agente IA: ogni passaggio è un comando che restituisce JSON (riga di comando o server MCP per Claude Desktop). Vedi [AGENT.md](AGENT.md) (in russo).
- Lingue dell'interfaccia della versione Qt: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча (si scelgono nelle Impostazioni; per impostazione predefinita la lingua di sistema; l'arabo è da destra a sinistra). Le traduzioni coprono le schermate principali, sono automatiche e non ancora riviste da madrelingua; i testi non tradotti appaiono in inglese.

## Installazione

- Windows con Python 3.9+ («Add python.exe to PATH») oppure esegui `install.bat`: installa Python (se manca), i pacchetti e crea i collegamenti. Serve internet.
- Installazione manuale: `pip install -r requirements.txt`.

## Avviare la versione Qt

Fai doppio clic su `run_qt.bat` (installa Pillow, pillow-heif, PySide6 e avvia `photo_crop_qt.py`). Autotest: `selftest_qt.bat`. La vecchia finestra Tkinter: `python photo_crop.py`.

### Modelli di rilevamento

I modelli YuNet / YOLOX (~36 MB) non sono nel repository; vengono scaricati al primo utilizzo (o con `python smart_crop.py setup`) in `%APPDATA%\PhotoCrop\models`.

## Modalità agente e MCP

Esegui `mcp_config.bat` (o `python photo_crop.py mcp-config`) per ottenere il blocco di configurazione, aggiungilo a `claude_desktop_config.json` (`%APPDATA%\Claude\`) e riavvia Claude Desktop. Per l'exe compilato il blocco `mcpServers.photocrop` è:

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

Comandi principali: `open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

Riga di comando: `python photo_crop.py agent set_format format=10x15`; `python photo_crop.py agent --list` elenca tutti i comandi. Lo stato è salvato in `%APPDATA%\PhotoCrop\agent_state.json`. `PHOTOCROP_AGENT_DRYRUN=1` vieta la stampa reale.

## Compilare gli exe

`build_exe.bat` compila con PyInstaller `PhotoCrop.exe` (finestra Tkinter) e `PhotoCropAgent.exe` (console, per MCP). Attenzione: lo script poi elimina `build\` e i file `.spec`. La versione Qt si compila con `pyinstaller PhotoCropQt.spec` → `dist\PhotoCropQt.exe`. Un tag `v*` avvia il workflow GitHub Actions (`.github/workflows/build.yml`), che compila `PhotoCropQt.exe` e `PhotoCropAgent.exe` e li allega a una GitHub Release.

## Licenza

License: [KopiTehnik Print Licence](LICENSE)
