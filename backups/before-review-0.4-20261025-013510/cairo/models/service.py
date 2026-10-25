"""Generic sync/async entry points over Cairo's existing model contract."""

import asyncio
from dataclasses import replace

from cairo.config import Settings
from cairo.models import Model, Reply, create_model
from cairo.models.errors import ModelError


class AIService:
    def __init__(self, settings: Settings, adapter: Model | None = None):
        self.settings = settings
        self.adapter = adapter or create_model(settings)

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        model: str | None = None,
    ) -> Reply:
        adapter = self.adapter
        if model is not None:
            if not isinstance(model, str) or not model.strip():
                raise ModelError("Informe um modelo não vazio.", code="invalid_request")
            adapter = create_model(replace(self.settings, model=model.strip()))
        return adapter.complete(messages, tools or [])

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        model: str | None = None,
    ) -> Reply:
        return await asyncio.to_thread(self.complete, messages, tools, model=model)

    def list_models(self) -> dict:
        listing = getattr(self.adapter, "list_models", None)
        if listing is None:
            raise ModelError(
                "Este adapter não oferece catálogo de modelos.", code="unsupported"
            )
        return listing()

    def health(self) -> dict:
        check = getattr(self.adapter, "health", None)
        if check is not None:
            return check()
        return {
            "provider": self.settings.provider,
            "status": "not_checked",
            "online": None,
            "selected_model": self.settings.model,
            "ready": None,
        }
