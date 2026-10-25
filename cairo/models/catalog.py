"""Bounded catalog and health for Ollama and OpenAI-compatible providers."""

import json
import socket
import urllib.error
import urllib.request

from cairo.models.errors import ModelError


def http_error(status):
    code = {
        401: "authentication",
        403: "authentication",
        404: "model_unavailable",
        429: "rate_limit",
    }.get(status, "http_error")
    return ModelError(
        f"Provedor retornou HTTP {status}; confira URL, modelo e autenticação.",
        code=code,
        status=status,
    )


def list_models(settings):
    from cairo.models import NoRedirect

    ollama = settings.provider == "ollama"
    request = urllib.request.Request(
        settings.base_url.rstrip("/") + ("/api/tags" if ollama else "/models")
    )
    if settings.api_key:
        request.add_header("Authorization", "Bearer " + settings.api_key)
    try:
        with urllib.request.build_opener(NoRedirect).open(
            request, timeout=min(settings.timeout, 8)
        ) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ModelError("Catálogo excede 2 MB", code="unexpected_response")
        data = json.loads(raw)
        entries = data["models" if ollama else "data"]
        if not isinstance(entries, list):
            raise ValueError
        names = []
        for item in entries[:1000]:
            name = item.get("name" if ollama else "id")
            if not isinstance(name, str) or not name:
                raise ValueError
            names.append(name[:300])
        return {
            "provider": settings.provider,
            "models": [{"id": name} for name in names],
            "selected_model": settings.model,
        }
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        raise http_error(status) from None
    except (TimeoutError, socket.timeout):
        raise ModelError(
            "Consulta de modelos excedeu o tempo limite.", code="timeout"
        ) from None
    except urllib.error.URLError as exc:
        code = (
            "timeout"
            if isinstance(exc.reason, (TimeoutError, socket.timeout))
            else "offline"
        )
        raise ModelError(
            "Não foi possível conectar ao provedor. Confira se está rodando e a URL configurada.",
            code=code,
        ) from None
    except OSError:
        raise ModelError(
            "Provedor indisponível durante a consulta de modelos.", code="offline"
        ) from None
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ModelError(
            "Catálogo de modelos em formato inesperado.", code="unexpected_response"
        ) from None


def health(settings):
    try:
        catalog = list_models(settings)
        selected = settings.model
        found = any(model["id"] == selected for model in catalog["models"])
        return {
            **catalog,
            "online": True,
            "status": "online",
            "ready": found,
            "model_found": found,
            "note": "Catálogo consultado; não executa inferência.",
        }
    except ModelError as exc:
        return {
            "provider": settings.provider,
            "online": False if exc.code in {"offline", "timeout"} else None,
            "status": exc.code,
            "ready": False,
            "selected_model": settings.model,
            "error": exc.as_dict(),
        }
