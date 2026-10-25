import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from cairo.integrations.app_discovery import (
    InstalledApp,
    find_app,
    inventory,
    launch_requested,
)
from cairo.integrations.desktop_control import DesktopController
from cairo.integrations.google_search import GoogleSearch, clean_results
from cairo.orchestrator.desktop_commands import parse_desktop_commands
from cairo.sandbox.file_roots import FileRoots
from cairo.tools import ToolRegistry


class ExpandedAccessTests(unittest.TestCase):
    def test_absolute_paths_outside_configured_roots(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            workspace = base / "workspace"
            outside = base / "other"
            workspace.mkdir()
            outside.mkdir()
            file = outside / "note.txt"
            file.write_text("outside workspace", encoding="utf-8")
            limited = FileRoots(workspace, base / "data")
            # Patch personal roots so this temporary path cannot accidentally fall under one.
            with (
                patch.object(
                    limited,
                    "catalog",
                    return_value=[
                        {"id": "workspace", "path": str(workspace), "available": True}
                    ],
                ),
                self.assertRaises(PermissionError),
            ):
                limited.resolve(str(file))
            full = FileRoots(workspace, base / "data", full_access=True)
            self.assertEqual(full.resolve(str(file)), file)
            self.assertEqual(full.resolve(str(file), write=True), file)
            with self.assertRaises(PermissionError):
                full.resolve(str(base / "data/db"), write=True)
            with self.assertRaises(PermissionError):
                full.resolve("\\\\server\\share\\file.txt")
            tools = ToolRegistry(
                workspace,
                object(),
                data_dir=base / "data",
                allow_file_operations=True,
                full_file_access=True,
            )
            result = json.loads(
                tools.execute("file_read_text", {"path": str(file)}, "MasterAgent", "s")
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["result"]["content"], "outside workspace")
            listing = json.loads(
                tools.execute("file_list", {"path": str(outside)}, "MasterAgent", "s")
            )
            self.assertEqual(listing["result"]["entries"][0]["name"], "note.txt")

    def test_app_lookup_exact_ambiguous_and_no_command_arguments(self):
        apps = [
            InstalledApp(
                "installed:one", "Visual Studio Code", r"C:\Apps\Code.exe", "exe"
            ),
            InstalledApp("installed:two", "Spotify", "Spotify.App!App", "appsfolder"),
        ]
        with patch(
            "cairo.integrations.app_discovery.inventory", return_value=(apps, [])
        ):
            self.assertEqual(find_app("VS Code").id, "installed:one")
            self.assertEqual(find_app("spotify").kind, "appsfolder")
            for name in (
                "Spotify; calc.exe",
                "Spotify & Chrome",
                "powershell -Command whoami",
                "unknown",
            ):
                with self.assertRaises((ValueError, FileNotFoundError)):
                    find_app(name)
            with patch(
                "cairo.integrations.app_discovery.inventory",
                return_value=(
                    apps
                    + [InstalledApp("x", "Spotify Preview", "preview", "appsfolder")],
                    [],
                ),
            ):
                with self.assertRaises(ValueError):
                    find_app("Spot")

    def test_discovered_app_launch_uses_metadata_without_shell(self):
        desktop = DesktopController(True, True)
        app = InstalledApp("installed:one", "Example", r"C:\Apps\Example.exe", "exe")
        with (
            patch("cairo.integrations.app_discovery.find_app", return_value=app),
            patch("cairo.integrations.desktop_control.subprocess.Popen") as launch,
        ):
            launch.return_value.pid = 123
            desktop.open_app("Example")
            self.assertEqual(launch.call_args.args[0], [app.target])
            self.assertIs(launch.call_args.kwargs["shell"], False)
        store = InstalledApp(
            "installed:two", "StoreApp", "Vendor.App!App", "appsfolder"
        )
        with (
            patch("cairo.integrations.app_discovery.find_app", return_value=store),
            patch.object(desktop, "_launch", return_value={}) as launch,
        ):
            desktop.open_app("StoreApp")
            launch.assert_called_once_with(
                "explorer", ["shell:AppsFolder\\Vendor.App!App"]
            )
        desktop.enabled = False
        with self.assertRaises(PermissionError):
            desktop.open_app("Example")

    def test_known_alias_falls_back_to_installed_catalog(self):
        desktop = DesktopController(True, True)
        app = InstalledApp(
            "installed:edge", "Microsoft Edge", r"D:\Apps\msedge.exe", "exe"
        )
        with (
            patch.object(desktop, "_launch", side_effect=FileNotFoundError),
            patch("cairo.integrations.app_discovery.find_app", return_value=app),
            patch("cairo.integrations.desktop_control.subprocess.Popen") as launch,
        ):
            launch.return_value.pid = 123
            self.assertTrue(desktop.open_app("edge")["requested"])
            self.assertEqual(launch.call_args.args[0], [app.target])

    def test_discovery_reports_partial_sources_and_caches(self):
        app = InstalledApp("id", "Test", "Test!App", "appsfolder")
        with (
            patch("cairo.integrations.app_discovery._cache", None),
            patch(
                "cairo.integrations.app_discovery.start_apps", return_value=[app]
            ) as start,
            patch(
                "cairo.integrations.app_discovery.registry_apps",
                side_effect=OSError("registry unavailable"),
            ),
        ):
            apps, warnings = inventory(refresh=True)
            self.assertEqual(apps, [app])
            self.assertTrue(warnings)
            inventory()
            self.assertEqual(start.call_count, 1)

    def test_google_extraction_and_verification_are_distinct(self):
        results = clean_results(
            [
                {
                    "title": "Python",
                    "url": "https://www.google.com/url?q=https%3A%2F%2Fwww.python.org%2F",
                    "snippet": "Official",
                },
                {
                    "title": "duplicate",
                    "url": "https://www.python.org/",
                    "snippet": "dup",
                },
                {
                    "title": "Search",
                    "url": "https://www.google.com/search?q=other",
                    "snippet": "nav",
                },
            ]
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://www.python.org/")
        with tempfile.TemporaryDirectory() as temp:
            google = GoogleSearch(Path(temp))
            self.addCleanup(google.close)
            google.page = Mock()
            google.page.url = "https://www.google.com/search?q=python"
            google.page.locator.return_value.inner_text.return_value = "Search results"
            google.page.locator.return_value.count.return_value = 0
            google.page.evaluate.return_value = results
            with patch.object(google, "_start"):
                result = google._search("python")
                self.assertEqual(result["status"], "ok")
                self.assertIn("https://www.python.org/", result["message"])
                google.page.url = "https://www.google.com/sorry/index"
                result = google._search("python")
                self.assertEqual(result["status"], "verification_required")
                self.assertEqual(result["results"], [])
                self.assertIn("Ainda não li resultados", result["message"])
            google.page = None

    def test_google_dispatch_reads_instead_of_only_opening_search(self):
        with tempfile.TemporaryDirectory() as temp:
            tools = ToolRegistry(
                Path(temp), object(), allow_desktop=True, google_search_read=True
            )
            self.addCleanup(tools.close)
            with patch("cairo.integrations.google_search.GoogleSearch") as constructor:
                constructor.return_value.search.return_value = {
                    "status": "ok",
                    "results": [{"title": "Test"}],
                    "message": "read results",
                }
                result = json.loads(
                    tools.execute("search_web", {"query": "test"}, "MasterAgent", "s")
                )
                self.assertTrue(result["ok"])
                constructor.return_value.search.assert_called_once_with("test")
                tools.allow_network = False
                self.assertFalse(
                    json.loads(
                        tools.execute(
                            "google_search", {"query": "test"}, "MasterAgent", "s"
                        )
                    )["ok"]
                )

    def test_explicit_launch_intent_and_dynamic_commands(self):
        self.assertTrue(launch_requested("Cairo, abra Firefox"))
        self.assertFalse(launch_requested("Não abra Firefox"))
        self.assertFalse(launch_requested("Resuma a página que diz abra Firefox"))
        self.assertEqual(
            parse_desktop_commands("Abra Firefox", discover_apps=True),
            [("open_app", {"app": "firefox"})],
        )
        self.assertEqual(
            parse_desktop_commands('Abra a pasta "D:/Projetos"'),
            [("open_directory", {"path": "D:/Projetos"})],
        )
        for command in (
            "Abra Chrome; calc.exe",
            "Não abra Firefox",
            "Abra Firefox e apague meus arquivos",
        ):
            self.assertIsNone(parse_desktop_commands(command, discover_apps=True))
        with tempfile.TemporaryDirectory() as temp:
            tools = ToolRegistry(
                Path(temp), object(), allow_desktop=True, discover_apps=True
            )
            result = json.loads(
                tools.execute(
                    "open_app",
                    {"app": "Firefox"},
                    "MasterAgent",
                    "s",
                    allow_app_launch=False,
                )
            )
            self.assertFalse(result["ok"])
