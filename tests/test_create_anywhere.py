import contextlib
import json
import tempfile
import time
import unittest
from pathlib import Path

from cairo.config import Settings
from cairo.integrations.file_manager import FileManager
from cairo.orchestrator import Orchestrator
from cairo.orchestrator.file_commands import parse_file_command
from cairo.sandbox.file_roots import FileRoots
from cairo.tools import ToolRegistry


class CreateAnywhereTests(unittest.TestCase):
    def test_empty_content_quotes_and_multiline(self):
        command = parse_file_command('Crie o arquivo "C:\\Projetos\\cairo.txt"')
        self.assertEqual(
            command,
            [
                (
                    "file_write_text",
                    {
                        "path": "C:\\Projetos\\cairo.txt",
                        "content": "",
                        "create_parents": True,
                    },
                )
            ],
        )
        text = 'linha 1\n{"nome": "Cairo"}'
        self.assertEqual(
            parse_file_command(
                f'Crie um arquivo "documents/test.json" com conteúdo "{text}"'
            )[0][1]["content"],
            text,
        )
        self.assertIsNone(parse_file_command('Não crie o arquivo "documents/no.txt"'))

    def test_outside_workspace_creation_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            manager = FileManager(
                FileRoots(workspace, root / "state", full_access=True), True
            )
            path = root / "outside/new/nested/file.json"
            manager.write_text(str(path), '{"nome":"Cairo"}', create_parents=True)
            self.assertEqual(path.read_text(encoding="utf-8"), '{"nome":"Cairo"}')
            with self.assertRaises(FileExistsError):
                manager.write_text(str(path), "replace", create_parents=True)
            with self.assertRaises(PermissionError):
                manager.write_text(
                    str(root / "state/internal.txt"), "bad", create_parents=True
                )
            restricted = FileManager(FileRoots(workspace, root / "state"), True)
            with self.assertRaises(PermissionError):
                restricted.write_text(
                    str(root / "other/no.txt"), "no", create_parents=True
                )

    def test_legacy_tool_accepts_absolute_path_with_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            tools = ToolRegistry(
                workspace,
                object(),
                allow_write=True,
                allow_file_operations=True,
                full_file_access=True,
                data_dir=root / "state",
            )
            self.addCleanup(tools.close)
            path = str(root / "outside/tool.txt")
            arguments = {"path": path, "content": "Cairo"}
            self.assertFalse(
                json.loads(
                    tools.execute(
                        "write_file",
                        arguments,
                        "MasterAgent",
                        "one",
                        allow_file_mutations=False,
                    )
                )["ok"]
            )
            result = json.loads(
                tools.execute(
                    "write_file",
                    arguments,
                    "MasterAgent",
                    "one",
                    allow_file_mutations=True,
                )
            )
            self.assertTrue(result["ok"], result)
            self.assertEqual(Path(path).read_text(), "Cairo")
            self.assertFalse(
                json.loads(
                    tools.execute(
                        "write_file",
                        dict(arguments, overwrite=True),
                        "MasterAgent",
                        "one",
                        allow_file_mutations=True,
                    )
                )["ok"]
            )

    def test_direct_chat_creation_outside_workspace_without_model(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
            root = Path(temp)
            app = Orchestrator(
                Settings(
                    workspace=root / "workspace",
                    data_dir=root / "state",
                    full_file_access=True,
                    allow_file_operations=True,
                )
            )
            stack.callback(app.close)
            sid = app.memory.create_session()["id"]
            path = root / "outside/nested/empty.txt"
            run = app.submit(sid, f'Crie o arquivo "{path}"', "swarm")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                result = app.memory.run(run["id"])
                if result["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.01)
            self.assertEqual(result["status"], "completed", result)
            self.assertTrue(path.exists())
            self.assertEqual(path.stat().st_size, 0)
