import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from cairo.api import Server
from cairo.config import Settings
from cairo.core.diagnostics import Diagnostics
from cairo.models import HTTPModel
from cairo.orchestrator import Orchestrator


class DiagnosticsTests(unittest.TestCase):
    def test_revision_and_historical_failures_without_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = Orchestrator(
                Settings(workspace=root / "workspace", data_dir=root / "state")
            )
            try:
                sources = root / "sources"
                sources.mkdir()
                source = sources / "main.py"
                source.write_text("old")
                doctor = Diagnostics(app, sources)
                self.assertFalse(doctor.snapshot()["restart_required"])
                source.write_text("new")
                self.assertTrue(doctor.snapshot()["restart_required"])
                sid = app.memory.create_session()["id"]
                failed = app.memory.create_run(sid, "normal")
                app.memory.update_run(
                    failed["id"],
                    "failed",
                    error="MasterAgent atingiu o limite de 6 rodadas",
                )
                cancelled = app.memory.create_run(sid, "normal")
                app.memory.update_run(
                    cancelled["id"], "cancelled", error="secret-cancel"
                )
                result = doctor.snapshot()
                self.assertEqual(
                    result["historical_errors"],
                    [
                        {
                            "category": "step_limit",
                            "label": "Limite de etapas",
                            "count": 1,
                        }
                    ],
                )
                self.assertNotIn("secret-cancel", json.dumps(result))
                self.assertNotIn("api_key", json.dumps(result))
            finally:
                app.close()

    def test_catalog_health_and_error_taxonomy(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, limit):
                return json.dumps({"models": [{"name": "local:7b"}]}).encode()

        model = HTTPModel(Settings(provider="ollama", model="local:7b"))
        with patch("urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = Response()
            self.assertTrue(model.health()["ready"])
            opener.return_value.open.side_effect = URLError("private-key-secret")
            result = model.health()
            self.assertEqual(result["status"], "offline")
            self.assertNotIn("private-key-secret", json.dumps(result))
            opener.return_value.open.side_effect = HTTPError(
                "https://host", 401, "secret", {}, None
            )
            self.assertEqual(model.health()["status"], "authentication")
            opener.return_value.open.side_effect = TimeoutError()
            self.assertEqual(model.health()["status"], "timeout")


class DiagnosticsAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        cls.server = Server(
            ("127.0.0.1", 0),
            Settings(workspace=root / "workspace", data_dir=root / "state"),
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(2)
        cls.temp.cleanup()

    def request(self, path):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=5
        )
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_diagnostics_and_new_static_asset(self):
        status, raw = self.request("/api/diagnostics")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["max_steps"], 30)
        self.assertNotIn(b"api_key", raw)
        self.assertEqual(self.request("/static/client.js")[0], 200)

    def test_unexpected_error_is_safe_json_and_server_survives(self):
        with patch.object(
            self.server.app.memory, "sessions", side_effect=RuntimeError("SECRET")
        ):
            status, raw = self.request("/api/sessions")
            self.assertEqual(status, 500)
            self.assertEqual(json.loads(raw)["error"]["code"], "internal_error")
            self.assertNotIn(b"SECRET", raw)
        self.assertEqual(self.request("/api/health")[0], 200)
