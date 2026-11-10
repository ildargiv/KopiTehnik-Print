[English](RELEASE_NOTES.md) | [Русский](RELEASE_NOTES.ru.md) | **Español** | [简体中文](RELEASE_NOTES.zh-CN.md) | [繁體中文](RELEASE_NOTES.zh-Hant.md) | [Deutsch](RELEASE_NOTES.de.md) | [Français](RELEASE_NOTES.fr.md) | [Português](RELEASE_NOTES.pt.md) | [日本語](RELEASE_NOTES.ja.md) | [한국어](RELEASE_NOTES.ko.md) | [Türkçe](RELEASE_NOTES.tr.md) | [Bahasa Indonesia](RELEASE_NOTES.id.md) | [العربية](RELEASE_NOTES.ar.md) | [हिन्दी](RELEASE_NOTES.hi.md) | [Italiano](RELEASE_NOTES.it.md) | [Polski](RELEASE_NOTES.pl.md) | [Українська](RELEASE_NOTES.uk.md) | [Tiếng Việt](RELEASE_NOTES.vi.md) | [ไทย](RELEASE_NOTES.th.md) | [Татарча](RELEASE_NOTES.tt.md)

# Notas de la versión — v1.9.0

- **Agente IA integrado «Print Assistant» (beta, apagado de forma predeterminada)**: pestaña de agente en el panel derecho y entrada de dos líneas bajo las pestañas (funciona desde cualquier pestaña), botones rápidos Improve, Crop, Prepare, Print. Una carpeta escrita más un botón es un comando; varios botones se ejecutan en orden. Nada se envía hasta que el agente está activado y se indica la dirección del modelo.
- **Cualquier modelo compatible con OpenAI**: llama.cpp local, Ollama, vLLM o un servicio en la nube. Las direcciones locales y de Tailscale no pasan por el proxy del sistema. Tarjeta de ajustes: Test connection, aviso para direcciones no locales; la clave API se guarda cifrada en Windows.
- **El agente ve las fotos**: con «Agent sees photos» activado, el modelo mira las vistas previas y recorta y corrige el color por su cuenta.
- **Quejas sobre la impresión con palabras normales** («demasiado rosa», «más oscuro que la pantalla», tinte en blanco y negro) ajustan la corrección de impresión para la impresora y el papel actuales en pasos fijos.
- Seguridad: el agente solo ve su carpeta de trabajo (predeterminada `Desktop\Печать ИИ`) y las carpetas y archivos que uno escribe en el chat; la impresión pregunta primero (modo automático opcional tras 3 confirmaciones), siempre ejecuta la comprobación previa y está limitada de forma predeterminada a 20 hojas por impresión; el modo de prueba está activado de forma predeterminada.
- Fiabilidad: Stop interrumpirá al modelo al instante; cada llamada a una herramienta recibe un id y su respuesta; se detienen bucles y turnos de más de 15 minutos; Roll back revierte todos los cambios del agente en la conversación. El agente responde en el idioma de la interfaz; sus textos están traducidos a 13 idiomas de interfaz más.
- Corregido: una petición con clave incorrecta al endpoint del agente podía terminar con la conexión caída en lugar de error 401.

Archivos de la versión: `KopiTehnikPrint-Setup-1.9.0.exe`, `KopiTehnikPrint-Portable-1.9.0.exe`, `SHA256SUMS.txt`.

# Notas de la versión — v1.0.0 (primera versión)

Primera versión pública de PhotoCrop (КопиТехник PRINT).

- Interfaz Qt (`PhotoCropQt.exe`) y la ventana Tkinter anterior (`photo_crop.py`).
- Recorte e impresión en 10×15 cm y otros formatos hasta A2.
- Recorte inteligente (rostros, personas, mascotas), corrección de color por foto, perfil ICC de impresora.
- Planificación de impresión con comprobaciones previas, sangrado por lado, un trabajo por hoja.
- Modo agente de IA y servidor MCP (`PhotoCropAgent.exe mcp`).
- Idiomas de la interfaz en la versión Qt: Русский, English, 日本語, 한국어, Türkçe, Bahasa Indonesia, العربية, हिन्दी, Italiano, Polski, Українська, Tiếng Việt, ไทย, 繁體中文, Татарча; las traducciones son automáticas y aún no las han revisado hablantes nativos.
- Los modelos de detección se descargan en el primer uso. License: PolyForm Noncommercial 1.0.0

Archivos de la versión: `PhotoCropQt.exe`, `PhotoCropAgent.exe`.