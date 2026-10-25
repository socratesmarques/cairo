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
