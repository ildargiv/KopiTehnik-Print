[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | **Français** | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Татарча](README.tt.md)

# PhotoCrop (КопиТехник PRINT)

Programme Windows pour recadrer et imprimer des photos (10×15 cm et autres formats), avec recadrage intelligent, correction des couleurs, profils colorimétriques, mise en page d'impression et mode agent IA.

**License: [PolyForm Noncommercial 1.0.0](LICENSE)**

## Screenshots

<p align="center"><img src="docs/promo.gif" alt="PhotoCrop animated overview" width="760"></p>

![PhotoCrop main window: crop frame on a demo photo](docs/screenshots/main-window.png)

![Colour adjustments page](docs/screenshots/color-adjustments.png)

![Print sheet with 4 photos per sheet](docs/screenshots/print-sheet.png)

| Arabic (right-to-left) | Japanese |
|---|---|
| ![Arabic interface](docs/screenshots/main-window-arabic-rtl.png) | ![Japanese interface](docs/screenshots/main-window-japanese.png) |
## Fonctionnalités

- Formats d'impression : 10×15, 9×13, 13×18, 15×21, 20×30, 30×40 cm, A5, A4, A3, A3+, A2 (recadrer pour remplir la feuille ou ajuster la photo entière).
- Recadrage intelligent : détection des visages (YuNet), des personnes et animaux (YOLOX), modèle de pose ; le cadre peut aussi être réglé à la main.
- Correction des couleurs par photo : luminosité, contraste, gamma, ombres/hautes lumières, saturation, température/teinte, RVB, auto, noir et blanc, sépia, réduction du bruit, netteté.
- Gestion des couleurs : profil ICC de l'imprimante et commutateur Windows ICM.
- Préparation de l'impression : plusieurs photos par feuille, fond perdu par côté, un travail par feuille avec pause, contrôles avant impression (dpi, ajustement).
- Export en JPEG, TIFF, PNG et PDF.
- Mode agent IA : chaque étape est une commande renvoyant du JSON (ligne de commande ou serveur MCP pour Claude Desktop). Voir [AGENT.md](AGENT.md) (en russe).
- Langues de l'interface de la version Qt : Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча (choix dans les Paramètres ; par défaut la langue du système ; l'arabe s'affiche de droite à gauche). Les traductions couvrent les écrans principaux, sont automatiques et n'ont pas encore été relues par des locuteurs natifs ; les textes non traduits restent en anglais.

## Installation

- Windows avec Python 3.9+ (« Add python.exe to PATH »), ou lancez `install.bat` : il installe Python (si absent), les paquets et crée des raccourcis. Internet requis.
- Installation manuelle : `pip install -r requirements.txt`.

## Lancer la version Qt

Double-cliquez sur `run_qt.bat` (installe Pillow, pillow-heif, PySide6 et lance `photo_crop_qt.py`). Autotest : `selftest_qt.bat`. L'ancienne fenêtre Tkinter : `python photo_crop.py`.

### Modèles de détection

Les modèles YuNet / YOLOX (~36 Mo) ne sont pas dans le dépôt ; ils sont téléchargés à la première utilisation (ou avec `python smart_crop.py setup`) dans `%APPDATA%\PhotoCrop\models`.

## Mode agent et MCP

Lancez `mcp_config.bat` (ou `python photo_crop.py mcp-config`) pour obtenir le bloc de configuration, ajoutez-le à `claude_desktop_config.json` (`%APPDATA%\Claude\`), puis redémarrez Claude Desktop. Pour l'exe compilé, le bloc `mcpServers.photocrop` est :

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

Commandes principales : `open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

En ligne de commande : `python photo_crop.py agent set_format format=10x15` ; `python photo_crop.py agent --list` liste toutes les commandes. L'état est enregistré dans `%APPDATA%\PhotoCrop\agent_state.json`. `PHOTOCROP_AGENT_DRYRUN=1` interdit l'impression réelle.

## Compiler les exe

`build_exe.bat` compile avec PyInstaller `PhotoCrop.exe` (fenêtre Tkinter) et `PhotoCropAgent.exe` (console, pour MCP). Attention : le script supprime ensuite `build\` et les fichiers `.spec`. La version Qt se compile avec `pyinstaller PhotoCropQt.spec` → `dist\PhotoCropQt.exe`. Un tag `v*` déclenche le workflow GitHub Actions (`.github/workflows/build.yml`), qui compile `PhotoCropQt.exe` et `PhotoCropAgent.exe` et les joint à une GitHub Release.

## Licence

License: [PolyForm Noncommercial 1.0.0](LICENSE)
