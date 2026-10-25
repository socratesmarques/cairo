"""SQLite memory with short-lived connections and serialized transactions."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
import uuid


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Memory:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,title TEXT,created_at TEXT);
                CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,session_id TEXT,role TEXT,content TEXT,created_at TEXT);
                CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY,session_id TEXT,content TEXT,created_at TEXT);
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,session_id TEXT,mode TEXT,status TEXT,result TEXT,error TEXT,created_at TEXT);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,run_id TEXT,agent TEXT,kind TEXT,message TEXT,created_at TEXT);
                CREATE INDEX IF NOT EXISTS msg_session ON messages(session_id,id);
                CREATE INDEX IF NOT EXISTS event_run ON events(run_id,id);
                CREATE INDEX IF NOT EXISTS note_session ON notes(session_id,id);
            """)

    def recover_interrupted(self) -> None:
        with self.db() as db:
            db.execute("UPDATE runs SET status='failed',error='Execução interrompida pelo encerramento anterior' WHERE status IN ('queued','running')")

    @contextmanager
    def db(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

    def create_session(self) -> dict:
        item = {"id": uuid.uuid4().hex, "title": "Nova conversa", "created_at": now()}
        with self.db() as db:
            db.execute("INSERT INTO sessions VALUES(:id,:title,:created_at)", item)
        return item

    def sessions(self) -> list:
        with self.db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM sessions ORDER BY created_at DESC LIMIT 200")]

    def session(self, session_id: str) -> dict:
        with self.db() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row is None:
                raise KeyError("Conversa não encontrada")
            result = dict(row)
            result["messages"] = [dict(r) for r in db.execute("SELECT * FROM (SELECT * FROM messages WHERE session_id=? ORDER BY id DESC LIMIT 200) ORDER BY id", (session_id,))]
            result["runs"] = [dict(r) for r in db.execute("SELECT * FROM runs WHERE session_id=? ORDER BY created_at DESC LIMIT 30", (session_id,))]
            return result

    def add_message(self, session_id: str, role: str, content: str) -> None:
        with self.db() as db:
            db.execute("INSERT INTO messages(session_id,role,content,created_at) VALUES(?,?,?,?)", (session_id, role, content, now()))
            if role == "user":
                db.execute("UPDATE sessions SET title=? WHERE id=? AND title='Nova conversa'", (content[:70], session_id))

    def save_note(self, session_id: str, content: str) -> None:
        with self.db() as db:
            db.execute("INSERT INTO notes(session_id,content,created_at) VALUES(?,?,?)", (session_id, content[:12000], now()))

    def search(self, query: str, session_id: str) -> list:
        with self.db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM notes WHERE session_id=? AND instr(lower(content),lower(?))>0 ORDER BY id DESC LIMIT 20", (session_id, query[:200]))]

    def create_run(self, session_id: str, mode: str) -> dict:
        item = dict(id=uuid.uuid4().hex, session_id=session_id, mode=mode, status="queued", result="", error="", created_at=now())
        with self.db() as db:
            db.execute("INSERT INTO runs VALUES(:id,:session_id,:mode,:status,:result,:error,:created_at)", item)
        return item

    def update_run(self, run_id: str, status: str, result: str = "", error: str = "") -> None:
        with self.db() as db:
            db.execute("UPDATE runs SET status=?,result=?,error=? WHERE id=?", (status, result, error, run_id))

    def run(self, run_id: str) -> dict:
        with self.db() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError("Execução não encontrada")
            item = dict(row)
            item["events"] = [dict(r) for r in db.execute("SELECT * FROM events WHERE run_id=? ORDER BY id", (run_id,))]
            return item

    def event(self, run_id: str, agent: str, kind: str, message: str) -> None:
        with self.db() as db:
            db.execute("INSERT INTO events(run_id,agent,kind,message,created_at) VALUES(?,?,?,?,?)", (run_id, agent, kind, message[:4000], now()))
