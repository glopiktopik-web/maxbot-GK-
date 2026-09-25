"""Последний рубеж: сообщения вне диалогов и неизвестные кнопки.

Если преподаватель просто пишет «21П» — не заставляем его искать
кнопку, а сразу отдаём расписание.
"""

from __future__ import annotations

import logging

from maxapi import Router
from maxapi.context.base import BaseContext
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

import keyboards as kb
import texts
from filters import HasText
from handlers.schedule import deliver
from services.groups import index
from utils import ack, remember_user, text_of

logger = logging.getLogger(__name__)
router = Router("fallback")


@router.message_created(HasText())
async def on_any_text(event: MessageCreated, context: BaseContext) -> None:
    await remember_user(event)
    query = text_of(event)

    group = index.find(query)
    if group is not None:
        await deliver(event, group, context=None)
        return

    suggestions = index.suggest(query) if len(query) <= 12 else []
    if suggestions:
        await event.message.answer(
            text=f"Не нашёл точного совпадения с «{query}». "
            "Может быть, одна из этих групп?",
            attachments=[kb.schedule_suggestions(suggestions).as_markup()],
        )
        return

    await event.message.answer(
        text=texts.MENU, attachments=[kb.main_menu().as_markup()]
    )


@router.message_callback()
async def on_unknown_callback(event: MessageCallback) -> None:
    logger.info("Неизвестный payload: %s", getattr(event.callback, "payload", None))
    await ack(event)
