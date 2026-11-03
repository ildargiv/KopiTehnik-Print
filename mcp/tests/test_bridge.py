"""End-to-end check of the stdio bridge using a fake agent.

Run from the ``pypi`` directory:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FAKE_AGENT = """\
import json, sys
mode = sys.argv[1] if len(sys.argv) > 1 else ""
print(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"mode": mode, "tools": ["print"]}}), flush=True)
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    if req.get("method") == "shutdown":
        break
    print(json.dumps({"jsonrpc": "2.0", "id": req.get("id"), "result": {"echo": req.get("method")}}), flush=True)
"""


class BridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.agent = Path(self.tmp.name) / "fake_agent.py"
        self.agent.write_text(FAKE_AGENT, encoding="utf-8")

    def run_bridge(self, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["KOPITEHNIK_AGENT_EXE"] = str(self.agent)
        env["PYTHONPATH"] = str(ROOT)
        return subprocess.run(
            [sys.executable, "-m", "kopitehnik_mcp", *args],
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=str(ROOT),
            timeout=60,
        )

    def test_passes_protocol_through(self) -> None:
        result = self.run_bridge(stdin='{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [json.loads(line) for line in result.stdout.strip().splitlines()]
        self.assertEqual(lines[0]["result"]["mode"], "mcp")
        self.assertEqual(lines[1]["result"]["echo"], "tools/list")

    def test_where_prints_resolved_command(self) -> None:
        result = self.run_bridge("--where")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fake_agent.py", result.stdout)
        self.assertIn(sys.executable, result.stdout)

    def test_missing_agent_is_reported_on_stderr(self) -> None:
        env = dict(os.environ)
        env["KOPITEHNIK_AGENT_EXE"] = str(Path(self.tmp.name) / "nope.exe")
        env["PYTHONPATH"] = str(ROOT)
        result = subprocess.run(
            [sys.executable, "-m", "kopitehnik_mcp"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=str(ROOT),
            timeout=60,
        )
        self.assertEqual(result.returncode, 3)
        self.assertIn("does not exist", result.stderr)
        self.assertEqual(result.stdout, "", "stdout must stay clean for the MCP stream")

    def test_help_does_not_start_the_agent(self) -> None:
        result = self.run_bridge("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("kopitehnik-mcp", result.stdout)


if __name__ == "__main__":
    unittest.main()
