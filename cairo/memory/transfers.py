"""Validate imported chat data before performing a single database transaction."""
from datetime import datetime, timezone
import json
import uuid

MAX_IMPORT_BYTES = 8 * 1024 * 1024
MAX_IMPORT_MESSAGES = 10000
MAX_MESSAGE_LENGTH = 200000


def import_conversation(memory, document):
    if not isinstance(document, dict):
        raise ValueError("Selecione um JSON de conversa exportado pelo Cairo")
    try:
        if len(json.dumps(document, ensure_ascii=False).encode("utf-8")) > MAX_IMPORT_BYTES:
            raise ValueError("Importações aceitam até 8 MB")
    except (TypeError, UnicodeEncodeError):
        raise ValueError("A conversa deve conter texto JSON válido") from None
    title = document.get("title")
    messages, notes = document.get("messages"), document.get("notes", [])
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
        raise ValueError("A conversa deve conter um título de até 100 caracteres")
    if not isinstance(messages, list) or len(messages) > MAX_IMPORT_MESSAGES:
        raise ValueError("A conversa deve conter até 10000 mensagens")
    if not isinstance(notes, list) or len(notes) > 1000:
        raise ValueError("A conversa deve conter até 1000 notas")
    validated = []
    timestamp = datetime.now(timezone.utc).isoformat()
    for message in messages:
        if not isinstance(message, dict) or not isinstance(message.get("role"), str) or message["role"] not in {"user", "assistant"}:
            raise ValueError("Somente mensagens de usuário e assistente podem ser importadas")
        content = message.get("content")
        if not isinstance(content, str) or len(content) > MAX_MESSAGE_LENGTH:
            raise ValueError("Mensagem inválida ou maior que 200000 caracteres")
        created = message.get("created_at", timestamp)
        if not isinstance(created, str):
            raise ValueError("Data de mensagem inválida")
        try:
            moment = datetime.fromisoformat(created)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            created = moment.astimezone(timezone.utc).isoformat()
        except (ValueError, OverflowError):
            raise ValueError("Data de mensagem inválida") from None
        validated.append((message["role"], content, created))
    note_contents = []
    for note in notes:
        content = note.get("content") if isinstance(note, dict) else None
        if not isinstance(content, str) or not 1 <= len(content) <= 12000:
            raise ValueError("Nota inválida ou maior que 12000 caracteres")
        note_contents.append(content)
    daily_items = {"tasks": [], "notes": []}
    if "daily" in document:
        from cairo.memory.productivity import Productivity, MAX_ITEMS
        daily = document["daily"]
        if not isinstance(daily, dict) or set(daily) - {"tasks", "notes"}:
            raise ValueError("Central do dia inválida na importação")
        for collection, kind in (("tasks", "task"), ("notes", "note")):
            entries = daily.get(collection, [])
            if not isinstance(entries, list) or len(entries) > MAX_ITEMS:
                raise ValueError("A central aceita até 500 tarefas e 500 notas por conversa")
            fields = {"text", "priority", "due", "status"} if kind == "task" else {"title", "text", "status"}
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError("Item inválido na central importada")
                values = Productivity.values(kind, {key: value for key, value in entry.items() if key in fields})
                values.setdefault("status", "open" if kind == "task" else "active")
                daily_items[collection].append(values)
        Productivity(memory)
    # Imported IDs and execution records never control local identities or run tools.
    item = {"id": uuid.uuid4().hex, "title": title.strip(), "created_at": timestamp,
            "pinned": 0, "archived": 0}
    with memory.db() as db:
        db.execute("INSERT INTO sessions(id,title,created_at) VALUES(:id,:title,:created_at)", item)
        db.executemany("INSERT INTO messages(session_id,role,content,created_at) VALUES(?,?,?,?)",
                       [(item["id"], role, content, created) for role, content, created in validated])
        db.executemany("INSERT INTO notes(session_id,content,created_at) VALUES(?,?,?)",
                       [(item["id"], content, timestamp) for content in note_contents])
        for collection, table in (("tasks", "daily_tasks"), ("notes", "daily_notes")):
            for values in daily_items[collection]:
                row = {**values, "id": uuid.uuid4().hex, "session_id": item["id"], "updated": timestamp}
                db.execute(f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))
    return {**item, "imported_messages": len(validated), "imported_notes": len(note_contents), "imported_tasks": len(daily_items["tasks"]), "imported_daily_notes": len(daily_items["notes"])}
