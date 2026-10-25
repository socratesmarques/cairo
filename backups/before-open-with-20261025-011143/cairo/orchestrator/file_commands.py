"""Explicit file actions from the current human message, not retrieved text."""

import re
import unicodedata


def mutation_requested(message: str) -> bool:
    text = "".join(
        c
        for c in unicodedata.normalize("NFD", message.lower())
        if not unicodedata.combining(c)
    ).strip()
    return bool(
        re.match(
            r"^(?:cairo[, ]+)?(?:por favor[, ]+)?(?:(?:eu )?quero que (?:voce )?|(?:voce )?(?:pode|poderia|consegue)\s+)?(?:copie|copiar|mova|mover|renomeie|renomear|crie|criar|escreva|escrever|salve|salvar|edite|editar|altere|alterar|substitua|substituir|apague|apagar|exclua|excluir|delete|deletar|restaure|restaurar|recupere|recuperar|organize|organizar|copy|move|rename|create|write|delete|restore)\b",
            text,
        )
    )


def parse_file_command(message: str) -> list[tuple[str, dict]] | None:
    raw = re.sub(r"^cairo[, ]+", "", message.strip(), flags=re.I)
    with_app = re.fullmatch(
        r'(?:abra|abrir|abre) (?:o )?arquivo "([^"]+)" (?:no|com o|usando o) (.+?)[.!]?',
        raw,
        flags=re.I,
    )
    if with_app:
        return [("open_file", {"path": with_app[1], "app": with_app[2]})]
    app_first = re.fullmatch(
        r'(?:abra|abrir|abre) (?:no|o) (.+?) (?:o )?arquivo "([^"]+)"[.!]?',
        raw,
        flags=re.I,
    )
    if app_first:
        return [("open_file", {"path": app_first[2], "app": app_first[1]})]
    opening = re.fullmatch(
        r'(?:por favor[, ]+)?(?:abra|abrir|abre) (?:o )?arquivo (?:"([^"]+)"|([^"\r\n]+))[.!]?',
        raw,
        flags=re.I,
    )
    if opening:
        return [("open_file", {"path": (opening[1] or opening[2]).strip()})]
    creation = re.fullmatch(
        r'(?:por favor[, ]+)?(?:crie|criar) (?:o |um )?arquivo(?: vazio)? "([^"]+)"(?: vazio| com (?:o )?(?:texto|conte[uú]do) "(.*)")?[.!]?',
        raw,
        flags=re.I | re.S,
    )
    if creation:
        return [
            (
                "file_write_text",
                {
                    "path": creation[1],
                    "content": creation[2] or "",
                    "create_parents": True,
                },
            )
        ]
    directory = re.fullmatch(
        r'(?:crie|criar) (?:a |uma )?pasta "([^"]+)"[.!]?', raw, flags=re.I
    )
    if directory:
        return [("file_mkdir", {"path": directory[1], "parents": True})]
    # Quoted paths preserve spaces, case and accents; no shell syntax is evaluated.
    patterns = [
        (r'leia (?:o )?arquivo "([^"]+)"', "file_read_text", ("path",)),
        (
            r'(?:liste|mostre) (?:os )?arquivos (?:em|da pasta) "([^"]+)"',
            "file_list",
            ("path",),
        ),
        (r'copie "([^"]+)" para "([^"]+)"', "file_copy", ("source", "destination")),
        (r'mova "([^"]+)" para "([^"]+)"', "file_move", ("source", "destination")),
        (r'renomeie "([^"]+)" para "([^"]+)"', "file_rename", ("path", "new_name")),
        (
            r'(?:edite|altere) "([^"]+)" substituindo "([^"]+)" por "([^"]*)"',
            "file_edit_text",
            ("path", "find", "replacement"),
        ),
        (
            r'(?:apague|exclua|envie para (?:a )?lixeira) "([^"]+)"',
            "file_trash",
            ("path",),
        ),
        (r"(?:restaure|recupere) ([a-f0-9]{32})", "file_restore", ("operation_id",)),
        (
            r'(?:informacoes|informações) (?:de |do arquivo )?"([^"]+)"',
            "file_info",
            ("path",),
        ),
        (r'(?:hash|sha256) "([^"]+)"', "file_hash", ("path",)),
        (
            r'(?:busque|procure) "([^"]+)" em "([^"]+)"',
            "file_search",
            ("query", "path"),
        ),
    ]
    for pattern, tool, keys in patterns:
        match = re.fullmatch(pattern + r"[.!]?", raw, flags=re.I)
        if match:
            return [(tool, dict(zip(keys, match.groups())))]
    if raw.lower().rstrip(".!?") in {
        "liste a lixeira",
        "minha lixeira",
        "lixeira do cairo",
    }:
        return [("file_trash_list", {})]
    if raw.lower().rstrip(".!?") in {
        "liste as pastas cadastradas",
        "pastas disponiveis",
        "pastas disponíveis",
    }:
        return [("file_roots", {})]
    return None
