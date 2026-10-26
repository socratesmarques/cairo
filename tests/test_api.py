import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from cairo.api import Server
from cairo.config import Settings
from cairo.models.errors import ModelError


class APITests(unittest.TestCase):
    def test_daily_api_validation_isolation_and_assets(self):
        _, first = self.post("/api/sessions", {})
        _, second = self.post("/api/sessions", {})
        sid = first["id"]
        def invoke(name, args, session=sid):
            return self.post("/api/productivity", {"session_id":session,"tool":name,"arguments":args})
        status, result = invoke("task_create", {"text":"API task"})
        self.assertEqual(status,200)
        item = result["result"]
        self.assertEqual(invoke("task_update", {"id":item["id"],"text":"hijack"}, second["id"])[0],400)
        self.assertEqual(invoke("run_command", {"shell":"cmd","command":"echo no"})[0],400)
        self.assertEqual(invoke("focus_start", {"seconds":True})[0],400)
        self.assertEqual(invoke("task_create", ["bad"])[0],400)
        status, _, body = self.request("GET", "/api/productivity?session_id="+sid)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)["tasks"][0]["text"],"API task")
        for path in ("/api/commands","/api/focus-alerts","/static/productivity.js","/static/productivity.css"):
            self.assertEqual(self.request("GET",path)[0],200)
        self.assertEqual(self.request("POST","/api/productivity",{})[0],403)

    def test_daily_commands_execute_without_model_or_desktop(self):
        _, session = self.post("/api/sessions", {})
        for message, fragment in (("Adicione tarefa: Preparar a reunião", "Tarefa salva"), ("Calcule (25+5)*3", "90"), ("Converta 2,5 km para m", "2500"), ("Meu dia", "1 tarefas abertas")):
            status, run = self.post("/api/runs", {"session_id":session["id"],"message":message,"mode":"normal"})
            self.assertEqual(status,202)
            for _ in range(100):
                current = self.server.app.memory.run(run["id"])
                if current["status"] in {"completed","failed"}: break
                time.sleep(.02)
            self.assertEqual(current["status"],"completed", current)
            self.assertIn(fragment,current["result"])

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.server = Server(
            ("127.0.0.1", 0),
            Settings(workspace=root / "workspace", data_dir=root / "data"),
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3
        )
        try:
            conn.request(
                method,
                path,
                body=json.dumps(body) if body is not None else None,
                headers=headers or {},
            )
            response = conn.getresponse()
            data = response.read()
            return response.status, dict(response.getheaders()), data
        finally:
            conn.close()

    def post(self, path, body):
        status, _, data = self.request(
            "POST",
            path,
            body,
            {"Content-Type": "application/json", "X-Cairo-Client": "web"},
        )
        return status, json.loads(data)

    def test_chat_end_to_end(self):
        status, session = self.post("/api/sessions", {})
        self.assertEqual(status, 201)
        status, run = self.post(
            "/api/runs",
            {"session_id": session["id"], "message": "Olá Cairo", "mode": "swarm"},
        )
        self.assertEqual(status, 202)
        for _ in range(100):
            _, _, data = self.request("GET", "/api/runs/" + run["id"])
            result = json.loads(data)
            if result["status"] in {"completed", "failed"}:
                break
            time.sleep(0.02)
        self.assertEqual(result["status"], "completed", result)
        _, _, data = self.request("GET", "/api/sessions/" + session["id"])
        self.assertEqual(len(json.loads(data)["messages"]), 2)

    def test_cross_origin_and_missing_header_blocked(self):
        self.assertEqual(self.request("POST", "/api/sessions", {})[0], 403)
        self.assertEqual(
            self.request("GET", "/api/config", headers={"Origin": "https://evil.test"})[
                0
            ],
            403,
        )
        self.assertEqual(
            self.request("GET", "/api/config", headers={"Host": "evil.test"})[0], 403
        )

    def test_static_assets_and_security_headers(self):
        for path in ("/", "/static/app.js", "/static/style.css"):
            status, headers, body = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertTrue(body)
            self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(self.request("GET", "/static/../../.env")[0], 404)

    def test_invalid_inputs_and_missing_resources(self):
        self.assertEqual(self.post("/api/runs", {"message": 2})[0], 400)
        self.assertEqual(
            self.post("/api/runs", {"session_id": "missing", "message": "hi"})[0], 404
        )
        self.assertEqual(self.request("GET", "/api/runs/missing")[0], 404)

    def test_config_never_contains_credentials(self):
        _, _, raw = self.request("GET", "/api/config")
        self.assertNotIn("api_key", json.loads(raw))

    def test_import_and_older_messages_boundaries(self):
        document = {"title": "Importada", "messages": [{"role": "user", "content": "x" * 70000}]}
        status, session = self.post("/api/sessions/import", document)
        self.assertEqual(status, 201)
        sid = session["id"]
        self.assertEqual(self.request("POST", "/api/sessions/import", document)[0], 403)
        self.assertEqual(self.post("/api/sessions/import", {"title": "bad", "messages": [{"role": "system", "content": "unsafe"}]})[0], 400)
        message = self.server.app.memory.session(sid)["messages"][0]
        status, _, raw = self.request("GET", f"/api/sessions/{sid}/messages?before={message['id'] + 1}")
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(raw)["messages"]), 1)
        self.assertEqual(self.request("GET", f"/api/sessions/{sid}/messages?before=-1")[0], 400)
        self.assertEqual(self.request("GET", "/api/sessions?offset=-1")[0], 400)
        self.assertEqual(self.request("GET", "/static/history.js")[0], 200)

    def test_session_organization_export_and_backup(self):
        _, session = self.post("/api/sessions", {})
        sid = session["id"]
        self.server.app.memory.add_message(sid, "user", "planejamento único")
        status, renamed = self.post(f"/api/sessions/{sid}/update", {"title": "Projeto Cairo", "pinned": True})
        self.assertEqual(status, 200)
        self.assertEqual(renamed["title"], "Projeto Cairo")
        self.assertEqual(self.request("POST", f"/api/sessions/{sid}/update", {"title": "unsafe"})[0], 403)
        self.assertEqual(self.post(f"/api/sessions/{sid}/update", {"archived": "yes"})[0], 400)
        _, _, raw = self.request("GET", "/api/sessions?q=planejamento")
        self.assertIn(sid, [item["id"] for item in json.loads(raw)])
        self.post(f"/api/sessions/{sid}/update", {"archived": True})
        self.assertEqual(self.post("/api/runs", {"session_id": sid, "message": "oi"})[0], 409)
        _, _, raw = self.request("GET", "/api/sessions?archived=1")
        self.assertIn(sid, [item["id"] for item in json.loads(raw)])
        status, _, raw = self.request("GET", f"/api/sessions/{sid}/export")
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(raw)["messages"]), 1)
        self.assertEqual(self.post("/api/backup", {})[0], 201)
        self.assertEqual(self.request("POST", "/api/backup", {})[0], 403)
        self.assertEqual(self.request("GET", "/api/sessions?q=" + "x" * 201)[0], 400)
        for path in ("/static/daily.css", "/static/markdown.js"):
            self.assertEqual(self.request("GET", path)[0], 200)

    def test_ai_diagnostics(self):
        with patch.object(
            self.server.app.ai,
            "health",
            return_value={"provider": "fcc", "online": False, "ready": False},
        ):
            status, _, raw = self.request("GET", "/api/ai/health")
            self.assertEqual(status, 200)
            self.assertFalse(json.loads(raw)["online"])
        with patch.object(
            self.server.app.ai,
            "list_models",
            return_value={"models": [{"id": "configured"}]},
        ):
            status, _, raw = self.request("GET", "/api/ai/models")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw)["models"][0]["id"], "configured")
        with patch.object(
            self.server.app.ai,
            "list_models",
            side_effect=ModelError("FCC offline", code="offline"),
        ):
            status, _, raw = self.request("GET", "/api/ai/models")
            self.assertEqual(status, 502)
            self.assertEqual(json.loads(raw)["error"]["code"], "offline")
            self.assertNotIn(b"Traceback", raw)

    def test_non_loopback_bind_rejected(self):
        with self.assertRaises(ValueError):
            Server(("0.0.0.0", 0), Settings())

    def test_reminder_api_and_session_boundary(self):
        from datetime import datetime, timedelta, timezone

        _, session = self.post("/api/sessions", {})
        due = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        status, reminder = self.post(
            "/api/reminders", {"session_id": session["id"], "text": "Pausa", "due": due}
        )
        self.assertEqual(status, 201)
        self.assertEqual(self.request("POST", "/api/reminders", {})[0], 403)
        _, _, raw = self.request("GET", "/api/reminders")
        self.assertIn(reminder["id"], [r["id"] for r in json.loads(raw)])
        self.assertEqual(
            self.post(
                "/api/reminders/dismiss", {"id": reminder["id"], "session_id": "wrong"}
            )[0],
            404,
        )
        self.assertEqual(
            self.post(
                "/api/reminders/dismiss",
                {"id": reminder["id"], "session_id": session["id"]},
            )[0],
            200,
        )
        self.assertEqual(
            self.post(
                "/api/reminders",
                {"session_id": session["id"], "text": "Pausa", "due": "bad"},
            )[0],
            400,
        )
