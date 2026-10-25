"""Parse explicit terminal requests and recognize current-user UI intent."""

import re
import unicodedata


def parse_command(message: str) -> dict | None:
    raw = re.sub(
        r"^(?:cairo[, ]+)?(?:por favor[, ]+)?", "", message.strip(), flags=re.I
    )
    match = re.fullmatch(
        r'(?:execute|executar|rode|rodar)?\s*(?:no |em )?(cmd|powershell)(?:\s+(?:em|na pasta)\s+"([^"]+)")?\s*:\s*(.+)',
        raw,
        re.I | re.S,
    )
    if not match:
        return None
    shell, cwd, command = match.groups()
    return {"shell": shell.lower(), "command": command, "cwd": cwd or ""}


def interaction_requested(message: str) -> bool:
    text = "".join(
        c
        for c in unicodedata.normalize("NFD", message.lower())
        if not unicodedata.combining(c)
    ).strip()
    if re.match(r"^(?:cairo[, ]+)?(?:nao|explique|resuma|leia)\b", text):
        return False
    return bool(
        re.search(
            r"(?:^|\be\s+)(?:cairo[, ]+)?(?:por favor[, ]+)?(?:(?:eu )?quero que (?:voce )?|(?:voce )?(?:pode|poderia|consegue)\s+)?(?:clique|clicar|digite|digitar|preencha|preencher|pressione|pressionar|selecione|selecionar|minimize|maximize|restaure|foque|feche|fechar|controle|controlar|navegue|navegar|role|rolar|click|fill|press|close)\b",
            text,
        )
    )
