# kopitehnik-print-mcp

<!-- mcp-name: io.github.ildargiv/kopitehnik-print -->

An MCP (Model Context Protocol) stdio bridge to **KopiTehnik Print** — a Windows
app that prints photos on Epson, Canon, HP, Brother and other inkjet printers
with ICC colour profiles, borderless printing, smart cropping and sheet layout.

This package does not reimplement anything: it finds the app's own agent
(`PhotoCropAgent.exe`) and starts it in `mcp` mode, so your AI client talks
straight to the print desk.

## What the agent can do

`open_folder`, `set_format`, `auto_crop`, `set_crop`, `set_adjust`,
`select_printer`, `plan_print`, `render_sheet`, `preflight`, `print`,
`multi_print`, `zoom_photo`, `crop_apply`, `epson_settings`, `quick_start`,
`printer_maintenance`, `add_test_sheet`.

The agent works in the same window you see: changes appear live, Ctrl+Z undoes
them, and a badge shows that the AI agent is working. In Settings you decide
whether the agent may print, how many sheets per job, and whether it must ask
first.

## Requirements

* Windows (the print path is Windows-only).
* [KopiTehnik Print](https://github.com/ildargiv/KopiTehnik-Print/releases/latest)
  installed, or a source checkout with `photo_crop.py`.

## Install

Claude Desktop — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kopitehnik": {
      "command": "uvx",
      "args": ["kopitehnik-print-mcp"]
    }
  }
}
```

Any MCP client that runs stdio servers works the same way:

```
uvx kopitehnik-print-mcp
```

Already using the bundled `PhotoCropAgent.exe mcp`? That still works; this
package only adds a package-manager-installable entry point.

## Troubleshooting

```bash
uvx kopitehnik-print-mcp --where
```

prints which binary would be launched. If the app lives in a non-standard
folder, set `KOPITEHNIK_AGENT_EXE` to the full path of `PhotoCropAgent.exe`.

## Example prompts

* "Open the folder Client_Ivanov, set 10x15, check the photos and print 3 copies of each."
* "Print this PDF on A4."
* "Print a borderless test sheet on the Epson and tell me which patches look wrong."

## Licence

The wrapper is a thin launcher and carries the KopiTehnik Print Licence: free
for personal use and for a business with one workstation at one location.
See [LICENSE](https://github.com/ildargiv/KopiTehnik-Print/blob/main/LICENSE).

Not affiliated with Epson, Canon, HP or Brother.
