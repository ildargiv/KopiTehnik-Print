**English** | [Русский](RELEASE_NOTES.ru.md) | [Español](RELEASE_NOTES.es.md) | [简体中文](RELEASE_NOTES.zh-CN.md) | [繁體中文](RELEASE_NOTES.zh-Hant.md) | [Deutsch](RELEASE_NOTES.de.md) | [Français](RELEASE_NOTES.fr.md) | [Português](RELEASE_NOTES.pt.md) | [日本語](RELEASE_NOTES.ja.md) | [한국어](RELEASE_NOTES.ko.md) | [Türkçe](RELEASE_NOTES.tr.md) | [Bahasa Indonesia](RELEASE_NOTES.id.md) | [العربية](RELEASE_NOTES.ar.md) | [हिन्दी](RELEASE_NOTES.hi.md) | [Italiano](RELEASE_NOTES.it.md) | [Polski](RELEASE_NOTES.pl.md) | [Українська](RELEASE_NOTES.uk.md) | [Tiếng Việt](RELEASE_NOTES.vi.md) | [ไทย](RELEASE_NOTES.th.md) | [Татарча](RELEASE_NOTES.tt.md)

# Release notes — v1.9.0

- **Built-in AI agent “Print Assistant” (beta, off by default)**: an agent tab in the right panel and a two-line input under the tabs (works from any tab), quick buttons Improve, Crop, Prepare, Print. A typed folder plus a button is one command; several buttons run in order. Nothing is sent until you enable the agent and set a model address.
- **Any OpenAI-compatible model**: local llama.cpp, Ollama, vLLM or a cloud service. Local and Tailscale addresses bypass the system proxy. Settings card: Test connection, a warning for a non-local address, the API key stored encrypted on Windows.
- **The agent sees the photos**: with “Agent sees photos” on, the model looks at the previews and crops and fixes colour by itself.
- **Print complaints in plain words** (“too pink”, “darker than the screen”, a tint in black-and-white) adjust the printer correction for the current printer and paper in fixed steps.
- Safety: the agent only sees its work folder (default `Desktop\Печать ИИ`) and the folders and files you type in the chat; printing asks first (optional auto mode after 3 confirmations), always runs the pre-print check and is limited to 20 sheets per print by default; trial mode is on by default.
- Reliability: Stop interrupts the model at once, every tool call gets an id and an answer, runaway loops and turns longer than 15 minutes are stopped, Roll back undoes everything the agent changed in the conversation. The agent answers in the interface language, its strings are translated into 13 additional interface languages.
- Fixed: a request with a wrong key to the agent endpoint could end with a dropped connection instead of error 401.

Release files: `KopiTehnikPrint-Setup-1.9.0.exe`, `KopiTehnikPrint-Portable-1.9.0.exe`, `SHA256SUMS.txt`.

# Release notes — v1.8.0

- **Network: auto-discovery and easy connect**: the app now finds other copies on the local network (and online Tailscale PCs) by itself. Click "+" in the chat, pick a found PC and press "Connect": a 6-digit code appears on your screen and must be typed in the request window on the other PC. Three wrong codes cancel the request. You can enter an address manually if a PC is not found.
- **Print on another PC**: a 🖧 button next to Print (shown when a connected PC is online): pick the PC and its printer; sheets are built on your PC and printed with that PC's colour and driver settings. Paper in that driver must match the sheet format.
- **Network section in Settings**: switch, accept printing, name, files folder, list of PCs (rename, hide, forbid printing, forget, app version), which printers to share.
- Status buttons for connected PCs at the bottom right (online, printing, needs attention, offline); a click opens the chat. A 🖼 chat button sends the checked photos. Chat shows "printed" or "print failed" lines, delivery status, and the unsent queue survives restarts.
- Security: password-authenticated code exchange (6 digits cannot be guessed from captured traffic, three mistakes cancel the request), ids and roles in signatures, connection and request limits, UDP address spoofing no longer redirects a paired PC, a second app copy cannot take the port, firewall rule in the installer (admin install).
- **Printers**: each printer can get its own display name and unneeded ones can be hidden (✎ button next to the printer list, in the “Printers for printing” window and in Settings, Print → Printers). Hidden printers are not shown in print lists.
- The network is now on by default (Windows may ask for a firewall permission on first start: allow it for private networks). The link is still not encrypted; the 6-digit code protects against accidental connections in a trusted network, use Tailscale for open networks.

Release files: `KopiTehnikPrint-Setup-1.8.0.exe`, `KopiTehnikPrint-Portable-1.8.0.exe`.

# Release notes — v1.7.0

- **Network (new)**: connect several copies of the program over the local network or Tailscale. Pair PCs with a one-time code; a chat panel on the left (text, emoji, any files; photos shown as pictures with a Download button; sounds on/off) and the foundation for printing on another PC's printer (sheets are prepared on your PC and printed with the printing PC's own colour profile and driver settings). Network access is off until you connect the first PC; connections are authenticated with a per-pair key but not encrypted (use a trusted LAN or Tailscale).
- Printer state, remote printing from the print dialog and the status buttons of connected PCs are not in the window yet.

Release files: `KopiTehnikPrint-Setup-1.7.0.exe`, `KopiTehnikPrint-Portable-1.7.0.exe`.


