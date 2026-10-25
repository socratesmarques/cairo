import json
from pathlib import Path
import tempfile
import unittest

from cairo.tools import ToolRegistry


class Notes:
    def __init__(self):
        self.notes = []

    def search(self, query, session_id):
        return [content for session, content in self.notes if session == session_id and query in content]

    def save_note(self, session_id, content):
        self.notes.append((session_id, content))


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.memory = Notes()
        self.tools = ToolRegistry(self.root, self.memory)

    def call(self, name, args, agent="MasterAgent", session="one"):
        return json.loads(self.tools.execute(name, args, agent, session))

    def test_read_write_permissions_and_overwrite(self):
        self.assertFalse(self.call("write_file", {"path": "a.txt", "content": "hi"})["ok"])
        self.tools = ToolRegistry(self.root, self.memory, allow_write=True)
        self.assertTrue(self.call("write_file", {"path": "nested/a.txt", "content": "hello"})["ok"])
        self.assertFalse(self.call("write_file", {"path": "nested/a.txt", "content": "lost"})["ok"])
        self.assertEqual(self.call("read_file", {"path": "nested/a.txt"})["result"]["content"], "hello")
        self.assertTrue(self.call("write_file", {"path": "nested/a.txt", "content": "updated", "overwrite": True})["ok"])
        self.assertEqual((self.root / "nested/a.txt").read_text(), "updated")

    def test_traversal_and_device_paths_are_denied(self):
        for path in ("../outside", "/etc/passwd", "C:/Windows/win.ini", "file:stream", "CON", "sub/../../escape", "sub\\file"):
            with self.subTest(path=path):
                self.assertFalse(self.call("read_file", {"path": path})["ok"])

    def test_symlink_escape_is_denied(self):
        with tempfile.TemporaryDirectory() as outside:
            (Path(outside) / "secret.txt").write_text("secret")
            try:
                (self.root / "link").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("Creating symlinks is unavailable on this host")
            self.assertFalse(self.call("read_file", {"path": "link/secret.txt"})["ok"])

    def test_agent_allowlists_apply_even_if_called_directly(self):
        self.assertFalse(self.call("read_file", {"path": "a.txt"}, "SystemAgent")["ok"])
        self.assertFalse(self.call("system_info", {}, "Reviewer")["ok"])
        self.assertEqual(self.tools.schemas("Reviewer"), [])
        self.assertFalse(any(item["function"]["name"] == "write_file" for item in self.tools.schemas("MasterAgent")))
        self.assertTrue(self.call("system_info", {}, "SystemAgent")["ok"])

    def test_memory_is_session_scoped(self):
        self.assertTrue(self.call("memory_save", {"content": "Cairo note"}, "ResearchAgent")["ok"])
        self.assertEqual(self.call("memory_search", {"query": "Cairo"})["result"]["notes"], ["Cairo note"])
        self.assertEqual(self.call("memory_search", {"query": "Cairo"}, session="two")["result"]["notes"], [])

    def test_limits_and_argument_validation(self):
        (self.root / "large.txt").write_bytes(b"x" * 65537)
        self.assertFalse(self.call("read_file", {"path": "large.txt"})["ok"])
        self.assertFalse(self.call("read_file", {"path": 2})["ok"])
        self.assertFalse(self.call("read_file", {"path": "large.txt", "extra": True})["ok"])
        self.assertFalse(self.call("memory_save", {"content": " "})["ok"])
        self.assertFalse(self.call("memory_save", {"content": "a" * 4001})["ok"])


if __name__ == "__main__":
    unittest.main()
