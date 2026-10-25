import contextlib
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from cairo.config import Settings
from cairo.integrations.app_discovery import launch_requested
from cairo.integrations.file_manager import FileManager
from cairo.orchestrator import Orchestrator
from cairo.orchestrator.file_commands import parse_file_command
from cairo.sandbox.file_roots import FileRoots


class VoiceFileOpenTests(unittest.TestCase):
    def test_exact_spoken_request_and_quoted_names(self):
        text = "usando visual Studio code Abra o arquivo teste ponto python"
        self.assertTrue(launch_requested(text))
        self.assertEqual(
            parse_file_command(text),
            [("open_file", {"path": "teste.py", "app": "visual Studio code"})],
        )
        self.assertEqual(
            parse_file_command(
                "Abra o arquivo teste ponto python na pasta documentos no VS Code"
            ),
            [("open_file", {"path": "documents/teste.py", "app": "VS Code"})],
        )
        self.assertEqual(
            parse_file_command(
                'Abra o arquivo "C:\\Docs\\teste no projeto.py" no VS Code'
            ),
            [
                (
                    "open_file",
                    {"path": "C:\\Docs\\teste no projeto.py", "app": "VS Code"},
                )
            ],
        )
        self.assertFalse(
            launch_requested('Explique "usando VS Code abra o arquivo teste.py"')
        )

    def test_bare_filename_unique_missing_and_ambiguous(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folders = {
                name: root / name
                for name in ("workspace", "documents", "downloads", "desktop")
            }
            for folder in folders.values():
                folder.mkdir()
            manager = FileManager(
                FileRoots(folders["workspace"], root / "state", full_access=True)
            )
            target = folders["documents"] / "teste.py"
            target.write_text("print('Cairo')")
            with patch(
                "cairo.sandbox.file_roots.known_folder",
                side_effect=lambda name: folders[name],
            ):
                self.assertEqual(manager.resolve_open_path("teste.py"), target)
                with self.assertRaises(FileNotFoundError):
                    manager.resolve_open_path("missing.py")
                (folders["downloads"] / "teste.py").write_text("other")
                with self.assertRaises(ValueError):
                    manager.resolve_open_path("teste.py")

    def test_spoken_request_runs_without_model_or_stale_refusal(self):
        class NoModel:
            def complete(self, messages, tools):
                raise AssertionError("Direct spoken form must bypass model")

        with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
            root = Path(temp)
            documents = root / "documents"
            documents.mkdir()
            target = documents / "teste.py"
            target.write_text("pass")
            app = Orchestrator(
                Settings(
                    workspace=root / "workspace",
                    data_dir=root / "state",
                    full_file_access=True,
                    allow_desktop=True,
                ),
                NoModel(),
            )
            stack.callback(app.close)
            sid = app.memory.create_session()["id"]
            app.memory.add_message(sid, "assistant", "open_app está bloqueado")
            with (
                patch(
                    "cairo.sandbox.file_roots.known_folder",
                    side_effect=lambda name: (
                        documents if name == "documents" else root / "missing"
                    ),
                ),
                patch.object(
                    app.tools.desktop,
                    "open_file",
                    return_value={"message": "Abertura solicitada"},
                ) as opened,
            ):
                run = app.submit(
                    sid,
                    "usando visual Studio code Abra o arquivo teste ponto python",
                    "normal",
                )
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    result = app.memory.run(run["id"])
                    if result["status"] in {"completed", "failed"}:
                        break
                    time.sleep(0.01)
                self.assertEqual(result["status"], "completed", result)
                opened.assert_called_once_with(str(target), app="visual Studio code")
