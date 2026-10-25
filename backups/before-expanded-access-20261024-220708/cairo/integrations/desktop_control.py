"""Explicit desktop capabilities. No command strings or model-chosen executables."""

import ctypes
import json
import os
import subprocess
import sys
import threading
from ctypes import wintypes
from pathlib import Path
from urllib.parse import urlencode


def catalog() -> dict:
    return json.loads(
        (Path(__file__).parents[1] / "config" / "desktop.json").read_text(
            encoding="utf-8"
        )
    )


def resolve_app(app: str) -> Path:
    apps = catalog()["apps"]
    if app not in apps:
        raise ValueError("Aplicativo não cadastrado")
    if sys.platform != "win32":
        raise OSError("O controle de aplicativos desta versão requer Windows")
    spec = apps[app]
    for template in spec["paths"]:
        candidate = Path(os.path.expandvars(template))
        if (
            candidate.is_absolute()
            and candidate.is_file()
            and candidate.suffix.lower() == ".exe"
        ):
            return candidate.resolve()
    raise FileNotFoundError(
        f"{spec['label']} não foi encontrado. Confira os caminhos em cairo/config/desktop.json"
    )


class DesktopController:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.lock = threading.Lock()
        self.children: list[subprocess.Popen] = []

    def require_enabled(self):
        if not self.enabled:
            raise PermissionError(
                "Controle de aplicativos desativado. Configure CAIRO_ALLOW_DESKTOP=true e reinicie Cairo"
            )

    def list_apps(self) -> dict:
        self.require_enabled()
        result = []
        for name, spec in catalog()["apps"].items():
            try:
                resolve_app(name)
                available = True
            except OSError:
                available = False
            result.append({"id": name, "label": spec["label"], "available": available})
        return {"apps": result, "sites": catalog()["sites"], "enabled": True}

    def _launch(self, app: str, arguments: list[str]) -> dict:
        executable = resolve_app(app)
        with self.lock:
            self.children = [child for child in self.children if child.poll() is None]
            child = subprocess.Popen(
                [str(executable), *arguments],
                shell=False,
                cwd=str(executable.parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            self.children.append(child)
        label = catalog()["apps"][app]["label"]
        return {
            "requested": True,
            "app": app,
            "message": f"Solicitei a abertura de {label}.",
            "pid": child.pid,
        }

    def open_app(self, app: str) -> dict:
        self.require_enabled()
        return self._launch(app, [])

    def open_folder(self, folder: str, path: str = ".") -> dict:
        from cairo.integrations.folders import FOLDERS, folder_path

        self.require_enabled()
        target = folder_path(folder, path)
        if not target.is_dir():
            raise ValueError("Escolha uma pasta para abrir")
        result = self._launch("explorer", [str(target)])
        result["message"] = (
            "Solicitei a abertura de "
            + FOLDERS[folder][1]
            + ("" if path == "." else "/" + path)
            + "."
        )
        return result

    def media_action(self, action: str) -> dict:
        from cairo.integrations.media import media_action

        self.require_enabled()
        return media_action(action)

    def open_url(self, url: str, browser: str = "chrome") -> dict:
        from cairo.integrations.web_reader import public_address, validate_url

        self.require_enabled()
        _, host = validate_url(url)
        public_address(host)
        if browser not in {"chrome", "edge"}:
            raise ValueError("Navegador não cadastrado")
        result = self._launch(browser, [url])
        result["message"] = "Solicitei a abertura da página no navegador."
        return result

    def open_site(self, site: str, browser: str = "chrome") -> dict:
        self.require_enabled()
        sites = catalog()["sites"]
        if site not in sites or browser not in {"chrome", "edge"}:
            raise ValueError("Site ou navegador não cadastrado")
        result = self._launch(browser, [sites[site]["url"]])
        result["message"] = (
            f"Solicitei a abertura de {sites[site]['label']} no {catalog()['apps'][browser]['label']}."
        )
        return result

    def search_music(self, query: str, browser: str = "chrome") -> dict:
        self.require_enabled()
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 500:
            raise ValueError("A pesquisa deve conter entre 1 e 500 caracteres")
        if browser not in {"chrome", "edge"}:
            raise ValueError("Navegador não cadastrado")
        url = (
            catalog()["sites"]["youtube_music"]["url"]
            + "/search?"
            + urlencode({"q": query.strip()})
        )
        result = self._launch(browser, [url])
        result["message"] = (
            f"Solicitei a pesquisa de ‘{query.strip()}’ no YouTube Music. Escolha uma faixa na página para reproduzir."
        )
        return result

    def search_web(self, query: str, browser: str = "chrome") -> dict:
        self.require_enabled()
        if not 1 <= len(query.strip()) <= 500 or browser not in {"chrome", "edge"}:
            raise ValueError("Pesquisa ou navegador inválido")
        url = "https://www.google.com/search?" + urlencode({"q": query.strip()})
        result = self._launch(browser, [url])
        result["message"] = (
            "Solicitei a busca no Google: "
            + query.strip()
            + ". Os resultados estão no navegador; não foram lidos por Cairo."
        )
        return result

    def window_action(self, app: str, action: str) -> dict:
        self.require_enabled()
        actions = {"minimize": 6, "maximize": 3, "restore": 9, "focus": 9}
        if action not in actions:
            raise ValueError("Ação de janela inválida")
        executable = resolve_app(app)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )
        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindowAsync.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        matches = []
        expected = str(executable).casefold()

        @callback_type
        def visit(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            handle = kernel32.OpenProcess(0x1000, False, pid.value)
            if handle:
                try:
                    size = wintypes.DWORD(32768)
                    buffer = ctypes.create_unicode_buffer(size.value)
                    if (
                        kernel32.QueryFullProcessImageNameW(
                            handle, 0, buffer, ctypes.byref(size)
                        )
                        and buffer.value.casefold() == expected
                    ):
                        matches.append(hwnd)
                finally:
                    kernel32.CloseHandle(handle)
            return True

        if not user32.EnumWindows(visit, 0):
            raise OSError("Não foi possível consultar as janelas do Windows")
        if not matches:
            raise ValueError("Nenhuma janela compatível deste aplicativo está aberta")
        hwnd = matches[0]
        if not user32.ShowWindowAsync(hwnd, actions[action]):
            raise OSError("Windows recusou a alteração da janela")
        if action == "focus" and not user32.SetForegroundWindow(hwnd):
            return {
                "requested": True,
                "message": "Janela restaurada; o Windows não permitiu colocá-la em primeiro plano. Use a barra de tarefas.",
            }
        return {
            "requested": True,
            "message": f"Solicitei a ação {action} na janela de {catalog()['apps'][app]['label']}.",
        }
