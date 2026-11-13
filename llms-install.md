# Install KopiTehnik Print MCP server (agent-facing)

KopiTehnik Print is a **Windows** photo-printing app; the MCP server runs inside it.
You (the coding agent) can set it up on a Windows 10/11 machine in two ways.

## Option A - installed app (recommended for end users)

1. Download the installer from <https://github.com/ildargiv/KopiTehnik-Print/releases/latest>
   (`KopiTehnikPrint-Setup-1.10.0.exe`, Inno Setup, per-user install, no admin needed).
2. Silent install: `KopiTehnikPrint-Setup-1.10.0.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-`
3. The agent binary is installed as `PhotoCropAgent.exe` next to the app. Add to the MCP client config:

```json
{
  "mcpServers": {
    "photocrop": {
      "command": "C:\\Users\\<user>\\AppData\\Local\\Programs\\KopiTehnik Print\\PhotoCropAgent.exe",
      "args": ["mcp"]
    }
  }
}
```

## Option B - PyPI launcher (any MCP client, needs uv)

```bash
uvx kopitehnik-print-mcp
```

The launcher only finds the installed `PhotoCropAgent.exe` and forwards stdio to it;
nothing is reimplemented in Python. Same config block:

```json
{
  "mcpServers": {
    "photocrop": { "command": "uvx", "args": ["kopitehnik-print-mcp"] }
  }
}
```

Claude Desktop config lives at `%APPDATA%\Claude\claude_desktop_config.json` (restart Claude after editing).

## Verification

The server must answer `initialize` over stdio. Quick check without an MCP client:
run `python photo_crop.py mcp-config` (source checkout) or `uvx kopitehnik-print-mcp --help`.

## Safety controls (user-configurable in Settings)

- `PHOTOCROP_AGENT_DRYRUN=1` - never touch a real printer.
- `PHOTOCROP_AGENT_ROOTS` - restrict folders the agent may open.
- Max sheets per job and ask-before-print are enforced by the app, not the model.

## Tools

`open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`, `select_printer`,
`plan_print`, `render_sheet`, `preflight`, `print` - all return JSON. Full list: [AGENT.md](AGENT.md).

Registry names: official MCP Registry `io.github.ildargiv/kopitehnik-print`; PyPI `kopitehnik-print-mcp`; Scoop bucket `ildargiv/scoop-bucket` (`kopitehnik-print`); winget ID `IldarGaisin.KopiTehnikPrint` (pending).
