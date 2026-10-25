"""Discover installed Windows launch targets without interpreting command strings."""

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

MAX_APPS = 2000
CACHE_SECONDS = 60
_lock = threading.Lock()
_cache = None
_updated = 0.0


@dataclass(frozen=True)
class InstalledApp:
    id: str
    label: str
    target: str
    kind: str


def normalize(value: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", value.casefold())
        if not unicodedata.combining(c)
    ).strip()


def launch_requested(message: str) -> bool:
    from cairo.orchestrator.file_commands import parse_file_command

    actions = parse_file_command(message)
    if actions and actions[0][0] == "open_file":
        return True
    # Quoted content and code are data, not independent opening instructions.
    text = normalize(re.sub(r'```[\s\S]*?```|`[^`]*`|"[^"]*"', " ", message))
    prefix = r"^(?:cairo[, ]+)?(?:por favor[, ]+)?"
    if re.match(prefix + r"(?:nao|explique|resuma|se eu|por que|porque)\b", text):
        return False
    verbs = r"(?:abra|abrir|abre|inicie|iniciar|execute|executar|open|launch|start)\b"
    return bool(
        re.match(
            prefix
            + r"(?:(?:eu )?quero que (?:voce )?|(?:voce )?(?:pode|poderia|consegue)\s+)?"
            + verbs,
            text,
        )
        or re.match(
            prefix + r"(?:nesse|neste|esse|este) (?:novo )?arquivo\s+" + verbs, text
        )
        or (
            re.match(
                prefix + r"(?:crie|criar|escreva|salve|edite|altere|copie|mova|leia)\b",
                text,
            )
            and re.search(r"\be\s+(?:(?:depois|entao)\s+)?" + verbs, text)
        )
    )


def record(label: str, target: str, kind: str) -> InstalledApp:
    identity = (
        "installed:"
        + hashlib.sha256((kind + "|" + target.casefold()).encode()).hexdigest()[:16]
    )
    return InstalledApp(identity, label, target, kind)


def start_apps() -> list[InstalledApp]:
    system = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    executable = system / "System32/WindowsPowerShell/v1.0/powershell.exe"
    script = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new(); Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
    try:
        result = subprocess.run(
            [str(executable), "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if result.returncode != 0 or len(result.stdout) > 2_000_000:
            raise OSError("Windows não conseguiu consultar o menu Iniciar")
        data = json.loads(result.stdout.decode("utf-8-sig"))
        if isinstance(data, dict):
            data = [data]
        if data is None:
            return []
        if not isinstance(data, list):
            raise ValueError
        apps = []
        for item in data[:MAX_APPS]:
            label, target = item.get("Name"), item.get("AppID")
            if (
                not isinstance(label, str)
                or not isinstance(target, str)
                or not target
                or any(ord(c) < 32 for c in target)
            ):
                continue
            if Path(target).is_absolute():
                if Path(target).suffix.lower() != ".exe" or not Path(target).is_file():
                    continue
                kind = "exe"
            else:
                kind = "appsfolder"
            apps.append(record(label, target, kind))
        return apps
    except (ValueError, TypeError, AttributeError):
        raise OSError("Windows retornou um catálogo de aplicativos inválido") from None
    except subprocess.TimeoutExpired:
        raise OSError("A descoberta de aplicativos excedeu 15 segundos") from None


def registry_apps() -> list[InstalledApp]:
    import winreg

    apps = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                root = winreg.OpenKey(
                    hive,
                    r"Software\Microsoft\Windows\CurrentVersion\App Paths",
                    0,
                    winreg.KEY_READ | view,
                )
            except OSError:
                continue
            with root:
                for i in range(min(winreg.QueryInfoKey(root)[0], MAX_APPS)):
                    try:
                        name = winreg.EnumKey(root, i)
                        with winreg.OpenKey(root, name) as entry:
                            value, _ = winreg.QueryValueEx(entry, "")
                        if not isinstance(value, str):
                            continue
                        path = Path(os.path.expandvars(value.strip().strip('"')))
                        if (
                            path.is_absolute()
                            and path.suffix.lower() == ".exe"
                            and path.is_file()
                        ):
                            apps.append(record(Path(name).stem, str(path), "exe"))
                    except OSError:
                        continue
    return apps


def inventory(*, refresh: bool = False) -> tuple[list[InstalledApp], list[str]]:
    global _cache, _updated
    if sys.platform != "win32":
        raise OSError("A descoberta de aplicativos requer Windows")
    with _lock:
        if (
            _cache is not None
            and not refresh
            and time.monotonic() - _updated < CACHE_SECONDS
        ):
            return list(_cache[0]), list(_cache[1])
        apps, errors = [], []
        for loader in (start_apps, registry_apps):
            try:
                apps.extend(loader())
            except OSError as exc:
                errors.append(str(exc))
        # Prefer menu names over executable stems for duplicate targets.
        unique = {}
        for app in apps:
            unique.setdefault((app.kind, app.target.casefold()), app)
        if not unique and errors:
            raise OSError("; ".join(errors))
        data = sorted(unique.values(), key=lambda app: normalize(app.label))[:MAX_APPS]
        _cache = (data, errors)
        _updated = time.monotonic()
        return list(data), list(errors)


def find_app(name: str) -> InstalledApp:
    if (
        not isinstance(name, str)
        or not 1 <= len(name) <= 2048
        or any(c in name for c in "\r\n;&|<>")
    ):
        raise ValueError(
            "Informe somente o nome do aplicativo ou o caminho de um executável"
        )
    path = Path(name)
    if path.is_absolute():
        if (
            name.startswith(("\\\\", "//"))
            or path.suffix.lower() != ".exe"
            or not path.is_file()
        ):
            raise ValueError(
                "Informe um executável .exe existente em uma unidade local"
            )
        return record(path.stem, str(path.resolve()), "exe")
    if any(c in name for c in '/\\"'):
        raise ValueError("Informe somente o nome do aplicativo")
    apps, _ = inventory()
    wanted = normalize(name)
    aliases = {
        "vs code": "visual studio code",
        "vscode": "visual studio code",
        "bloco de notas": "notepad",
        "windows terminal": "terminal",
    }
    wanted = aliases.get(wanted, wanted)
    exact = [
        app
        for app in apps
        if name == app.id
        or wanted in {normalize(app.label), normalize(Path(app.target).stem)}
    ]
    matches = exact or [app for app in apps if wanted in normalize(app.label)]
    # Several catalog entries may launch the same executable through a different ID.
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(
            "Encontrei mais de um aplicativo. Especifique um nome ou ID: "
            + ", ".join(app.label + " [" + app.id + "]" for app in matches[:6])
        )
    raise FileNotFoundError(
        "Aplicativo não encontrado. Liste os aplicativos instalados ou informe o caminho completo do .exe."
    )
