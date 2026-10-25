"""FCC HTTP adapter. No FCC package, subprocess, provider credentials or routing."""

import http.client
import json
import urllib.error
import urllib.request

from cairo.config import Settings, validate_fcc_url
from cairo.models import NoRedirect
from cairo.models.errors import ModelError
from cairo.models.fcc_protocol import decode, encode

MAX_RESPONSE_BYTES = 2_000_000
HEALTH_TIMEOUT = 5


class FCCModel:
    def __init__(self, settings: Settings):
        validate_fcc_url(settings.base_url)
        self.settings = settings

    def _request(
        self, path: str, body: dict | None = None, *, timeout: float | None = None
    ) -> dict:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if self.settings.api_key:
            headers["Authorization"] = "Bearer " + self.settings.api_key
        try:
            request = urllib.request.Request(
                self.settings.base_url.rstrip("/") + path,
                data=None
                if body is None
                else json.dumps(body, allow_nan=False).encode(),
                headers=headers,
            )
            # Loopback traffic must not send the proxy token to an OS-configured HTTP proxy.
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}), NoRedirect
            )
            with opener.open(
                request, timeout=timeout or self.settings.timeout
            ) as response:
                if (
                    response.status != 200
                    or response.headers.get_content_type() != "application/json"
                ):
                    raise ModelError(
                        "FCC retornou HTTP ou Content-Type inválido.",
                        code="invalid_http",
                        status=response.status,
                    )
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ModelError(
                        "Resposta FCC excede 2 MB.", code="unexpected_response"
                    )
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError
            return data
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            if status in {401, 403}:
                code, message = (
                    "authentication",
                    "FCC recusou a autenticação; confira FCC_AUTH_TOKEN.",
                )
            elif status == 404 and body is not None:
                code, message = (
                    "model_unavailable",
                    "FCC não encontrou o modelo ou a rota de mensagens. Confira modelo e versão.",
                )
            else:
                code, message = (
                    "http_error",
                    f"FCC retornou HTTP {status}; confira o serviço e sua configuração.",
                )
            raise ModelError(message, code=code, status=status) from None
        except TimeoutError:
            raise ModelError(
                "FCC excedeu o tempo limite da chamada.", code="timeout"
            ) from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise ModelError(
                    "FCC excedeu o tempo limite da chamada.", code="timeout"
                ) from None
            raise ModelError(
                "FCC está offline ou inacessível; inicie fcc-server e confira FCC_BASE_URL.",
                code="offline",
            ) from None
        except http.client.HTTPException:
            raise ModelError(
                "FCC retornou uma resposta HTTP inválida ou incompleta.",
                code="invalid_http",
            ) from None
        except OSError:
            raise ModelError(
                "A conexão com FCC foi interrompida.", code="network"
            ) from None
        except (ValueError, TypeError, UnicodeError):
            raise ModelError(
                "FCC retornou JSON inválido ou recebeu dados incompatíveis.",
                code="unexpected_response",
            ) from None

    def list_models(self, *, timeout: float | None = None) -> dict:
        data = self._request("/v1/models?view=messages", timeout=timeout)
        try:
            items = data["data"]
            if not isinstance(items, list) or data.get("has_more", False):
                raise ValueError
            models = []
            for item in items:
                if not isinstance(item["id"], str) or not item["id"].strip():
                    raise ValueError
                ref = item.get("provider_model_ref")
                if ref is not None and not isinstance(ref, str):
                    raise ValueError
                models.append({"id": item["id"], "provider_model_ref": ref})
            default = data.get("default_model_id")
            if default is not None and not isinstance(default, str):
                raise ValueError
            if not default:
                default = self._request("/", timeout=timeout).get("model")
                if not isinstance(default, str) or not default:
                    raise ValueError
            return {"models": models, "default_model": default}
        except (ValueError, TypeError, KeyError):
            raise ModelError(
                "FCC retornou um catálogo inesperado ou incompleto.",
                code="unexpected_response",
            ) from None

    def _selected(self, catalog: dict) -> str:
        wanted = self.settings.model or catalog["default_model"]
        for item in catalog["models"]:
            if wanted in {item["id"], item["provider_model_ref"]}:
                return item["id"]
        raise ModelError(
            "Modelo selecionado indisponível no catálogo FCC; confira FCC_MODEL ou o modelo padrão no Admin.",
            code="model_unavailable",
        )

    def complete(self, messages: list[dict], tools: list[dict]):
        body = encode(messages, tools)
        body.update(
            model=self._selected(self.list_models()),
            max_tokens=self.settings.max_output_tokens,
        )
        return decode(self._request("/v1/messages", body))

    def health(self) -> dict:
        result = {
            "provider": "fcc",
            "url": self.settings.base_url,
            "status": "unknown",
            "online": None,
            "authentication": "not_checked",
            "token_configured": bool(self.settings.api_key),
            "models": [],
            "selected_model": self.settings.model or None,
            "ready": False,
        }
        try:
            catalog = self.list_models(
                timeout=min(HEALTH_TIMEOUT, self.settings.timeout)
            )
            result.update(
                status="online",
                online=True,
                authentication="request_accepted"
                if self.settings.api_key
                else "not_required",
                models=catalog["models"],
                default_model=catalog["default_model"],
            )
            result["selected_model"] = self._selected(catalog)
            result["ready"] = True
        except ModelError as exc:
            if exc.code == "offline":
                result.update(status="offline", online=False)
            elif exc.code in {"timeout", "network"}:
                result.update(status="unreachable", online=None)
            else:
                result.update(status="online", online=True)
            if exc.code == "authentication":
                result["authentication"] = "rejected"
            result["error"] = exc.as_dict()
        result["models_found"] = len(result["models"])
        return result
