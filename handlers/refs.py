"""Раздел «Справочники»: звонки, аудитории, преподаватели, свободные кабинеты."""

from __future__ import annotations

import logging
from datetime import date, datetime

from maxapi import Router
from maxapi.context.base import BaseContext
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

import keyboards as kb
from filters import HasText, Payload
from services.timetable import DAY_NAMES, format_bells, timetable
from states import RefsSG
from utils import remember_user, text_of

logger = logging.getLogger(__name__)
router = Router("refs")


@router.message_callback(Payload(kb.CB_REFS))
async def cb_refs(event: MessageCallback, context: BaseContext) -> None:
    await remember_user(event)
    await context.clear()
    await event.edit(
        text=(
            "📖 Справочники\n\n"
            "Всё, что обычно приходится искать глазами по расписанию."
        ),
        attachments=[kb.refs_menu().as_markup()],
    )


@router.message_callback(Payload(kb.CB_REFS_BELLS))
async def cb_bells(event: MessageCallback) -> None:
    await event.edit(
        text=format_bells(), attachments=[kb.refs_back().as_markup()]
    )


@router.message_callback(Payload(kb.CB_REFS_ROOMS))
async def cb_rooms(event: MessageCallback) -> None:
    rooms = timetable.rooms()
    if not rooms:
        await event.edit(
            text="Данных об аудиториях нет.",
            attachments=[kb.refs_back().as_markup()],
        )
        return

    numeric = sorted(r for r in rooms if r.isdigit())
    other = sorted(r for r in rooms if not r.isdigit())
    text = (
        f"🚪 Аудитории в расписании ({len(rooms)})\n\n"
        + "Учебные кабинеты:\n"
        + "  ".join(numeric)
        + "\n\nМастерские и залы:\n"
        + "  ".join(other)
    )
    await event.edit(text=text, attachments=[kb.refs_back().as_markup()])


@router.message_callback(Payload(kb.CB_REFS_TEACHERS))
async def cb_teachers(event: MessageCallback) -> None:
    teachers = timetable.teachers()
    if not teachers:
        await event.edit(
            text="Данных о преподавателях нет.",
            attachments=[kb.refs_back().as_markup()],
        )
        return

    lines = [f"👥 Преподаватели в расписании ({len(teachers)})", ""]
    for name in teachers:
        count = len(timetable.for_teacher(name))
        lines.append(f"• {name} — {count} занятий в неделю")
    await event.edit(
        text="\n".join(lines), attachments=[kb.refs_back().as_markup()]
    )


@router.message_callback(Payload(kb.CB_REFS_FREE))
async def cb_free_prompt(event: MessageCallback, context: BaseContext) -> None:
    await context.set_state(RefsSG.waiting_room_query)
    now = datetime.now()
    await event.edit(
        text=(
            "🔍 Свободные аудитории\n\n"
            "Напишите день и номер урока — например: «ср 3».\n"
            "Или просто номер урока, чтобы посмотреть на сегодня: «3».\n\n"
            f"Сегодня {DAY_NAMES.get(now.isoweekday(), '')}."
        ),
        attachments=[kb.cancel_only().as_markup()],
    )


_DAYS = {
    "пн": 1, "понедельник": 1,
    "вт": 2, "вторник": 2,
    "ср": 3, "среда": 3,
    "чт": 4, "четверг": 4,
    "пт": 5, "пятница": 5,
    "сб": 6, "суббота": 6,
}


@router.message_created(RefsSG.waiting_room_query, HasText())
async def on_free_query(event: MessageCreated, context: BaseContext) -> None:
    raw = text_of(event).lower().replace("ё", "е")
    parts = raw.split()
    await context.clear()

    day = date.today().isoweekday()
    number: int | None = None

    for part in parts:
        if part.isdigit():
            number = int(part)
        elif part in _DAYS:
            day = _DAYS[part]

    if number is None or not (1 <= number <= len(timetable.bells)):
        await event.message.answer(
            text="Не понял запрос. Пример: «ср 3» или «3».",
            attachments=[kb.refs_menu().as_markup()],
        )
        return

    free = timetable.free_rooms(day, number)
    busy = len(timetable.rooms()) - len(free)
    start, end = timetable.bells[number - 1]

    text = (
        f"🔍 {DAY_NAMES.get(day, '').capitalize()}, {number} урок "
        f"({start}–{end})\n\n"
        f"Свободно аудиторий: {len(free)} из {len(timetable.rooms())} "
        f"(занято {busy})\n\n"
        + ("  ".join(free) if free else "Свободных аудиторий нет.")
    )
    await event.message.answer(
        text=text, attachments=[kb.refs_menu().as_markup()]
    )
