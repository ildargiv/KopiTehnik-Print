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


class AllowPathTest(unittest.TestCase):
    def test_person_allows_new_folder(self):
        root, other = tempfile.mkdtemp(), tempfile.mkdtemp()
        ran = []
        gate = ac.ToolGate(SPEC, roots=[root])
        a = ac.Agent(Stub([("open_folder", {"path": other}), "ok"]), gate, lambda r: ran.append(r) or {"ok": True}, allow_path=lambda p: True)
        a.say("x")
        self.assertEqual(len(ran), 1)

    def test_person_refuses_new_folder(self):
        root, other = tempfile.mkdtemp(), tempfile.mkdtemp()
        ran = []
        gate = ac.ToolGate(SPEC, roots=[root])
        a = ac.Agent(Stub([("open_folder", {"path": other}), "ok"]), gate, lambda r: ran.append(r) or {"ok": True}, allow_path=lambda p: False)
        a.say("x")
        self.assertEqual(ran, [])


class ProviderTest(unittest.TestCase):
    def test_openai_compatible_roundtrip(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        seen = {}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                seen["path"], seen["auth"] = self.path, self.headers.get("Authorization")
                seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                out = json.dumps({"choices": [{"message": {"role": "assistant", "content": "hi"}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            r = ac.OpenAICompatible("http://127.0.0.1:%d/v1" % srv.server_port, "m").chat([{"role": "user", "content": "x"}], [])
        finally:
            srv.shutdown()
        self.assertEqual(r["content"], "hi")
        self.assertEqual(seen["path"], "/v1/chat/completions")
        self.assertIsNone(seen["auth"])
