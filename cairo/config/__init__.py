"""Validated process configuration; environment overrides local .env values."""

import json
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
    max_steps: int = 30
    allow_desktop: bool = False
    max_output_tokens: int = 8192
    weather_city: str = ""
    allow_personal_files: bool = False
    allow_network: bool = True
    allow_file_operations: bool = False
    file_roots: dict[str, str] = field(default_factory=dict)
    browser_javascript: bool = False
    browser_channel: str = "chrome"
    full_file_access: bool = False
    discover_apps: bool = False
    google_search_read: bool = False
    allow_commands: bool = False
    command_timeout: float = 30
    allow_app_control: bool = False
    browser_automation: bool = False

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
        steps = int(os.getenv("CAIRO_MAX_STEPS", "30"))
        output_tokens = int(os.getenv("CAIRO_MAX_OUTPUT_TOKENS", "8192"))
        if not 1 <= output_tokens <= 131072:
            raise ValueError("CAIRO_MAX_OUTPUT_TOKENS must be 1..131072")
        key = os.getenv("FCC_AUTH_TOKEN" if provider == "fcc" else "CAIRO_API_KEY", "")
        if any(ord(c) < 32 or ord(c) > 126 for c in key):
            raise ValueError(
                "Provider token must contain printable ASCII without line breaks"
            )
        if not 1 <= timeout <= 600 or not 1 <= steps <= 100:
            raise ValueError("Timeout must be 1..600 and max steps 1..100")
        flag = os.getenv("CAIRO_ALLOW_WRITE", "false").lower()
        if flag not in {"true", "false"}:
            raise ValueError("CAIRO_ALLOW_WRITE must be true or false")
        desktop_flag = os.getenv("CAIRO_ALLOW_DESKTOP", "false").lower()
        if desktop_flag not in {"true", "false"}:
            raise ValueError("CAIRO_ALLOW_DESKTOP must be true or false")
        personal = os.getenv("CAIRO_ALLOW_PERSONAL_FILES", "false").lower()
        network = os.getenv("CAIRO_ALLOW_NETWORK", "true").lower()
        if personal not in {"true", "false"} or network not in {"true", "false"}:
            raise ValueError(
                "CAIRO_ALLOW_PERSONAL_FILES and CAIRO_ALLOW_NETWORK must be true or false"
            )
        city = os.getenv("CAIRO_WEATHER_CITY", "").strip()
        if len(city) > 120 or any(ord(c) < 32 for c in city):
            raise ValueError(
                "CAIRO_WEATHER_CITY must be a city name up to 120 characters"
            )
        operations = os.getenv("CAIRO_ALLOW_FILE_OPERATIONS", "false").lower()
        javascript = os.getenv("CAIRO_BROWSER_JAVASCRIPT", "false").lower()
        channel = os.getenv("CAIRO_BROWSER_CHANNEL", "chrome").lower()
        full_files = os.getenv("CAIRO_FULL_FILE_ACCESS", "false").lower()
        discover = os.getenv("CAIRO_DISCOVER_APPS", "false").lower()
        google_read = os.getenv("CAIRO_GOOGLE_SEARCH_READ", "false").lower()
        commands = os.getenv("CAIRO_ALLOW_COMMANDS", "false").lower()
        app_control = os.getenv("CAIRO_ALLOW_APP_CONTROL", "false").lower()
        automation = os.getenv("CAIRO_BROWSER_AUTOMATION", "false").lower()
        command_timeout = float(os.getenv("CAIRO_COMMAND_TIMEOUT", "30"))
        if (
            any(
                value not in {"true", "false"}
                for value in (commands, app_control, automation)
            )
            or not 1 <= command_timeout <= 300
        ):
            raise ValueError(
                "Invalid control flags or command timeout (1..300 seconds)"
            )
        if any(
            flag not in {"true", "false"}
            for flag in (full_files, discover, google_read)
        ):
            raise ValueError(
                "Full file access, app discovery and Google reader flags must be true or false"
            )
        if (
            operations not in {"true", "false"}
            or javascript not in {"true", "false"}
            or channel not in {"chrome", "msedge", "chromium"}
        ):
            raise ValueError(
                "Invalid file operations flag, JavaScript flag or browser channel"
            )
        try:
            roots = json.loads(os.getenv("CAIRO_FILE_ROOTS", "{}"))
            if (
                not isinstance(roots, dict)
                or len(roots) > 20
                or any(
                    not isinstance(k, str) or not isinstance(v, str)
                    for k, v in roots.items()
                )
            ):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError(
                "CAIRO_FILE_ROOTS must be a JSON object mapping aliases to absolute directories"
            ) from None
        from cairo.sandbox.file_roots import FileRoots

        FileRoots(
            Path(os.getenv("CAIRO_WORKSPACE", "workspace")),
            Path(os.getenv("CAIRO_DATA_DIR", "storage")),
            roots,
        )
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
            city,
            personal == "true",
            network == "true",
            operations == "true",
            roots,
            javascript == "true",
            channel,
            full_files == "true",
            discover == "true",
            google_read == "true",
            commands == "true",
            command_timeout,
            app_control == "true",
            automation == "true",
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
