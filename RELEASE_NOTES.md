**English** | [Русский](RELEASE_NOTES.ru.md) | [Español](RELEASE_NOTES.es.md) | [简体中文](RELEASE_NOTES.zh-CN.md) | [繁體中文](RELEASE_NOTES.zh-Hant.md) | [Deutsch](RELEASE_NOTES.de.md) | [Français](RELEASE_NOTES.fr.md) | [Português](RELEASE_NOTES.pt.md) | [日本語](RELEASE_NOTES.ja.md) | [한국어](RELEASE_NOTES.ko.md) | [Türkçe](RELEASE_NOTES.tr.md) | [Bahasa Indonesia](RELEASE_NOTES.id.md) | [العربية](RELEASE_NOTES.ar.md) | [हिन्दी](RELEASE_NOTES.hi.md) | [Italiano](RELEASE_NOTES.it.md) | [Polski](RELEASE_NOTES.pl.md) | [Українська](RELEASE_NOTES.uk.md) | [Tiếng Việt](RELEASE_NOTES.vi.md) | [ไทย](RELEASE_NOTES.th.md) | [Татарча](RELEASE_NOTES.tt.md)

# Release notes — v1.7.0

- **Network (new)**: connect several copies of the program over the local network or Tailscale. Pair PCs with a one-time code; a chat panel on the left (text, emoji, any files; photos shown as pictures with a Download button; sounds on/off) and the foundation for printing on another PC's printer (sheets are prepared on your PC and printed with the printing PC's own colour profile and driver settings). Network access is off until you connect the first PC; connections are authenticated with a per-pair key but not encrypted (use a trusted LAN or Tailscale).
- Printer state, remote printing from the print dialog and the status buttons of connected PCs are not in the window yet.

Files in the release: `KopiTehnikPrint-Setup-1.7.0.exe`, `KopiTehnikPrint-Portable-1.7.0.exe`.

# Release notes — v1.6.1

- **AI agent (MCP)**: new tools `multi_print` (printers, Quick Start slot per printer, blocks / one-at-a-time modes, resume), `zoom_photo` (percent, fit, fill, original) and `crop_apply` (crop to the frame into the "Обрезанные" subfolder). With several printers ticked, `print_photos` distributes the sheets between them.
- **Translations**: English for all strings added in 1.5–1.6 (multi-printer, Quick Start, Epson controls, zoom/crop); key labels in the other interface languages (machine-assisted, not reviewed by native speakers).
- The portable file is now `KopiTehnikPrint-Portable-<version>.exe`.
- The data folder is now `%APPDATA%\KopiTehnik Print`; the old `PhotoCrop` folder (settings, projects, logs, models) is moved there on first start.


