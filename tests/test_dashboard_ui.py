import os
import tempfile
import threading
import unittest
from pathlib import Path

from cairo.api import Server
from cairo.config import Settings


@unittest.skipUnless(os.getenv("CAIRO_TEST_BROWSER") == "1", "Optional Chrome UI test")
class DashboardUITests(unittest.TestCase):
    def test_diagnostics_shortcuts_reload_and_update_banner(self):
        from playwright.sync_api import sync_playwright

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            server = Server(
                ("127.0.0.1", 0),
                Settings(workspace=root / "workspace", data_dir=root / "state"),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as driver:
                    browser = driver.chromium.launch(channel="chrome", headless=True)
                    try:
                        page = browser.new_page(
                            viewport={"width": 1440, "height": 1000}
                        )
                        errors = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.goto(f"http://127.0.0.1:{server.server_port}")
                        page.locator("#connection").filter(
                            has_text="Cairo conectado"
                        ).wait_for()
                        page.get_by_text("Ferramentas do dia a dia", exact=True).click()
                        page.locator("#check-cairo").click()
                        page.locator("#diagnostics h3").filter(
                            has_text="Cairo 0.4.0"
                        ).wait_for()
                        page.get_by_text("Meus atalhos", exact=True).click()
                        page.locator("#message").fill("Abra a pasta downloads")
                        page.locator("#shortcut-name").fill("Downloads")
                        page.locator("#save-shortcut").click()
                        page.reload()
                        page.get_by_text("Ferramentas do dia a dia", exact=True).click()
                        page.get_by_text("Meus atalhos", exact=True).click()
                        page.locator("#shortcuts button").filter(
                            has_text="Downloads"
                        ).click()
                        self.assertEqual(
                            page.locator("#message").input_value(),
                            "Abra a pasta downloads",
                        )
                        self.assertEqual(page.locator("#messages").inner_text(), "")
                        server.diagnostics.loaded_revision = "older"
                        page.locator("#check-cairo").click()
                        page.locator("#update-banner").wait_for(state="visible")
                        self.assertIn(
                            "Ctrl+C", page.locator("#update-banner").inner_text()
                        )
                        page.screenshot(
                            path=str(
                                Path(__file__).resolve().parents[2]
                                / "dashboard-desktop.png"
                            )
                        )
                        page.set_viewport_size({"width": 390, "height": 844})
                        page.screenshot(
                            path=str(
                                Path(__file__).resolve().parents[2]
                                / "dashboard-mobile.png"
                            )
                        )
                        page.set_viewport_size({"width": 1440, "height": 1000})
                        page.context.grant_permissions(
                            ["clipboard-read", "clipboard-write"]
                        )
                        page.locator("#message").fill("O que você pode fazer")
                        page.locator("#send").click()
                        answer = page.locator(".message.assistant:not(.pending)").last
                        answer.wait_for()
                        expected = answer.locator(".message-content").inner_text()
                        answer.get_by_role("button", name="Copiar", exact=True).click()
                        self.assertEqual(
                            page.evaluate("navigator.clipboard.readText()").replace(
                                "\r\n", "\n"
                            ),
                            expected,
                        )
                        page.get_by_role(
                            "button", name="Reutilizar", exact=True
                        ).click()
                        self.assertEqual(
                            page.locator("#message").input_value(),
                            "O que você pode fazer",
                        )
                        self.assertEqual(page.locator(".message.user").count(), 1)
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(3)
