# Security policy

KopiTehnik Print runs on working computers in copy centres and photo desks, prints on real printers, can be driven by an AI agent over a local MCP endpoint and can talk to other copies of the program on the network. Reports about anything that lets someone else read files, print, change settings or run code through the program are welcome.

## Supported versions

Only the [latest release](https://github.com/ildargiv/KopiTehnik-Print/releases/latest) receives fixes. The program offers the update itself (Settings, About).

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Report it privately: the **Security** tab of this repository, then **Report a vulnerability**
(<https://github.com/ildargiv/KopiTehnik-Print/security/advisories/new>).

Include the program version (Settings, About), the Windows version, what you did and what happened. A proof of concept helps, a fix is not required.

You can expect a first answer within a week. When the fix is released, the report is credited in the release notes unless you prefer otherwise.

## What is in scope

- The local MCP endpoint of the window (`agent_bridge.py`): access without the key, requests from web pages, bypass of the print limits set in Settings.
- The network link between copies of the program (`net_*.py`): pairing without the 6-digit code, printing or file transfer from a PC that was not paired or was forbidden.
- The updater (`updater.py`) and the installer: installing a file that is not the release installer.
- Files the program opens: photos, documents, projects and ICC profiles that make it run code or write outside its folders.

Known limits, stated in the release notes: the network link is authenticated but not encrypted. Use it on a trusted local network or over Tailscale.

## Checking a download

Releases are built by GitHub Actions from this repository ([build workflow](.github/workflows/build.yml)). Starting with the release after v1.8.0, each release carries `SHA256SUMS.txt`. To check a file in PowerShell:

```powershell
(Get-FileHash .\KopiTehnikPrint-Setup-<version>.exe -Algorithm SHA256).Hash
```

and compare the result with the line for that file in `SHA256SUMS.txt`. GitHub also shows a SHA-256 digest next to each release file. The executables are not code-signed, so Windows SmartScreen may warn on first start.
