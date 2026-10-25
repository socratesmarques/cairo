import contextlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from cairo.config import Settings
from cairo.integrations.app_discovery import InstalledApp, launch_requested
from cairo.integrations.desktop_control import DesktopController
from cairo.models import Reply
from cairo.orchestrator import Orchestrator
from cairo.orchestrator.desktop_commands import parse_desktop_commands
from cairo.orchestrator.file_commands import parse_file_command


class OpenWithTests(unittest.TestCase):
    def test_compound_and_reversed_speech_requests(self):
        for text in (
            "nesse novo arquivo abre o visual Studio",
            "Abra no VS Code",
            'Crie o arquivo "teste.py" e abra no VS Code',
            'Leia "documents/test.py" e depois abra no VS Code',
        ):
            self.assertTrue(launch_requested(text), text)
        for text in (
            "Não abra no VS Code",
            'Explique "abra no VS Code"',
            "Se eu disser abra no VS Code, o que acontece?",
            'Crie um arquivo com texto "e abra no VS Code"',
            "Leia o arquivo que manda abrir o VS Code",
        ):
            self.assertFalse(launch_requested(text), text)

    def test_open_with_parser_preserves_target(self):
        self.assertIsNone(
            parse_desktop_commands(
                "Abra o visual Studio code nesse nesse novo arquivo", discover_apps=True
            )
        )
        self.assertIsNone(parse_desktop_commands("Abra no VS Code", discover_apps=True))
        expected = [("open_file", {"path": "C:\\Docs\\teste.py", "app": "VS Code"})]
        self.assertEqual(
            parse_file_command('Abra o arquivo "C:\\Docs\\teste.py" no VS Code'),
            expected,
        )
        self.assertEqual(
            parse_file_command('Abra no VS Code o arquivo "C:\\Docs\\teste.py"'),
            expected,
        )

    def test_selected_editor_gets_file_as_separate_argument(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "test & code.py"
            target.write_text("print('Cairo')")
            editor = Path(temp) / "Code.exe"
            installed = InstalledApp(
                "installed:code", "Visual Studio Code", str(editor), "exe"
            )
            desktop = DesktopController(True, discover_apps=True)
            with (
                patch(
                    "cairo.integrations.app_discovery.find_app", return_value=installed
                ),
                patch("cairo.integrations.desktop_control.subprocess.Popen") as popen,
            ):
                result = desktop.open_file(str(target), app="VS Code")
                self.assertTrue(result["requested"])
                self.assertEqual(popen.call_args.args[0], [str(editor), str(target)])
                self.assertFalse(popen.call_args.kwargs["shell"])
            start_menu = InstalledApp(
                "installed:code",
                "Visual Studio Code",
                "Microsoft.VisualStudioCode",
                "appsfolder",
            )
            with (
                patch(
                    "cairo.integrations.app_discovery.find_app", return_value=start_menu
                ),
                patch(
                    "cairo.integrations.desktop_control.resolve_app",
                    return_value=editor,
                ) as resolve,
                patch("cairo.integrations.desktop_control.subprocess.Popen") as popen,
            ):
                desktop.open_file(str(target), app="installed:code")
                resolve.assert_called_once_with("vscode")
                self.assertEqual(popen.call_args.args[0], [str(editor), str(target)])

    def test_model_can_open_after_compound_request(self):
        class Model:
            count = 0

            def complete(self, messages, tools):
                self.count += 1
                if self.count == 1:
                    return Reply(
                        calls=[
                            {
                                "id": "open",
                                "type": "function",
                                "function": {
                                    "name": "open_file",
                                    "arguments": json.dumps(
                                        {"path": str(target), "app": "VS Code"}
                                    ),
                                },
                            }
                        ]
                    )
                return Reply("Abertura solicitada")

        with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
            root = Path(temp)
            target = root / "teste.py"
            target.write_text("print('Cairo')")
            app = Orchestrator(
                Settings(
                    workspace=root / "workspace",
                    data_dir=root / "data",
                    allow_desktop=True,
                    full_file_access=True,
                    discover_apps=True,
                ),
                Model(),
            )
            stack.callback(app.close)
            with patch.object(
                app.tools.desktop,
                "open_file",
                return_value={"requested": True, "message": "ok"},
            ) as opened:
                sid = app.memory.create_session()["id"]
                submitted = app.submit(
                    sid, "nesse novo arquivo abre o visual Studio", "normal"
                )
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    result = app.memory.run(submitted["id"])
                    if result["status"] in {"completed", "failed"}:
                        break
                    time.sleep(0.01)
                self.assertEqual(result["status"], "completed", result)
                opened.assert_called_once_with(str(target), app="VS Code")
