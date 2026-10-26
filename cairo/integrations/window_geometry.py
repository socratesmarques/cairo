"""Pure window geometry in physical screen coordinates and monitor work areas."""

POSITIONS = {
    "left": "metade esquerda", "right": "metade direita",
    "top": "metade superior", "bottom": "metade inferior",
    "top_left": "canto superior esquerdo", "top_right": "canto superior direito",
    "bottom_left": "canto inferior esquerdo", "bottom_right": "canto inferior direito",
    "center": "centro", "custom": "posição personalizada",
}


def placement(work, position, current, *, x=None, y=None, width=None, height=None, unit="pixels"):
    left, top, right, bottom = work
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0 or position not in POSITIONS:
        raise ValueError("Área de trabalho ou posição inválida")
    cw, ch = max(1, current[2] - current[0]), max(1, current[3] - current[1])
    mx, my = left + w // 2, top + h // 2
    if position == "center":
        cw, ch = min(cw, w), min(ch, h)
        return left + (w - cw) // 2, top + (h - ch) // 2, cw, ch
    if position == "custom":
        if type(x) is not int or type(y) is not int:
            raise ValueError("Informe coordenadas inteiras x e y")
        if any(value is not None and type(value) is not int for value in (width, height)):
            raise ValueError("Largura e altura devem ser inteiros")
        if unit == "percent":
            if not 0 <= x < 100 or not 0 <= y < 100:
                raise ValueError("Coordenadas percentuais devem estar entre 0 e 99")
            if any(v is not None and not 1 <= v <= 100 for v in (width, height)):
                raise ValueError("Dimensões percentuais devem estar entre 1 e 100")
            x, y, width, height = left + w*x//100, top + h*y//100, w*width//100 if width is not None else cw, h*height//100 if height is not None else ch
        elif unit == "pixels":
            width, height = width if width is not None else cw, height if height is not None else ch
        else:
            raise ValueError("Unidade deve ser pixels ou percent")
        if not 1 <= width <= w or not 1 <= height <= h or x < left or y < top or x + width > right or y + height > bottom:
            raise ValueError("A posição e o tamanho precisam caber na área útil do monitor escolhido")
        return x, y, width, height
    horizontal = position in {"left", "right"} or "_" in position
    vertical = position in {"top", "bottom"} or "_" in position
    x1 = mx if position == "right" or position.endswith("_right") else left
    x2 = mx if position == "left" or position.endswith("_left") else right
    y1 = my if position == "bottom" or position.startswith("bottom_") else top
    y2 = my if position == "top" or position.startswith("top_") else bottom
    return x1 if horizontal else left, y1 if vertical else top, x2-x1 if horizontal else w, y2-y1 if vertical else h


def reanchor(work, position, actual, requested):
    """Respect an application's minimum size while keeping the requested edge visible."""
    left, top, right, bottom = work
    width, height = actual[2] - actual[0], actual[3] - actual[1]
    if width > right-left or height > bottom-top:
        raise ValueError("O tamanho mínimo deste aplicativo é maior que a área útil do monitor")
    x, y = requested[:2]
    if position in {"right", "top_right", "bottom_right"}:
        x = right - width
    if position in {"bottom", "bottom_left", "bottom_right"}:
        y = bottom - height
    if position == "center":
        x, y = left + (right-left-width)//2, top + (bottom-top-height)//2
    return max(left, min(x, right-width)), max(top, min(y, bottom-height)), width, height
