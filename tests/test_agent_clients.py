import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agent_clients as ac

CMD = {"command": r"C:\Program Files\KopiTehnik Print\PhotoCropQt.exe", "args": ["mcp"]}


class ClientsTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="pc_home_")
        self.old = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE", "APPDATA")}
        os.environ["HOME"] = os.environ["USERPROFILE"] = self.home
        os.environ["APPDATA"] = str(Path(self.home) / "AppData" / "Roaming")

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_every_client_has_a_snippet_with_the_command(self):
        for k in ac.CLIENTS:
            self.assertIn("PhotoCropQt.exe", ac.snippet(k, CMD).replace("\\\\", "\\"), k)

    def test_claude_desktop_creates_config_and_keeps_others(self):
        p = ac.config_path("claude_desktop")
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"mcpServers": {"x": {"command": "y"}}}), encoding="utf-8")
        ok, msg = ac.install("claude_desktop", CMD)
        self.assertTrue(ok, msg)
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(d["mcpServers"]["photocrop"], {"command": CMD["command"], "args": ["mcp"]})
        self.assertIn("x", d["mcpServers"])
        self.assertTrue(ac.uninstall("claude_desktop")[0])
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertNotIn("photocrop", d["mcpServers"])
        self.assertIn("x", d["mcpServers"])

    def test_cursor_not_installed_gives_snippet_not_files(self):
        ok, msg = ac.install("cursor", CMD)
        self.assertFalse(ok)
        self.assertIn("mcpServers", msg)
        self.assertFalse(ac.config_path("cursor").exists())

    def test_cursor_installed_is_written(self):
        ac.config_path("cursor").parent.mkdir(parents=True)
        ok, msg = ac.install("cursor", CMD)
        self.assertTrue(ok, msg)
        self.assertIn("photocrop", json.loads(ac.config_path("cursor").read_text(encoding="utf-8"))["mcpServers"])

    def test_opencode_uses_local_command_array(self):
        ac.config_path("opencode").parent.mkdir(parents=True)
        ok, msg = ac.install("opencode", CMD)
        self.assertTrue(ok, msg)
        d = json.loads(ac.config_path("opencode").read_text(encoding="utf-8"))
        self.assertEqual(d["mcp"]["photocrop"], {"type": "local", "command": [CMD["command"], "mcp"], "enabled": True})
        self.assertIn("$schema", d)

    def test_json_with_comments_is_not_overwritten(self):
        p = ac.config_path("opencode")
        p.parent.mkdir(parents=True)
        p.write_text('{\n  // my settings\n  "theme": "dark",\n}', encoding="utf-8")
        before = p.read_text(encoding="utf-8")
        ok, msg = ac.install("opencode", CMD)
        self.assertFalse(ok)
        self.assertEqual(p.read_text(encoding="utf-8"), before)
        self.assertIn("photocrop", msg)

    def test_cli_clients_run_the_clients_command(self):
        calls = []
        fake = lambda cmd, **kw: (calls.append(cmd), types.SimpleNamespace(returncode=0, stdout="ok", stderr=""))[1]
        bindir = tempfile.mkdtemp(prefix="pc_bin_")
        for exe in ("openclaw", "claude"):
            f = Path(bindir) / exe
            f.write_text("#!/bin/sh\n")
            f.chmod(0o755)
        old = os.environ["PATH"]
        os.environ["PATH"] = bindir + os.pathsep + old
        try:
            ok, _ = ac.install("openclaw", CMD, run=fake)
            self.assertTrue(ok)
            self.assertEqual(calls[-1][:5], ["openclaw", "mcp", "add", "photocrop", "--command"])
            self.assertEqual(calls[-1][-2:], ["--arg", "mcp"])
            ok, _ = ac.install("claude_code", CMD, run=fake)
            self.assertTrue(ok)
            self.assertEqual(calls[-1][:6], ["claude", "mcp", "add", "--scope", "user", "photocrop"])
        finally:
            os.environ["PATH"] = old

    def test_text_clients_never_claim_success(self):
        for k in ("hermes", "vscode", "other"):
            self.assertFalse(ac.install(k, CMD)[0])


if __name__ == "__main__":
    unittest.main()
