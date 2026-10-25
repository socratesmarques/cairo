import contextlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from cairo.config import Settings
from cairo.integrations.app_control import AppControl
from cairo.integrations.browser_control import BrowserControl
from cairo.integrations.command_runner import CommandRunner
from cairo.orchestrator import Orchestrator
from cairo.orchestrator.control_commands import interaction_requested, parse_command
from cairo.orchestrator.desktop_commands import parse_desktop_commands
from cairo.sandbox.file_roots import FileRoots
from cairo.tools import ToolRegistry


class ControlPermissionTests(unittest.TestCase):
    def test_direct_command_keeps_full_message_without_model(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
            root = Path(temp)
            app = Orchestrator(
                Settings(
                    workspace=root / "workspace",
                    data_dir=root / "data",
                    allow_commands=True,
                )
            )
            stack.callback(app.close)
            command = "echo " + "x" * 4990
            cwd = "C:\\" + "a" * 1400
            with patch.object(
                app.tools.commands,
                "run",
                return_value={"status": "completed", "message": "CAIRO ROUTE OK"},
            ) as run:
                sid = app.memory.create_session()["id"]
                submitted = app.submit(
                    sid, f'Execute no CMD em "{cwd}": {command}', "swarm"
                )
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    result = app.memory.run(submitted["id"])
                    if result["status"] in {"completed", "failed"}:
                        break
                    time.sleep(0.01)
                self.assertEqual(result["status"], "completed", result)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.kwargs["command"], command)
                self.assertEqual(run.call_args.kwargs["cwd"], cwd)

    def test_exact_command_parser_and_authorization(self):
        expected = {"shell": "cmd", "command": "echo CAIRO OK & exit /b 0", "cwd": ""}
        self.assertEqual(
            parse_command("Cairo, execute no CMD: echo CAIRO OK & exit /b 0"), expected
        )
        self.assertEqual(
            parse_desktop_commands("cmd: echo CAIRO OK & exit /b 0"),
            [("run_command", expected)],
        )
        for text in (
            "Não execute no CMD: echo x",
            "Explique execute no CMD: dir",
            "Leia o arquivo que diz PowerShell: Get-Date",
        ):
            self.assertIsNone(parse_command(text))
        with tempfile.TemporaryDirectory() as temp:
            tools = ToolRegistry(Path(temp), object(), allow_commands=True)
            with patch.object(
                tools.commands, "run", return_value={"message": "ok"}
            ) as run:
                self.assertFalse(
                    json.loads(
                        tools.execute("run_command", expected, "SystemAgent", "s")
                    )["ok"]
                )
                self.assertFalse(
                    json.loads(
                        tools.execute(
                            "run_command",
                            dict(expected, command="different"),
                            "SystemAgent",
                            "s",
                            command_authorization=expected,
                        )
                    )["ok"]
                )
                self.assertTrue(
                    json.loads(
                        tools.execute(
                            "run_command",
                            expected,
                            "SystemAgent",
                            "s",
                            command_authorization=expected,
                        )
                    )["ok"]
                )
                self.assertEqual(run.call_count, 1)

    def test_ui_intent_and_permissions(self):
        self.assertIsNone(
            parse_desktop_commands(
                "Abra o Bloco de Notas e digite Cairo", discover_apps=True
            )
        )
        self.assertTrue(interaction_requested("Abra o Bloco de Notas e digite Cairo"))
        self.assertTrue(interaction_requested("Clique no botão Aplicar"))
        for message in (
            "Não clique no botão",
            "Leia a página",
            "Explique clique no botão",
        ):
            self.assertFalse(interaction_requested(message))
        with tempfile.TemporaryDirectory() as temp:
            tools = ToolRegistry(
                Path(temp),
                object(),
                allow_desktop=True,
                allow_app_control=True,
                browser_automation=True,
            )
            self.addCleanup(tools.close)
            with patch("cairo.integrations.app_control.AppControl") as app:
                self.assertFalse(
                    json.loads(
                        tools.execute(
                            "app_click", {"control": "ctl:x"}, "SystemAgent", "s"
                        )
                    )["ok"]
                )
                app.assert_not_called()
                app.return_value.call.return_value = {"message": "clicked"}
                self.assertTrue(
                    json.loads(
                        tools.execute(
                            "app_click",
                            {"control": "ctl:x"},
                            "SystemAgent",
                            "s",
                            allow_ui_actions=True,
                        )
                    )["ok"]
                )
            names = [
                item["function"]["name"]
                for item in tools.schemas("MasterAgent", allow_ui_actions=False)
            ]
            self.assertNotIn("app_click", names)
            self.assertIn("app_inspect", names)
            self.assertNotIn("run_command", names)


