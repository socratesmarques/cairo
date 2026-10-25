"""In-process recurring callbacks; intentionally no durable scheduling claim."""
from dataclasses import dataclass
import math
import threading
import time
from typing import Callable


@dataclass
class Job:
    name: str
    interval: float
    callback: Callable[[], None]
    next_at: float
    last_error: str = ""
    runs: int = 0


class Scheduler:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def add(self, name: str, interval: float, callback: Callable[[], None]) -> None:
        if not math.isfinite(interval) or interval < 0.05 or not callable(callback):
            raise ValueError("Interval must be >= 0.05 seconds and callback callable")
        with self.lock:
            if name in self.jobs:
                raise ValueError("Duplicate scheduled job")
            self.jobs[name] = Job(name, interval, callback, time.monotonic() + interval)

    def remove(self, name: str) -> None:
        with self.lock:
            self.jobs.pop(name, None)

    def start(self) -> None:
        with self.lock:
            if self.thread and self.thread.is_alive():
                return
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._loop, daemon=True, name="cairo-scheduler")
            self.thread.start()

    def _loop(self):
        while not self.stop_event.wait(0.02):
            with self.lock:
                due = [job for job in self.jobs.values() if job.next_at <= time.monotonic()]
            for job in due:
                if self.stop_event.is_set():
                    return
                try:
                    job.callback()
                    job.last_error = ""
                except Exception as exc:
                    job.last_error = type(exc).__name__
                finally:
                    with self.lock:
                        job.runs += 1
                        job.next_at = time.monotonic() + job.interval

    def close(self):
        self.stop_event.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=5)
