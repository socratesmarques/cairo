import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from cairo.config import Settings, load_env
from cairo.models import HTTPModel, ModelError, Reply


class Response:
    def __init__(self, data):
        self.data = json.dumps(data).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, size):
        return self.data[:size]


class ModelTests(unittest.TestCase):
    def test_openai_request_and_function_result(self):
        response = {"choices": [{"message": {"content": None, "tool_calls": [{"id": "call1", "function": {"name": "system_info", "arguments": "{}"}}]}}]}
        with patch("urllib.request.build_opener") as factory:
            factory.return_value.open.return_value = Response(response)
            model = HTTPModel(Settings(provider="openai-compatible", model="test", base_url="https://example.test/v1", api_key="test-key"))
            reply = model.complete([{"role": "user", "content": "hi"}], [])
            request = factory.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, "https://example.test/v1/chat/completions")
            self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
            self.assertFalse(json.loads(request.data)["stream"])
            self.assertEqual(reply.calls[0]["id"], "call1")

    def test_ollama_normalizes_arguments_without_mutating_history(self):
        call = {"id": "one", "type": "function", "function": {"name": "system_info", "arguments": "{}"}}
        history = [Reply(calls=[call]).message(), {"role": "tool", "name": "system_info", "tool_call_id": "one", "content": "{}"}]
        with patch("urllib.request.build_opener") as factory:
            factory.return_value.open.return_value = Response({"message": {"content": "done"}})
            reply = HTTPModel(Settings(provider="ollama", model="local")).complete(history, [])
            request = factory.return_value.open.call_args.args[0]
            wire = json.loads(request.data)
            self.assertTrue(request.full_url.endswith("/api/chat"))
            self.assertEqual(wire["messages"][0]["tool_calls"][0]["function"]["arguments"], {})
            self.assertEqual(wire["messages"][1]["tool_name"], "system_info")
            self.assertEqual(history[0]["tool_calls"][0]["function"]["arguments"], "{}")
            self.assertEqual(reply.content, "done")

    def test_malformed_and_empty_responses_fail(self):
        for payload in ({}, {"choices": []}, {"choices": [{"message": {"content": ""}}]}):
            with self.subTest(payload=payload), patch("urllib.request.build_opener") as factory:
                factory.return_value.open.return_value = Response(payload)
                with self.assertRaises(ModelError):
                    HTTPModel(Settings(provider="openai-compatible")).complete([], [])

    def test_connection_and_auth_errors_are_sanitized(self):
        for error in (URLError("secret"), HTTPError("https://example.test", 401, "secret", {}, None)):
            with patch("urllib.request.build_opener") as factory:
                factory.return_value.open.side_effect = error
                with self.assertRaises(ModelError) as caught:
                    HTTPModel(Settings()).complete([], [])
                self.assertNotIn("secret", str(caught.exception))

    def test_blank_example_values_use_demo_defaults(self):
        with patch.dict(os.environ, {"CAIRO_PROVIDER": "demo", "CAIRO_MODEL": "", "CAIRO_BASE_URL": ""}, clear=True), patch("cairo.config.load_env"):
            settings = Settings.from_env()
            self.assertEqual(settings.model, "demo")
            self.assertTrue(settings.base_url.startswith("http://127.0.0.1"))

    def test_bad_configuration_is_rejected(self):
        cases = [{"CAIRO_PROVIDER": "unknown"}, {"CAIRO_PROVIDER": "ollama"}, {"CAIRO_TIMEOUT": "nan"}, {"CAIRO_MAX_STEPS": "0"}, {"CAIRO_ALLOW_WRITE": "yes"}, {"CAIRO_BASE_URL": "http://remote.test"}]
        for case in cases:
            with self.subTest(case=case), patch.dict(os.environ, case, clear=True), patch("cairo.config.load_env"):
                with self.assertRaises(ValueError):
                    Settings.from_env()

    def test_environment_has_priority_over_env_file(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"CAIRO_MODEL": "existing"}, clear=True):
            path = Path(folder) / ".env"
            path.write_text("CAIRO_MODEL=other\nCAIRO_PROVIDER=demo\n", encoding="utf-8")
            load_env(path)
            self.assertEqual(os.environ["CAIRO_MODEL"], "existing")
            self.assertEqual(os.environ["CAIRO_PROVIDER"], "demo")
