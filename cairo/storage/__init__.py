"""Storage paths and durable state are configured through Settings.data_dir.

SQLite persistence lives in cairo.memory; this package owns retention helpers.
"""
from pathlib import Path
import sqlite3


def backup(database: Path, destination: Path) -> None:
    """Consistent online backup, including committed WAL contents."""
    if not database.is_file() or database.resolve() == destination.resolve():
        raise ValueError("Choose an existing database and a different backup path")
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(database)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
