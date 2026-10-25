"""Validated process configuration; environment overrides local .env values."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


def load_env(path: Path) -> None:
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if sep and (
                key.strip().startswith("CAIRO_")
                or key.strip() in {"FCC_BASE_URL", "FCC_AUTH_TOKEN", "FCC_MODEL"}
            ):
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Settings:
    provider: str = "demo"
    model: str = "demo"
    base_url: str = "http://127.0.0.1:11434"
    api_key: str = field(default="", repr=False)
    workspace: Path = Path("workspace")
    data_dir: Path = Path("storage")
    allow_write: bool = False
    timeout: float = 90
    max_steps: int = 6
    allow_desktop: bool = False
    max_output_tokens: int = 8192

    @classmethod
    def from_env(cls) -> "Settings":
        load_env(Path(".env"))
        provider = os.getenv("CAIRO_PROVIDER", "demo")
        if provider not in {"demo", "ollama", "openai-compatible", "fcc"}:
            raise ValueError(
                "CAIRO_PROVIDER must be demo, ollama, openai-compatible or fcc"
            )
        model = os.getenv(
            "FCC_MODEL" if provider == "fcc" else "CAIRO_MODEL", ""
        ).strip() or ("demo" if provider == "demo" else "")
        if not model and provider != "fcc":
            raise ValueError(
                "Set CAIRO_MODEL to an installed or provider-supported model"
            )
        base = (
            os.getenv("CAIRO_BASE_URL", "").strip()
            or (
                "https://api.openai.com/v1"
                if provider == "openai-compatible"
                else "http://127.0.0.1:11434"
            )
        ).rstrip("/")
        if provider == "fcc":
            base = (
                os.getenv("FCC_BASE_URL", "").strip() or "http://127.0.0.1:8082"
            ).rstrip("/")
            validate_fcc_url(base)
        url = urlsplit(base)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "CAIRO_BASE_URL must be an HTTP(S) endpoint without credentials/query"
            )
        if url.scheme == "http" and url.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError("Remote model endpoints require HTTPS")
        timeout = float(os.getenv("CAIRO_TIMEOUT", "90"))
        steps = int(os.getenv("CAIRO_MAX_STEPS", "6"))
        output_tokens = int(os.getenv("CAIRO_MAX_OUTPUT_TOKENS", "8192"))
        if not 1 <= output_tokens <= 131072:
            raise ValueError("CAIRO_MAX_OUTPUT_TOKENS must be 1..131072")
        key = os.getenv("FCC_AUTH_TOKEN" if provider == "fcc" else "CAIRO_API_KEY", "")
        if any(ord(c) < 32 or ord(c) > 126 for c in key):
            raise ValueError(
                "Provider token must contain printable ASCII without line breaks"
            )
        if not 1 <= timeout <= 600 or not 1 <= steps <= 20:
            raise ValueError("Timeout must be 1..600 and max steps 1..20")
        flag = os.getenv("CAIRO_ALLOW_WRITE", "false").lower()
        if flag not in {"true", "false"}:
            raise ValueError("CAIRO_ALLOW_WRITE must be true or false")
        desktop_flag = os.getenv("CAIRO_ALLOW_DESKTOP", "false").lower()
        if desktop_flag not in {"true", "false"}:
            raise ValueError("CAIRO_ALLOW_DESKTOP must be true or false")
        return cls(
            provider,
            model,
            base,
            key,
            Path(os.getenv("CAIRO_WORKSPACE", "workspace")).resolve(),
            Path(os.getenv("CAIRO_DATA_DIR", "storage")).resolve(),
            flag == "true",
            timeout,
            steps,
            desktop_flag == "true",
            output_tokens,
        )


def validate_fcc_url(base: str) -> None:
    try:
        url = urlsplit(base)
        port = url.port
        valid = (
            url.scheme in {"http", "https"}
            and url.hostname in {"127.0.0.1", "localhost", "::1"}
            and not (url.username or url.password or url.query or url.fragment)
            and url.path in {"", "/"}
            and (port is None or 1 <= port <= 65535)
        )
        if not valid or any(ord(c) <= 32 for c in base):
            raise ValueError
    except ValueError:
        raise ValueError(
            "FCC_BASE_URL must be a local HTTP(S) origin, e.g. http://127.0.0.1:8082, without /v1, credentials or query"
        ) from None
