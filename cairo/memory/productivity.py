"""Conversation-scoped tasks, editable notes and durable focus clocks."""

import math
import time
import uuid
from datetime import date, datetime, timezone

from cairo.integrations.local_utilities import calculate, convert, transform
from cairo.integrations.local_utilities import fold
from cairo.scheduler.reminders import Reminders

MAX_ITEMS = 500
MAX_TIMERS = 100
PRIORITIES = {"high", "normal", "low"}


def text_value(value, label, maximum, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise ValueError(f"{label}: informe {'0' if empty else '1'} a {maximum} caracteres")
    return value.strip()


def due_date(value):
    if value == "":
        return ""
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Prazo deve usar AAAA-MM-DD")
    return date.fromisoformat(value).isoformat()


class Productivity:
    def __init__(self, memory, clock=time.time):
        self.memory, self.clock = memory, clock
        with memory.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS daily_tasks(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,text TEXT NOT NULL,priority TEXT NOT NULL,due TEXT NOT NULL,status TEXT NOT NULL,updated TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS daily_tasks_session ON daily_tasks(session_id,status);
                CREATE TABLE IF NOT EXISTS daily_notes(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,title TEXT NOT NULL,text TEXT NOT NULL,status TEXT NOT NULL,updated TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS daily_notes_session ON daily_notes(session_id,status);
                CREATE TABLE IF NOT EXISTS focus_timers(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,text TEXT NOT NULL,seconds INTEGER NOT NULL,remaining REAL NOT NULL,due REAL NOT NULL,status TEXT NOT NULL,created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS focus_session ON focus_timers(session_id,status);
            """)

    def call(self, name, args, session_id):
        self.memory.session(session_id)
        if name == "command_help":
            from cairo.tools.productivity_actions import GUIDE
            query = fold(text_value(args.get("query", ""), "Busca", 200, empty=True))
            examples = [{"category": category, "command": command} for category, command in GUIDE if query in fold(category + " " + command)]
            return {"examples": examples, "message": "\n".join(f"• {item['command']}" for item in examples) or "Nenhum exemplo encontrado."}
        if name == "daily_overview":
            tasks = self.list("task", session_id)["items"]
            timers = [item for item in self.timers(session_id)["items"] if item["status"] in {"running", "paused", "finished"}]
            reminders = Reminders(self.memory).list(session_id)
            return {"open_tasks": len(tasks), "overdue_tasks": sum(item["overdue"] for item in tasks), "active_timers": len(timers), "pending_reminders": len(reminders), "message": f"Seu dia nesta conversa: {len(tasks)} tarefas abertas ({sum(item['overdue'] for item in tasks)} atrasadas), {len(reminders)} lembretes e {len(timers)} temporizadores ativos ou aguardando confirmação.\n" + "\n".join(f"• {item['text']} · {item['due'] or 'sem prazo'}" for item in tasks[:20])}
        if name == "calculate":
            return calculate(**args)
        if name == "unit_convert":
            return convert(**args)
        if name == "text_transform":
            return transform(**args)
        if name in {"task_create", "note_create"}:
            return self.create(name.split("_")[0], args, session_id)
        if name in {"task_update", "note_update"}:
            return self.update(name.split("_")[0], args, session_id)
        if name in {"task_list", "note_list"}:
            result = self.list(name.split("_")[0], session_id, **args)
            result["items"] = result["items"][:30]
            for item in result["items"]:
                if name == "note_list" and len(item["text"]) > 320:
                    item["text"] = item["text"][:320] + "…"
                    item["preview"] = True
            result["has_more"] = result["count"] > len(result["items"])
            result["message"] = "\n".join(f"• {item.get('title', item['text'])} [ID: {item['id']}]" + (f"\n{item['text']}" if name == "note_list" else f" · {item['priority']} · {item['due'] or 'sem prazo'} · {item['status']}") for item in result["items"]) or "Nenhum item encontrado nesta conversa."
            if result["has_more"]:
                result["message"] += "\nMostrando 30 itens. Refine a busca ou abra a Central do dia para ver todos."
            return result
        if name == "note_read":
            item_id = text_value(args["id"], "ID", 32)
            with self.memory.db() as db:
                row = db.execute("SELECT * FROM daily_notes WHERE id=? AND session_id=?", (item_id, session_id)).fetchone()
                if not row:
                    raise KeyError("Nota não encontrada nesta conversa")
                item = dict(row)
            return {**item, "message": f"{item['title']}\n\n{item['text']}"}
        if name == "focus_start":
            return self.start(session_id, **args)
        if name == "focus_action":
            return self.timer_action(session_id, **args)
        if name == "focus_list":
            return self.timers(session_id)
        raise ValueError("Ferramenta de produtividade desconhecida")

    def create(self, kind, args, sid):
        values = self.values(kind, args)
        values.update(id=uuid.uuid4().hex, session_id=sid, status="open" if kind == "task" else "active", updated=datetime.now(timezone.utc).isoformat())
        table = "daily_tasks" if kind == "task" else "daily_notes"
        with self.memory.db() as db:
            if db.execute(f"SELECT COUNT(*) FROM {table} WHERE session_id=?", (sid,)).fetchone()[0] >= MAX_ITEMS:
                raise ValueError(f"Limite de {MAX_ITEMS} itens por conversa; use outra conversa")
            columns = ",".join(values)
            db.execute(f"INSERT INTO {table} ({columns}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))
        label = "Tarefa" if kind == "task" else "Nota"
        return {**values, "message": f"{label} salva: {values.get('title', values['text'])}\nID: {values['id']}"}

    @staticmethod
    def values(kind, args, editing=False):
        allowed = {"text", "priority", "due", "status"} if kind == "task" else {"title", "text", "status"}
        if set(args) - allowed - ({"id"} if editing else set()):
            raise ValueError("Campo de produtividade desconhecido")
        result = {}
        if "text" in args:
            result["text"] = text_value(args["text"], "Texto", 500 if kind == "task" else 12000)
        elif not editing:
            raise ValueError("Informe o texto")
        if kind == "task":
            if "priority" in args or not editing:
                priority = args.get("priority", "normal")
                if priority not in PRIORITIES:
                    raise ValueError("Prioridade: high, normal ou low")
                result["priority"] = priority
            if "due" in args or not editing:
                result["due"] = due_date(args.get("due", ""))
        elif "title" in args or not editing:
            result["title"] = text_value(args.get("title"), "Título", 120)
        if "status" in args:
            statuses = {"open", "done", "archived"} if kind == "task" else {"active", "archived"}
            if args["status"] not in statuses:
                raise ValueError("Estado inválido")
            result["status"] = args["status"]
        return result

    def update(self, kind, args, sid):
        values = self.values(kind, args, editing=True)
        if not values:
            raise ValueError("Informe uma alteração")
        item_id = text_value(args.get("id"), "ID", 32)
        values["updated"] = datetime.now(timezone.utc).isoformat()
        table = "daily_tasks" if kind == "task" else "daily_notes"
        with self.memory.db() as db:
            cursor = db.execute(f"UPDATE {table} SET " + ",".join(f"{key}=?" for key in values) + " WHERE id=? AND session_id=?", (*values.values(), item_id, sid))
            if not cursor.rowcount:
                raise KeyError("Item não encontrado nesta conversa")
            item = dict(db.execute(f"SELECT * FROM {table} WHERE id=? AND session_id=?", (item_id, sid)).fetchone())
        return {**item, "message": f"{'Tarefa' if kind == 'task' else 'Nota'} atualizada. ID: {item_id}"}

    def list(self, kind, sid, status=None, query=""):
        query = text_value(query, "Busca", 200, empty=True)
        status = status or ("open" if kind == "task" else "active")
        if status not in ({"open", "done", "archived", "all"} if kind == "task" else {"active", "archived", "all"}):
            raise ValueError("Filtro inválido")
        table = "daily_tasks" if kind == "task" else "daily_notes"
        search = "text" if kind == "task" else "title || ' ' || text"
        ordering = "CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,CASE WHEN due='' THEN 1 ELSE 0 END,due,updated DESC,id" if kind == "task" else "updated DESC,id"
        with self.memory.db() as db:
            items = [dict(row) for row in db.execute(f"SELECT * FROM {table} WHERE session_id=? AND (?='all' OR status=?) AND instr(search_fold({search}), search_fold(?))>0 ORDER BY {ordering} LIMIT ?", (sid, status, status, query, MAX_ITEMS))]
        today = date.today().isoformat()
        for item in items:
            if kind == "task":
                item["overdue"] = item["status"] == "open" and bool(item["due"]) and item["due"] < today
        lines = [f"• {item.get('title', item['text'])} [ID: {item['id']}]" + (f" · {item['priority']} · {item['due'] or 'sem prazo'} · {item['status']}" if kind == "task" else f"\n{item['text']}") for item in items]
        return {"items": items, "count": len(items), "message": "\n".join(lines) or "Nenhum item encontrado nesta conversa."}

    def expire(self, db, sid):
        db.execute("UPDATE focus_timers SET status='finished',remaining=0 WHERE session_id=? AND status='running' AND due<=?", (sid, self.clock()))

    def start(self, sid, seconds, text="Foco"):
        if type(seconds) is not int or not 1 <= seconds <= 86400:
            raise ValueError("Duração deve ser de 1 segundo a 24 horas")
        text = text_value(text, "Nome do temporizador", 200)
        current = self.clock()
        item = dict(id=uuid.uuid4().hex, session_id=sid, text=text, seconds=seconds, remaining=seconds, due=current + seconds, status="running", created=current)
        with self.memory.db() as db:
            self.expire(db, sid)
            if db.execute("SELECT 1 FROM focus_timers WHERE session_id=? AND status IN ('running','paused')", (sid,)).fetchone():
                raise ValueError("Já existe um temporizador ativo nesta conversa. Pause, retome ou cancele pelo painel.")
            # Retain the latest clocks and every alert awaiting acknowledgement.
            db.execute("DELETE FROM focus_timers WHERE session_id=? AND status IN ('cancelled','acknowledged') AND id NOT IN (SELECT id FROM focus_timers WHERE session_id=? ORDER BY created DESC LIMIT 20)", (sid, sid))
            if db.execute("SELECT COUNT(*) FROM focus_timers WHERE session_id=?", (sid,)).fetchone()[0] >= MAX_TIMERS:
                raise ValueError("Confirme os alertas concluídos antes de iniciar outro temporizador")
            db.execute("INSERT INTO focus_timers VALUES(:id,:session_id,:text,:seconds,:remaining,:due,:status,:created)", item)
        return {**item, "message": f"Temporizador iniciado: {text}, {seconds} s. Alertas aparecem com a página do Cairo aberta.\nID: {item['id']}"}

    def timer_action(self, sid, id, action):
        if action not in {"pause", "resume", "cancel", "acknowledge"}:
            raise ValueError("Ação de temporizador inválida")
        with self.memory.db() as db:
            self.expire(db, sid)
            row = db.execute("SELECT * FROM focus_timers WHERE id=? AND session_id=?", (id, sid)).fetchone()
            if not row:
                raise KeyError("Temporizador não encontrado nesta conversa")
            item = dict(row)
            expected = {"pause": {"running"}, "resume": {"paused"}, "cancel": {"paused", "running"}, "acknowledge": {"finished"}}
            if item["status"] not in expected[action]:
                raise ValueError("Ação incompatível com o estado atual; atualize o painel")
            if action == "pause":
                item.update(remaining=max(0, item["due"] - self.clock()), status="paused")
            elif action == "resume":
                item.update(due=self.clock() + item["remaining"], status="running")
            else:
                item["status"] = "cancelled" if action == "cancel" else "acknowledged"
            db.execute("UPDATE focus_timers SET remaining=?,due=?,status=? WHERE id=? AND session_id=?", (item["remaining"], item["due"], item["status"], id, sid))
        return {**item, "message": {"pause": "Temporizador pausado.", "resume": "Temporizador retomado.", "cancel": "Temporizador cancelado.", "acknowledge": "Alerta confirmado."}[action]}

    def timers(self, sid):
        with self.memory.db() as db:
            self.expire(db, sid)
            rows = [dict(row) for row in db.execute("SELECT * FROM focus_timers WHERE session_id=? ORDER BY CASE WHEN status IN ('running','paused','finished') THEN 0 ELSE 1 END,created DESC LIMIT ?", (sid, MAX_TIMERS))]
        for item in rows:
            item["remaining_seconds"] = math.ceil(max(0, item["due"] - self.clock())) if item["status"] == "running" else math.ceil(item["remaining"])
        return {"items": rows, "message": "\n".join(f"• {i['text']}: {i['status']}, {i['remaining_seconds']} s [ID: {i['id']}]" for i in rows) or "Nenhum temporizador nesta conversa."}

    def snapshot(self, sid):
        self.memory.session(sid)
        return {"tasks": self.list("task", sid, status="all")["items"], "notes": self.list("note", sid, status="all")["items"], "timers": self.timers(sid)["items"], "reminders": Reminders(self.memory).list(sid)}

    def alerts(self):
        with self.memory.db() as db:
            db.execute("UPDATE focus_timers SET status='finished',remaining=0 WHERE status='running' AND due<=?", (self.clock(),))
            return [dict(row) for row in db.execute("SELECT id,session_id,text FROM focus_timers WHERE status='finished' ORDER BY due LIMIT 100")]
