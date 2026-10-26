"""Durable reminders, surfaced while the local interface is connected."""
from datetime import datetime, timezone, timedelta
import uuid


class Reminders:
    def __init__(self, memory):
        self.memory = memory
        with memory.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS reminders(id TEXT PRIMARY KEY, session_id TEXT, text TEXT, due TEXT, status TEXT)")
            db.execute("CREATE INDEX IF NOT EXISTS reminder_due ON reminders(status,due)")

    def create(self, session_id, text, due):
        self.memory.session(session_id)
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1000:
            raise ValueError("Lembrete deve conter 1 a 1000 caracteres")
        moment = datetime.fromisoformat(due)
        if moment.tzinfo is None:
            raise ValueError("Informe data com fuso horário")
        moment = moment.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        if not now < moment <= now + timedelta(days=366):
            raise ValueError("Escolha um horário futuro, até um ano")
        item = dict(id=uuid.uuid4().hex, session_id=session_id, text=text.strip(), due=moment.isoformat(), status="pending")
        with self.memory.db() as db:
            count = db.execute("SELECT count(*) FROM reminders WHERE status='pending'").fetchone()[0]
            if count >= 200:
                raise ValueError("Limite de 200 lembretes pendentes")
            db.execute("INSERT INTO reminders VALUES(:id,:session_id,:text,:due,:status)", item)
        return item

    def list(self, session_id=None):
        with self.memory.db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM reminders WHERE status='pending' AND (? IS NULL OR session_id=?) ORDER BY due LIMIT 200", (session_id, session_id))]

    def dismiss(self, reminder_id, session_id):
        with self.memory.db() as db:
            cursor = db.execute("UPDATE reminders SET status='dismissed' WHERE id=? AND session_id=? AND status='pending'", (reminder_id, session_id))
            if not cursor.rowcount:
                raise KeyError("Lembrete não encontrado nesta conversa")
        return {"dismissed": True}

    def snooze(self, reminder_id, session_id, minutes):
        if type(minutes) is not int or not 1 <= minutes <= 527040:
            raise ValueError("Adiamento deve ser de 1 minuto a 366 dias")
        with self.memory.db() as db:
            row = db.execute("SELECT due FROM reminders WHERE id=? AND session_id=? AND status='pending'", (reminder_id, session_id)).fetchone()
            if not row:
                raise KeyError("Lembrete não encontrado nesta conversa")
            current = datetime.now(timezone.utc)
            moment = max(current, datetime.fromisoformat(row["due"]).astimezone(timezone.utc)) + timedelta(minutes=minutes)
            if moment > current + timedelta(days=366):
                raise ValueError("O novo horário deve estar dentro de um ano")
            due = moment.isoformat()
            db.execute("UPDATE reminders SET due=? WHERE id=? AND session_id=? AND status='pending'", (due, reminder_id, session_id))
        return {"id": reminder_id, "due": due, "message": f"Lembrete adiado por {minutes} minutos."}
