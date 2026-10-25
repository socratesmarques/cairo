"""Explicit user commands, bounded output/runtime and Windows job cleanup."""

import base64
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from cairo.sandbox.file_roots import FileRoots
from cairo.sandbox.windows_job import WindowsJob

MAX_COMMAND = 5000
MAX_STREAM = 32768
MAX_DISPLAY = 12000


class CommandRunner:
    def __init__(self, roots: FileRoots, enabled: bool = False, timeout: float = 30):
        self.roots, self.enabled, self.timeout = roots, enabled, timeout
        self.slot = threading.BoundedSemaphore(2)

    @staticmethod
    def arguments(shell: str, command: str):
        system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        if shell == "cmd":
            executable = system / "cmd.exe"
            # /S removes the wrapper quotes; the explicitly supplied command remains intact.
            return f'"{executable}" /d /s /c "chcp 65001 >nul & {command}"'
        executable = system / "WindowsPowerShell/v1.0/powershell.exe"
        script = (
            "$ProgressPreference='SilentlyContinue'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); $ErrorActionPreference='Stop'; try { & {\n"
            + command
            + "\n}; if ($null -ne $LASTEXITCODE) { exit $LASTEXITCODE } } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }"
        )
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        return [
            str(executable),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-OutputFormat",
            "Text",
            "-EncodedCommand",
            encoded,
        ]

    def run(
        self,
        shell: str,
        command: str,
        cwd: str = "",
        cancelled: threading.Event | None = None,
    ) -> dict:
        if not self.enabled:
            raise PermissionError(
                "Execução de comandos desativada em CAIRO_ALLOW_COMMANDS"
            )
        if sys.platform != "win32":
            raise OSError("Este executor de CMD/PowerShell requer Windows")
        if (
            shell not in {"cmd", "powershell"}
            or not isinstance(command, str)
            or not 1 <= len(command) <= MAX_COMMAND
            or "\x00" in command
        ):
            raise ValueError("Shell ou comando inválido")
        directory = self.roots.resolve(cwd) if cwd else self.roots.workspace
        if not directory.is_dir():
            raise NotADirectoryError("A pasta de trabalho não existe")
        if cancelled is not None and cancelled.is_set():
            return {
                "status": "cancelled",
                "exit_code": None,
                "message": "Comando cancelado antes de iniciar.",
            }
        if not self.slot.acquire(blocking=False):
            raise OSError("Já existem dois comandos em execução")
        job = None
        process = None
        buffers = [bytearray(), bytearray()]
        truncated = [False, False]
        threads = []
        status = "completed"

        def drain(stream, index):
            try:
                for chunk in iter(lambda: stream.read(4096), b""):
                    room = MAX_STREAM - len(buffers[index])
                    buffers[index].extend(chunk[: max(0, room)])
                    if len(chunk) > room:
                        truncated[index] = True
            finally:
                stream.close()

        try:
            job = WindowsJob()
            # Provider credentials are not inherited by child commands.
            environment = {
                k: v
                for k, v in os.environ.items()
                if not k.upper().startswith(("CAIRO_", "FCC_", "OPENAI_", "ANTHROPIC_"))
            }
            environment.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
            process = subprocess.Popen(
                self.arguments(shell, command),
                shell=False,
                cwd=str(directory),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW
                | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            try:
                job.assign(process)
            except OSError:
                # A very short command may already have exited before assignment.
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                    raise
            for index, stream in enumerate((process.stdout, process.stderr)):
                thread = threading.Thread(
                    target=drain, args=(stream, index), daemon=True
                )
                thread.start()
                threads.append(thread)
            deadline = time.monotonic() + self.timeout
            while process.poll() is None:
                if cancelled is not None and cancelled.is_set():
                    status = "cancelled"
                    break
                if time.monotonic() >= deadline:
                    status = "timeout"
                    break
                time.sleep(0.05)
            job.close()
            process.wait(timeout=5)
            for thread in threads:
                thread.join(timeout=3)
            output, error = (
                bytes(value)
                .decode("utf-8", errors="replace")
                .replace("\r\n", "\n")
                .replace("\r", "")
                for value in buffers
            )
            if status == "completed" and process.returncode != 0:
                status = "failed"
            labels = {
                "completed": "Comando concluído",
                "failed": "Comando falhou",
                "timeout": "Comando excedeu o tempo limite",
                "cancelled": "Comando cancelado",
            }
            message = f"{labels[status]} ({shell}; código {process.returncode})."
            if output:
                message += "\nSaída:\n" + output
            if error:
                message += "\nErros:\n" + error
            cut = len(message) > MAX_DISPLAY or any(truncated)
            message = message[:MAX_DISPLAY] + ("\n[Saída truncada]" if cut else "")
            return {
                "status": status,
                "shell": shell,
                "cwd": str(directory),
                "exit_code": process.returncode,
                "stdout": output,
                "stderr": error,
                "truncated": cut,
                "message": message,
            }
        finally:
            if job:
                job.close()
            if process and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            for thread in threads:
                thread.join(timeout=1)
            self.slot.release()
