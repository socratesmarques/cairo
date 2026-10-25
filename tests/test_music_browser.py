import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

from cairo.config import Settings
from cairo.integrations.browser_control import BrowserControl, native_media_host
from cairo.orchestrator.control_commands import interaction_requested
from cairo.orchestrator.desktop_commands import parse_desktop_commands


class MusicTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_music_streams_use_chrome_transport(self):
        browser = BrowserControl.__new__(BrowserControl)
        browser.sessions = {}
        context = Mock()
        page = Mock()
        context.new_page = AsyncMock(return_value=page)
        context.route = AsyncMock()
        context.route_web_socket = AsyncMock()
        browser.browser = Mock()
        browser.browser.new_context = AsyncMock(return_value=context)
        state = await browser._new_session("one")
        state["native_media"] = True
        route = Mock()
        route.request.url = "https://r1.googlevideo.com/videoplayback?range=0-9999999"
        route.request.resource_type = "media"
        route.continue_ = AsyncMock()
        route.abort = AsyncMock()
        handler = context.route.call_args.args[1]
        with (
            patch(
                "cairo.integrations.browser_control.public_address",
                return_value="8.8.8.8",
            ) as dns,
            patch("cairo.integrations.browser_control.fetch_resource") as fetch,
        ):
            await handler(route)
            route.continue_.assert_awaited_once()
            fetch.assert_not_called()
            dns.assert_called_once()
        route.continue_.reset_mock()
        state["validated_hosts"].clear()
        with patch(
            "cairo.integrations.browser_control.public_address",
            side_effect=PermissionError("private address"),
        ):
            await handler(route)
            route.abort.assert_awaited_once()
            route.continue_.assert_not_awaited()

    async def test_media_host_boundary_and_explicit_intent(self):
        self.assertTrue(native_media_host("https://music.youtube.com"))
        self.assertFalse(native_media_host("https://youtube.com.attacker.test"))
        self.assertFalse(native_media_host("https://fakeyoutube.com"))
        self.assertEqual(
            parse_desktop_commands("Abra o YouTube Music e toque uma música"),
            [("browser_play_music", {"query": "música"})],
        )
        self.assertEqual(
            parse_desktop_commands("Toque Imagine no YouTube Music"),
            [("browser_play_music", {"query": "Imagine"})],
        )
        self.assertTrue(interaction_requested("Toque Imagine"))
        self.assertFalse(interaction_requested("Não toque Imagine"))
        self.assertIsNone(parse_desktop_commands("Não toque Imagine"))
        self.assertEqual(Settings().max_steps, 30)
        with patch.dict(os.environ, {"CAIRO_MAX_STEPS": "100"}):
            self.assertEqual(Settings.from_env().max_steps, 100)
        with patch.dict(os.environ, {"CAIRO_MAX_STEPS": "101"}):
            with self.assertRaises(ValueError):
                Settings.from_env()


@unittest.skipUnless(os.getenv("CAIRO_TEST_BROWSER") == "1", "Optional Chrome test")
class MusicPlayerTests(unittest.TestCase):
    def test_playback_requires_advancing_player(self):
        html = b"""<html><body><ytmusic-responsive-list-item-renderer><a href="/watch?v=fixture" onclick="event.preventDefault();const v=document.querySelector('video');Object.defineProperty(v,'paused',{value:false});Object.defineProperty(v,'readyState',{value:4});v.currentTime=1;">Test Song</a></ytmusic-responsive-list-item-renderer><video></video></body></html>"""
        browser = BrowserControl(headless=True)
        self.addCleanup(browser.close)
        with (
            patch(
                "cairo.integrations.browser_control.native_media_host",
                return_value=False,
            ),
            patch(
                "cairo.integrations.browser_control.fetch_resource",
                return_value=(200, {"content-type": "text/html"}, html),
            ),
        ):
            result = browser.call("play_music", {"query": "Test Song"}, "one")
            self.assertTrue(result["playing"])
