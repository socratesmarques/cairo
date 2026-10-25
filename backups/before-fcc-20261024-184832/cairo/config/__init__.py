"""Validated process configuration; environment overrides local .env values."""
from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit


def load_env(path: Path) -> None:
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if sep and key.strip().startswith("CAIRO_"):
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Settings:
    provider: str = "demo"
    model: str = "demo"
    base_url: str = "http://127.0.0.1:11434"
    api_key: str = ""
    workspace: Path = Path("workspace")
    data_dir: Path = Path("storage")
    allow_write: bool = False
    timeout: float = 90
    max_steps: int = 6
    allow_desktop: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        load_env(Path(".env"))
        provider = os.getenv("CAIRO_PROVIDER", "demo")
        if provider not in {"demo", "ollama", "openai-compatible"}:
            raise ValueError("CAIRO_PROVIDER must be demo, ollama or openai-compatible")
        model = os.getenv("CAIRO_MODEL", "").strip() or ("demo" if provider == "demo" else "")
        if not model:
            raise ValueError("Set CAIRO_MODEL to an installed or provider-supported model")
        base = (os.getenv("CAIRO_BASE_URL", "").strip() or ("https://api.openai.com/v1" if provider == "openai-compatible" else "http://127.0.0.1:11434")).rstrip("/")
        url = urlsplit(base)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("CAIRO_BASE_URL must be an HTTP(S) endpoint without credentials/query")
        if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Remote model endpoints require HTTPS")
        timeout = float(os.getenv("CAIRO_TIMEOUT", "90"))
        steps = int(os.getenv("CAIRO_MAX_STEPS", "6"))
        if not 1 <= timeout <= 600 or not 1 <= steps <= 20:
            raise ValueError("Timeout must be 1..600 and max steps 1..20")
        flag = os.getenv("CAIRO_ALLOW_WRITE", "false").lower()
        if flag not in {"true", "false"}:
            raise ValueError("CAIRO_ALLOW_WRITE must be true or false")
        desktop_flag = os.getenv("CAIRO_ALLOW_DESKTOP", "false").lower()
        if desktop_flag not in {"true", "false"}:
            raise ValueError("CAIRO_ALLOW_DESKTOP must be true or false")
        return cls(provider, model, base, os.getenv("CAIRO_API_KEY", ""), Path(os.getenv("CAIRO_WORKSPACE", "workspace")).resolve(), Path(os.getenv("CAIRO_DATA_DIR", "storage")).resolve(), flag == "true", timeout, steps, desktop_flag == "true")
