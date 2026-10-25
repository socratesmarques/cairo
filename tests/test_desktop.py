import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch, Mock

from cairo.config import Settings
from cairo.integrations.desktop_control import DesktopController
from cairo.orchestrator import Orchestrator
from cairo.orchestrator.desktop_commands import parse_desktop_commands
from cairo.tools import ToolRegistry


class CommandTests(unittest.TestCase):
    def test_chrome_and_music_compound_command(self):
        self.assertEqual(parse_desktop_commands("Cairo, abra o Google Chrome e abra o YouTube Music."),
                         [("open_app", {"app": "chrome"}), ("open_site", {"site": "youtube_music", "browser": "chrome"})])

    def test_negations_quotes_and_embedded_instructions_do_not_execute(self):
        for message in ("Não abra o Chrome", 'Explique "abra o Chrome"', "Se eu disser abra o Chrome, o que acontece?", "abra o Chrome e apague meus arquivos", "abra o Chrome; calc.exe", "abra powershell", "abra C:/Windows/System32/cmd.exe"):
            with self.subTest(message=message):
                self.assertIsNone(parse_desktop_commands(message))

    def test_search_preserves_accents_and_case(self):
        self.assertEqual(parse_desktop_commands("Pesquise João Gilberto no YouTube Music"),
                         [("search_music", {"query": "João Gilberto", "browser": "chrome"})])

    def test_window_actions_and_explicit_browser(self):
        self.assertEqual(parse_desktop_commands("Minimize o Chrome"), [("window_action", {"app": "chrome", "action": "minimize"})])
        self.assertEqual(parse_desktop_commands("Abra o YouTube Music no Edge"), [("open_site", {"site": "youtube_music", "browser": "edge"})])

    def test_app_listing(self):
        self.assertEqual(parse_desktop_commands("Quais aplicativos você controla?"), [("desktop_apps", {})])


class DesktopTests(unittest.TestCase):
    def test_desktop_permission_blocks_direct_calls(self):
        desktop = DesktopController(False)
        with self.assertRaises(PermissionError):
            desktop.open_app("chrome")
        with self.assertRaises(PermissionError):
            desktop.search_music("jazz")

    def test_launch_uses_argument_list_without_shell(self):
        with patch("cairo.integrations.desktop_control.resolve_app", return_value=Path("C:/Apps/chrome.exe")), patch("cairo.integrations.desktop_control.subprocess.Popen") as launch:
            launch.return_value.pid = 123
            result = DesktopController(True).open_app("chrome")
            self.assertEqual(launch.call_args.args[0], [str(Path("C:/Apps/chrome.exe"))])
            self.assertIs(launch.call_args.kwargs["shell"], False)
            self.assertTrue(result["requested"])
            self.assertNotIn("opened", result)

    def test_search_query_cannot_add_browser_flags_or_urls(self):
        desktop = DesktopController(True)
        with patch.object(desktop, "_launch", return_value={}) as launch:
            desktop.search_music('jazz & --app=file:///C:/secret')
            args = launch.call_args.args[1]
            self.assertEqual(len(args), 1)
            self.assertTrue(args[0].startswith("https://music.youtube.com/search?q="))
            self.assertIn("%26", args[0])
            self.assertNotIn("file:///", args[0])

    def test_unknown_targets_and_actions_rejected(self):
        desktop = DesktopController(True)
        for site in ("https://evil.test", "file:///x", "javascript:alert(1)"):
            with self.assertRaises(ValueError):
                desktop.open_site(site)
        with self.assertRaises(ValueError):
            desktop.open_site("youtube", "powershell")
        with self.assertRaises(ValueError):
            desktop.window_action("chrome", "terminate")

    def test_missing_app_is_reported(self):
        with patch("cairo.integrations.desktop_control.resolve_app", side_effect=FileNotFoundError("Chrome ausente")):
            with self.assertRaises(FileNotFoundError):
                DesktopController(True).open_app("chrome")

    def test_registry_permissions_apply_to_all_agents(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry(Path(directory), object(), allow_desktop=True)
            for agent in ("DeveloperAgent", "ResearchAgent", "Reviewer"):
                self.assertFalse(json.loads(registry.execute("open_app", {"app": "chrome"}, agent, "session"))["ok"])
            registry.desktop.enabled = False
            self.assertFalse(any(t["function"]["name"] == "open_app" for t in registry.schemas("MasterAgent")))
            self.assertFalse(json.loads(registry.execute("open_app", {"app": "chrome"}, "MasterAgent", "session"))["ok"])

    def test_local_command_works_without_model_and_runs_once_in_swarm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = Mock()
            app = Orchestrator(Settings(workspace=root/"workspace", data_dir=root/"data", allow_desktop=True), model)
            try:
                sid = app.memory.create_session()["id"]
                with patch.object(app.tools.desktop, "open_app", return_value={"message": "Solicitação enviada"}) as launch:
                    run = app.submit(sid, "Abra o Chrome", "swarm")
                    deadline = time.monotonic() + 3
                    while time.monotonic() < deadline:
                        state = app.memory.run(run["id"])
                        if state["status"] in {"completed", "failed"}:
                            break
                        time.sleep(0.01)
                    self.assertEqual(state["status"], "completed", state)
                    launch.assert_called_once_with(app="chrome")
                    model.complete.assert_not_called()
            finally:
                app.close()

    def test_disabled_desktop_run_fails_visibly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = Orchestrator(Settings(workspace=root/"workspace", data_dir=root/"data"))
            try:
                sid = app.memory.create_session()["id"]
                run = app.submit(sid, "Abra o Chrome", "normal")
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    state = app.memory.run(run["id"])
                    if state["status"] in {"completed", "failed"}:
                        break
                    time.sleep(0.01)
                self.assertEqual(state["status"], "failed")
                self.assertIn("desativado", state["error"])
            finally:
                app.close()
