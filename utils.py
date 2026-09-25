"""Мелкие помощники, общие для всех разделов."""

from __future__ import annotations

import logging
from typing import Any

import db
from config import ADMIN_IDS

logger = logging.getLogger(__name__)


async def ack(event: Any, text: str = "Готово") -> None:
    """Подтверждает нажатие кнопки.

    API MAX отклоняет подтверждение без текста
    (``message or notification required``), поэтому уведомление
    всегда непустое. Сбой подтверждения не должен ронять обработчик —
    пользователю важнее результат нажатия, чем всплывающая подсказка.
    """
    try:
        await event.ack(text)
    except Exception:  # noqa: BLE001
        logger.debug("Не удалось подтвердить callback", exc_info=True)


def ids_of(event: Any) -> tuple[int | None, int | None]:
    """(chat_id, user_id) для любого события maxapi."""
    return event.get_ids()


def user_name(event: Any) -> str:
    """Имя пользователя, каким его показывает MAX."""
    user = None
    message = getattr(event, "message", None)
    callback = getattr(event, "callback", None)

    if callback is not None:
        user = callback.user
    elif message is not None:
        user = message.sender
    elif getattr(event, "user", None) is not None:
        user = event.user

    if user is None:
        return "коллега"

    parts = [user.first_name, user.last_name]
    return " ".join(part for part in parts if part).strip() or "коллега"


def text_of(event: Any) -> str:
    """Текст входящего сообщения (или пустая строка)."""
    message = getattr(event, "message", None)
    body = getattr(message, "body", None) if message else None
    return (getattr(body, "text", None) or "").strip()


def is_admin(user_id: int | None) -> bool:
    return bool(user_id) and user_id in ADMIN_IDS


async def remember_user(event: Any) -> None:
    """Запоминает пользователя, чтобы уметь писать ему первым."""
    chat_id, user_id = ids_of(event)
    if not user_id:
        return
    await db.upsert_user(user_id, chat_id, user_name(event))


def payload_of(event: Any) -> str:
    callback = getattr(event, "callback", None)
    return (getattr(callback, "payload", None) or "") if callback else ""


def payload_arg(payload: str, prefix: str) -> str:
    """Хвост payload'а после префикса."""
    return payload[len(prefix) :] if payload.startswith(prefix) else ""
