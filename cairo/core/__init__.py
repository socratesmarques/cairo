"""Execution lifecycle and structured diagnostics."""
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import os


class Cancelled(RuntimeError):
    pass


class DataLock:
    """One runtime per data directory; OS releases the lock after a crash."""
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.handle = (directory / "runtime.lock").open("a+b")
        self.handle.seek(0, 2)
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise ValueError("Outro Cairo já está usando esta pasta de dados") from None

    def close(self):
        if self.handle.closed:
            return
        self.handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


def trace_logger(directory: Path) -> logging.Logger:
    directory.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"cairo.{directory.resolve()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(directory / "traces.jsonl", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger


def log_event(logger: logging.Logger, **fields) -> None:
    logger.info(json.dumps(fields, ensure_ascii=False))
