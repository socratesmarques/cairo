"""Local diagnostics without prompts, credentials or automatic repair actions."""

import hashlib
import importlib.util
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from cairo import __version__


def source_revision(root: Path) -> str:
    digest = hashlib.sha256()
    total = 0
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".js", ".html", ".css", ".json"}
        and "__pycache__" not in path.parts
    )
    if len(paths) > 512:
        raise OSError("Fontes excedem o limite de diagnóstico")
    for path in paths:
        data = path.read_bytes()
        total += len(data)
        if total > 12 * 1024 * 1024:
            raise OSError("Fontes excedem 12 MiB")
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(hashlib.sha256(data).digest())
    env = root.parent / ".env"
    if env.is_file():
        metadata = env.stat()
        digest.update(f"env:{metadata.st_mtime_ns}:{metadata.st_size}".encode())
    return digest.hexdigest()[:16]


def error_category(message: str) -> str:
    text = message.casefold()
    for needle, category in [
        ("rodadas", "step_limit"),
        ("aplicativo", "application"),
        ("resposta vazia", "model_response"),
        ("formato", "model_response"),
        ("pasta", "file_path"),
        ("arquivo", "file_path"),
        ("autentica", "authentication"),
        ("credencia", "authentication"),
        ("prazo", "connection"),
        ("timeout", "connection"),
        ("conectar", "connection"),
    ]:
        if needle in text:
            return category
    return "other"


class Diagnostics:
    def __init__(self, app, source_root: Path | None = None):
        self.app = app
        self.root = source_root or Path(__file__).resolve().parents[1]
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.loaded_revision = source_revision(self.root)

    def snapshot(self):
        s = self.app.settings
        checks = []

        def add(label, ready, detail):
            checks.append(
                {
                    "label": label,
                    "status": "ok" if ready else "attention",
                    "detail": detail,
                }
            )

        add(
            "Arquivos fora da workspace",
            s.full_file_access and s.allow_file_operations,
            "Acesso absoluto e criação habilitados"
            if s.full_file_access and s.allow_file_operations
            else "Confira CAIRO_FULL_FILE_ACCESS e CAIRO_ALLOW_FILE_OPERATIONS",
        )
        add(
            "Aplicativos e arquivos",
            s.allow_desktop and s.discover_apps,
            "Abertura habilitada"
            if s.allow_desktop and s.discover_apps
            else "Confira CAIRO_ALLOW_DESKTOP e CAIRO_DISCOVER_APPS",
        )
        for flag, module, label in [
            (s.allow_app_control, "pywinauto", "Controle de janelas"),
            (s.browser_automation, "playwright", "Navegador com JavaScript"),
        ]:
            installed = importlib.util.find_spec(module) is not None
            add(
                label,
                flag and installed,
                "Habilitado; dependência instalada (não verifica cada aplicativo/site)"
                if flag and installed
                else "Desativado ou dependência opcional ausente",
            )
        add(
            "Comandos de terminal",
            s.allow_commands,
            f"Limite: {s.command_timeout} segundos"
            if s.allow_commands
            else "CAIRO_ALLOW_COMMANDS desativado",
        )
        add(
            "Limite de etapas",
            s.max_steps >= 30,
            f"{s.max_steps} etapas por agente; configurável em CAIRO_MAX_STEPS",
        )
        current = source_revision(self.root)
        counts = Counter()
        for item in self.app.memory.failure_counts():
            counts[error_category(item["error"])] += item["count"]
        labels = {
            "step_limit": "Limite de etapas",
            "application": "Aplicativos",
            "model_response": "Resposta do modelo",
            "file_path": "Caminhos e arquivos",
            "authentication": "Autenticação",
            "connection": "Conexão",
            "other": "Outros",
        }
        return {
            "version": __version__,
            "pid": os.getpid(),
            "started_at": self.started_at,
            "loaded_revision": self.loaded_revision,
            "disk_revision": current,
            "restart_required": current != self.loaded_revision,
            "provider": s.provider,
            "selected_model": s.model,
            "max_steps": s.max_steps,
            "checks": checks,
            "historical_errors": [
                {"category": key, "label": labels[key], "count": value}
                for key, value in counts.most_common()
            ],
            "history_note": "Erros históricos; cancelamentos manuais não entram nesta contagem. Não significam bloqueio atual.",
        }
