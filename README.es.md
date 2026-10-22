[English](README.md) | [Русский](README.ru.md) | **Español** | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-Hant.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [Bahasa Indonesia](README.id.md) | [العربية](README.ar.md) | [हिन्दी](README.hi.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Українська](README.uk.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Татарча](README.tt.md)

# PhotoCrop (КопиТехник PRINT)

Programa para Windows para recortar e imprimir fotos (10×15 cm y otros formatos), con recorte inteligente, corrección de color, perfiles de color, diseño de impresión y modo de agente de IA.

**License: [KopiTehnik Print Licence](LICENSE)**

## Screenshots

<p align="center"><img src="docs/promo.gif" alt="PhotoCrop animated overview" width="760"></p>

![PhotoCrop main window: crop frame on a demo photo](docs/screenshots/main-window.png)

![Colour adjustments page](docs/screenshots/color-adjustments.png)

![Print sheet with 4 photos per sheet](docs/screenshots/print-sheet.png)

| Arabic (right-to-left) | Japanese |
|---|---|
| ![Arabic interface](docs/screenshots/main-window-arabic-rtl.png) | ![Japanese interface](docs/screenshots/main-window-japanese.png) |
## Características

- Formatos de impresión: 10×15, 9×13, 13×18, 15×21, 20×30, 30×40 cm, A5, A4, A3, A3+, A2 (recortar para llenar la hoja o ajustar la foto completa).
- Recorte inteligente: detección de rostros (YuNet), personas y mascotas (YOLOX), modelo de pose; el marco también se puede fijar a mano.
- Corrección de color por foto: brillo, contraste, gamma, sombras/luces, saturación, temperatura/tono, RGB, automático, blanco y negro, sepia, reducción de ruido, nitidez.
- Gestión de color: perfil ICC de la impresora e interruptor de Windows ICM.
- Planificación de impresión: varias fotos por hoja, sangrado por lado, un trabajo por hoja con pausa entre trabajos, comprobaciones previas (dpi, encaje).
- Exportación a JPEG, TIFF, PNG y PDF.
- Modo agente de IA: cada paso es un comando que devuelve JSON (línea de comandos o servidor MCP para Claude Desktop). Véase [AGENT.md](AGENT.md) (en ruso).
- Idiomas de la interfaz en la versión Qt: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча (se elige en Ajustes; por defecto el idioma del sistema; árabe de derecha a izquierda). Las traducciones cubren las pantallas principales, son automáticas y no han sido revisadas por hablantes nativos; el texto sin traducir aparece en inglés.

## Instalación

- Windows con Python 3.9+ («Add python.exe to PATH»), o ejecute `install.bat`: instala Python (si falta), los paquetes y crea accesos directos. Requiere internet.
- Instalación manual: `pip install -r requirements.txt`.

## Ejecutar la versión Qt

Haga doble clic en `run_qt.bat` (instala Pillow, pillow-heif, PySide6 y lanza `photo_crop_qt.py`). Autoprueba: `selftest_qt.bat`. La ventana anterior en Tkinter: `python photo_crop.py`.

### Modelos de detección

Los modelos YuNet / YOLOX (~36 MB) no están en el repositorio; se descargan en el primer uso (o con `python smart_crop.py setup`) a `%APPDATA%\PhotoCrop\models`.

## Modo agente y MCP

Ejecute `mcp_config.bat` (o `python photo_crop.py mcp-config`) para obtener el bloque de configuración, añádalo a `claude_desktop_config.json` (`%APPDATA%\Claude\`) y reinicie Claude Desktop. Para el exe compilado, el bloque `mcpServers.photocrop` es:

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

Comandos principales: `open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`.

Línea de comandos: `python photo_crop.py agent set_format format=10x15`; `python photo_crop.py agent --list` muestra todos los comandos. El estado se guarda en `%APPDATA%\PhotoCrop\agent_state.json`. `PHOTOCROP_AGENT_DRYRUN=1` prohíbe la impresión real.

## Compilar los exe

`build_exe.bat` genera con PyInstaller `PhotoCrop.exe` (ventana Tkinter) y `PhotoCropAgent.exe` (consola, para MCP). Atención: el script borra después `build\` y los archivos `.spec`. La versión Qt se compila con `pyinstaller PhotoCropQt.spec` → `dist\PhotoCropQt.exe`. Una etiqueta `v*` lanza el flujo de GitHub Actions (`.github/workflows/build.yml`), que compila `PhotoCropQt.exe` y `PhotoCropAgent.exe` y los adjunta a un GitHub Release.

## Licencia

License: [KopiTehnik Print Licence](LICENSE)
