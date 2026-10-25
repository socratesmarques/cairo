"""Provider boundary shared by all agents."""

import copy
import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from cairo.config import Settings
from cairo.models.errors import ModelError


@dataclass
class Reply:
    content: str = ""
    calls: list[dict] = field(default_factory=list)
    provider_state: dict = field(default_factory=dict, repr=False)

    def message(self) -> dict:
        result = {"role": "assistant", "content": self.content}
        if self.calls:
            result["tool_calls"] = self.calls
        if self.provider_state:
            result["_provider_state"] = copy.deepcopy(self.provider_state)
        return result


class Model(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> Reply: ...


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HTTPModel:
    def __init__(self, settings: Settings):
        self.settings = settings

    def list_models(self):
        from cairo.models.catalog import list_models

        return list_models(self.settings)

    def health(self):
        from cairo.models.catalog import health

        return health(self.settings)

    def complete(self, messages: list[dict], tools: list[dict]) -> Reply:
        ollama = self.settings.provider == "ollama"
        wire = copy.deepcopy(messages)
        if ollama:
            for message in wire:
                for call in message.get("tool_calls", []):
                    args = call["function"]["arguments"]
                    if isinstance(args, str):
                        call["function"]["arguments"] = json.loads(args)
                if message["role"] == "tool":
                    message["tool_name"] = message.pop("name", "")
                    message.pop("tool_call_id", None)
        body = {"model": self.settings.model, "messages": wire, "stream": False}
        if tools:
            body["tools"] = tools
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = "Bearer " + self.settings.api_key
        url = self.settings.base_url.rstrip("/") + (
            "/api/chat" if ollama else "/chat/completions"
        )
        request = urllib.request.Request(url, json.dumps(body).encode(), headers)
        try:
            with urllib.request.build_opener(NoRedirect).open(
                request, timeout=self.settings.timeout
            ) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ModelError("Resposta do provedor excede o limite de 2 MB")
                data = json.loads(raw)
            message = data["message"] if ollama else data["choices"][0]["message"]
            calls = []
            for call in message.get("tool_calls", [])[:8]:
                function = call["function"]
                args = function.get("arguments", {})
                calls.append(
                    {
                        "id": call.get("id") or uuid.uuid4().hex,
                        "type": "function",
                        "function": {
                            "name": function["name"],
                            "arguments": args
                            if isinstance(args, str)
                            else json.dumps(args),
                        },
                    }
                )
            content = message.get("content") or ""
            if not isinstance(content, str) or (not content.strip() and not calls):
                raise ModelError(
                    "Provedor retornou resposta vazia ou formato incompatível. Confira o modelo e o limite de saída configurado.",
                    code="unexpected_response",
                )
            return Reply(content[:100000], calls)
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            from cairo.models.catalog import http_error

            raise http_error(status) from None
        except TimeoutError:
            raise ModelError(
                "O provedor excedeu o tempo limite configurado.", code="timeout"
            ) from None
        except urllib.error.URLError as exc:
            code = "timeout" if isinstance(exc.reason, TimeoutError) else "offline"
            raise ModelError(
                "Não foi possível conectar ao provedor. Confira o serviço e a URL configurada.",
                code=code,
            ) from None
        except OSError:
            raise ModelError(
                "Falha de rede ao acessar o provedor.", code="offline"
            ) from None
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise ModelError(
                "Resposta do provedor não segue o contrato de chat/tools"
            ) from None


class DemoModel:
    """Deterministic pipeline exercise, explicitly not a language model."""

    def complete(self, messages: list[dict], tools: list[dict]) -> Reply:
        prompt = messages[0]["content"]
        agent = next(
            (
                name
                for name in (
                    "DeveloperAgent",
                    "ResearchAgent",
                    "SystemAgent",
                    "Reviewer",
                )
                if f"IDENTITY={name}" in prompt
            ),
            "MasterAgent",
        )
        if tools and not any(m["role"] == "tool" for m in messages):
            preferred = {
                "MasterAgent": "system_info",
                "DeveloperAgent": "list_files",
                "ResearchAgent": "memory_search",
                "SystemAgent": "system_info",
            }.get(agent)
            names = {t["function"]["name"] for t in tools}
            if preferred in names:
                args = (
                    {"query": "Cairo"}
                    if preferred == "memory_search"
                    else ({"path": "."} if preferred == "list_files" else {})
                )
                return Reply(
                    calls=[
                        {
                            "id": uuid.uuid4().hex,
                            "type": "function",
                            "function": {
                                "name": preferred,
                                "arguments": json.dumps(args),
                            },
                        }
                    ]
                )
        evidence = [m["content"][:2500] for m in messages if m["role"] == "tool"]
        detail = (
            "\n\nResultado real da ferramenta:\n" + "\n".join(evidence)
            if evidence
            else "\n\nFluxo de coordenação verificado."
        )
        if "STAGE=plan" in prompt:
            detail = "\n\nDeveloperAgent: examine os arquivos. ResearchAgent: consulte a memória. SystemAgent: inspecione o ambiente."
        if agent == "Reviewer":
            detail = "\n\nRevisão demonstrativa: as contribuições foram recebidas. Não houve avaliação semântica por IA."
        return Reply(
            f"[Demonstração · {agent}] Cairo está executando o pipeline local. Este modo é determinístico e não responde semanticamente ao pedido. Configure Ollama ou um provedor compatível para usar IA."
            + detail
        )


def create_model(settings: Settings) -> Model:
    if settings.provider == "fcc":
        from cairo.models.fcc import FCCModel

        return FCCModel(settings)
    return DemoModel() if settings.provider == "demo" else HTTPModel(settings)
