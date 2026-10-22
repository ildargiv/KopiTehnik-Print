**English** | [Русский](RELEASE_NOTES.ru.md) | [Español](RELEASE_NOTES.es.md) | [简体中文](RELEASE_NOTES.zh-CN.md) | [繁體中文](RELEASE_NOTES.zh-Hant.md) | [Deutsch](RELEASE_NOTES.de.md) | [Français](RELEASE_NOTES.fr.md) | [Português](RELEASE_NOTES.pt.md) | [日本語](RELEASE_NOTES.ja.md) | [한국어](RELEASE_NOTES.ko.md) | [Türkçe](RELEASE_NOTES.tr.md) | [Bahasa Indonesia](RELEASE_NOTES.id.md) | [العربية](RELEASE_NOTES.ar.md) | [हिन्दी](RELEASE_NOTES.hi.md) | [Italiano](RELEASE_NOTES.it.md) | [Polski](RELEASE_NOTES.pl.md) | [Українська](RELEASE_NOTES.uk.md) | [Tiếng Việt](RELEASE_NOTES.vi.md) | [ไทย](RELEASE_NOTES.th.md) | [Татарча](RELEASE_NOTES.tt.md)

# Next version

- **New licence.** KopiTehnik Print Licence 1.0: one workstation is free, including for commercial use; more by agreement. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
- HEIC reading now uses `pi-heif` (decoder only) instead of `pillow-heif`, which bundled a GPL encoder.

# Release notes — v1.4.0

- **One-click update.** When a new version is out, the program offers **Update now**: it downloads the installer from the release (with progress and Cancel), checks its size and SHA-256, saves your settings, closes, installs the update silently and starts again by itself. If the download fails or the file is damaged, nothing is installed and you get a link for a manual download. The "Open download page" and "Skip this version" buttons are still there, and the new version's notes are shown in the window. Running from source still just opens the download page.
- The release now carries the installer only (`KopiTehnikPrint-Setup-*.exe`); it contains the same program.
- Fixed the preset-name check in the built-in self-test.

Files in the release: `KopiTehnikPrint-Setup-1.4.0.exe` (the standalone `PhotoCropQt.exe` is also attached while the build workflow still publishes it).
