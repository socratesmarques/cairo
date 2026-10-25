"""Session-bound UI Automation controls owned by one COM worker thread."""

import itertools
import re
import time
import uuid

KEYS = {
    "enter": "{ENTER}",
    "tab": "{TAB}",
    "escape": "{ESC}",
    "ctrl+s": "^s",
    "ctrl+a": "^a",
    "ctrl+c": "^c",
    "ctrl+v": "^v",
    "ctrl+f": "^f",
    "ctrl+o": "^o",
    "ctrl+n": "^n",
    "ctrl+w": "^w",
    "ctrl+l": "^l",
    "alt+f4": "%{F4}",
    "f5": "{F5}",
    "up": "{UP}",
    "down": "{DOWN}",
    "left": "{LEFT}",
    "right": "{RIGHT}",
}
TTL = 120


class UIAutomation:
    def __init__(self):
        self.desktop = None
        self.controls = {}

    def _start(self):
        if self.desktop is None:
            import pythoncom

            pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
            from pywinauto import Desktop

            self.desktop = Desktop(backend="uia")

    @staticmethod
    def token(window):
        return f"win:{window.handle}:{window.process_id()}"

    def _window(self, value):
        match = re.fullmatch(r"win:(\d+):(\d+)", value)
        if not match:
            raise ValueError("Use o ID retornado por app_windows")
        wrapper = self.desktop.window(handle=int(match[1])).wrapper_object()
        if wrapper.process_id() != int(match[2]):
            raise ValueError(
                "A janela mudou ou está indisponível; liste as janelas novamente"
            )
        return wrapper

    def _control(self, value, session_id):
        item = self.controls.get(value)
        if item is None or item[0] != session_id or time.monotonic() - item[3] > TTL:
            raise ValueError(
                "Controle expirado ou de outra conversa; inspecione a janela novamente"
            )
        _, window_id, wrapper, _ = item
        window = self._window(window_id)
        if (
            wrapper.top_level_parent().handle != window.handle
            or not wrapper.is_visible()
            or not wrapper.is_enabled()
        ):
            raise ValueError(
                "O controle mudou ou está desativado; inspecione novamente"
            )
        return window, wrapper

    def _call(self, action, args, session_id):
        self._start()
        if action == "windows":
            windows = []
            for window in itertools.islice(self.desktop.windows(visible_only=True), 60):
                try:
                    title = window.window_text()[:200]
                    if title:
                        windows.append(
                            {
                                "id": self.token(window),
                                "title": title,
                                "pid": window.process_id(),
                            }
                        )
                except (OSError, RuntimeError):
                    continue
            return {
                "windows": windows,
                "message": "\n".join(
                    item["id"] + " — " + item["title"] for item in windows
                )
                or "Nenhuma janela disponível.",
            }
        if action == "inspect":
            window = self._window(args["window"])
            # Every new inspection replaces this chat's previous control handles.
            self.controls = {
                key: value
                for key, value in self.controls.items()
                if value[0] != session_id and time.monotonic() - value[3] <= TTL
            }
            result = []
            for wrapper in itertools.islice(window.iter_descendants(depth=5), 150):
                try:
                    if not wrapper.is_visible():
                        continue
                    info = wrapper.element_info
                    if bool(info.element.CurrentIsPassword):
                        name = "[campo protegido]"
                    else:
                        name = info.name[:200]
                    token = "ctl:" + uuid.uuid4().hex
                    self.controls[token] = (
                        session_id,
                        args["window"],
                        wrapper,
                        time.monotonic(),
                    )
                    result.append(
                        {
                            "id": token,
                            "name": name,
                            "type": info.control_type,
                            "automation_id": info.automation_id[:100],
                            "enabled": wrapper.is_enabled(),
                        }
                    )
                except (OSError, RuntimeError, AttributeError):
                    continue
            if len(self.controls) > 500:
                self.controls = dict(list(self.controls.items())[-500:])
            return {
                "window": args["window"],
                "controls": result,
                "message": "\n".join(
                    item["id"] + " — " + item["type"] + " — " + item["name"]
                    for item in result
                )
                or "O aplicativo não expõe controles acessíveis.",
            }
        if action in {"click", "fill"}:
            window, control = self._control(args["control"], session_id)
            window.set_focus()
            if action == "click":
                if hasattr(control, "click"):
                    control.click()
                else:
                    control.click_input()
            else:
                text = args["text"]
                if len(text) > 4000 or "\x00" in text:
                    raise ValueError("Texto limitado a 4 mil caracteres")
                if control.element_info.control_type not in {
                    "Edit",
                    "Document",
                    "ComboBox",
                }:
                    raise ValueError("Selecione um controle de edição de texto")
                if hasattr(control, "set_edit_text"):
                    control.set_edit_text(text)
                else:
                    control.click_input()
                    control.type_keys("^a", set_foreground=False)
                    escape = {c: "{" + c + "}" for c in "+^%~()"}
                    escape.update({"{": "{{}", "}": "{}}"})
                    literal = "".join(escape.get(c, c) for c in text)
                    control.type_keys(
                        literal,
                        with_spaces=True,
                        with_tabs=True,
                        with_newlines=True,
                        set_foreground=False,
                    )
            return {
                "requested": True,
                "message": "Clique enviado ao controle."
                if action == "click"
                else "Texto preenchido no controle solicitado.",
            }
        window = self._window(args["window"])
        if action == "window":
            operation = args["action"]
            if operation not in {"focus", "minimize", "maximize", "restore", "close"}:
                raise ValueError("Ação de janela inválida")
            if operation == "focus":
                window.set_focus()
            else:
                getattr(window, operation)()
            return {
                "requested": True,
                "message": "Solicitei a ação "
                + operation
                + " na janela. Diálogos de salvar podem exigir interação.",
            }
        if action == "keys":
            key = args["keys"].lower()
            if key not in KEYS:
                raise ValueError("Atalho não suportado")
            window.set_focus()
            window.type_keys(KEYS[key], set_foreground=False)
            return {
                "requested": True,
                "message": "Enviei o atalho " + key + " à janela solicitada.",
            }
        raise ValueError("Ação de controle inválida")


def main():
    import json
    import os
    import sys

    automation = UIAutomation()
    for line in sys.stdin:
        try:
            if len(line) > 20000:
                raise ValueError("Solicitação muito grande")
            request = json.loads(line)
            result = automation._call(
                request["action"], request["args"], request["session"]
            )
            response = {"result": result}
        except ImportError:
            response = {
                "error": 'Instale o suporte desktop: python -m pip install -e ".[desktop]"'
            }
        except (ValueError, KeyError) as exc:
            response = {"error": str(exc)[:500]}
        except Exception:
            response = {
                "error": "Windows não conseguiu acessar o controle. Inspecione novamente; aplicativos elevados, fechados ou sem acessibilidade podem impedir a operação."
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
        sys.stdout.flush()
    # COM wrappers belong exclusively to this process. OS teardown avoids
    # releasing cached UIA pointers after their COM apartment has disappeared.
    os._exit(0)


if __name__ == "__main__":
    main()
