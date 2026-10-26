"""Explicit desktop capabilities. No command strings or model-chosen executables."""

import json
import os
import re
import subprocess
import sys
import threading
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
    def __init__(self, enabled: bool = False, discover_apps: bool = False):
        self.enabled = enabled
        self.discover_apps = discover_apps
        self.lock = threading.Lock()
        self.children: list[subprocess.Popen] = []

    def require_enabled(self):
        if not self.enabled:
            raise PermissionError(
                "Controle de aplicativos desativado. Configure CAIRO_ALLOW_DESKTOP=true e reinicie Cairo"
            )

    def list_apps(self, query: str = "") -> dict:
        self.require_enabled()
        result = []
        for name, spec in catalog()["apps"].items():
            try:
                resolve_app(name)
                available = True
            except OSError:
                available = False
            result.append({"id": name, "label": spec["label"], "available": available})
        warnings = []
        if self.discover_apps:
            from cairo.integrations.app_discovery import inventory, normalize

            apps, warnings = inventory()
            known = {normalize(item["label"]) for item in result}
            result.extend(
                {
                    "id": app.id,
                    "label": app.label,
                    "available": True,
                    "source": app.kind,
                }
                for app in apps
                if normalize(app.label) not in known
            )
        if query:
            result = [
                item
                for item in result
                if query.casefold() in item["label"].casefold() or query == item["id"]
            ]
        total = len(result)
        return {
            "apps": result[:200],
            "sites": catalog()["sites"],
            "enabled": True,
            "total": total,
            "truncated": total > 200,
            "warnings": warnings,
        }

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
        if app in catalog()["apps"]:
            try:
                return self._launch(app, [])
            except FileNotFoundError:
                if not self.discover_apps:
                    raise
        if not self.discover_apps:
            raise ValueError(
                "Aplicativo não cadastrado; descoberta automática desativada"
            )
        from cairo.integrations.app_discovery import find_app

        installed = find_app(app)
        if installed.kind == "appsfolder":
            result = self._launch("explorer", ["shell:AppsFolder\\" + installed.target])
        else:
            executable = Path(installed.target)
            with self.lock:
                self.children = [
                    child for child in self.children if child.poll() is None
                ]
                child = subprocess.Popen(
                    [str(executable)],
                    shell=False,
                    cwd=str(executable.parent),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
                self.children.append(child)
            result = {"requested": True, "pid": child.pid}
        result.update(
            app=installed.id, message="Solicitei a abertura de " + installed.label + "."
        )
        return result

    def open_file(self, path: str, app: str = "") -> dict:
        self.require_enabled()
        if sys.platform != "win32":
            raise OSError("Abertura no aplicativo padrão requer Windows")
        target = Path(path)
        if not target.is_absolute():
            raise ValueError("Informe o caminho completo do arquivo")
        if not target.exists():
            raise FileNotFoundError("Arquivo não encontrado: " + str(target))
        if not target.is_file():
            raise ValueError("O caminho é uma pasta; use abrir pasta")
        if app:
            if not self.discover_apps:
                raise PermissionError(
                    "Ative CAIRO_DISCOVER_APPS para escolher um aplicativo instalado"
                )
            from cairo.integrations.app_discovery import find_app

            installed = find_app(app)
            if installed.kind != "exe":
                from cairo.integrations.app_discovery import normalize

                configured = next(
                    (
                        key
                        for key, spec in catalog()["apps"].items()
                        if installed.target in spec.get("app_ids", [])
                        or normalize(installed.label) == normalize(spec["label"])
                    ),
                    None,
                )
                if configured is None:
                    raise ValueError(
                        "Este aplicativo não possui executável configurado para abrir arquivos; use o aplicativo padrão"
                    )
                executable = resolve_app(configured)
            else:
                executable = Path(installed.target)
            with self.lock:
                self.children = [
                    child for child in self.children if child.poll() is None
                ]
                child = subprocess.Popen(
                    [str(executable), str(target)],
                    shell=False,
                    cwd=str(executable.parent),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
                self.children.append(child)
            return {
                "requested": True,
                "path": str(target),
                "app": installed.id,
                "pid": child.pid,
                "message": "Solicitei a abertura de "
                + str(target)
                + " em "
                + installed.label
                + ".",
            }
        try:
            # ShellExecute receives a literal filename, never a command string.
            os.startfile(str(target), "open")
        except OSError as exc:
            code = getattr(exc, "winerror", None)
            if code in {31, 1155}:
                raise OSError(
                    "Não há aplicativo padrão associado a este tipo de arquivo. Escolha um em Configurações > Aplicativos > Aplicativos padrão."
                ) from None
            if code == 5:
                raise PermissionError(
                    "O Windows recusou acesso ao arquivo. Verifique suas permissões e se o arquivo está bloqueado nas Propriedades."
                ) from None
            if code in {1260, 577, 225, 226}:
                raise PermissionError(
                    "Uma política ou proteção do Windows bloqueou a abertura deste arquivo. Cairo não altera essas proteções automaticamente."
                ) from None
            if code == 1223:
                raise OSError("A abertura foi cancelada no Windows.") from None
            if code in {2, 3}:
                raise FileNotFoundError(
                    "O arquivo ou o aplicativo associado não está mais disponível."
                ) from None
            raise OSError(
                f"O Windows não conseguiu abrir o arquivo (código {code or 'indisponível'}). Confira o aplicativo padrão e as permissões."
            ) from None
        return {
            "requested": True,
            "path": str(target),
            "message": "Solicitei a abertura de "
            + str(target)
            + " no aplicativo padrão do Windows.",
        }

    def open_directory(self, path: str) -> dict:
        self.require_enabled()
        target = Path(path)
        if not target.is_absolute() or not target.is_dir():
            raise ValueError("Escolha uma pasta absoluta existente")
        result = self._launch("explorer", [str(target)])
        result["message"] = "Solicitei a abertura da pasta " + str(target) + "."
        return result

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

    def window_action(self, app: str, action: str, **options) -> dict:
        self.require_enabled()
        from cairo.integrations.window_layout import act_on_target, act_on_window
        from cairo.integrations.window_native import WindowTarget

        token = re.fullmatch(r"win:(\d+):(\d+)", app)
        if token:
            return act_on_target(WindowTarget(label="janela selecionada", hwnd=int(token[1]), pid=int(token[2])), action, **options)
        if app in catalog()["apps"]:
            try:
                executable = resolve_app(app)
            except FileNotFoundError:
                if not self.discover_apps:
                    raise
            else:
                if self.discover_apps:
                    from dataclasses import replace
                    from cairo.integrations.app_discovery import find_app, window_identity
                    try:
                        target = window_identity(find_app(catalog()["apps"][app]["label"]))
                    except (OSError, ValueError):
                        pass
                    else:
                        target = replace(target, executable=target.executable or str(executable), label=catalog()["apps"][app]["label"])
                        return act_on_target(target, action, **options)
                return act_on_window(executable, catalog()["apps"][app]["label"], action, **options)
        if not self.discover_apps:
            raise ValueError("Aplicativo não cadastrado; descoberta automática desativada")
        from cairo.integrations.app_discovery import find_app, window_identity

        return act_on_target(window_identity(find_app(app)), action, **options)

    def desktop_monitors(self) -> dict:
        self.require_enabled()
        from cairo.integrations.window_layout import list_monitors

        return list_monitors()