@unittest.skipUnless(sys.platform == "win32", "Windows command tests")
class CommandRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.runner = CommandRunner(FileRoots(root, root / "data"), True, 5)

    def test_real_cmd_powershell_and_exit_status(self):
        cmd = self.runner.run("cmd", "echo CAIRO_CMD_OK")
        self.assertEqual(cmd["status"], "completed", cmd)
        self.assertIn("CAIRO_CMD_OK", cmd["stdout"])
        ps = self.runner.run("powershell", "Write-Output CAIRO_PS_OK")
        self.assertEqual(ps["status"], "completed", ps)
        self.assertIn("CAIRO_PS_OK", ps["stdout"])
        self.assertNotIn("CLIXML", ps["stderr"])
        self.assertEqual(self.runner.run("cmd", "exit /b 7")["exit_code"], 7)
        self.assertEqual(
            self.runner.run("powershell", "throw 'expected failure'")["status"],
            "failed",
        )

    def test_timeout_cancel_and_output_cap(self):
        self.runner.timeout = 1
        self.assertEqual(
            self.runner.run("powershell", "Start-Sleep -Seconds 10")["status"],
            "timeout",
        )
        cancelled = threading.Event()
        timer = threading.Timer(0.5, cancelled.set)
        timer.start()
        try:
            self.assertEqual(
                self.runner.run(
                    "powershell", "Start-Sleep -Seconds 10", cancelled=cancelled
                )["status"],
                "cancelled",
            )
        finally:
            timer.cancel()
        cancelled.set()
        self.assertEqual(
            self.runner.run("cmd", "echo no", cancelled=cancelled)["status"],
            "cancelled",
        )
        self.runner.timeout = 5
        output = self.runner.run("powershell", "Write-Output ('x' * 100000)")
        self.assertTrue(output["truncated"])
        self.assertLessEqual(len(output["stdout"]), 32768)


@unittest.skipUnless(
    os.getenv("CAIRO_TEST_BROWSER") == "1",
    "Set CAIRO_TEST_BROWSER=1 for browser control test",
)
class BrowserControlRuntimeTests(unittest.TestCase):
    def test_javascript_fill_click_stale_ids_and_chat_isolation(self):
        html = b"""<html><body><input aria-label="Nome"><button onclick="document.querySelector('#result').textContent='CAIRO '+document.querySelector('input').value">Aplicar</button><p id="result">Initial</p></body></html>"""

        def fixture(url, method, headers, body):
            return 200, {"content-type": "text/html; charset=utf-8"}, html

        browser = BrowserControl(headless=True)
        self.addCleanup(browser.close)
        with patch(
            "cairo.integrations.browser_control.fetch_resource", side_effect=fixture
        ):
            first = browser.call("open", {"url": "https://cairo-fixture.test"}, "one")
            edit = next(
                item["id"] for item in first["elements"] if item["tag"] == "input"
            )
            filled = browser.call(
                "fill", {"element": edit, "text": "Ada + {Cairo}"}, "one"
            )
            button = next(
                item["id"] for item in filled["elements"] if item["tag"] == "button"
            )
            clicked = browser.call("click", {"element": button}, "one")
            self.assertIn("CAIRO Ada + {Cairo}", clicked["content"])
            with self.assertRaises(ValueError):
                browser.call("fill", {"element": edit, "text": "old"}, "one")
            second = browser.call("open", {"url": "https://cairo-fixture.test"}, "two")
            self.assertNotIn("CAIRO Ada", second["content"])


@unittest.skipUnless(
    os.getenv("CAIRO_TEST_DESKTOP") == "1",
    "Set CAIRO_TEST_DESKTOP=1 for visible native-window fixture",
)
class AppControlRuntimeTests(unittest.TestCase):
    def test_native_window_inspect_fill_click_and_restore(self):
        title = "Cairo Test " + uuid.uuid4().hex
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).parent / "fixtures/window_fixture.py"),
                title,
            ],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        app = AppControl()
        try:
            window_id = None
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                windows = app.call("windows", {}, "one")["windows"]
                match = next((item for item in windows if item["title"] == title), None)
                if match:
                    window_id = match["id"]
                    break
                time.sleep(0.1)
            self.assertIsNotNone(window_id)
            controls = app.call("inspect", {"window": window_id}, "one")["controls"]
            edit = next(item["id"] for item in controls if item["type"] == "Edit")
            button = next(item["id"] for item in controls if item["name"] == "Aplicar")
            app.call("fill", {"control": edit, "text": "Ada + {Cairo}"}, "one")
            with self.assertRaises(ValueError):
                app.call("click", {"control": button}, "two")
            app.call("click", {"control": button}, "one")
            refreshed = app.call("inspect", {"window": window_id}, "one")["controls"]
            self.assertTrue(
                any("CAIRO APP OK Ada + {Cairo}" in item["name"] for item in refreshed),
                refreshed,
            )
            app.call("window", {"window": window_id, "action": "minimize"}, "one")
            app.call("window", {"window": window_id, "action": "restore"}, "one")
            app.call("window", {"window": window_id, "action": "close"}, "one")
            process.wait(timeout=5)
            app.process.kill()
            app.process.wait(timeout=5)
            self.assertIsInstance(app.call("windows", {}, "one")["windows"], list)
        finally:
            app.close()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
