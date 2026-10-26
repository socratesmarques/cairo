import copy
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from cairo.core import DataLock
from cairo.memory import Memory
from cairo.memory.recovery import restore_history


class HistoryRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.memory = Memory(self.root / "data/cairo.db")
        self.session = self.memory.create_session()

    def test_pagination_has_no_gaps_duplicates_or_other_session_messages(self):
        sid = self.session["id"]
        other = self.memory.create_session()["id"]
        with self.memory.db() as db:
            db.executemany("INSERT INTO messages(session_id,role,content,created_at) VALUES(?,?,?,?)",
                [(session, "user", str(i), "2026-10-25") for i in range(550) for session in (sid, other)])
        messages = self.memory.session(sid)["messages"]
        while True:
            page = self.memory.older_messages(sid, messages[0]["id"])
            messages = page["messages"] + messages
            if not page["has_more"]:
                break
        self.assertEqual([m["content"] for m in messages], [str(i) for i in range(550)])
        self.assertEqual(len({m["id"] for m in messages}), 550)
        self.assertTrue(all(m["session_id"] == sid for m in messages))
        with self.assertRaises(KeyError):
            self.memory.older_messages("missing", 1)
        for before in (0, -1, True, "1"):
            with self.assertRaises(ValueError):
                self.memory.older_messages(sid, before)

    def test_session_pagination_reaches_every_session(self):
        for _ in range(205):
            self.memory.create_session()
        first = self.memory.sessions()
        second = self.memory.sessions(offset=200)
        self.assertEqual(len(first), 200)
        self.assertEqual(len(second), 6)
        self.assertEqual(len({s["id"] for s in first + second}), 206)
        with self.assertRaises(ValueError):
            self.memory.sessions(offset=-1)

    def test_import_roundtrip_creates_new_identity_and_never_replays_runs(self):
        sid = self.session["id"]
        self.memory.add_message(sid, "user", "Minha pergunta")
        self.memory.add_message(sid, "assistant", "Minha resposta")
        self.memory.save_note(sid, "Minha nota")
        self.memory.create_run(sid, "normal")
        exported = self.memory.export_session(sid)
        imported = self.memory.import_session(exported)
        self.assertNotEqual(imported["id"], sid)
        restored = self.memory.export_session(imported["id"])
        self.assertEqual([m["content"] for m in restored["messages"]], ["Minha pergunta", "Minha resposta"])
        self.assertEqual(restored["notes"][0]["content"], "Minha nota")
        self.assertEqual(restored["runs"], [])
        self.assertEqual(len(self.memory.session(sid)["messages"]), 2)

    def test_invalid_imports_do_not_partially_create_sessions(self):
        base = {"title": "Conversa", "messages": [{"role": "user", "content": "Olá"}]}
        variants = [None, [], {**base, "title": ""}, {**base, "messages": "wrong"},
            {**base, "notes": [{"content": 4}]}]
        for field, value in (("role", "system"), ("role", []), ("content", 5), ("created_at", "bad")):
            item = copy.deepcopy(base)
            item["messages"].append({**base["messages"][0], field: value})
            variants.append(item)
        for item in variants:
            with self.subTest(item=item), self.assertRaises(ValueError):
                self.memory.import_session(item)
        self.assertEqual(len(self.memory.sessions()), 1)

    def test_restore_dry_run_then_apply_keeps_a_previous_copy(self):
        sid = self.session["id"]
        self.memory.add_message(sid, "user", "Antes")
        snapshot = Path(self.memory.backup()["path"])
        self.memory.add_message(sid, "assistant", "Depois")
        preview = restore_history(snapshot, self.root / "new-location")
        self.assertFalse(preview["restored"])
        self.assertFalse((self.root / "new-location").exists())
        result = restore_history(snapshot, self.memory.path.parent, apply=True)
        self.assertTrue(result["restored"])
        self.assertEqual(len(self.memory.session(sid)["messages"]), 1)
        with closing(sqlite3.connect(result["previous_backup"])) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 2)

    def test_restore_rejects_running_cairo_and_invalid_snapshots(self):
        snapshot = Path(self.memory.backup()["path"])
        lock = DataLock(self.memory.path.parent)
        try:
            with self.assertRaises(ValueError):
                restore_history(snapshot, self.memory.path.parent, apply=True)
        finally:
            lock.close()
        with self.assertRaises(ValueError):
            restore_history(self.memory.path, self.memory.path.parent, apply=True)
        bad = self.root / "bad.sqlite3"
        with closing(sqlite3.connect(bad)) as db:
            db.execute("CREATE TABLE arbitrary(id INTEGER)")
            db.commit()
        with self.assertRaises(ValueError):
            restore_history(bad, self.memory.path.parent, apply=True)
        self.assertEqual(self.memory.session(self.session["id"])["title"], "Nova conversa")
