import asyncio
import copy
import http.client
import json
import os
import tempfile
import threading
import unittest
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from cairo.config import Settings, load_env
from cairo.models import ModelError, create_model
from cairo.models.fcc import MAX_RESPONSE_BYTES, FCCModel
from cairo.models.fcc_protocol import decode, encode
from cairo.models.service import AIService

CATALOG = {
    "data": [{"id": "provider/model-a"}, {"id": "provider/model-b"}],
    "default_model_id": "provider/model-a",
    "has_more": False,
}
ANSWER = {
    "type": "message",
    "role": "assistant",
    "content": [{"type": "text", "text": "CAIRO OK"}],
    "stop_reason": "end_turn",
}


class Response:
    def __init__(self, payload, *, content_type="application/json", status=200):
        self.raw = (
            payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        )
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, count):
        return self.raw[:count]


def settings(**kwargs):
    return Settings(
        provider="fcc",
        base_url="http://127.0.0.1:8082",
        model=kwargs.pop("model", ""),
        **kwargs,
    )


class FCCTests(unittest.TestCase):
    def test_factory_and_chat_default_model(self):
        with patch("urllib.request.build_opener") as factory:
            factory.return_value.open.side_effect = [
                Response(CATALOG),
                Response(ANSWER),
            ]
            model = create_model(settings(api_key="test-token"))
            result = model.complete(
                [
                    {"role": "system", "content": "Português"},
                    {"role": "user", "content": "Olá"},
                ],
                [],
            )
            self.assertIsInstance(model, FCCModel)
            self.assertEqual(result.content, "CAIRO OK")
            requests = factory.return_value.open.call_args_list
            self.assertEqual(
                requests[0].args[0].full_url,
                "http://127.0.0.1:8082/v1/models?view=messages",
            )
            request = requests[1].args[0]
            self.assertEqual(request.full_url, "http://127.0.0.1:8082/v1/messages")
            self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
            body = json.loads(request.data)
            self.assertEqual(body["model"], CATALOG["default_model_id"])
            self.assertEqual(body["system"], "Português")
            self.assertFalse(body["stream"])
            self.assertNotIn("thinking", body)

    def test_offline_timeout_and_http_errors_are_distinct_and_safe(self):
        cases = [
            (URLError(ConnectionRefusedError()), "offline"),
            (TimeoutError(), "timeout"),
            (URLError(TimeoutError()), "timeout"),
            (http.client.BadStatusLine("secret"), "invalid_http"),
            (ConnectionResetError("secret"), "network"),
        ]
        cases += [
            (
                HTTPError("secret", status, "secret", {}, None),
                "authentication" if status in (401, 403) else "http_error",
            )
            for status in (401, 403, 404, 422, 429, 500, 503)
        ]
        for error, code in cases:
            with (
                self.subTest(code=code),
                patch("urllib.request.build_opener") as factory,
            ):
                factory.return_value.open.side_effect = error
                with self.assertRaises(ModelError) as caught:
                    FCCModel(settings()).list_models()
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn("secret", str(caught.exception))

    def test_invalid_http_json_and_catalog(self):
        responses = [
            (Response(b"<html>oops</html>", content_type="text/html"), "invalid_http"),
            (Response(b"{broken"), "unexpected_response"),
            (Response(b"x" * (MAX_RESPONSE_BYTES + 1)), "unexpected_response"),
            (Response({"data": [None]}), "unexpected_response"),
            (Response([]), "unexpected_response"),
            (Response({**CATALOG, "has_more": True}), "unexpected_response"),
        ]
        for response, code in responses:
            with (
                self.subTest(code=code),
                patch("urllib.request.build_opener") as factory,
            ):
                factory.return_value.open.return_value = response
                with self.assertRaises(ModelError) as caught:
                    FCCModel(settings()).list_models()
                self.assertEqual(caught.exception.code, code)

    def test_tool_roundtrip_preserves_ids_system_and_opaque_reasoning(self):
        payload = {
            **ANSWER,
            "content": [
                {"type": "thinking", "thinking": "private", "signature": "sig"},
                {
                    "type": "tool_use",
                    "id": "call-a",
                    "name": "read_file",
                    "input": {"path": "x"},
                },
                {
                    "type": "tool_use",
                    "id": "call-b",
                    "name": "system_info",
                    "input": {},
                },
            ],
        }
        reply = decode(payload)
        history = [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "test"},
            reply.message(),
            {"role": "tool", "tool_call_id": "call-a", "content": "contents"},
            {"role": "tool", "tool_call_id": "call-b", "content": "info"},
        ]
        before = copy.deepcopy(history)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read",
                    "parameters": {"type": "object"},
                },
            }
        ]
        body = encode(history, tools)
        self.assertEqual(history, before)
        self.assertEqual(body["messages"][1]["content"], payload["content"])
        self.assertEqual(
            [b["tool_use_id"] for b in body["messages"][2]["content"]],
            ["call-a", "call-b"],
        )
        self.assertEqual(body["tools"][0]["input_schema"], {"type": "object"})
        self.assertNotIn("private", reply.content)
        self.assertNotIn("private", repr(reply))

    def test_response_parsing_rejects_partial_invalid_and_unsupported_blocks(self):
        payloads = [
            {},
            {**ANSWER, "content": "wrong"},
            {**ANSWER, "content": [{"type": "text", "text": 3}]},
            {
                **ANSWER,
                "content": [{"type": "tool_use", "id": "a", "name": "x", "input": []}],
            },
            {**ANSWER, "content": [{"type": "server_tool_use"}]},
            {**ANSWER, "content": []},
        ]
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(ModelError) as caught:
                decode(payload)
            self.assertEqual(caught.exception.code, "unexpected_response")
        with self.assertRaises(ModelError) as caught:
            decode({**ANSWER, "stop_reason": "max_tokens"})
        self.assertEqual(caught.exception.code, "output_limit")

    def test_health_online_auth_missing_model_and_offline(self):
        with patch("urllib.request.build_opener") as factory:
            factory.return_value.open.return_value = Response(CATALOG)
            health = FCCModel(settings(api_key="SECRET")).health()
            self.assertTrue(health["ready"])
            self.assertEqual(health["models_found"], 2)
            self.assertNotIn("SECRET", json.dumps(health))
            missing = FCCModel(settings(model="typo")).health()
            self.assertTrue(missing["online"])
            self.assertFalse(missing["ready"])
            self.assertEqual(missing["error"]["code"], "model_unavailable")
            factory.return_value.open.side_effect = HTTPError(
                "secret", 401, "secret", {}, None
            )
            self.assertEqual(
                FCCModel(settings()).health()["authentication"], "rejected"
            )
            factory.return_value.open.side_effect = URLError("secret")
            self.assertFalse(FCCModel(settings()).health()["online"])

    def test_async_chat_model_override_does_not_mutate_default(self):
        with patch("urllib.request.build_opener") as factory:
            factory.return_value.open.side_effect = [
                Response(CATALOG),
                Response(ANSWER),
            ]
            ai = AIService(settings())
            reply = asyncio.run(
                ai.chat([{"role": "user", "content": "hi"}], model="provider/model-b")
            )
            self.assertEqual(reply.content, "CAIRO OK")
            self.assertEqual(
                json.loads(factory.return_value.open.call_args.args[0].data)["model"],
                "provider/model-b",
            )
            self.assertEqual(ai.settings.model, "")

    def test_environment_configuration_and_validation(self):
        with (
            patch.dict(
                os.environ,
                {
                    "CAIRO_PROVIDER": "fcc",
                    "CAIRO_MODEL": "stale",
                    "CAIRO_API_KEY": "other-provider-secret",
                },
                clear=True,
            ),
            patch("cairo.config.load_env"),
        ):
            conf = Settings.from_env()
            self.assertEqual(conf.base_url, "http://127.0.0.1:8082")
            self.assertEqual(conf.model, "")
            self.assertEqual(conf.api_key, "")
        for url in (
            "http://remote.test",
            "http://127.0.0.1:8082/v1",
            "http://user:secret@localhost",
            "http://localhost:bad",
            "http://localhost?token=x",
        ):
            with (
                patch.dict(
                    os.environ,
                    {"CAIRO_PROVIDER": "fcc", "FCC_BASE_URL": url},
                    clear=True,
                ),
                patch("cairo.config.load_env"),
                self.assertRaises(ValueError),
            ):
                Settings.from_env()
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {"FCC_MODEL": "environment"}, clear=True),
        ):
            path = Path(folder) / ".env"
            path.write_text(
                "FCC_MODEL=file\nFCC_AUTH_TOKEN=secret\nFCC_BASE_URL=http://localhost:8082\n",
                encoding="utf-8",
            )
            load_env(path)
            self.assertEqual(os.environ["FCC_MODEL"], "environment")
            self.assertEqual(os.environ["FCC_AUTH_TOKEN"], "secret")
        self.assertNotIn("secret", repr(settings(api_key="secret")))


class LocalHTTPTests(unittest.TestCase):
    def test_real_http_auth_and_redirect_do_not_leak_token(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                seen.append((self.path, self.headers.get("Authorization")))
                if self.headers.get("Authorization") != "Bearer local-test":
                    self.send_response(401)
                    self.end_headers()
                    return
                body = json.dumps(CATALOG).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(307)
                self.send_header("Location", "/must-not-follow")
                self.end_headers()

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conf = Settings(
                provider="fcc",
                model="",
                base_url=f"http://127.0.0.1:{server.server_port}",
                api_key="local-test",
            )
            model = FCCModel(conf)
            self.assertTrue(model.health()["ready"])
            with self.assertRaises(ModelError) as caught:
                model.complete([{"role": "user", "content": "hi"}], [])
            self.assertEqual(caught.exception.status, 307)
            self.assertNotIn("/must-not-follow", [x[0] for x in seen])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
