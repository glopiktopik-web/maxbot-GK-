"""Подписка на расписание: уведомления об изменениях и утренняя рассылка."""

from __future__ import annotations

import logging

from maxapi import Router
from maxapi.context.base import BaseContext
from maxapi.types.updates.message_callback import MessageCallback

import db
import keyboards as kb
from filters import Payload, PayloadPrefix
from utils import ack, ids_of, payload_arg, payload_of, remember_user

logger = logging.getLogger(__name__)
router = Router("subscribe")


def _text(user: dict | None) -> str:
    group = (user or {}).get("group_name")
    teacher = (user or {}).get("teacher_name")
    notify = bool((user or {}).get("notify_changes", 1))
    digest = (user or {}).get("digest_time")

    lines = ["🔔 Подписка и рассылка", ""]
    lines.append(f"Моя группа: {group or 'не выбрана'}")
    lines.append(f"Моя фамилия: {teacher or 'не указана'}")
    lines.append("")
    lines.append(
        "Уведомлять, когда обновят расписание моей группы: "
        + ("да" if notify else "нет")
    )
    lines.append(
        "Присылать расписание утром: " + (digest if digest else "не присылать")
    )
    lines.append("")
    if teacher:
        lines.append("Утром придёт ваш личный день из всех групп.")
    elif group:
        lines.append("Утром придёт картинка расписания вашей группы.")
    else:
        lines.append(
            "Чтобы рассылка заработала, выберите группу или укажите фамилию."
        )
    return "\n".join(lines)


@router.message_callback(Payload(kb.CB_SUB))
async def cb_subscriptions(event: MessageCallback, context: BaseContext) -> None:
    await remember_user(event)
    await context.clear()
    _chat_id, user_id = ids_of(event)
    user = await db.get_user(user_id or 0)

    await event.edit(
        text=_text(user),
        attachments=[
            kb.subscriptions(
                group=(user or {}).get("group_name"),
                notify=bool((user or {}).get("notify_changes", 1)),
                digest_time=(user or {}).get("digest_time"),
            ).as_markup()
        ],
    )


@router.message_callback(Payload(kb.CB_SUB_TOGGLE))
async def cb_toggle(event: MessageCallback) -> None:
    _chat_id, user_id = ids_of(event)
    if not user_id:
        await ack(event)
        return

    user = await db.get_user(user_id)
    enabled = not bool((user or {}).get("notify_changes", 1))
    await db.set_notify_changes(user_id, enabled)

    user = await db.get_user(user_id)
    await event.answer(
        notification="Уведомления включены" if enabled else "Уведомления выключены",
        new_text=_text(user),
        attachments=[
            kb.subscriptions(
                group=(user or {}).get("group_name"),
                notify=enabled,
                digest_time=(user or {}).get("digest_time"),
            ).as_markup()
        ],
    )


@router.message_callback(PayloadPrefix(kb.CB_SUB_DIGEST))
async def cb_digest(event: MessageCallback) -> None:
    choice = payload_arg(payload_of(event), kb.CB_SUB_DIGEST)
    _chat_id, user_id = ids_of(event)
    if not user_id:
        await ack(event)
        return

    value = None if choice == "off" else choice
    await db.set_digest_time(user_id, value)

    user = await db.get_user(user_id)
    await event.answer(
        notification=(
            f"Буду присылать в {value}" if value else "Утренняя рассылка выключена"
        ),
        new_text=_text(user),
        attachments=[
            kb.subscriptions(
                group=(user or {}).get("group_name"),
                notify=bool((user or {}).get("notify_changes", 1)),
                digest_time=value,
            ).as_markup()
        ],
    )
