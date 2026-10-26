"""Exact Portuguese shortcuts for local daily tools; preserve literal user text."""

import re
from datetime import datetime, timedelta

from cairo.integrations.local_utilities import fold


def parse_productivity(message):
    raw = re.sub(r"^(?:cairo[, ]+|por favor[, ]+)", "", message.strip(), flags=re.I)
    normalized = fold(raw).rstrip(".!?")
    exact = {
        "minhas tarefas": ("task_list", {}), "liste minhas tarefas": ("task_list", {}),
        "tarefas concluidas": ("task_list", {"status": "done"}),
        "minhas notas": ("note_list", {}), "liste minhas notas": ("note_list", {}),
        "meu dia": ("daily_overview", {}), "resumo do meu dia": ("daily_overview", {}),
        "meus temporizadores": ("focus_list", {}), "ajuda com comandos": ("command_help", {}),
        "mostre os comandos": ("command_help", {}),
    }
    if normalized in exact:
        return [exact[normalized]]
    patterns = [
        (r"(?:adicione|crie) (?:uma )?tarefa:\s*(.+)", "task_create", ("text",)),
        (r"(?:salve|crie) (?:uma )?nota (.+?):\s*(.+)", "note_create", ("title", "text")),
        (r"(?:busque|procure) (?:nas )?notas (.+)", "note_list", ("query",)),
        (r"(?:busque|procure) (?:nas )?tarefas (.+)", "task_list", ("query",)),
        (r"calcule\s+(.+)", "calculate", ("expression",)),
        (r"converta ([+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+))\s+(.+?)\s+(?:para|em)\s+(.+)", "unit_convert", ("value", "source", "target")),
    ]
    for pattern, tool, keys in patterns:
        match = re.fullmatch(pattern, raw, re.I | re.S)
        if match:
            return [(tool, dict(zip(keys, match.groups()))) ]
    task = re.fullmatch(r"(conclua|reabra|arquive) (?:a )?tarefa ([0-9a-f]{32})", normalized)
    if task:
        return [("task_update", {"id": task[2], "status": {"conclua": "done", "reabra": "open", "arquive": "archived"}[task[1]]})]
    note_read = re.fullmatch(r"leia (?:a )?nota ([0-9a-f]{32})", normalized)
    if note_read:
        return [("note_read", {"id": note_read[1]})]
    timer = re.fullmatch(r"(?:inicie (?:um )?foco|inicie (?:um )?temporizador|temporizador|foco) (?:de |por )?(\d{1,5}) (segundos?|minutos?|horas?)(?: (?:para|de) (.+))?", raw, re.I)
    if timer:
        factor = 1 if timer[2].lower().startswith("seg") else 60 if timer[2].lower().startswith("min") else 3600
        return [("focus_start", {"seconds": int(timer[1])*factor, "text": timer[3] or "Foco"})]
    timer_action = re.fullmatch(r"(pause|retome|cancele) (?:o )?temporizador ([0-9a-f]{32})", normalized)
    if timer_action:
        return [("focus_action", {"id": timer_action[2], "action": {"pause": "pause", "retome": "resume", "cancele": "cancel"}[timer_action[1]]})]
    snooze = re.fullmatch(r"adie (?:o )?lembrete ([0-9a-f]{32}) (?:por|em) (\d{1,6}) minutos?", normalized)
    if snooze:
        return [("reminder_snooze", {"id": snooze[1], "minutes": int(snooze[2])})]
    stats = re.fullmatch(r"conte (?:as )?palavras(?: do texto)?:\s*(.*)", raw, re.I | re.S)
    if stats:
        return [("text_transform", {"text": stats[1], "action": "stats"})]
    reminder = re.fullmatch(r"(?:me lembre|lembre-me) em (\d{1,6}) (segundos?|minutos?|horas?|dias?) de (.+)", raw, re.I)
    if reminder:
        unit = reminder[2].lower()
        seconds = int(reminder[1]) * (1 if unit.startswith("seg") else 60 if unit.startswith("min") else 3600 if unit.startswith("hora") else 86400)
        if 1 <= seconds <= 366*86400:
            return [("reminder_create", {"text": reminder[3], "due": (datetime.now().astimezone() + timedelta(seconds=seconds)).isoformat()})]
    dated = re.fullmatch(r"(?:me lembre|lembre-me) (hoje|amanhã|amanha) [àa]s? (\d{1,2})(?::(\d{2}))? de (.+)", raw, re.I)
    if dated and int(dated[2]) < 24 and int(dated[3] or 0) < 60:
        moment = datetime.now().astimezone().replace(hour=int(dated[2]), minute=int(dated[3] or 0), second=0, microsecond=0)
        if fold(dated[1]) == "amanha":
            moment += timedelta(days=1)
        return [("reminder_create", {"text": dated[4], "due": moment.isoformat()})]
    return None
