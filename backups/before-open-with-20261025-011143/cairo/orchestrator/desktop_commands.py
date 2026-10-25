"""Anchored commands from the current user message; never from retrieved text."""

import re
import unicodedata
from datetime import datetime, timedelta, timezone

from cairo.integrations.desktop_control import catalog
from cairo.integrations.folders import ALIASES
from cairo.orchestrator.control_commands import parse_command
from cairo.orchestrator.file_commands import parse_file_command


def normalize(text: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", text.lower())
        if not unicodedata.combining(c)
    )


def parse_desktop_commands(
    message: str, *, discover_apps: bool = False
) -> list[tuple[str, dict]] | None:
    command = parse_command(message)
    if command:
        return [("run_command", command)]
    music_request = re.fullmatch(
        r"(?:cairo[, ]+)?(?:(?:abra|abrir) (?:o )?youtube music e )?(?:toque|tocar|reproduza|reproduzir)\s+(.+?)(?:\s+no youtube music)?[.!]?",
        message.strip(),
        re.I,
    )
    if (
        music_request
        and normalize(message.strip()).rstrip(".!?") != "reproduza ou pause a musica"
    ):
        query = music_request[1].strip().strip('"')
        if normalize(query) in {"uma musica", "musica", "alguma musica"}:
            query = "música"
        return [("browser_play_music", {"query": query})]
    raw_control = re.sub(r"^cairo[, ]+", "", message.strip(), flags=re.I)
    if normalize(raw_control).rstrip(".!?") in {
        "liste as janelas",
        "listar janelas",
        "janelas abertas",
    }:
        return [("app_windows", {})]
    if normalize(raw_control).rstrip(".!?") in {
        "leia a pagina atual",
        "inspecione a pagina",
    }:
        return [("browser_read", {})]
    control_patterns = [
        (r"inspecione (?:a )?janela (win:\d+:\d+)", "app_inspect", ("window",)),
        (r"clique (?:no )?controle (ctl:[0-9a-f]+)", "app_click", ("control",)),
        (r'preencha (ctl:[0-9a-f]+) com "([^"]*)"', "app_fill", ("control", "text")),
        (
            r"pressione ([a-z0-9+]+) (?:na )?janela (win:\d+:\d+)",
            "app_keys",
            ("keys", "window"),
        ),
        (r"abra (?:no )?navegador cairo (https://\S+)", "browser_open", ("url",)),
        (r"clique (?:no )?elemento (dom:[0-9a-f]+)", "browser_click", ("element",)),
        (
            r'preencha (dom:[0-9a-f]+) com "([^"]*)"',
            "browser_fill",
            ("element", "text"),
        ),
    ]
    for pattern, tool, keys in control_patterns:
        match = re.fullmatch(pattern, raw_control, re.I | re.S)
        if match:
            return [(tool, dict(zip(keys, match.groups())))]
    files = parse_file_command(message)
    if files:
        return files
    raw = message.strip()
    if "https://" not in raw.lower():
        raw = raw.rstrip(".!?").strip()
    raw = re.sub(r"^(?:cairo[, ]+|por favor[, ]+)", "", raw, flags=re.I)
    text = normalize(raw)
    window_action = re.fullmatch(
        r"(foque|minimize|maximize|restaure|feche) (?:a )?janela (win:\d+:\d+)", text
    )
    if window_action:
        return [
            (
                "app_window",
                {
                    "window": window_action[2],
                    "action": {
                        "foque": "focus",
                        "minimize": "minimize",
                        "maximize": "maximize",
                        "restaure": "restore",
                        "feche": "close",
                    }[window_action[1]],
                },
            )
        ]
    directory = re.fullmatch(r'(?:abra|abrir|abre) (?:a )?pasta "([^"]+)"', raw, re.I)
    if directory:
        return [("open_directory", {"path": directory[1]})]
    executable = re.fullmatch(
        r'(?:abra|abrir|abre) "?([a-z]:[/\\].+\.exe)"?', raw, re.I
    )
    if discover_apps and executable:
        return [("open_app", {"app": executable[1]})]
    if text in {
        "o que voce pode fazer",
        "o que voce consegue fazer",
        "quais sao suas funcoes",
        "suas capacidades",
    }:
        return [("capabilities", {})]
    weather = re.fullmatch(
        r"(?:como esta (?:o )?(?:clima|tempo)|qual (?:e )?(?:o )?(?:clima|tempo)|(?:clima|tempo)|previsao do tempo)(?: (?:agora|hoje|amanha))?(?: (?:em|para) (.+))?",
        text,
    )
    if weather:
        # Preserve original spelling/accents in the city sent to geocoding.
        location = re.search(r"\s(?:em|para)\s+(.+)$", raw, re.I)
        return [("weather", {"city": location[1]} if location else {})]
    if text in {
        "que horas sao",
        "qual e a hora",
        "que dia e hoje",
        "qual a data de hoje",
        "data e hora",
    }:
        return [("local_time", {})]
    media = {
        "proxima musica": "next",
        "proxima faixa": "next",
        "musica anterior": "previous",
        "faixa anterior": "previous",
        "aumente o volume": "volume_up",
        "aumentar volume": "volume_up",
        "diminua o volume": "volume_down",
        "abaixe o volume": "volume_down",
        "ative ou desative o mudo": "mute",
        "alterne o mudo": "mute",
        "reproduza ou pause a musica": "play_pause",
        "alterne reproducao e pausa": "play_pause",
        "pare a musica": "stop",
    }
    if text in media:
        return [("media_action", {"action": media[text]})]
    read_url = re.fullmatch(r"leia (?:a pagina |o site )?(https://\S+)", raw, re.I)
    if read_url:
        return [("read_webpage", {"url": read_url[1]})]
    open_url = re.fullmatch(r"(?:abra|abrir|abre) (https://\S+)", raw, re.I)
    if open_url:
        return [("open_url", {"url": open_url[1]})]
    listing = re.fullmatch(
        r"(?:liste|mostre|listar) (?:os )?(?:arquivos (?:da|de|em) )?(?:pasta )?(.+)",
        text,
    )
    if listing and listing[1] in ALIASES:
        return [("list_personal_files", {"folder": ALIASES[listing[1]]})]
    if text in {"liste meus lembretes", "listar lembretes", "meus lembretes"}:
        return [("reminder_list", {})]
    reminder = re.fullmatch(
        r"(?:me lembre|lembre-me) em (\d{1,5}) (minutos?|horas?) de (.+)", raw, re.I
    )
    if reminder:
        minutes = int(reminder[1]) * (
            60 if reminder[2].lower().startswith("hora") else 1
        )
        if 1 <= minutes <= 527040:
            due = datetime.now(timezone.utc) + timedelta(minutes=minutes)
            return [("reminder_create", {"text": reminder[3], "due": due.isoformat()})]
    web = re.fullmatch(r"(?:pesquise|busque|procure) (.+) no google", raw, re.I)
    if web:
        return [("search_web", {"query": web[1]})]
    if text in {
        "liste os aplicativos",
        "listar aplicativos",
        "quais aplicativos voce controla",
        "quais aplicativos estao disponiveis",
    }:
        return [("desktop_apps", {})]
    search = re.fullmatch(
        r"(?:pesquise|procure|busque|buscar|pesquisar) (.+?) no (?:youtube music|yt music)(?: pelo (chrome|edge))?",
        raw,
        flags=re.I,
    )
    if search:
        return [
            (
                "search_music",
                {"query": search[1], "browser": (search[2] or "chrome").lower()},
            )
        ]
    # A compound command is accepted only when every clause matches an exact action.
    pieces = re.split(
        r"\s+e\s+(?=(?:abra|abrir|abre|minimize|maximize|restaure|foque)\b)", text
    )
    if len(pieces) > 4:
        return None
    data = catalog()
    actions = []
    for piece in pieces:
        match = re.fullmatch(
            r"(abra|abrir|abre|minimize|maximize|restaure|foque) (?:o |a |os |as )?(.+?)(?: (?:no|pelo) (chrome|edge))?(?:,? por favor)?",
            piece,
        )
        if not match:
            return None
        verb, target, browser = match.groups()
        folder = ALIASES.get(target.removeprefix("pasta ").removeprefix("de "))
        app = next(
            (key for key, spec in data["apps"].items() if target in spec["aliases"]),
            None,
        )
        site = next(
            (key for key, spec in data["sites"].items() if target in spec["aliases"]),
            None,
        )
        if verb in {"abra", "abrir", "abre"}:
            if folder and not browser:
                actions.append(("open_folder", {"folder": folder}))
            elif site:
                actions.append(
                    ("open_site", {"site": site, "browser": browser or "chrome"})
                )
            elif app and not browser:
                actions.append(("open_app", {"app": app}))
            elif (
                discover_apps
                and not browser
                and not target.startswith(("no ", "na ", "com "))
                and not re.search(r"\b(?:nesse|neste|esse|este|arquivo)\b", target)
                and not any(c in target for c in ';|&<>/\\"')
                and not re.search(
                    r"\be (?:apague|exclua|delete|mova|copie|digite|preencha|clique|pressione|selecione|feche|controle)\b",
                    target,
                )
            ):
                actions.append(("open_app", {"app": target}))
            else:
                return None
        elif app and not browser:
            actions.append(
                (
                    "window_action",
                    {
                        "app": app,
                        "action": {
                            "minimize": "minimize",
                            "maximize": "maximize",
                            "restaure": "restore",
                            "foque": "focus",
                        }[verb],
                    },
                )
            )
        else:
            return None
    return actions or None
