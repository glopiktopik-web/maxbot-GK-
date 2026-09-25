"""Раздел «Расписание учебных занятий».

Пользователь нажимает кнопку, пишет название своей группы —
и получает фотографию расписания.
"""

from __future__ import annotations

import logging

from maxapi import Router
from maxapi.context.base import BaseContext
from maxapi.filters.command import Command
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

import db
import keyboards as kb
import texts
from config import SCHEDULES_DIR
from filters import HasText, Payload, PayloadPrefix
from services import photos
from services.groups import Group, index
from states import ScheduleSG
from utils import (
    ack,
    ids_of,
    payload_arg,
    payload_of,
    remember_user,
    text_of,
)

logger = logging.getLogger(__name__)
router = Router("schedule")


# ── общие помощники раздела ────────────────────────────────────────────────
async def my_group_of(user_id: int | None) -> str | None:
    if not user_id:
        return None
    user = await db.get_user(user_id)
    return (user or {}).get("group_name")


async def ask_group(event: MessageCallback, context: BaseContext) -> None:
    """Экран «напишите название группы»."""
    _chat_id, user_id = ids_of(event)
    await context.set_state(ScheduleSG.waiting_group)

    if not len(index):
        await event.edit(
            text=texts.NO_SCHEDULES.format(path=SCHEDULES_DIR),
            attachments=[kb.only_menu().as_markup()],
        )
        return

    mine = await my_group_of(user_id)
    hint = f"\n\nВсего групп в базе: {len(index)}"
    await event.edit(
        text=texts.ASK_GROUP + hint,
        attachments=[kb.schedule_prompt(mine).as_markup()],
    )


async def deliver(event, group: Group, *, context: BaseContext | None) -> None:
    """Отправляет расписание группы и закрывает диалог."""
    chat_id, user_id = ids_of(event)
    if chat_id is None:
        return

    mine = await my_group_of(user_id)
    caption = (
        f"📅 Расписание группы {group.name}\n"
        f"Обновлено: {group.updated}"
    )
    await photos.send_schedule(
        event.bot,
        chat_id,
        group,
        caption=caption,
        keyboard=kb.schedule_result(
            group.name, is_mine=(mine == group.name)
        ).as_markup(),
    )
    if context is not None:
        await context.clear()


async def handle_query(
    event: MessageCreated, query: str, context: BaseContext
) -> None:
    """Ищет группу по введённому тексту."""
    group = index.find(query)
    if group is not None:
        await deliver(event, group, context=context)
        return

    suggestions = index.suggest(query)
    if suggestions:
        await event.message.answer(
            text=texts.GROUP_NOT_FOUND.format(query=query)
            + "\n\nВозможно, вы имели в виду:",
            attachments=[kb.schedule_suggestions(suggestions).as_markup()],
        )
    else:
        await event.message.answer(
            text=texts.GROUP_NOT_FOUND.format(query=query),
            attachments=[kb.schedule_prompt(None).as_markup()],
        )


# ── вход в раздел ──────────────────────────────────────────────────────────
@router.message_callback(Payload(kb.CB_SCHEDULE))
async def cb_schedule(event: MessageCallback, context: BaseContext) -> None:
    await remember_user(event)
    await ask_group(event, context)


@router.message_created(Command("schedule"))
async def cmd_schedule(event: MessageCreated, context: BaseContext) -> None:
    await remember_user(event)
    await context.set_state(ScheduleSG.waiting_group)
    mine = await my_group_of(ids_of(event)[1])
    await event.message.answer(
        text=texts.ASK_GROUP,
        attachments=[kb.schedule_prompt(mine).as_markup()],
    )


# ── пользователь ввёл название группы ──────────────────────────────────────
@router.message_created(ScheduleSG.waiting_group, HasText())
async def on_group_typed(event: MessageCreated, context: BaseContext) -> None:
    await remember_user(event)
    await handle_query(event, text_of(event), context)


# ── выбор группы кнопкой ───────────────────────────────────────────────────
@router.message_callback(PayloadPrefix(kb.CB_SCHEDULE_GROUP))
async def cb_pick_group(event: MessageCallback, context: BaseContext) -> None:
    name = payload_arg(payload_of(event), kb.CB_SCHEDULE_GROUP)
    group = index.find(name)
    await ack(event, "Загружаю расписание…")

    if group is None:
        chat_id, _user_id = ids_of(event)
        if chat_id is not None:
            await event.bot.send_message(
                chat_id=chat_id,
                text=texts.GROUP_NOT_FOUND.format(query=name),
                attachments=[kb.schedule_prompt(None).as_markup()],
            )
        return

    await deliver(event, group, context=context)


# ── «запомнить как мою группу» ─────────────────────────────────────────────
@router.message_callback(PayloadPrefix(kb.CB_SCHEDULE_SAVE))
async def cb_save_group(event: MessageCallback) -> None:
    name = payload_arg(payload_of(event), kb.CB_SCHEDULE_SAVE)
    _chat_id, user_id = ids_of(event)
    group = index.find(name)

    if group is None or not user_id:
        await ack(event, "Не удалось сохранить группу")
        return

    await remember_user(event)
    await db.set_user_group(user_id, group.name)
    await ack(event, f"Группа {group.name} сохранена")


# ── список групп ───────────────────────────────────────────────────────────
@router.message_callback(Payload(kb.CB_SCHEDULE_LIST))
async def cb_list(event: MessageCallback) -> None:
    if not len(index):
        await event.edit(
            text=texts.NO_SCHEDULES.format(path=SCHEDULES_DIR),
            attachments=[kb.only_menu().as_markup()],
        )
        return

    courses = list(index.by_course().keys())
    await event.edit(
        text="📋 Группы в базе\n\n" + index.as_text() + "\n\nВыберите курс:",
        attachments=[kb.schedule_courses(courses).as_markup()],
    )


@router.message_callback(PayloadPrefix(kb.CB_SCHEDULE_COURSE))
async def cb_course(event: MessageCallback, context: BaseContext) -> None:
    raw = payload_arg(payload_of(event), kb.CB_SCHEDULE_COURSE)
    try:
        course = int(raw)
    except ValueError:
        await ack(event)
        return

    groups = index.by_course().get(course, [])
    await context.set_state(ScheduleSG.waiting_group)
    await event.edit(
        text=f"{course} курс — выберите группу\n\n"
        "Или просто напишите её название сообщением.",
        attachments=[kb.schedule_group_buttons(groups).as_markup()],
    )
