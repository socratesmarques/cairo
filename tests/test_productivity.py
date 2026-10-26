import json
import tempfile
import unittest
from pathlib import Path

from cairo.integrations.local_utilities import calculate, convert, transform
from cairo.memory import Memory
from cairo.memory.productivity import Productivity
from cairo.orchestrator.productivity_commands import parse_productivity
from cairo.tools.registry import ToolRegistry


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.memory = Memory(self.root / "memory.db")
        self.sid = self.memory.create_session()["id"]
        self.other = self.memory.create_session()["id"]
        self.clock = [1000.0]
        self.daily = Productivity(self.memory, lambda: self.clock[0])

    def call(self, name, **args):
        return self.daily.call(name, args, self.sid)

    def test_tasks_priority_deadline_search_edit_and_recovery(self):
        normal = self.call("task_create", text="Preparar café")
        high = self.call("task_create", text="Revisão do projeto", priority="high", due="2000-01-01")
        tasks = self.call("task_list")["items"]
        self.assertEqual(tasks[0]["id"], high["id"])
        self.assertTrue(tasks[0]["overdue"])
        self.assertEqual(self.call("task_list", query="REVISAO")["count"], 1)
        self.call("task_update", id=high["id"], text="Revisado", status="done", due="")
        self.assertEqual(self.call("task_list")["count"], 1)
        self.call("task_update", id=normal["id"], status="archived")
        self.assertEqual(self.call("task_list")["count"], 0)
        self.call("task_update", id=normal["id"], status="open")
        fresh = Productivity(Memory(self.root / "memory.db"))
        self.assertEqual(fresh.call("task_list", {}, self.sid)["count"], 1)

    def test_notes_preserve_text_and_search_accents(self):
        note = self.call("note_create", title="Reunião", text="Anotação <script>alert(1)</script>\nsegunda linha")
        self.assertEqual(self.call("note_list", query="ANOTACAO")["count"], 1)
        self.call("note_update", id=note["id"], text="Conteúdo alterado", status="archived")
        self.assertEqual(self.call("note_list")["count"], 0)
        self.call("note_update", id=note["id"], status="active")
        self.assertEqual(self.call("note_list")["items"][0]["text"], "Conteúdo alterado")

    def test_note_previews_are_bounded_and_full_read_is_scoped(self):
        note = self.call("note_create", title="Longa", text="x"*2000)
        preview = self.call("note_list")["items"][0]
        self.assertTrue(preview["preview"])
        self.assertLess(len(preview["text"]),400)
        self.assertEqual(len(self.call("note_read",id=note["id"])["text"]),2000)
        with self.assertRaises(KeyError): self.daily.call("note_read",{"id":note["id"]},self.other)

    def test_cross_session_mutations_and_reads(self):
        for tool, args, update in [
            ("task_create", {"text": "Privado"}, "task_update"),
            ("note_create", {"title": "Privado", "text": "Conteúdo"}, "note_update"),
        ]:
            item = self.call(tool, **args)
            with self.assertRaises(KeyError):
                self.daily.call(update, {"id": item["id"], "text": "outro"}, self.other)
        self.assertEqual(self.daily.snapshot(self.other)["tasks"], [])
        self.assertEqual(self.daily.snapshot(self.other)["notes"], [])
        with self.assertRaises(KeyError):
            self.daily.call("task_create", {"text": "x"}, "missing")

    def test_validation_has_no_partial_writes(self):
        for args in ({"text": ""}, {"text": "x", "due": "2026-02-30"}, {"text": "x", "priority": "critical"}, {"text": "x", "extra": "bad"}):
            with self.assertRaises(ValueError):
                self.call("task_create", **args)
        item = self.call("task_create", text="Original")
        with self.assertRaises(ValueError):
            self.call("task_update", id=item["id"], text="Changed", priority="wrong")
        self.assertEqual(self.call("task_list")["items"][0]["text"], "Original")
        with self.assertRaises(ValueError):
            self.call("note_create", title="ok", text="a"*12001)

    def test_export_import_central_regenerates_ids_and_is_atomic(self):
        task = self.call("task_create", text="Exportar", priority="high")
        self.call("note_create", title="Ideia", text="Conteúdo")
        document = self.memory.export_session(self.sid)
        imported = self.memory.import_session(document)
        snapshot = self.daily.snapshot(imported["id"])
        self.assertEqual(snapshot["tasks"][0]["text"],"Exportar")
        self.assertNotEqual(snapshot["tasks"][0]["id"],task["id"])
        self.assertEqual(snapshot["notes"][0]["text"],"Conteúdo")
        count = len(self.memory.sessions())
        document["daily"]["tasks"][0]["priority"] = "invalid"
        with self.assertRaises(ValueError): self.memory.import_session(document)
        self.assertEqual(len(self.memory.sessions()),count)

    def test_snooze_reminder_boundary(self):
        from cairo.scheduler.reminders import Reminders
        from datetime import datetime, timedelta, timezone
        reminders = Reminders(self.memory)
        reminder = reminders.create(self.sid,"Pausa",(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat())
        with self.assertRaises(KeyError): reminders.snooze(reminder["id"],self.other,15)
        with self.assertRaises(ValueError): reminders.snooze(reminder["id"],self.sid,True)
        postponed = reminders.snooze(reminder["id"],self.sid,15)["due"]
        self.assertEqual(datetime.fromisoformat(postponed) - datetime.fromisoformat(reminder["due"]),timedelta(minutes=15))

    def test_timer_pause_resume_restart_expire_and_acknowledge(self):
        timer = self.call("focus_start", seconds=60, text="Leitura")
        self.clock[0] += 20
        paused = self.call("focus_action", id=timer["id"], action="pause")
        self.assertEqual(paused["remaining"], 40)
        self.clock[0] += 300
        fresh = Productivity(self.memory, lambda: self.clock[0])
        self.assertEqual(fresh.call("focus_list", {}, self.sid)["items"][0]["remaining_seconds"], 40)
        fresh.call("focus_action", {"id":timer["id"], "action":"resume"}, self.sid)
        self.clock[0] += 41
        self.assertEqual(fresh.alerts()[0]["id"], timer["id"])
        self.assertEqual(self.call("focus_list")["items"][0]["status"], "finished")
        self.call("focus_action", id=timer["id"], action="acknowledge")
        self.assertEqual(fresh.alerts(), [])

    def test_timer_state_and_limits(self):
        for seconds in (0, -1, 86401, True, 1.5):
            with self.assertRaises(ValueError):
                self.call("focus_start", seconds=seconds)
        timer = self.call("focus_start", seconds=10)
        with self.assertRaises(ValueError):
            self.call("focus_start", seconds=1)
        with self.assertRaises(ValueError):
            self.call("focus_action", id=timer["id"], action="resume")
        with self.assertRaises(KeyError):
            self.daily.call("focus_action", {"id":timer["id"], "action":"cancel"}, self.other)
        self.call("focus_action", id=timer["id"], action="cancel")
        self.call("focus_start", seconds=20)

    def test_offline_utility_tools_roles_and_type_boundaries(self):
        tools = ToolRegistry(self.root, self.memory, allow_network=False)
        response = json.loads(tools.execute("calculate", {"expression":"2+3*4"}, "SystemAgent", self.sid))
        self.assertEqual(response["result"]["value"],14)
        self.assertFalse(json.loads(tools.execute("focus_start", {"seconds":True}, "MasterAgent", self.sid))["ok"])
        self.assertFalse(json.loads(tools.execute("task_create", {"text":"x"}, "Reviewer", self.sid))["ok"])
        self.assertFalse(json.loads(tools.execute("task_create", {"text":"x", "surprise":True}, "MasterAgent", self.sid))["ok"])
        self.assertEqual(self.call("daily_overview")["open_tasks"],0)
        self.assertTrue(self.call("command_help", query="musica")["examples"])


class UtilityTests(unittest.TestCase):
    def test_arithmetic_and_precedence(self):
        for expression, expected in [("(10+5)*2",30),("2**3 + 1",9),("-3 * -2",6),("10,5 / 2",5.25),("9//2",4),("10%3",1)]:
            self.assertEqual(calculate(expression)["value"],expected)

    def test_expression_abuse_rejected(self):
        for expression in ("__import__('os')", "2**9999999", "True+1", "1/0", "[1]*1000000", "2<<999", "1e309", "(-1)**0.5", "(1).__class__", "1+"*50+"1"):
            with self.assertRaises(ValueError, msg=expression):
                calculate(expression)

    def test_conversions_dimensions_temperature_and_binary_bytes(self):
        self.assertEqual(convert("2,5","km","m")["value"],2500)
        self.assertAlmostEqual(convert("32","F","C")["value"],0)
        self.assertAlmostEqual(convert("100","C","F")["value"],212)
        self.assertEqual(convert("1","MiB","B")["value"],1048576)
        self.assertAlmostEqual(convert("36","km/h","m/s")["value"],10)
        self.assertAlmostEqual(convert("1","lb","kg")["value"],.45359237)
        for args in (("1","kg","m"),("-1","K","C"),("nan","m","km"),("1.000,50","m","km")):
            with self.assertRaises(ValueError): convert(*args)

    def test_text_functions(self):
        self.assertEqual(transform("Olá mundo\nCairo", "stats")["words"],3)
        self.assertEqual(transform("Olá, Meu Mundo!", "slug")["text"],"ola-meu-mundo")
        self.assertEqual(transform("b\na\nb", "unique_lines")["text"],"b\na")
        self.assertEqual(transform("b\na", "sort_lines")["text"],"a\nb")
        self.assertEqual(transform("  x  \n y  ", "trim")["text"],"x\ny")
        self.assertEqual(transform("", "stats")["words"],0)
        with self.assertRaises(ValueError): transform("x","execute")

    def test_direct_commands_preserve_literals_and_reject_explanations(self):
        self.assertEqual(parse_productivity("Salve nota Reunião: Café às 9")[0],("note_create",{"title":"Reunião","text":"Café às 9"}))
        self.assertEqual(parse_productivity("Inicie foco de 25 minutos para ler")[0][1]["seconds"],1500)
        self.assertEqual(parse_productivity("Converta 2,5 km para m")[0][1]["value"],"2,5")
        self.assertEqual(parse_productivity("Conte palavras: Olá Mundo")[0][1]["text"],"Olá Mundo")
        for text in ("Não adicione tarefa: x", 'Explique "calcule 1+1"', "talvez inicie foco de 2 minutos"):
            self.assertIsNone(parse_productivity(text))
        for command in ("Me lembre em 30 segundos de descansar", "Me lembre amanhã às 9 de estudar"):
            self.assertEqual(parse_productivity(command)[0][0],"reminder_create")


if __name__ == "__main__":
    unittest.main()
