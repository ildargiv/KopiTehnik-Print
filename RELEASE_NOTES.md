**English** | [Русский](RELEASE_NOTES.ru.md) | [Español](RELEASE_NOTES.es.md) | [简体中文](RELEASE_NOTES.zh-CN.md) | [繁體中文](RELEASE_NOTES.zh-Hant.md) | [Deutsch](RELEASE_NOTES.de.md) | [Français](RELEASE_NOTES.fr.md) | [Português](RELEASE_NOTES.pt.md) | [日本語](RELEASE_NOTES.ja.md) | [한국어](RELEASE_NOTES.ko.md) | [Türkçe](RELEASE_NOTES.tr.md) | [Bahasa Indonesia](RELEASE_NOTES.id.md) | [العربية](RELEASE_NOTES.ar.md) | [हिन्दी](RELEASE_NOTES.hi.md) | [Italiano](RELEASE_NOTES.it.md) | [Polski](RELEASE_NOTES.pl.md) | [Українська](RELEASE_NOTES.uk.md) | [Tiếng Việt](RELEASE_NOTES.vi.md) | [ไทย](RELEASE_NOTES.th.md) | [Татарча](RELEASE_NOTES.tt.md)

# Release notes — v1.6.0

- **Printing on several printers at once**: tick printers in the new square "Printers" button next to Print; with more than one ticked the photos are distributed by readiness (faster printers get more). Each printer uses its own Quick Start mode. Modes: queue, in turns, in blocks. Pause, per-printer progress, "print what is missing" after a failure, automatic exclusion of a failing printer, slowdown detection (Epson) via the Windows spooler, and a check for the FILE: port / offline printers. The button turns green while the mode is active. Everything can be turned off in Settings (off by default).
- **Quick Start**: up to 8 cells (a small gear chooses how many are shown); the active cell turns fully green until you change settings by hand.
- **Layout tab**: zoom of the open photo in percent as in Epson Photo+ with automatic centring, "Fit" for this photo only, "Original" (previous behaviour) and a real "Crop" (cuts everything outside the frame, keeps white margins inside).
- Settings: a "Print modes" card with switches for these modes.

Files in the release: `KopiTehnikPrint-Setup-1.6.0.exe`.
