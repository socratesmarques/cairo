"""Reuse an existing local Cairo only when it owns the configured data directory."""

import json
import urllib.request
from pathlib import Path


def existing_instance(url: str, data_dir: Path) -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url + "/api/config", timeout=2) as response:
            data = json.loads(response.read(16384))
        return (
            isinstance(data, dict)
            and isinstance(data.get("data_dir"), str)
            and Path(data["data_dir"]).resolve() == data_dir.resolve()
        )
    except (OSError, ValueError, TypeError):
        return False


def open_interface(url: str):
    import webbrowser

    from cairo.integrations.desktop_control import resolve_app

    try:
        executable = resolve_app("chrome")
        webbrowser.BackgroundBrowser(str(executable)).open(url)
    except OSError:
        webbrowser.open(url)
