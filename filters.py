"""Свои фильтры для callback-кнопок."""

from __future__ import annotations

from typing import Any

from maxapi.filters.filter import BaseFilter


class Payload(BaseFilter):
    """Точное совпадение payload кнопки с одним из значений."""

    def __init__(self, *values: str) -> None:
        self.values = set(values)

    async def __call__(self, event: Any) -> bool:
        callback = getattr(event, "callback", None)
        payload = getattr(callback, "payload", None) if callback else None
        return payload in self.values


class PayloadPrefix(BaseFilter):
    """Payload начинается с префикса (например, ``sched:g:``)."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    async def __call__(self, event: Any) -> bool:
        callback = getattr(event, "callback", None)
        payload = getattr(callback, "payload", None) if callback else None
        return isinstance(payload, str) and payload.startswith(self.prefix)


class HasText(BaseFilter):
    """В сообщении есть непустой текст."""

    async def __call__(self, event: Any) -> bool:
        message = getattr(event, "message", None)
        body = getattr(message, "body", None) if message else None
        text = getattr(body, "text", None) if body else None
        return bool(text and text.strip())
