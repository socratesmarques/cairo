"""Inspect or restore a history snapshot while holding Cairo's runtime lock."""
import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from cairo.core import DataLock
from cairo.memory import Memory

MAX_BACKUP_BYTES = 1024 * 1024 * 1024
REQUIRED_COLUMNS = {
    "sessions": {"id", "title", "created_at"},
    "messages": {"id", "session_id", "role", "content", "created_at"},
    "notes": {"id", "session_id", "content", "created_at"},
    "runs": {"id", "session_id", "mode", "status", "result", "error", "created_at"},
    "events": {"id", "run_id", "agent", "kind", "message", "created_at"},
}


def restore_history(snapshot: Path, data_dir: Path, apply: bool = False) -> dict:
    snapshot = Path(snapshot).resolve(strict=True)
    data_dir = Path(data_dir).resolve()
    destination = data_dir / "cairo.db"
    if snapshot == destination or not snapshot.is_file() or snapshot.stat().st_size > MAX_BACKUP_BYTES:
        raise ValueError("Selecione uma cópia SQLite de até 1 GB, diferente do banco em uso")
    with closing(sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True)) as source:
        source.execute("PRAGMA trusted_schema=OFF")
        source.execute("BEGIN")
        if source.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("A cópia não passou na verificação de integridade")
        for table, required in REQUIRED_COLUMNS.items():
            kind = source.execute("SELECT type FROM sqlite_master WHERE name=?", (table,)).fetchone()
            if not kind or kind[0] != "table":
                raise ValueError("A cópia não contém um histórico Cairo completo")
            columns = {row[1] for row in source.execute(f"PRAGMA table_info({table})")}
            if not required <= columns:
                raise ValueError("A cópia contém uma estrutura incompatível: " + table)
        summary = {table: source.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                   for table in REQUIRED_COLUMNS}
        result = {"restored": False, "counts": summary, "destination": str(destination)}
        if not apply:
            return result
        lock = DataLock(data_dir)
        try:
            if destination.exists():
                result["previous_backup"] = Memory(destination).backup()["path"]
            with closing(sqlite3.connect(destination)) as target:
                source.backup(target)
                if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise OSError("Não foi possível verificar o histórico restaurado")
            result["restored"] = True
            return result
        finally:
            lock.close()


def main():
    parser = argparse.ArgumentParser(description="Conferir ou restaurar uma cópia do histórico Cairo")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path("storage"))
    parser.add_argument("--apply", action="store_true", help="Restaurar; feche Cairo antes. Sem esta opção, apenas confere a cópia.")
    args = parser.parse_args()
    try:
        print(json.dumps(restore_history(args.snapshot, args.data_dir, args.apply), ensure_ascii=False, indent=2))
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(2, "Cairo: não foi possível restaurar: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
