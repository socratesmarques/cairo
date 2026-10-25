"""Anchored commands from the current user message; never from retrieved text."""
from datetime import datetime, timezone, timedelta
import re
import unicodedata
from cairo.integrations.desktop_control import catalog


def normalize(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))


def parse_desktop_commands(message: str) -> list[tuple[str, dict]] | None:
    raw = message.strip().rstrip(".!?").strip()
    raw = re.sub(r"^(?:cairo[, ]+|por favor[, ]+)", "", raw, flags=re.I)
    text = normalize(raw)
    if text in {"liste meus lembretes", "listar lembretes", "meus lembretes"}:
        return [("reminder_list", {})]
    reminder = re.fullmatch(r"(?:me lembre|lembre-me) em (\d{1,5}) (minutos?|horas?) de (.+)", raw, re.I)
    if reminder:
        minutes = int(reminder[1]) * (60 if reminder[2].lower().startswith("hora") else 1)
        if 1 <= minutes <= 527040:
            due = datetime.now(timezone.utc) + timedelta(minutes=minutes)
            return [("reminder_create", {"text": reminder[3], "due": due.isoformat()})]
    web = re.fullmatch(r"(?:pesquise|busque|procure) (.+) no google", raw, re.I)
    if web:
        return [("search_web", {"query": web[1]})]
    if text in {"liste os aplicativos", "listar aplicativos", "quais aplicativos voce controla", "quais aplicativos estao disponiveis"}:
        return [("desktop_apps", {})]
    search = re.fullmatch(r"(?:pesquise|procure|busque|buscar|pesquisar) (.+?) no (?:youtube music|yt music)(?: pelo (chrome|edge))?", raw, flags=re.I)
    if search:
        return [("search_music", {"query": search[1], "browser": (search[2] or "chrome").lower()})]
    # A compound command is accepted only when every clause matches an exact action.
    pieces = re.split(r"\s+e\s+(?=(?:abra|abrir|abre|minimize|maximize|restaure|foque)\b)", text)
    if len(pieces) > 4:
        return None
    data = catalog()
    actions = []
    for piece in pieces:
        match = re.fullmatch(r"(abra|abrir|abre|minimize|maximize|restaure|foque) (?:o |a |os |as )?(.+?)(?: (?:no|pelo) (chrome|edge))?(?:,? por favor)?", piece)
        if not match:
            return None
        verb, target, browser = match.groups()
        app = next((key for key, spec in data["apps"].items() if target in spec["aliases"]), None)
        site = next((key for key, spec in data["sites"].items() if target in spec["aliases"]), None)
        if verb in {"abra", "abrir", "abre"}:
            if site:
                actions.append(("open_site", {"site": site, "browser": browser or "chrome"}))
            elif app and not browser:
                actions.append(("open_app", {"app": app}))
            else:
                return None
        elif app and not browser:
            actions.append(("window_action", {"app": app, "action": {"minimize": "minimize", "maximize": "maximize", "restaure": "restore", "foque": "focus"}[verb]}))
        else:
            return None
    return actions or None
