import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path

from cairo.config import Settings
from cairo.integrations.file_manager import FileManager
from cairo.models import Reply
from cairo.orchestrator import Orchestrator
from cairo.orchestrator.file_commands import mutation_requested, parse_file_command
from cairo.sandbox.file_roots import FileRoots
from cairo.tools import ToolRegistry


class FileManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.personal = self.root / "personal"
        self.workspace.mkdir()
        self.personal.mkdir()
        self.roots = FileRoots(
            self.workspace, self.root / "state", {"personal": str(self.personal)}
        )
        self.manager = FileManager(self.roots, True)

    def test_create_copy_move_rename_hash_and_search_binary(self):
        source = self.workspace / "data.bin"
        source.write_bytes(b"\x00binary\xff")
        self.manager.mkdir("personal/Reports")
        self.manager.copy("workspace/data.bin", "personal/Reports/copy.bin")
        self.assertEqual(
            (self.personal / "Reports/copy.bin").read_bytes(), source.read_bytes()
        )
        self.manager.move("personal/Reports/copy.bin", "personal/moved.bin")
        self.assertFalse((self.personal / "Reports/copy.bin").exists())
        self.manager.rename("personal/moved.bin", "Renamed.bin")
        self.assertEqual(
            self.manager.hash_file("personal/Renamed.bin")["sha256"],
            hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        self.assertEqual(len(self.manager.search("personal", "RENAMED")["matches"]), 1)
        self.assertEqual(self.manager.info("personal/Renamed.bin")["kind"], "file")

    def test_no_overwrite_and_no_escape_or_link_traversal(self):
        self.manager.write_text("workspace/source.txt", "original")
        self.manager.write_text("personal/dest.txt", "keep")
        with self.assertRaises(FileExistsError):
            self.manager.move("workspace/source.txt", "personal/dest.txt")
        self.assertEqual((self.personal / "dest.txt").read_text(), "keep")
        self.assertTrue((self.workspace / "source.txt").exists())
        for value in (
            "personal/../state/x",
            "personal/file:stream",
            "personal/CON.txt",
            "personal/trailing.",
            "personal/../workspace/source.txt",
            str(self.root / "outside.txt"),
        ):
            with (
                self.subTest(value=value),
                self.assertRaises((ValueError, PermissionError)),
            ):
                self.roots.resolve(value, write=True)
        try:
            (self.personal / "link").symlink_to(
                self.workspace, target_is_directory=True
            )
        except OSError:
            pass
        else:
            with self.assertRaises(PermissionError):
                self.roots.resolve("personal/link/source.txt")

    def test_internal_state_protected_and_extra_roots_validated(self):
        state = self.root / "state"
        state.mkdir()
        roots = FileRoots(self.workspace, state, {"all": str(self.root)})
        with self.assertRaises(PermissionError):
            roots.resolve("all/state/credentials.txt", write=True)
        for extra in (
            {"downloads": str(self.personal)},
            {"bad alias": str(self.personal)},
            {"drive": self.root.anchor},
        ):
            with self.assertRaises(ValueError):
                FileRoots(self.workspace, state, extra)

    def test_recoverable_trash_session_scope_and_conflicts(self):
        self.manager.write_text("personal/document.txt", "important")
        record = self.manager.trash_file("personal/document.txt", "one")
        self.assertFalse((self.personal / "document.txt").exists())
        self.assertEqual(len(self.manager.list_trash("one")["items"]), 1)
        self.assertEqual(self.manager.list_trash("two")["items"], [])
        with self.assertRaises(PermissionError):
            self.manager.restore(record["operation_id"], "two")
        (self.personal / "document.txt").write_text("new")
        with self.assertRaises(FileExistsError):
            self.manager.restore(record["operation_id"], "one")
        (self.personal / "document.txt").unlink()
        self.manager.restore(record["operation_id"], "one")
        self.assertEqual((self.personal / "document.txt").read_text(), "important")
        with self.assertRaises(ValueError):
            self.manager.restore("../../secrets", "one")

    def test_edit_backup_restore_and_prevent_lost_later_changes(self):
        self.manager.write_text("personal/note.txt", "Olá Cairo")
        record = self.manager.edit_text("personal/note.txt", "Cairo", "mundo", "one")
        self.assertEqual(
            (self.personal / "note.txt").read_text(encoding="utf-8"), "Olá mundo"
        )
        self.manager.restore(record["operation_id"], "one")
        self.assertEqual(
            (self.personal / "note.txt").read_text(encoding="utf-8"), "Olá Cairo"
        )
        record = self.manager.edit_text("personal/note.txt", "Cairo", "mundo", "one")
        (self.personal / "note.txt").write_text("independent change")
        with self.assertRaises(ValueError):
            self.manager.restore(record["operation_id"], "one")
        self.assertEqual((self.personal / "note.txt").read_text(), "independent change")
        with self.assertRaises(ValueError):
            self.manager.edit_text("personal/note.txt", "missing", "new", "one")

    def test_disabled_permission_and_registry_mutation_gate(self):
        self.manager.enabled = False
        with self.assertRaises(PermissionError):
            self.manager.write_text("personal/new.txt", "x")
        tools = ToolRegistry(
            self.workspace,
            object(),
            allow_file_operations=True,
            file_roots={"personal": str(self.personal)},
            data_dir=self.root / "data",
        )
        denied = json.loads(
            tools.execute(
                "file_write_text",
                {"path": "personal/new.txt", "content": "x"},
                "MasterAgent",
                "one",
            )
        )
        self.assertFalse(denied["ok"])
        allowed = json.loads(
            tools.execute(
                "file_write_text",
                {"path": "personal/new.txt", "content": "x"},
                "MasterAgent",
                "one",
                allow_file_mutations=True,
            )
        )
        self.assertTrue(allowed["ok"])
        self.assertNotIn(
            "file_write_text",
            [
                s["function"]["name"]
                for s in tools.schemas("MasterAgent", allow_file_mutations=False)
            ],
        )
        self.assertFalse(
            json.loads(
                tools.execute(
                    "file_trash",
                    {"path": "personal/new.txt"},
                    "ResearchAgent",
                    "one",
                    allow_file_mutations=True,
                )
            )["ok"]
        )

    def test_mutation_intent_and_exact_commands(self):
        for message in (
            "Copie o arquivo",
            "Cairo, renomeie esse arquivo",
            "Quero que você organize Downloads",
            "Edite minha nota",
        ):
            self.assertTrue(mutation_requested(message))
        for message in (
            "Não apague arquivos",
            "Leia a página",
            'Explique "apague arquivo"',
            "Resuma o documento",
        ):
            self.assertFalse(mutation_requested(message))
        self.assertEqual(
            parse_file_command(
                'Copie "downloads/Relatório.pdf" para "documents/Relatório.pdf"'
            ),
            [
                (
                    "file_copy",
                    {
                        "source": "downloads/Relatório.pdf",
                        "destination": "documents/Relatório.pdf",
                    },
                )
            ],
        )
        self.assertIsNone(parse_file_command('Não copie "a" para "b"'))

    def test_explicit_mutation_gate_cannot_be_granted_by_model(self):
        class MaliciousModel:
            count = 0

            def complete(self, messages, tools):
                self.count += 1
                if self.count == 1:
                    return Reply(
                        calls=[
                            {
                                "id": "one",
                                "type": "function",
                                "function": {
                                    "name": "file_trash",
                                    "arguments": json.dumps(
                                        {"path": "personal/keep.txt"}
                                    ),
                                },
                            }
                        ]
                    )
                return Reply("A operação não foi autorizada neste pedido.")

        (self.personal / "keep.txt").write_text("keep")
        app = Orchestrator(
            Settings(
                workspace=self.workspace,
                data_dir=self.root / "runtime",
                allow_file_operations=True,
                file_roots={"personal": str(self.personal)},
            ),
            MaliciousModel(),
        )
        try:
            sid = app.memory.create_session()["id"]
            run = app.submit(sid, "Resuma o documento", "normal")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = app.memory.run(run["id"])
                if state["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.02)
            self.assertEqual(state["status"], "completed", state)
            self.assertTrue((self.personal / "keep.txt").exists())
        finally:
            app.close()
