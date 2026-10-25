"""Stable boundary for optional connectors; adapters are explicitly registered."""
from typing import Protocol


class Integration(Protocol):
    name: str

    def health(self) -> dict: ...
    def close(self) -> None: ...


class IntegrationRegistry:
    def __init__(self):
        self._items: dict[str, Integration] = {}

    def register(self, adapter: Integration) -> None:
        if adapter.name in self._items:
            raise ValueError(f"Integration already registered: {adapter.name}")
        self._items[adapter.name] = adapter

    def health(self) -> dict:
        return {name: item.health() for name, item in self._items.items()}

    def close(self) -> None:
        errors = []
        for item in reversed(list(self._items.values())):
            try:
                item.close()
            except Exception as exc:
                errors.append(exc)
        self._items.clear()
        if errors:
            raise ExceptionGroup("Integration shutdown failed", errors)
