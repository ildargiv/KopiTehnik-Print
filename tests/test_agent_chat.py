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
        a = self.agent([("preflight", {"path": self.root + "/%d" % i}) for i in range(5)], max_steps=3, route=False)
        self.assertIn("limit", a.say("x"))
        self.assertEqual(len(self.ran), 3)

    def test_stop(self):
        a = self.agent([("preflight", {}), "x"], route=False)
        a.stop()
        a.stopped = False
        orig = a.execute
        a.execute = lambda r: (a.stop(), orig(r))[1]
        self.assertEqual(a.say("x"), "(stopped)")

    def test_repeated_call_stops(self):
        a = self.agent([("preflight", {})] * 5, route=False)
        self.assertIn("repeated", a.say("x"))
        self.assertEqual(len(self.ran), 2)

    def test_text_tool_call_is_parsed(self):
        a = self.agent(['<tool_call>{"name": "preflight", "arguments": {}}</tool_call>', "done"], route=False)
        self.assertEqual(a.say("x"), "done")
        self.assertEqual(len(self.ran), 1)

    def test_routing_limits_tools(self):
        spec = {n: ("d", []) for n in ("open_folder", "set_adjust", "print_photos", "list_printers")}
        gate = ac.ToolGate(spec, groups=[])
        gate.route("открой папку")
        self.assertNotIn("print_photos", gate.names)
        gate.route("распечатай")
        self.assertIn("print_photos", gate.names)
        self.assertIn("list_printers", gate.names)

    def test_need_tools_adds_group(self):
        a = self.agent([("need_tools", {"group": "print"}), ("preflight", {}), "ok"])
        a.say("x")
        self.assertEqual(len(self.ran), 1)

    def test_images_are_dropped_from_results(self):
        a = ac.Agent(Stub([("preflight", {}), "ok"]), self.gate, lambda r: {"ok": True, "_image_b64": "A" * 5000, "n": 1}, route=False)
        a.say("x")
        tool = [m for m in a.messages if m["role"] == "tool"][0]["content"]
        self.assertNotIn("AAAA", tool)

    def test_required_in_schema(self):
        g = ac.ToolGate(SPEC, required={"open_folder": ["path"]})
        t = [x for x in g.tools() if x["function"]["name"] == "open_folder"][0]
        self.assertEqual(t["function"]["parameters"]["required"], ["path"])

    def test_rollback_uses_undo_steps(self):
        depth = [3]
        a = ac.Agent(Stub([("preflight", {}), "ok"]), self.gate, lambda r: self.ran.append(r) or depth.__setitem__(0, depth[0] + 2) or {"ok": True},
                     undo_depth=lambda: depth[0], route=False)
        a.say("x")
        self.assertEqual(a.rollback(), 2)
        self.assertEqual(self.ran[-1], {"cmd": "undo", "steps": 2})

    def test_find_outliers(self):
        ph = [{"index": i, "name": "%d.jpg" % i, "mean_luma": 120, "sharpness": 10, "shadow_clip_pct": 0, "highlight_clip_pct": 0} for i in range(5)]
        ph[1]["mean_luma"] = 30
        ph[3]["sharpness"] = 2
        out = ac.find_outliers(ph)
        self.assertEqual([o["index"] for o in out], [1, 3])
        self.assertIn("dark", out[0]["why"])

    def test_prepare_series_runs_subcommands_and_respects_roots(self):
        cmds = []

        def ex(r):
            cmds.append(r["cmd"])
            if r["cmd"] == "open_folder":
                return {"ok": True, "result": {"photo_count": 4}}
            if r["cmd"] == "preflight":
                return {"ok": True, "result": {"ready": True, "checks": [], "sheets_to_print": 8}}
            return {"ok": True, "result": {}}
        spec = {n: ("d", []) for n in ("open_folder", "set_format", "set_copies", "preflight", "analyze_photos")}
        gate = ac.ToolGate(spec, roots=[self.root])
        a = ac.Agent(Stub([("prepare_series", {"folder": self.root, "format": "10x15", "copies": 2}), "ok"]), gate, ex, route=False)
        a.say("x")
        self.assertEqual(cmds, ["open_folder", "set_format", "set_copies", "preflight"])
        self.assertNotIn("print_photos", cmds)
        other = tempfile.mkdtemp()
        cmds.clear()
        a = ac.Agent(Stub([("prepare_series", {"folder": other, "format": "10x15"}), "ok"]), gate, ex, route=False)
        a.say("x")
        self.assertEqual(cmds, [])

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
