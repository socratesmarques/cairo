import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from cairo.memory import Memory


class WorkspaceDailyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.memory = Memory(Path(self.tmp.name) / "cairo.db")
        self.session = self.memory.create_session()

    def test_search_content_unicode_and_literal_sql(self):
        sid = self.session["id"]
        self.memory.add_message(sid, "user", "Organizar AÇÃO e reunião")
        self.assertEqual(self.memory.sessions("acao")[0]["id"], sid)
        self.assertEqual(self.memory.sessions("REUNIAO")[0]["id"], sid)
        self.assertEqual(self.memory.sessions("%' OR 1=1 --"), [])
        with self.assertRaises(ValueError):
            self.memory.sessions("a" * 201)

    def test_pin_archive_restore_and_validation(self):
        sid = self.session["id"]
        self.memory.create_session()
        self.memory.update_session(sid, {"title": " Projeto pessoal ", "pinned": True})
        self.assertEqual(self.memory.sessions()[0]["title"], "Projeto pessoal")
        self.memory.update_session(sid, {"archived": True})
        self.assertNotIn(sid, [s["id"] for s in self.memory.sessions()])
        self.assertEqual(self.memory.sessions(archived=True)[0]["id"], sid)
        self.memory.update_session(sid, {"archived": False})
        self.assertEqual(self.memory.session(sid)["title"], "Projeto pessoal")
        for changes in ({}, {"title": " "}, {"title": 4}, {"pinned": 1}, {"archived": "true"}, {"id": "other"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.memory.update_session(sid, changes)
        with self.assertRaises(KeyError):
            self.memory.update_session("missing", {"title": "Nome"})

    def test_archive_active_run_is_rejected(self):
        sid = self.session["id"]
        run = self.memory.create_run(sid, "normal")
        with self.assertRaises(RuntimeError):
            self.memory.update_session(sid, {"archived": True})
        self.memory.update_run(run["id"], "completed")
        self.memory.update_session(sid, {"archived": True})

    def test_full_export_and_verified_backup_include_all_messages(self):
        sid = self.session["id"]
        with self.memory.db() as db:
            db.executemany(
                "INSERT INTO messages(session_id,role,content,created_at) VALUES(?,?,?,?)",
                [(sid, "user", str(i), "2026-10-25") for i in range(250)],
            )
        self.memory.save_note(sid, "Uma nota importante")
        self.assertEqual(len(self.memory.session(sid)["messages"]), 200)
        self.assertEqual(self.memory.session(sid)["message_count"], 250)
        exported = self.memory.export_session(sid)
        self.assertEqual(len(exported["messages"]), 250)
        self.assertEqual(exported["messages"][0]["content"], "0")
        self.assertEqual(exported["notes"][0]["content"], "Uma nota importante")
        backup = self.memory.backup()
        self.assertGreater(backup["bytes"], 0)
        with closing(sqlite3.connect(backup["path"])) as db:
            self.assertEqual(db.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 250)
        self.memory.add_message(sid, "user", "depois")
        with closing(sqlite3.connect(backup["path"])) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 250)

    def test_legacy_migration_is_repeatable_and_keeps_backup(self):
        path = Path(self.tmp.name) / "legacy.db"
        with closing(sqlite3.connect(path)) as db:
            db.execute("CREATE TABLE sessions(id TEXT PRIMARY KEY,title TEXT,created_at TEXT)")
            db.execute("INSERT INTO sessions VALUES('legacy','Minha conversa','2026-10-25')")
            db.commit()
        migrated = Memory(path)
        self.assertFalse(migrated.session("legacy")["archived"])
        self.assertEqual(Memory(path).session("legacy")["title"], "Minha conversa")
        self.assertEqual(len(list((path.parent / "backups").glob("*.sqlite3"))), 1)
