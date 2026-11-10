# Changelog

Short history of releases. Full notes for each version are on the [Releases page](https://github.com/ildargiv/KopiTehnik-Print/releases); notes for the latest versions in 20 languages are in [RELEASE_NOTES.md](RELEASE_NOTES.md).

Versions released on or after 2026-10-22 are under the KopiTehnik Print Licence; section 12 of [LICENSE](LICENSE) covers earlier ones.

## Unreleased

- Tests and the Qt self-test run on GitHub for every push and pull request and before a release build.
- Release builds use pinned package versions (`requirements-lock.txt`) and publish `SHA256SUMS.txt`.
- Fixed: a request with a wrong key to the agent endpoint could end with a dropped connection instead of error 401.
- The promo animation in the README is now WebP (half the size).

## [1.8.0](https://github.com/ildargiv/KopiTehnik-Print/releases/tag/v1.8.0) - 2026-11-03

- Network: other copies of the program are found automatically; pairing by a 6-digit code.
- Printing on another PC's printer with that PC's colour and driver settings.
- Network section in Settings, status buttons for connected PCs, delivery status in the chat.
- Printers can be renamed and hidden.

## [1.7.0](https://github.com/ildargiv/KopiTehnik-Print/releases/tag/v1.7.0) - 2026-10-31

- First version of the network link between copies of the program: pairing, chat, file transfer.

## [1.6.1](https://github.com/ildargiv/KopiTehnik-Print/releases/tag/v1.6.1) - 2026-10-30

- Agent tools `multi_print`, `zoom_photo`, `crop_apply`.
- English for all strings added in 1.5 and 1.6.
- The data folder moved to `%APPDATA%\KopiTehnik Print`; the portable file got its current name.

## [1.6.0](https://github.com/ildargiv/KopiTehnik-Print/releases/tag/v1.6.0) - 2026-10-30

- Printing on several printers at once, with queue, in-turn and block modes.
- Quick Start grew to 8 cells.
- Layout tab: zoom in percent, Fit, Original and a real Crop.

## [1.5.0](https://github.com/ildargiv/KopiTehnik-Print/releases/tag/v1.5.0) - 2026-10-27

- Epson driver controls in the Printer tab: quality, borderless, driver colour correction.
- Quick Start slots per printer.
- Nozzle check, head cleaning and a printed test sheet.
- Agent tools `epson_settings`, `quick_start`, `printer_maintenance`, `add_test_sheet`.

## [1.4.1](https://github.com/ildargiv/KopiTehnik-Print/releases/tag/v1.4.1) - 2026-10-22

- Installer in 24 languages.
- Trim values on the frame follow the orientation of the photo.

## [1.4.0](https://github.com/ildargiv/KopiTehnik-Print/releases/tag/v1.4.0) - 2026-10-22

- One-click update with a size and SHA-256 check of the installer.

## [1.3.0](https://github.com/ildargiv/KopiTehnik-Print/releases/tag/v1.3.0) - 2026-10-22

- Printer correction: a colour correction applied at print time, after the ICC profile.

## [1.2.0](https://github.com/ildargiv/KopiTehnik-Print/releases/tag/v1.2.0) - 2026-10-22

- The AI agent (MCP) works inside the program window.
- Installer with an option to connect the agent to Claude Desktop.
- Print profiles per printer, sheet size and paper type; colour presets; new look.

## [1.1.0](https://github.com/ildargiv/KopiTehnik-Print/releases/tag/v1.1.0) - 2026-10-21

- Photo and Document modes: printing PDF, Word, Excel and PowerPoint.
- Levels, Curves and selective colour; Before / After comparison.
- Print counter and the borderless test sheet.

## [1.0.0](https://github.com/ildargiv/KopiTehnik-Print/releases/tag/v1.0.0) - 2026-10-18

- First public release: cropping and printing up to A2, smart crop, ICC profile, AI-agent mode and MCP server.
