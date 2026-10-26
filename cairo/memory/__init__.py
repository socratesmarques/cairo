"""SQLite memory with short-lived connections and serialized transactions."""

import sqlite3
import threading
import uuid
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


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
            columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
            if "pinned" not in columns and db.execute("SELECT 1 FROM sessions LIMIT 1").fetchone():
                self.backup()
            for name in ("pinned", "archived"):
                if name not in columns:
                    db.execute(f"ALTER TABLE sessions ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")

    def recover_interrupted(self) -> None:
        with self.db() as db:
            db.execute(
                "UPDATE runs SET status='failed',error='Execução interrompida pelo encerramento anterior' WHERE status IN ('queued','running')"
            )

    def failure_counts(self) -> list[dict]:
        with self.db() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT error,COUNT(*) AS count FROM runs WHERE status='failed' AND length(error)>0 GROUP BY error ORDER BY count DESC LIMIT 50"
                )
            ]

    @contextmanager
    def db(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            db.create_function("search_fold", 1, lambda value: "".join(
                c for c in unicodedata.normalize("NFKD", str(value or "").casefold())
                if not unicodedata.combining(c)
            ), deterministic=True)
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
            db.execute("INSERT INTO sessions(id,title,created_at) VALUES(:id,:title,:created_at)", item)
        return item

    def sessions(self, query: str = "", archived: bool = False, offset: int = 0) -> list:
        if not isinstance(query, str) or len(query) > 200:
            raise ValueError("Busca deve conter até 200 caracteres")
        if type(offset) is not int or not 0 <= offset <= 1000000:
            raise ValueError("Página de conversas inválida")
        with self.db() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT s.* FROM sessions s WHERE archived=? AND "
                    "(?='' OR instr(search_fold(title),search_fold(?))>0 OR EXISTS "
                    "(SELECT 1 FROM messages m WHERE m.session_id=s.id AND instr(search_fold(m.content),search_fold(?))>0)) "
                    "ORDER BY pinned DESC,MAX(s.created_at,COALESCE((SELECT MAX(created_at) FROM messages WHERE session_id=s.id),s.created_at)) DESC,s.id DESC LIMIT 200 OFFSET ?",
                    (int(archived), query.strip(), query.strip(), query.strip(), offset),
                )
            ]

    def backup(self) -> dict:
        directory = self.path.parent / "backups"
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / ("cairo-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8] + ".sqlite3")
        temporary = destination.with_suffix(".tmp")
        try:
            with self.db() as source:
                target = sqlite3.connect(temporary)
                try:
                    source.backup(target)
                    if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        raise OSError("Não foi possível verificar a cópia do histórico")
                finally:
                    target.close()
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return {"path": str(destination.resolve()), "bytes": destination.stat().st_size}

    def update_session(self, session_id: str, changes: dict) -> dict:
        if not changes or set(changes) - {"title", "pinned", "archived"}:
            raise ValueError("Informe título, fixação ou arquivamento")
        values = dict(changes)
        if "title" in values:
            title = values["title"]
            if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
                raise ValueError("Título deve conter de 1 a 100 caracteres")
            values["title"] = title.strip()
        for key in ("pinned", "archived"):
            if key in values and not isinstance(values[key], bool):
                raise ValueError("Fixação e arquivamento devem ser booleanos")
        with self.db() as db:
            if values.get("archived") and db.execute(
                "SELECT 1 FROM runs WHERE session_id=? AND status IN ('queued','running')",
                (session_id,),
            ).fetchone():
                raise RuntimeError("Aguarde a execução terminar antes de arquivar")
            cursor = db.execute(
                "UPDATE sessions SET " + ",".join(f"{key}=?" for key in values) + " WHERE id=?",
                (*values.values(), session_id),
            )
            if not cursor.rowcount:
                raise KeyError("Conversa não encontrada")
            return dict(db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone())

    def export_session(self, session_id: str) -> dict:
        with self.db() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row is None:
                raise KeyError("Conversa não encontrada")
            result = dict(row)
            result["messages"] = [dict(r) for r in db.execute(
                "SELECT * FROM messages WHERE session_id=? ORDER BY id", (session_id,)
            )]
            result["notes"] = [dict(r) for r in db.execute(
                "SELECT * FROM notes WHERE session_id=? ORDER BY id", (session_id,)
            )]
            result["runs"] = [dict(r) for r in db.execute(
                "SELECT * FROM runs WHERE session_id=? ORDER BY created_at", (session_id,)
            )]
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if {"daily_tasks", "daily_notes"} <= tables:
                result["daily"] = {key: [dict(r) for r in db.execute(
                    f"SELECT * FROM {table} WHERE session_id=? ORDER BY updated,id", (session_id,)
                )] for key, table in (("tasks", "daily_tasks"), ("notes", "daily_notes"))}
            return result

    def session(self, session_id: str) -> dict:
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            if row is None:
                raise KeyError("Conversa não encontrada")
            result = dict(row)
            result["message_count"] = db.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id=?", (session_id,)
            ).fetchone()[0]
            result["messages"] = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM (SELECT * FROM messages WHERE session_id=? ORDER BY id DESC LIMIT 200) ORDER BY id",
                    (session_id,),
                )
            ]
            result["runs"] = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM runs WHERE session_id=? ORDER BY created_at DESC LIMIT 30",
                    (session_id,),
                )
            ]
            return result

    def older_messages(self, session_id: str, before: int, limit: int = 100) -> dict:
        if type(before) is not int or before < 1 or type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Página de mensagens inválida")
        with self.db() as db:
            if not db.execute("SELECT 1 FROM sessions WHERE id=?", (session_id,)).fetchone():
                raise KeyError("Conversa não encontrada")
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM messages WHERE session_id=? AND id<? ORDER BY id DESC LIMIT ?",
                (session_id, before, limit + 1),
            )]
            return {"messages": list(reversed(rows[:limit])), "has_more": len(rows) > limit}

    def import_session(self, document: dict) -> dict:
        from cairo.memory.transfers import import_conversation

        return import_conversation(self, document)

    def add_message(self, session_id: str, role: str, content: str) -> None:
        with self.db() as db:
            db.execute(
                "INSERT INTO messages(session_id,role,content,created_at) VALUES(?,?,?,?)",
                (session_id, role, content, now()),
            )
            if role == "user":
                db.execute(
                    "UPDATE sessions SET title=? WHERE id=? AND title='Nova conversa'",
                    (content[:70], session_id),
                )

    def save_note(self, session_id: str, content: str) -> None:
        with self.db() as db:
            db.execute(
                "INSERT INTO notes(session_id,content,created_at) VALUES(?,?,?)",
                (session_id, content[:12000], now()),
            )

    def search(self, query: str, session_id: str) -> list:
        with self.db() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM notes WHERE session_id=? AND instr(lower(content),lower(?))>0 ORDER BY id DESC LIMIT 20",
                    (session_id, query[:200]),
                )
            ]

    def create_run(self, session_id: str, mode: str) -> dict:
        item = dict(
            id=uuid.uuid4().hex,
            session_id=session_id,
            mode=mode,
            status="queued",
            result="",
            error="",
            created_at=now(),
        )
        with self.db() as db:
            db.execute(
                "INSERT INTO runs VALUES(:id,:session_id,:mode,:status,:result,:error,:created_at)",
                item,
            )
        return item

    def update_run(
        self, run_id: str, status: str, result: str = "", error: str = ""
    ) -> None:
        with self.db() as db:
            db.execute(
                "UPDATE runs SET status=?,result=?,error=? WHERE id=?",
                (status, result, error, run_id),
            )

    def run(self, run_id: str) -> dict:
        with self.db() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError("Execução não encontrada")
            item = dict(row)
            item["events"] = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM events WHERE run_id=? ORDER BY id", (run_id,)
                )
            ]
            return item

    def event(self, run_id: str, agent: str, kind: str, message: str) -> None:
        with self.db() as db:
            db.execute(
                "INSERT INTO events(run_id,agent,kind,message,created_at) VALUES(?,?,?,?,?)",
                (run_id, agent, kind, message[:4000], now()),
            )
