**English** | [Русский](RELEASE_NOTES.ru.md) | [Español](RELEASE_NOTES.es.md) | [简体中文](RELEASE_NOTES.zh-CN.md) | [繁體中文](RELEASE_NOTES.zh-Hant.md) | [Deutsch](RELEASE_NOTES.de.md) | [Français](RELEASE_NOTES.fr.md) | [Português](RELEASE_NOTES.pt.md) | [日本語](RELEASE_NOTES.ja.md) | [한국어](RELEASE_NOTES.ko.md) | [Türkçe](RELEASE_NOTES.tr.md) | [Bahasa Indonesia](RELEASE_NOTES.id.md) | [العربية](RELEASE_NOTES.ar.md) | [हिन्दी](RELEASE_NOTES.hi.md) | [Italiano](RELEASE_NOTES.it.md) | [Polski](RELEASE_NOTES.pl.md) | [Українська](RELEASE_NOTES.uk.md) | [Tiếng Việt](RELEASE_NOTES.vi.md) | [ไทย](RELEASE_NOTES.th.md) | [Татарча](RELEASE_NOTES.tt.md)

# Release notes — v1.5.0

- **Epson driver controls in the Printer tab** (T50, P50, TX650, PX660, R290, 1410, L805, L1800, L8050, L18050): print quality, borderless printing and the driver's colour correction; modes the driver would roll back on the chosen paper are hidden, and the program warns when borderless changes the paper type.
- **Quick Start**: three slots per printer with format, paper, quality, borderless, colour profile and processing; save, rename, apply.
- **Nozzle check and head cleaning** buttons (with a warning that cleaning uses ink and fills the waste tank).
- **Print test sheet** (grey wedge, shadows/highlights, colours, skin tones I–VI, gradients, sharpness) for the current paper size.
- **AI agent (MCP)**: new tools `epson_settings`, `quick_start` (list / save / apply / clear), `printer_maintenance` (needs `confirm=true`) and `add_test_sheet`; `select_printer` now really switches the printer in the window.
- New **Settings** button in the header (gear with a label, turns on hover).
- Photo counter no longer clips digits; the about box states that the program is not affiliated with Epson.

Files in the release: `KopiTehnikPrint-Setup-1.5.0.exe`.
