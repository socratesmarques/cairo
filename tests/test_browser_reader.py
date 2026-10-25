import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cairo.integrations import browser_reader
from cairo.tools import ToolRegistry


class BrowserReaderTests(unittest.TestCase):
    def test_javascript_permission_and_network_permission(self):
        with tempfile.TemporaryDirectory() as temp:
            tools = ToolRegistry(Path(temp), object(), browser_javascript=True)
            with patch.object(
                browser_reader, "render_page", return_value={"message": "dynamic"}
            ) as render:
                result = json.loads(
                    tools.execute(
                        "read_webpage",
                        {"url": "https://example.com"},
                        "MasterAgent",
                        "one",
                    )
                )
                self.assertTrue(result["ok"])
                render.assert_called_once_with(
                    channel="chrome", url="https://example.com"
                )
                tools.allow_network = False
                self.assertFalse(
                    json.loads(
                        tools.execute(
                            "read_dynamic_webpage",
                            {"url": "https://example.com"},
                            "MasterAgent",
                            "one",
                        )
                    )["ok"]
                )
            tools.allow_network = True
            tools.browser_javascript = False
            self.assertFalse(
                json.loads(
                    tools.execute(
                        "read_dynamic_webpage",
                        {"url": "https://example.com"},
                        "MasterAgent",
                        "one",
                    )
                )["ok"]
            )

    def test_private_endpoints_and_write_methods_blocked_before_browser(self):
        for url in ("https://127.0.0.1", "file:///C:/secret"):
            with self.assertRaises(ValueError):
                browser_reader.render_page(url)
        with self.assertRaises(ValueError):
            browser_reader.fetch_resource("https://example.com", "DELETE", {}, None)
        with (
            patch.object(
                browser_reader, "public_address", side_effect=PermissionError("private")
            ),
            self.assertRaises(PermissionError),
        ):
            browser_reader.fetch_resource("https://example.com", "GET", {}, None)


@unittest.skipUnless(
    os.getenv("CAIRO_TEST_BROWSER") == "1",
    "Set CAIRO_TEST_BROWSER=1 for real Chrome JavaScript tests",
)
class BrowserRuntimeTests(unittest.TestCase):
    def test_google_result_extraction_from_real_dom(self):
        from playwright.sync_api import sync_playwright

        from cairo.integrations.google_search import EXTRACT_RESULTS, clean_results

        with sync_playwright() as driver:
            browser = driver.chromium.launch(channel="chrome", headless=True)
            try:
                page = browser.new_page()
                page.set_content(
                    '<div class="MjjYud"><a href="https://www.python.org/"><h3>Python official</h3></a><p>Language documentation</p></div>'
                )
                results = clean_results(page.evaluate(EXTRACT_RESULTS))
                self.assertEqual(results[0]["title"], "Python official")
                self.assertIn("Language documentation", results[0]["snippet"])
                self.assertEqual(results[0]["url"], "https://www.python.org/")
            finally:
                browser.close()

    def test_javascript_runs_and_contexts_do_not_share_cookies(self):
        html = b"""<html><body><div id="output">Loading</div><script>
        let old = document.cookie.includes('cairo_test=1');
        document.cookie = 'cairo_test=1; SameSite=Lax; Secure';
        document.getElementById('output').textContent = old ? 'LEAK' : 'CAIRO JAVASCRIPT OK';
        </script></body></html>"""

        def fixture(url, method, headers, body):
            return 200, {"content-type": "text/html; charset=utf-8"}, html

        with patch.object(browser_reader, "fetch_resource", side_effect=fixture):
            for _ in range(2):
                result = browser_reader.render_page(
                    "https://cairo-fixture.test", wait_for="#output"
                )
                self.assertIn("CAIRO JAVASCRIPT OK", result["content"])
                self.assertNotIn("LEAK", result["content"])
