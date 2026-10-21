import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pc_bridge_")
        self.old = os.environ.get("APPDATA")
        os.environ["APPDATA"] = self.tmp
        import agent_bridge as ab
        self.ab = ab

    def tearDown(self):
        if self.old is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self.old

    def server(self, handle=None):
        handle = handle or (lambda m: {"jsonrpc": "2.0", "id": m.get("id"), "result": {"echo": m.get("method")}} if m.get("id") is not None else None)
        srv = self.ab.AgentHttpServer(handle, self.ab.new_token())
        srv.start()
        self.addCleanup(srv.stop)
        return srv

    def test_post_roundtrip_and_endpoint_file(self):
        srv = self.server()
        ep = self.ab.read_endpoint()
        self.assertEqual(ep["port"], srv.port)
        r = self.ab.post(ep, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
        self.assertEqual(r["result"]["echo"], "ping")
        self.assertIsNone(self.ab.post(ep, {"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertTrue(self.ab.window_alive())

    def test_wrong_token_and_foreign_origin_rejected(self):
        import urllib.error
        import urllib.request
        srv = self.server()
        ep = dict(self.ab.read_endpoint())
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.ab.post({"port": ep["port"], "token": "wrong"}, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
        self.assertEqual(cm.exception.code, 401)
        rq = urllib.request.Request("http://127.0.0.1:%d/mcp" % srv.port, data=b"{}", method="POST",
                                    headers={"Authorization": "Bearer " + ep["token"], "Origin": "http://evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(rq, timeout=5)
        self.assertEqual(cm.exception.code, 401)

    def test_stop_removes_endpoint(self):
        srv = self.server()
        srv.stop()
        self.assertIsNone(self.ab.read_endpoint())
        self.assertIsNone(self.ab.window_alive())

    def test_stdio_mcp_proxies_to_window(self):
        self.server()
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
        env = dict(os.environ, APPDATA=self.tmp, PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, str(ROOT / "photo_crop.py"), "mcp"], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                           capture_output=True, text=True, env=env, timeout=60)
        out = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]
        self.assertEqual([o["result"]["echo"] for o in out], ["ping", "tools/list"])      # ответы пришли от «окна», а не от встроенного движка

    def test_stdio_mcp_without_window_uses_local_engine(self):
        env = dict(os.environ, APPDATA=self.tmp, PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, str(ROOT / "photo_crop.py"), "mcp"], input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n",
                           capture_output=True, text=True, env=env, timeout=60)
        names = {t["name"] for t in json.loads(p.stdout.splitlines()[0])["result"]["tools"]}
        self.assertIn("open_folder", names)


class HandleTest(unittest.TestCase):
    def test_session_can_extend_tools_and_resources(self):
        import photo_crop as pc

        class S:
            spec = {"hello": ("Say hello", [("name", "string", "who")])}
            readonly = {"hello"}
            required = {"hello": ["name"]}
            instructions = "custom"

            def execute(self, req):
                return {"ok": True, "cmd": req["cmd"], "result": {"hi": req.get("name")}}

            def resources(self):
                return [("x://a", "A", "")]

            def read_resource(self, uri):
                return "text of " + uri
        s = S()
        init = pc.mcp_handle(s, {"id": 1, "method": "initialize", "params": {}})["result"]
        self.assertEqual(init["instructions"], "custom")
        self.assertIn("resources", init["capabilities"])
        tools = pc.mcp_handle(s, {"id": 2, "method": "tools/list"})["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], ["hello"])
        self.assertEqual(tools[0]["inputSchema"]["required"], ["name"])
        self.assertTrue(tools[0]["annotations"]["readOnlyHint"])
        r = pc.mcp_handle(s, {"id": 3, "method": "tools/call", "params": {"name": "hello", "arguments": {"name": "Z"}}})["result"]
        self.assertIn('"hi": "Z"', r["content"][0]["text"])
        self.assertEqual(pc.mcp_handle(s, {"id": 4, "method": "resources/read", "params": {"uri": "x://a"}})["result"]["contents"][0]["text"], "text of x://a")
        self.assertIn("error", pc.mcp_handle(s, {"id": 5, "method": "resources/read", "params": {"uri": "x://nope"}}))

    def test_gui_tools_are_all_documented_and_wired(self):
        import agent_guide as guide
        import gui_agent as ga
        for name in ga.GUI_SPEC:
            self.assertTrue(ga.GUI_SPEC[name][0].strip(), name)
        text = guide.guide("all")
        for name in ga.GUI_SPEC:
            self.assertIn(name, text, "инструмент %s не описан в справке агента" % name)
        agent = ga.GuiAgent.__new__(ga.GuiAgent)
        self.assertEqual(set(ga.GUI_REQUIRED) - set(ga.GUI_SPEC), set())


if __name__ == "__main__":
    unittest.main()
