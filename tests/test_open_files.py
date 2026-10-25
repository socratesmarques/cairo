import contextlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from cairo.config import Settings
from cairo.integrations.desktop_control import DesktopController
from cairo.orchestrator import Orchestrator
from cairo.orchestrator.file_commands import parse_file_command
from cairo.tools import ToolRegistry


class OpenFilesTests(unittest.TestCase):
    def test_parser_preserves_filename_and_negation(self):
        path = "C:\\Users\\Usuario\\Downloads\\Relatório 2026.pdf"
        self.assertEqual(
            parse_file_command(f'Abra o arquivo "{path}"'),
            [("open_file", {"path": path})],
        )
        self.assertEqual(
            parse_file_command(f"Abra o arquivo {path}"),
            [("open_file", {"path": path})],
        )
        self.assertIsNone(parse_file_command(f'Não abra o arquivo "{path}"'))
        self.assertIsNone(parse_file_command(f'Explique "abra o arquivo {path}"'))

    def test_default_application_receives_literal_filename_and_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "report & notes.pdf"
            target.write_bytes(b"fixture")
            desktop = DesktopController(True)
            with patch(
                "cairo.integrations.desktop_control.os.startfile", create=True
            ) as start:
                result = desktop.open_file(str(target))
                start.assert_called_once_with(str(target), "open")
                self.assertTrue(result["requested"])
                for code, text in [
                    (1155, "aplicativo padrão"),
                    (5, "recusou acesso"),
                    (1260, "política"),
                    (1223, "cancelada"),
                ]:
                    error = OSError("raw error")
                    error.winerror = code
                    start.side_effect = error
                    with self.assertRaises(OSError) as caught:
                        desktop.open_file(str(target))
                    self.assertIn(text, str(caught.exception))
            with self.assertRaises(FileNotFoundError):
                desktop.open_file(str(target.with_name("missing.pdf")))
            with self.assertRaises(ValueError):
                desktop.open_file(str(target.parent))

    def test_full_access_and_current_turn_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            target = root / "outside.xlsx"
            target.write_bytes(b"fixture")
            tools = ToolRegistry(
                workspace,
                object(),
                allow_desktop=True,
                full_file_access=True,
                data_dir=root / "state",
            )
            self.addCleanup(tools.close)
            with patch.object(
                tools.desktop, "open_file", return_value={"requested": True}
            ) as open_file:
                denied = json.loads(
                    tools.execute(
                        "open_file", {"path": str(target)}, "MasterAgent", "one"
                    )
                )
                self.assertFalse(denied["ok"])
                open_file.assert_not_called()
                result = json.loads(
                    tools.execute(
                        "open_file",
                        {"path": str(target)},
                        "MasterAgent",
                        "one",
                        allow_app_launch=True,
                    )
                )
                self.assertTrue(result["ok"], result)
                open_file.assert_called_once_with(str(target))
            names = [
                tool["function"]["name"]
                for tool in tools.schemas("MasterAgent", allow_app_launch=False)
            ]
            self.assertNotIn("open_file", names)

    def test_direct_open_file_runs_once_without_model_in_swarm(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
            root = Path(temp)
            target = root / "outside.pdf"
            target.write_bytes(b"fixture")
            app = Orchestrator(
                Settings(
                    workspace=root / "workspace",
                    data_dir=root / "state",
                    allow_desktop=True,
                    full_file_access=True,
                )
            )
            stack.callback(app.close)
            with patch.object(
                app.tools.desktop,
                "open_file",
                return_value={"message": "Abertura solicitada"},
            ) as open_file:
                sid = app.memory.create_session()["id"]
                submitted = app.submit(sid, f'Abra o arquivo "{target}"', "swarm")
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    result = app.memory.run(submitted["id"])
                    if result["status"] in {"completed", "failed"}:
                        break
                    time.sleep(0.01)
                self.assertEqual(result["status"], "completed", result)
                open_file.assert_called_once_with(str(target))
