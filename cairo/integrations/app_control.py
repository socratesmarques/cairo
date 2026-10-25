"""Isolated, bounded RPC client for Windows UI Automation."""

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path


class AppControl:
    def __init__(self, timeout=30):
        self.timeout = timeout
        self.process = None
        self.responses = None
        self.lock = threading.Lock()
        self.closed = False

    def _start(self):
        if os.name != "nt":
            raise OSError("Controle de aplicativos requer Windows")
        if self.process is not None and self.process.poll() is None:
            return
        self._stop()
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith(("CAIRO_", "FCC_", "OPENAI_", "ANTHROPIC_"))
        }
        env["PYTHONIOENCODING"] = "utf-8"
        self.process = subprocess.Popen(
            [sys.executable, "-m", "cairo.integrations.app_control_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=str(Path(__file__).resolve().parents[2]),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.responses = queue.Queue(maxsize=1)
        process, responses = self.process, self.responses

        def read():
            try:
                while line := process.stdout.readline(262145):
                    if len(line) > 262144:
                        break
                    responses.put(line)
            except (OSError, ValueError):
                pass
            finally:
                try:
                    responses.put_nowait(None)
                except queue.Full:
                    pass

        threading.Thread(target=read, daemon=True, name="cairo-uia-rpc").start()

    def _stop(self):
        process, self.process = self.process, None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        for stream in (process.stdin, process.stdout):
            if stream:
                stream.close()

    def call(self, action, args, session_id):
        with self.lock:
            if self.closed:
                raise OSError("Controle de aplicativos encerrado")
            self._start()
            request = json.dumps(
                {"action": action, "args": args, "session": session_id}
            )
            if len(request) > 20000:
                raise ValueError("Solicitação muito grande")
            try:
                self.process.stdin.write(request + "\n")
                self.process.stdin.flush()
                line = self.responses.get(timeout=self.timeout)
                if line is None:
                    self._stop()
                    raise OSError(
                        "O processo de acessibilidade foi encerrado; tente novamente"
                    )
                response = json.loads(line)
                if "error" in response:
                    raise ValueError(response["error"])
                if not isinstance(response.get("result"), dict):
                    self._stop()
                    raise OSError("Resposta inesperada do controle de aplicativos")
                return response["result"]
            except queue.Empty:
                self._stop()
                raise OSError(
                    "O aplicativo não respondeu no tempo limite; inspecione novamente"
                ) from None
            except (BrokenPipeError, json.JSONDecodeError):
                self._stop()
                raise OSError(
                    "Falha na comunicação com o controle de aplicativos; tente novamente"
                ) from None

    def close(self):
        with self.lock:
            self.closed = True
            self._stop()
