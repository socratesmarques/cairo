"""Loopback-only HTTP interface; no dependency on a web framework."""

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from cairo import __version__
from cairo.config import Settings
from cairo.core import log_event
from cairo.core.diagnostics import Diagnostics
from cairo.models import ModelError
from cairo.orchestrator import Orchestrator


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], settings: Settings):
        if address[0] not in {"127.0.0.1", "localhost"}:
            raise ValueError(
                "Cairo V1 aceita apenas host local: 127.0.0.1 ou localhost"
            )
        super().__init__(address, Handler)
        try:
            self.app = Orchestrator(settings)
            self.diagnostics = Diagnostics(self.app)
        except Exception:
            if hasattr(self, "app"):
                self.app.close()
            super().server_close()
            raise

    def server_close(self):
        super().server_close()
        if hasattr(self, "app"):
            self.app.close()


class Handler(BaseHTTPRequestHandler):
    server: Server

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, fmt, *args):
        # Avoid recording user-controlled URLs or raw HTTP payloads.
        return

    def send(self, status: int, data, content_type="application/json; charset=utf-8"):
        payload = (
            json.dumps(data, ensure_ascii=False).encode()
            if not isinstance(data, bytes)
            else data
        )
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(payload)

    def allowed(self, mutation=False) -> bool:
        port = self.server.server_address[1]
        hosts = {f"localhost:{port}", f"127.0.0.1:{port}"}
        if self.headers.get("Host", "") not in hosts:
            self.send(403, {"error": "Host não permitido"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + host for host in hosts}:
            self.send(403, {"error": "Origem não permitida"})
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.send(403, {"error": "Requisição entre sites bloqueada"})
            return False
        if mutation and (
            self.headers.get("X-Cairo-Client") != "web"
            or self.headers.get_content_type() != "application/json"
        ):
            self.send(403, {"error": "Use JSON e o cabeçalho X-Cairo-Client: web"})
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        path = urlsplit(self.path).path
        app = self.server.app
        try:
            if path == "/api/health":
                self.send(200, {"status": "ok", "version": __version__})
            elif path == "/api/diagnostics":
                self.send(200, self.server.diagnostics.snapshot())
            elif path == "/api/ai/health":
                self.send(200, app.ai.health())
            elif path == "/api/ai/models":
                self.send(200, app.ai.list_models())
            elif path == "/api/config":
                s = app.settings
                self.send(
                    200,
                    {
                        "provider": s.provider,
                        "model": s.model,
                        "max_steps": s.max_steps,
                        "version": __version__,
                        "allow_write": s.allow_write,
                        "allow_desktop": s.allow_desktop,
                        "workspace": str(s.workspace),
                        "data_dir": str(s.data_dir.resolve()),
                        "weather_city": s.weather_city,
                        "allow_personal_files": s.allow_personal_files,
                        "allow_network": s.allow_network,
                        "allow_file_operations": s.allow_file_operations,
                        "browser_javascript": s.browser_javascript,
                        "browser_channel": s.browser_channel,
                        "full_file_access": s.full_file_access,
                        "discover_apps": s.discover_apps,
                        "google_search_read": s.google_search_read,
                        "allow_commands": s.allow_commands,
                        "command_timeout": s.command_timeout,
                        "allow_app_control": s.allow_app_control,
                        "browser_automation": s.browser_automation,
                    },
                )
            elif path == "/api/reminders":
                self.send(200, app.reminders.list())
            elif path == "/api/sessions":
                self.send(200, app.memory.sessions())
            elif path.startswith("/api/sessions/"):
                self.send(200, app.memory.session(path.removeprefix("/api/sessions/")))
            elif path.startswith("/api/runs/"):
                self.send(200, app.memory.run(path.removeprefix("/api/runs/")))
            elif path in {
                "/",
                "/static/style.css",
                "/static/app.js",
                "/static/voice.js",
                "/static/client.js",
            }:
                filename = "index.html" if path == "/" else path.split("/")[-1]
                file = Path(__file__).parent.parent / "web" / filename
                media = {
                    ".js": "text/javascript",
                    ".css": "text/css",
                    ".html": "text/html",
                }[file.suffix]
                self.send(200, file.read_bytes(), media + "; charset=utf-8")
            else:
                self.send(404, {"error": "Rota não encontrada"})
        except ModelError as exc:
            self.send(502, {"error": exc.as_dict()})
        except KeyError as exc:
            self.send(404, {"error": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (OSError, sqlite3.Error):
            self.send(
                503,
                {
                    "error": {
                        "code": "local_resource",
                        "message": "Não foi possível acessar um recurso local. Confira o painel Diagnóstico e as permissões das pastas.",
                    }
                },
            )
        except Exception as exc:
            log_event(
                app.logger,
                kind="http_error",
                operation="GET",
                error_type=type(exc).__name__,
            )
            self.send(
                500,
                {
                    "error": {
                        "code": "internal_error",
                        "message": "Falha interna ao atender a solicitação. Consulte o diagnóstico.",
                    }
                },
            )

    def do_POST(self):
        if not self.allowed(mutation=True):
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 65536 or self.headers.get("Transfer-Encoding"):
                self.send(413, {"error": "Envie um corpo JSON de até 64 KB"})
                return
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("Corpo JSON deve ser um objeto")
            path = urlsplit(self.path).path
            app = self.server.app
            if path == "/api/sessions":
                self.send(201, app.memory.create_session())
            elif path == "/api/reminders":
                self.send(
                    201,
                    app.reminders.create(body["session_id"], body["text"], body["due"]),
                )
            elif path == "/api/reminders/dismiss":
                self.send(200, app.reminders.dismiss(body["id"], body["session_id"]))
            elif path == "/api/runs":
                sid, message, mode = (
                    body.get("session_id"),
                    body.get("message"),
                    body.get("mode", "normal"),
                )
                if not all(isinstance(v, str) for v in (sid, message, mode)):
                    raise ValueError("session_id, message e mode devem ser strings")
                self.send(202, app.submit(sid, message, mode))
            elif path.startswith("/api/runs/") and path.endswith("/cancel"):
                self.send(200, app.cancel(path.split("/")[-2]))
            else:
                self.send(404, {"error": "Rota não encontrada"})
        except KeyError as exc:
            self.send(404, {"error": str(exc)})
        except (ValueError, TypeError):
            self.send(
                400, {"error": "Dados inválidos; confira mensagem, conversa e modo"}
            )
        except RuntimeError as exc:
            self.send(409, {"error": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except TimeoutError:
            self.send(408, {"error": "O envio da solicitação excedeu o tempo limite."})
        except (OSError, sqlite3.Error):
            self.send(
                503,
                {
                    "error": "Não foi possível salvar ou acessar os dados locais. Confira espaço em disco e permissões."
                },
            )
        except Exception as exc:
            log_event(
                self.server.app.logger,
                kind="http_error",
                operation="POST",
                error_type=type(exc).__name__,
            )
            self.send(
                500,
                {
                    "error": "Falha interna ao atender a solicitação. Consulte o diagnóstico."
                },
            )
