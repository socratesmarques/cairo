"""Anchored window commands; application names remain literal data."""
import re
import unicodedata

ALIASES = {
    "left": ("esquerda", "lado esquerdo", "metade esquerda"),
    "right": ("direita", "lado direito", "metade direita"),
    "top": ("cima", "topo", "parte de cima", "superior", "metade superior"),
    "bottom": ("baixo", "parte de baixo", "inferior", "metade inferior"),
    "top_left": ("canto superior esquerdo", "canto de cima a esquerda", "canto esquerdo de cima", "cima a esquerda", "superior esquerdo"),
    "top_right": ("canto superior direito", "canto de cima a direita", "canto direito de cima", "cima a direita", "superior direito"),
    "bottom_left": ("canto inferior esquerdo", "canto de baixo a esquerda", "canto esquerdo de baixo", "baixo a esquerda", "inferior esquerdo"),
    "bottom_right": ("canto inferior direito", "canto de baixo a direita", "canto direito de baixo", "baixo a direita", "inferior direito"),
    "center": ("centro", "meio", "centro da tela", "meio da tela"),
    "maximize": ("tela inteira", "tela cheia", "maximizado", "maximizada"),
}


def fold(text):
    return " ".join("".join(c for c in unicodedata.normalize("NFD", text.casefold()) if not unicodedata.combining(c)).split())


def destination(text):
    text = fold(text)
    options = {}
    monitor = re.search(r"\s+(?:no |na )?(?:monitor|tela) (\d+|principal)$", text)
    if monitor:
        options["monitor"] = 1 if monitor[1] == "principal" else int(monitor[1])
        if not 1 <= options["monitor"] <= 32:
            raise ValueError("Informe um monitor entre 1 e 32")
        text = text[:monitor.start()].strip()
    for position, aliases in ALIASES.items():
        if text in aliases:
            return {"action": position if position in {"center", "maximize"} else "snap_" + position, **options}
    custom = re.fullmatch(r"(?:posicao )?(?:x\s*)?(-?\d+)(%)?\s*(?:,|e|;| )\s*(?:y\s*)?(-?\d+)(%)?(?:\s+(?:com )?(?:tamanho\s+(\d+)\s*[x×]\s*(\d+)|largura\s+(\d+)(%)?\s+(?:e )?altura\s+(\d+)(%)?))?", text)
    if custom:
        result = {"action": "custom", "x": int(custom[1]), "y": int(custom[3]), **options}
        if custom[5]:
            result.update(width=int(custom[5]), height=int(custom[6]))
        elif custom[7]:
            result.update(width=int(custom[7]), height=int(custom[9]))
        if any(custom[i] for i in (2, 4, 8, 10)):
            result["unit"] = "percent"
        return result
    return None


def parse_window_command(message, *, discover_apps=False):
    from cairo.integrations.desktop_control import catalog

    raw = re.sub(r"^(?:cairo[, ]+)?(?:por favor[, ]+)?", "", message.strip(), flags=re.I).rstrip(".!?")
    if fold(raw) in {"liste os monitores", "liste monitores", "listar monitores", "mostre os monitores", "quais monitores estao conectados"}:
        return [("desktop_monitors", {})]
    opening = re.fullmatch(r"(?:abra|abre|abrir|inicie)\s+(?:o |a )?(.+?)\s+(?:e\s+(?:coloque|coloca|colocar|ponha|posicione|posicionar|mova|mover)(?:\s+(?:ele|ela|a janela|o aplicativo))?\s+)?(?:na|no|a|à|ao|em|pra|pro|para(?: a| o)?|do lado|no lado)\s+(.+)", raw, re.I)
    moving = re.fullmatch(r"(?:mova|mover|coloque|coloca|colocar|posicione|posicionar|ponha|centralize)\s+(?:(?:a )?janela (?:do |da |de )?|o aplicativo |o |a )?(.+?)\s+(?:na|no|a|à|ao|em|pra|pro|para(?: a| o)?|do lado|no lado)\s+(.+)", raw, re.I)
    match = opening or moving
    if not match:
        central = re.fullmatch(r"centralize\s+(?:o |a )?(.+)", raw, re.I)
        if central:
            return parse_window_command("Mova " + central[1] + " para o centro", discover_apps=discover_apps)
    if not match:
        return None
    args = destination(match[2])
    if args is None:
        return None
    target = match[1].strip().strip('"')
    if fold(target) in {"ele", "ela", "isso", "a janela", "janela", "o aplicativo", "aplicativo"}:
        return None
    if not target or len(target) > 2048 or any(c in target for c in '\r\n;&|<>') or re.search(r"\b(?:e|depois)\s+(?:apague|exclua|execute|rode|digite)\b", fold(target)):
        return None
    app = next((key for key, spec in catalog()["apps"].items() if fold(target) in spec["aliases"]), None)
    window_id = bool(re.fullmatch(r"win:\d+:\d+", target))
    if not app and not discover_apps and not window_id:
        return None
    if opening and window_id:
        return None
    target = app or target
    actions = [("open_app", {"app": target})] if opening else []
    actions.append(("window_action", {"app": target, **args}))
    return actions
