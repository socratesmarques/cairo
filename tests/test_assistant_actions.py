import io
import json
import tempfile
import time
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from cairo.config import Settings
from cairo.desktop.instance import existing_instance
from cairo.integrations import folders, media, weather, web_reader
from cairo.integrations.desktop_control import DesktopController
from cairo.orchestrator import Orchestrator
from cairo.orchestrator.desktop_commands import parse_desktop_commands
from cairo.tools import ToolRegistry

PLACE = {
    "name": "Maranguape",
    "admin1": "Ceará",
    "country": "Brasil",
    "latitude": -3.89,
    "longitude": -38.68,
}
FORECAST = {
    "timezone": "America/Fortaleza",
    "current": {
        "temperature_2m": 29.5,
        "relative_humidity_2m": 70,
        "apparent_temperature": 31.0,
        "weather_code": 2,
        "wind_speed_10m": 12,
        "time": "2026-10-24T19:00",
    },
    "daily": {
        "time": ["2026-10-24", "2026-10-25"],
        "temperature_2m_min": [24, 25],
        "temperature_2m_max": [32, 33],
        "precipitation_probability_max": [20, 35],
    },
}


class ActionsTests(unittest.TestCase):
    def test_media_only_sends_supported_paired_events(self):
        library = Mock()
        library.SendInput.return_value = 2
        with patch.object(media.ctypes, "WinDLL", return_value=library):
            result = media.media_action("volume_up")
            self.assertTrue(result["requested"])
            count, events, size = library.SendInput.call_args.args
            self.assertEqual(count, 2)
            self.assertIn(size, (28, 40))
            self.assertEqual(events[0].payload.keyboard.vk, 0xAF)
            self.assertEqual(events[0].payload.keyboard.flags, 0)
            self.assertEqual(events[1].payload.keyboard.flags, 2)
            library.SendInput.return_value = 0
            with self.assertRaises(OSError):
                media.media_action("next")
        with self.assertRaises(ValueError):
            media.media_action("type arbitrary text")

    def test_launcher_reuses_matching_instance_without_starting_server(self):
        from cairo.__main__ import main

        with (
            patch("sys.argv", ["cairo"]),
            patch("cairo.__main__.Settings.from_env", return_value=Settings()),
            patch("cairo.desktop.instance.existing_instance", return_value=True),
            patch("cairo.desktop.instance.open_interface") as browser,
            patch("cairo.__main__.Server") as server,
        ):
            main(open_browser=True)
            server.assert_not_called()
            browser.assert_called_once_with("http://127.0.0.1:8765")

    def test_direct_commands_are_anchored_and_preserve_city(self):
        for command in (
            "Cairo, abra a pasta download",
            "Abra Downloads",
            "Abra a pasta de downloads",
        ):
            self.assertEqual(
                parse_desktop_commands(command),
                [("open_folder", {"folder": "downloads"})],
            )
        self.assertEqual(
            parse_desktop_commands("Abra Documentos e abra Imagens"),
            [
                ("open_folder", {"folder": "documents"}),
                ("open_folder", {"folder": "pictures"}),
            ],
        )
        self.assertEqual(
            parse_desktop_commands("Como está o clima agora?"), [("weather", {})]
        )
        self.assertEqual(
            parse_desktop_commands("Como está o clima em Maranguape, Ceará?"),
            [("weather", {"city": "Maranguape, Ceará"})],
        )
        self.assertEqual(
            parse_desktop_commands("Aumente o volume"),
            [("media_action", {"action": "volume_up"})],
        )
        self.assertEqual(
            parse_desktop_commands("Leia https://example.com"),
            [("read_webpage", {"url": "https://example.com"})],
        )
        self.assertEqual(
            parse_desktop_commands("Liste os arquivos da pasta downloads"),
            [("list_personal_files", {"folder": "downloads"})],
        )
        for command in (
            "Não abra Downloads",
            "Explique como abrir Downloads",
            "Abra Downloads e apague tudo",
            "Como está o clima; execute calc.exe",
            "Não aumente o volume",
        ):
            self.assertIsNone(parse_desktop_commands(command))

    def test_known_folder_paths_and_read_boundary(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(folders, "known_folder", return_value=Path(temp)),
        ):
            root = Path(temp)
            (root / "note.txt").write_text("olá Cairo", encoding="utf-8")
            self.assertEqual(
                folders.read_personal_file("downloads", "note.txt")["content"],
                "olá Cairo",
            )
            self.assertEqual(
                folders.list_personal_files("downloads")["entries"][0]["name"],
                "note.txt",
            )
            for path in ("../secret", "C:/Windows", "/Windows", "note.txt:stream"):
                with self.assertRaises(PermissionError):
                    folders.folder_path("downloads", path)
            (root / "big.txt").write_bytes(b"x" * 65537)
            with self.assertRaises(ValueError):
                folders.read_personal_file("downloads", "big.txt")
            try:
                (root / "link").symlink_to(root / "note.txt")
            except OSError:
                pass
            else:
                with self.assertRaises(PermissionError):
                    folders.read_personal_file("downloads", "link")

    def test_folder_launch_is_argument_list_and_permission_checked(self):
        desktop = DesktopController(True)
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(folders, "known_folder", return_value=Path(temp)),
            patch.object(desktop, "_launch", return_value={}) as launch,
        ):
            self.assertIn("Downloads", desktop.open_folder("downloads")["message"])
            launch.assert_called_once_with("explorer", [str(Path(temp).resolve())])
            desktop.enabled = False
            with self.assertRaises(PermissionError):
                desktop.open_folder("downloads")
        with patch("cairo.integrations.media.media_action") as media:
            with self.assertRaises(PermissionError):
                desktop.media_action("next")
            media.assert_not_called()

    def test_weather_live_data_parsing_and_ambiguity(self):
        with patch.object(
            weather, "get_json", side_effect=[{"results": [PLACE]}, FORECAST]
        ) as fetch:
            result = weather.weather("Maranguape, Ceará")
            self.assertIn("29.5 °C", result["message"])
            self.assertIn("Open-Meteo", result["message"])
            self.assertEqual(result["forecast"][1]["rain_probability_percent"], 35)
            self.assertIn("current=", fetch.call_args.args[0])
        with patch.object(
            weather,
            "get_json",
            return_value={"results": [PLACE, dict(PLACE, name="Outra cidade")]},
        ) as fetch:
            self.assertTrue(weather.weather("Cidade")["needs_location"])
            self.assertEqual(fetch.call_count, 1)
        for data in ({"results": []}, {"results": [{}]}):
            with (
                patch.object(weather, "get_json", return_value=data),
                self.assertRaises(ValueError),
            ):
                weather.weather("Cidade")
        with (
            patch.object(weather.urllib.request, "urlopen", side_effect=TimeoutError),
            self.assertRaisesRegex(OSError, "internet"),
        ):
            weather.weather("Cidade")

    def test_registry_permissions_missing_location_and_default(self):
        with tempfile.TemporaryDirectory() as temp:
            tools = ToolRegistry(Path(temp), object(), weather_city="Maranguape, Ceará")
            with patch(
                "cairo.tools.registry.weather", return_value={"message": "clima real"}
            ) as fetch:
                self.assertTrue(
                    json.loads(tools.execute("weather", {}, "MasterAgent", "session"))[
                        "ok"
                    ]
                )
                fetch.assert_called_once_with("Maranguape, Ceará")
                tools.allow_network = False
                self.assertFalse(
                    json.loads(tools.execute("weather", {}, "MasterAgent", "session"))[
                        "ok"
                    ]
                )
                self.assertEqual(fetch.call_count, 1)
            self.assertFalse(
                json.loads(
                    tools.execute(
                        "list_personal_files",
                        {"folder": "downloads"},
                        "MasterAgent",
                        "session",
                    )
                )["ok"]
            )
            self.assertFalse(
                json.loads(tools.execute("weather", {}, "DeveloperAgent", "session"))[
                    "ok"
                ]
            )
            tools.allow_network = True
            tools.weather_city = ""
            self.assertTrue(
                json.loads(tools.execute("weather", {}, "MasterAgent", "session"))[
                    "result"
                ]["needs_location"]
            )

    def test_public_web_validation_dns_and_extraction(self):
        for url in (
            "file:///C:/secret",
            "http://example.com",
            "https://127.0.0.1",
            "https://[::1]",
            "https://user:pass@example.com",
            "https://localhost",
            "https://example.com:8000",
            "https://10.0.0.1",
        ):
            with self.assertRaises(ValueError):
                web_reader.validate_url(url)
        with (
            patch.object(
                web_reader.socket,
                "getaddrinfo",
                return_value=[(2, 1, 6, "", ("192.168.0.1", 443))],
            ),
            self.assertRaises(PermissionError),
        ):
            web_reader.public_address("public-looking.example")
        parser = web_reader.TextExtractor()
        parser.feed(
            "<title>Fonte</title><script>steal()</script><style>x</style><p>Texto &amp; evidência</p>"
        )
        self.assertEqual(parser.title, ["Fonte"])
        self.assertNotIn("steal()", "\n".join(parser.parts))
        self.assertIn("Texto & evidência", parser.parts)

    def test_web_reader_redirects_checked_and_network_failures(self):
        response = Mock(status=302)
        response.getheader.return_value = "https://127.0.0.1/private"
        connection = Mock()
        connection.getresponse.return_value = response
        with (
            patch.object(web_reader, "public_address", return_value="93.184.216.34"),
            patch.object(web_reader, "PublicHTTPS", return_value=connection),
            self.assertRaises(ValueError),
        ):
            web_reader.read_webpage("https://example.com")
        connection.close.assert_called_once()
        response.status = 200
        response.getheader.side_effect = lambda key, default=None: {
            "Content-Type": "text/html",
            "Content-Encoding": "identity",
        }.get(key, default)
        response.read.return_value = b"<title>Example</title><p>Hello</p>"
        response.headers = Message()
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        with (
            patch.object(web_reader, "public_address", return_value="93.184.216.34"),
            patch.object(web_reader, "PublicHTTPS", return_value=connection),
        ):
            self.assertEqual(
                web_reader.read_webpage("https://example.com")["content"],
                "Example\nHello",
            )

    def test_existing_instance_must_match_data_directory(self):
        response = io.BytesIO(
            json.dumps({"data_dir": str(Path("data").resolve())}).encode()
        )
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with patch(
            "cairo.desktop.instance.urllib.request.build_opener", return_value=opener
        ):
            self.assertTrue(existing_instance("http://127.0.0.1:8765", Path("data")))
        opener.open.side_effect = OSError
        with patch(
            "cairo.desktop.instance.urllib.request.build_opener", return_value=opener
        ):
            self.assertFalse(existing_instance("http://127.0.0.1:8765", Path("data")))

    def test_weather_and_downloads_execute_once_without_model_in_swarm(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = Mock()
            app = Orchestrator(
                Settings(
                    workspace=root / "work",
                    data_dir=root / "data",
                    allow_desktop=True,
                    weather_city="Maranguape, Ceará",
                ),
                model,
            )
            try:
                sid = app.memory.create_session()["id"]
                with (
                    patch.object(
                        app.tools.desktop,
                        "open_folder",
                        return_value={"message": "Pasta aberta"},
                    ) as folder,
                    patch(
                        "cairo.tools.registry.weather",
                        return_value={"message": "Clima consultado"},
                    ) as forecast,
                ):
                    for command in (
                        "Cairo, abra a pasta download",
                        "Como está o clima agora?",
                    ):
                        run = app.submit(sid, command, "swarm")
                        deadline = time.monotonic() + 8
                        while time.monotonic() < deadline:
                            state = app.memory.run(run["id"])
                            if state["status"] in {"failed", "completed"}:
                                break
                            time.sleep(0.02)
                        self.assertEqual(state["status"], "completed", state)
                    folder.assert_called_once_with(folder="downloads")
                    forecast.assert_called_once_with("Maranguape, Ceará")
                    model.complete.assert_not_called()
            finally:
                app.close()
