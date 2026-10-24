import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agent_chat as ac  # noqa: E402

SPEC = {n: ("d", [("path", "string", "p")]) for n in ("open_folder", "set_format", "print_photos", "preflight", "app_settings", "clear_queue")}


class Stub:
    def __init__(self, calls):
        self.calls = list(calls)
        self.seen = []

    def chat(self, messages, tools):
        self.seen.append(len(messages))
        c = self.calls.pop(0)
        if isinstance(c, str):
            return {"content": c}
        return {"content": "", "tool_calls": [{"id": "1", "function": {"name": c[0], "arguments": json.dumps(c[1])}}]}


class ChatTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.ran = []
        self.gate = ac.ToolGate(SPEC, roots=[self.root])

    def agent(self, calls, **kw):
        return ac.Agent(Stub(calls), kw.pop("gate", self.gate), lambda r: self.ran.append(r) or {"ok": True}, **kw)

    def test_tools_whitelist_hides_forbidden(self):
        names = {t["function"]["name"] for t in self.gate.tools()}
        self.assertIn("open_folder", names)
        self.assertNotIn("app_settings", names)
        self.assertNotIn("clear_queue", names)

    def test_forbidden_tool_not_executed(self):
        a = self.agent([("app_settings", {}), "done"])
        a.say("x")
        self.assertEqual(self.ran, [])

    def test_path_outside_roots_denied(self):
        a = self.agent([("open_folder", {"path": "/etc"}), "done"])
        a.say("x")
        self.assertEqual(self.ran, [])
        a = self.agent([("open_folder", {"path": self.root + "/a"}), "done"])
        a.say("x")
        self.assertEqual(len(self.ran), 1)

    def test_path_traversal_denied(self):
        a = self.agent([("open_folder", {"path": self.root + "/../x"}), "done"])
        a.say("x")
        self.assertEqual(self.ran, [])

    def test_no_roots_means_no_files(self):
        g = ac.ToolGate(SPEC, roots=[])
        a = self.agent([("open_folder", {"path": self.root}), "done"], gate=g)
        a.say("x")
        self.assertEqual(self.ran, [])

    def test_print_asks_and_declines(self):
        a = self.agent([("print_photos", {}), "ok"], confirm=lambda t: False)
        a.say("print")
        self.assertEqual(self.ran, [])

    def test_print_confirmed(self):
        a = self.agent([("print_photos", {}), "ok"], confirm=lambda t: True)
        a.say("print")
        self.assertEqual(len(self.ran), 1)
        self.assertEqual(a.printed_ok, 1)

    def test_print_disabled(self):
        g = ac.ToolGate(SPEC, roots=[self.root], policy={"allow_print": False})
        a = self.agent([("print_photos", {}), "ok"], gate=g, confirm=lambda t: True)
        a.say("print")
        self.assertEqual(self.ran, [])

    def test_step_limit(self):
        a = self.agent([("preflight", {})] * 5, max_steps=3)
        self.assertIn("limit", a.say("x"))
        self.assertEqual(len(self.ran), 3)

    def test_stop(self):
        a = self.agent([("preflight", {}), "x"])
        a.stop()
        a.stopped = False
        orig = a.execute
        a.execute = lambda r: (a.stop(), orig(r))[1]
        self.assertEqual(a.say("x"), "(stopped)")

    def test_bad_arguments_json(self):
        a = ac.Agent(Stub([]), self.gate, lambda r: {"ok": True})
        out = json.loads(a._run({"function": {"name": "preflight", "arguments": "{bad"}}))
        self.assertFalse(out["ok"])


if __name__ == "__main__":
    unittest.main()
