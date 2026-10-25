import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from cairo.config import Settings
from cairo.memory import Memory
from cairo.models import DemoModel, ModelError, Reply
from cairo.orchestrator import Orchestrator
from cairo.scheduler import Scheduler
from cairo.storage import backup


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def app(self, model=None, **options):
        settings = Settings(workspace=self.root / "workspace", data_dir=self.root / "data", **options)
        app = Orchestrator(settings, model)
        self.addCleanup(app.close)
        return app

    def wait(self, app, run):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = app.memory.run(run["id"])
            if result["status"] in {"completed", "failed", "cancelled"}:
                return result
            time.sleep(0.01)
        self.fail("Run did not finish within five seconds")

    def test_normal_tools_and_history_survive_reopen(self):
        app = self.app()
        sid = app.memory.create_session()["id"]
        result = self.wait(app, app.submit(sid, "Verifique o sistema", "normal"))
        self.assertEqual(result["status"], "completed", result["error"])
        self.assertTrue(any(e["kind"] == "tool" for e in result["events"]))
        self.assertIn("Demonstração", result["result"])
        reopened = Memory(app.settings.data_dir / "cairo.db")
        self.assertEqual([m["role"] for m in reopened.session(sid)["messages"]], ["user", "assistant"])

    def test_swarm_review_follows_all_three_agents(self):
        app = self.app()
        sid = app.memory.create_session()["id"]
        result = self.wait(app, app.submit(sid, "Analise o workspace", "swarm"))
        self.assertEqual(result["status"], "completed", result["error"])
        events = result["events"]
        reviewer_start = next(e["id"] for e in events if e["agent"] == "Reviewer" and e["kind"] == "started")
        for name in ("DeveloperAgent", "ResearchAgent", "SystemAgent"):
            finish = next(e["id"] for e in events if e["agent"] == name and e["kind"] == "completed")
            self.assertLess(finish, reviewer_start)
        self.assertEqual(len([e for e in events if e["agent"] == "MasterAgent" and e["kind"] == "started"]), 2)

    def test_model_failure_is_visible_without_demo_fallback(self):
        class Failed:
            def complete(self, messages, tools):
                raise ModelError("Provider unavailable")
        app = self.app(Failed())
        sid = app.memory.create_session()["id"]
        result = self.wait(app, app.submit(sid, "hello", "normal"))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"], "Provider unavailable")
        self.assertEqual(len(app.memory.session(sid)["messages"]), 1)

    def test_cancel_and_same_session_concurrency(self):
        entered, release = threading.Event(), threading.Event()
        class Slow:
            def complete(self, messages, tools):
                entered.set()
                release.wait(3)
                return Reply("must not persist")
        app = self.app(Slow())
        sid = app.memory.create_session()["id"]
        run = app.submit(sid, "hello", "normal")
        self.assertTrue(entered.wait(2))
        try:
            with self.assertRaises(RuntimeError):
                app.submit(sid, "overlapping", "normal")
            app.cancel(run["id"])
        finally:
            release.set()
        self.assertEqual(self.wait(app, run)["status"], "cancelled")
        self.assertEqual(len(app.memory.session(sid)["messages"]), 1)

    def test_tool_loop_has_budget(self):
        class Loop:
            def complete(self, messages, tools):
                return Reply(calls=[{"id": "one", "type": "function", "function": {"name": "system_info", "arguments": "{}"}}])
        app = self.app(Loop(), max_steps=2)
        sid = app.memory.create_session()["id"]
        run = self.wait(app, app.submit(sid, "loop", "normal"))
        self.assertEqual(run["status"], "failed")
        self.assertIn("limite", run["error"])
        self.assertEqual(len([e for e in run["events"] if e["kind"] == "tool"]), 2)

    def test_session_notes_do_not_leak_and_online_backup(self):
        memory = Memory(self.root / "state.db")
        a, b = memory.create_session()["id"], memory.create_session()["id"]
        memory.save_note(a, "Cairo architecture")
        self.assertEqual(memory.search("Cairo", b), [])
        target = self.root / "backup.db"
        backup(memory.path, target)
        self.assertEqual(Memory(target).search("Cairo", a)[0]["content"], "Cairo architecture")
        with self.assertRaises(FileExistsError):
            backup(memory.path, target)

    def test_recovery_marks_interrupted_runs_failed(self):
        memory = Memory(self.root / "state.db")
        run = memory.create_run(memory.create_session()["id"], "normal")
        recovered = Memory(memory.path)
        self.assertEqual(recovered.run(run["id"])["status"], "queued")
        recovered.recover_interrupted()
        self.assertEqual(recovered.run(run["id"])["status"], "failed")

    def test_data_directory_cannot_be_shared_by_two_runtimes(self):
        app = self.app()
        with self.assertRaisesRegex(ValueError, "Outro Cairo"):
            Orchestrator(app.settings)

    def test_scheduler_records_failure_and_keeps_running(self):
        scheduler = Scheduler()
        self.addCleanup(scheduler.close)
        event = threading.Event()
        def bad():
            raise ValueError("expected")
        scheduler.add("bad", 0.05, bad)
        scheduler.add("good", 0.05, event.set)
        scheduler.start()
        self.assertTrue(event.wait(2))
        scheduler.close()
        self.assertEqual(scheduler.jobs["bad"].last_error, "ValueError")
        self.assertGreaterEqual(scheduler.jobs["good"].runs, 1)

    def test_specialists_actually_overlap(self):
        barrier = threading.Barrier(3, timeout=2)
        class Concurrent(DemoModel):
            def complete(self, messages, tools):
                if tools and not any(m["role"] == "tool" for m in messages):
                    barrier.wait()
                return super().complete(messages, tools)
        app = self.app(Concurrent())
        sid = app.memory.create_session()["id"]
        result = self.wait(app, app.submit(sid, "parallel", "swarm"))
        self.assertEqual(result["status"], "completed", result["error"])


if __name__ == "__main__":
    unittest.main()
