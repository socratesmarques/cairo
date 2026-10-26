"""Coordinate verified placements for executable, app-ID and explicit window targets."""
import time

from cairo.integrations.window_geometry import POSITIONS, placement, reanchor
from cairo.integrations.window_native import Windows, WindowTarget

WINDOW_WAIT_SECONDS = 10
WINDOW_POLL_SECONDS = 0.15
POSITION_SETTLE_SECONDS = 1
POSITION_TOLERANCE = 12


def half_rect(work, side):
    if side not in {"left", "right"}:
        raise ValueError("Lado inválido")
    return placement(work, side, work)


def list_monitors():
    native = Windows()
    try:
        items = [{k: v for k, v in item.items() if k != "handle"} for item in native.monitors()]
        return {"monitors": items, "message": "\n".join(
            f"Monitor {item['id']}{' (principal)' if item['primary'] else ''}: área útil {item['work']}" for item in items)}
    finally:
        native.close()


def act_on_window(executable, label, action, **options):
    return act_on_target(WindowTarget(label=label, executable=str(executable)), action, **options)


def act_on_target(target, action, *, monitor=None, x=None, y=None, width=None, height=None, unit="pixels"):
    position = action.removeprefix("snap_")
    states = {"minimize": 6, "maximize": 3, "restore": 9, "focus": 9}
    if position not in POSITIONS and action not in states:
        raise ValueError("Ação de janela inválida")
    if monitor is not None and (type(monitor) is not int or not 1 <= monitor <= 32):
        raise ValueError("Informe um monitor entre 1 e 32")
    if position != "custom" and (any(value is not None for value in (x, y, width, height)) or unit != "pixels"):
        raise ValueError("Coordenadas e dimensões só se aplicam à posição custom")
    native = Windows()
    try:
        deadline = time.monotonic() + WINDOW_WAIT_SECONDS
        while True:
            hwnd = native.find(target)
            if hwnd or time.monotonic() >= deadline:
                break
            time.sleep(WINDOW_POLL_SECONDS)
        if not hwnd:
            raise ValueError("Não encontrei uma janela de " + target.label + ". Abra o aplicativo ou selecione seu ID em 'Liste as janelas'")
        if action in states:
            if monitor is not None:
                raise ValueError("Escolha uma posição para mover a janela entre monitores")
            native.show(hwnd, states[action])
            focused = native.focus(hwnd) if action == "focus" else None
            return {"requested": True, "window": f"win:{hwnd}:{native.pid(hwnd)}",
                "message": "Janela restaurada; o Windows não permitiu primeiro plano." if focused is False else "Solicitei a ação " + action + " na janela de " + target.label + "."}
        monitors = native.monitors()
        if monitor is not None:
            chosen = next((item for item in monitors if item["id"] == monitor), None)
        elif position == "custom" and unit == "pixels" and type(x) is int and type(y) is int:
            chosen = next((item for item in monitors if item["work"][0] <= x < item["work"][2] and item["work"][1] <= y < item["work"][3]), None)
        else:
            chosen = next((item for item in monitors if item["handle"] == native.monitor_for(hwnd)), None)
        if chosen is None:
            raise ValueError("O monitor ou as coordenadas não estão disponíveis. Use 'Liste os monitores'")
        was_maximized = native.maximized(hwnd)
        previous = native.bounds(hwnd)
        native.show(hwnd, 9)
        current = native.bounds(hwnd)
        try:
            rect = placement(chosen["work"], position, current, x=x, y=y, width=width, height=height, unit=unit)
            native.move(hwnd, rect)
            expected = (rect[0], rect[1], rect[0]+rect[2], rect[1]+rect[3])
            settle = time.monotonic() + POSITION_SETTLE_SECONDS
            actual = native.bounds(hwnd)
            while max(abs(a-b) for a,b in zip(actual, expected)) > POSITION_TOLERANCE and time.monotonic() < settle:
                time.sleep(0.05)
                actual = native.bounds(hwnd)
            exact = max(abs(a-b) for a,b in zip(actual, expected)) <= POSITION_TOLERANCE
            if not exact:
                adjusted = reanchor(chosen["work"], position, actual, rect)
                native.move(hwnd, adjusted)
                actual = native.bounds(hwnd)
                if max(abs(actual[0]-adjusted[0]), abs(actual[1]-adjusted[1])) > POSITION_TOLERANCE:
                    raise ValueError("O aplicativo não aceitou a posição solicitada")
            left, top, right, bottom = chosen["work"]
            if actual[0] < left-POSITION_TOLERANCE or actual[1] < top-POSITION_TOLERANCE or actual[2] > right+POSITION_TOLERANCE or actual[3] > bottom+POSITION_TOLERANCE:
                raise ValueError("O aplicativo não aceitou uma posição dentro da área útil do monitor")
        except (ValueError, OSError):
            try:
                native.move(hwnd, (previous[0], previous[1], previous[2]-previous[0], previous[3]-previous[1]))
                if was_maximized:
                    native.show(hwnd, 3)
            except OSError:
                pass
            raise
        return {"requested": True, "positioned": True, "exact": exact, "adjusted": not exact,
            "window": f"win:{hwnd}:{native.pid(hwnd)}", "monitor": chosen["id"], "bounds": list(actual),
            "message": "Posicionei " + target.label + ": " + POSITIONS[position] + ", monitor " + str(chosen["id"]) + "." + (" O aplicativo impôs restrições de tamanho; ajustei o encaixe e verifiquei a posição disponível." if not exact else "")}
    finally:
        native.close()
