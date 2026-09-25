"""Раздел «Объявления» — рассылка коллегам."""

from __future__ import annotations

import asyncio
import logging

from maxapi import Router
from maxapi.context.base import BaseContext
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

import db
import keyboards as kb
import texts
from filters import HasText, Payload
from states import AnnounceSG
from utils import (
    ack,
    ids_of,
    is_admin,
    remember_user,
    text_of,
    user_name,
)

logger = logging.getLogger(__name__)
router = Router("announce")


@router.message_callback(Payload(kb.CB_ANNOUNCE))
async def cb_announce(event: MessageCallback, context: BaseContext) -> None:
    await remember_user(event)
    await context.clear()
    _chat_id, user_id = ids_of(event)

    if not is_admin(user_id):
        await event.edit(
            text=texts.NOT_ADMIN.format(user_id=user_id),
            attachments=[kb.announce_menu(False).as_markup()],
        )
        return

    recipients = len(await db.all_users())
    await event.edit(
        text=(
            "📢 Объявления\n\n"
            f"Получателей в базе: {recipients}.\n"
            "Рассылка уйдёт всем, кто хотя бы раз открывал бота."
        ),
        attachments=[kb.announce_menu(True).as_markup()],
    )


@router.message_callback(Payload(kb.CB_ANNOUNCE_NEW))
async def cb_announce_new(event: MessageCallback, context: BaseContext) -> None:
    _chat_id, user_id = ids_of(event)
    if not is_admin(user_id):
        await ack(event, "Недостаточно прав")
        return

    await context.set_state(AnnounceSG.waiting_text)
    await event.edit(
        text=texts.ASK_ANNOUNCE, attachments=[kb.cancel_only().as_markup()]
    )


@router.message_created(AnnounceSG.waiting_text, HasText())
async def on_announce(event: MessageCreated, context: BaseContext) -> None:
    chat_id, user_id = ids_of(event)
    await context.clear()

    if not is_admin(user_id):
        return

    body = text_of(event)
    message = f"📢 Объявление\n\n{body}\n\n— {user_name(event)}"

    sent = 0
    failed = 0
    for user in await db.all_users():
        target = user["chat_id"]
        if not target or target == chat_id:
            continue
        try:
            await event.bot.send_message(chat_id=target, text=message)
            sent += 1
        except Exception:  # noqa: BLE001
            failed += 1
            logger.warning(
                "Объявление не доставлено в чат %s", target, exc_info=True
            )
        await asyncio.sleep(0.05)  # бережём лимиты API

    await event.message.answer(
        text=(
            "✅ Рассылка завершена\n\n"
            f"Доставлено: {sent}\n"
            f"Не доставлено: {failed}"
        ),
        attachments=[kb.main_menu().as_markup()],
    )
