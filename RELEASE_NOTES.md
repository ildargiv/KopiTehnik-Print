**English** | [Русский](RELEASE_NOTES.ru.md) | [Español](RELEASE_NOTES.es.md) | [简体中文](RELEASE_NOTES.zh-CN.md) | [繁體中文](RELEASE_NOTES.zh-Hant.md) | [Deutsch](RELEASE_NOTES.de.md) | [Français](RELEASE_NOTES.fr.md) | [Português](RELEASE_NOTES.pt.md) | [日本語](RELEASE_NOTES.ja.md) | [한국어](RELEASE_NOTES.ko.md) | [Türkçe](RELEASE_NOTES.tr.md) | [Bahasa Indonesia](RELEASE_NOTES.id.md) | [العربية](RELEASE_NOTES.ar.md) | [हिन्दी](RELEASE_NOTES.hi.md) | [Italiano](RELEASE_NOTES.it.md) | [Polski](RELEASE_NOTES.pl.md) | [Українська](RELEASE_NOTES.uk.md) | [Tiếng Việt](RELEASE_NOTES.vi.md) | [ไทย](RELEASE_NOTES.th.md) | [Татарча](RELEASE_NOTES.tt.md)

# Release notes — v1.3.0

- **Printer colour correction.** A new switch and "Set up correction…" button on the Printer tab. Tint (green ↔ magenta), warm ↔ cool balance, brightness, saturation and a correction for each of six colours (red, yellow, green, cyan, blue, magenta) compensate the colour cast of your printer and paper. It works with an ICC profile and without one, is applied only when printing and saving and is never shown on screen, because it makes the print match the screen.
- The correction is stored in the print profile (printer + sheet size + paper type) together with the ICC profile; changing the ICC profile resets it. The agent can read and set it through `set_color_profile` (`pcorr_on`, `pcorr`).
- **About** now shows the program name simply as "KopiTehnik Print".
- Fixed the preset-name check in the built-in self-test.

Files in the release: `PhotoCropQt.exe`, `KopiTehnikPrint-Setup-1.3.0.exe`.
