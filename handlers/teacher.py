"""Раздел «Моё расписание» — личное расписание преподавателя.

Картинка расписания показывает одну группу. Преподаватель же ведёт
занятия у нескольких групп сразу, и собрать свой день по десятку
фотографий — та самая рутина, ради которой всё и затевалось. Здесь
бот собирает день из всех групп по фамилии.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from maxapi import Router
from maxapi.context.base import BaseContext
from maxapi.filters.command import Command
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

import db
import keyboards as kb
from filters import HasText, Payload, PayloadPrefix
from services.timetable import DAY_NAMES, format_day, format_week, timetable
from states import TeacherSG
from utils import ack, ids_of, payload_arg, payload_of, remember_user, text_of

logger = logging.getLogger(__name__)
router = Router("teacher")

NO_DATA = (
    "Структурированное расписание не загружено.\n\n"
    "Файл data/timetable.json отсутствует — соберите его командой\n"
    "python tools/build_timetable.py"
)

ASK_NAME = (
    "👤 Моё расписание\n\n"
    "Напишите свою фамилию — я соберу ваши занятия из расписаний "
    "всех групп.\n\n"
    "Например: Божко или Сагателян Л.Р."
)


async def teacher_of(user_id: int | None) -> str | None:
    if not user_id:
        return None
    user = await db.get_user(user_id)
    return (user or {}).get("teacher_name")


def _menu_text(teacher: str | None) -> str:
    if not teacher:
        return ASK_NAME

    lessons = timetable.for_teacher(teacher)
    days = len({lesson.day for lesson in lessons})
    groups = len({lesson.group for lesson in lessons})
    return (
        f"👤 {teacher}\n\n"
        f"Занятий в неделю: {len(lessons)}\n"
        f"Учебных дней: {days}\n"
        f"Групп: {groups}\n\n"
        "Что показать?"
    )


# ── вход в раздел ──────────────────────────────────────────────────────────
@router.message_callback(Payload(kb.CB_MINE))
async def cb_mine(event: MessageCallback, context: BaseContext) -> None:
    await remember_user(event)
    await context.clear()

    if not timetable.available:
        await event.edit(text=NO_DATA, attachments=[kb.only_menu().as_markup()])
        return

    _chat_id, user_id = ids_of(event)
    teacher = await teacher_of(user_id)
    if not teacher:
        await context.set_state(TeacherSG.waiting_name)

    await event.edit(
        text=_menu_text(teacher),
        attachments=[kb.mine_menu(teacher).as_markup()],
    )


@router.message_callback(Payload(kb.CB_MINE_SET))
async def cb_set_name(event: MessageCallback, context: BaseContext) -> None:
    await context.set_state(TeacherSG.waiting_name)
    await event.edit(text=ASK_NAME, attachments=[kb.cancel_only().as_markup()])


@router.message_created(Command("me"))
async def cmd_me(event: MessageCreated, context: BaseContext) -> None:
    await remember_user(event)
    _chat_id, user_id = ids_of(event)
    teacher = await teacher_of(user_id)
    if not teacher:
        await context.set_state(TeacherSG.waiting_name)
        await event.message.answer(
            text=ASK_NAME, attachments=[kb.cancel_only().as_markup()]
        )
        return
    await event.message.answer(
        text=_menu_text(teacher), attachments=[kb.mine_menu(teacher).as_markup()]
    )


# ── ввод фамилии ───────────────────────────────────────────────────────────
@router.message_created(TeacherSG.waiting_name, HasText())
async def on_name(event: MessageCreated, context: BaseContext) -> None:
    await remember_user(event)
    query = text_of(event)
    matches = timetable.find_teachers(query)

    if not matches:
        await event.message.answer(
            text=(
                f"Не нашёл преподавателя «{query}» в расписании.\n\n"
                "Попробуйте только фамилию — например, «Ваккер»."
            ),
            attachments=[kb.cancel_only().as_markup()],
        )
        return

    if len(matches) == 1:
        await _save_teacher(event, context, matches[0])
        return

    await event.message.answer(
        text="Нашёл несколько — выберите себя:",
        attachments=[kb.mine_pick(matches).as_markup()],
    )


@router.message_callback(PayloadPrefix(kb.CB_MINE_PICK))
async def cb_pick_teacher(event: MessageCallback, context: BaseContext) -> None:
    name = payload_arg(payload_of(event), kb.CB_MINE_PICK)
    await ack(event, f"Сохранил: {name}")
    await _save_teacher(event, context, name)


async def _save_teacher(event, context: BaseContext, name: str) -> None:
    chat_id, user_id = ids_of(event)
    await context.clear()
    if not user_id or chat_id is None:
        return

    await db.set_user_teacher(user_id, name)
    today = date.today()
    lessons = timetable.for_teacher(name, today.isoweekday())

    await event.bot.send_message(
        chat_id=chat_id,
        text=(
            f"✅ Запомнил: {name}\n\n"
            + format_day(
                lessons,
                day=today.isoweekday(),
                when=today,
                show_group=True,
                show_teacher=False,
            )
        ),
        attachments=[kb.mine_menu(name).as_markup()],
    )


# ── просмотр ───────────────────────────────────────────────────────────────
async def _require_teacher(event: MessageCallback, context: BaseContext) -> str | None:
    _chat_id, user_id = ids_of(event)
    teacher = await teacher_of(user_id)
    if teacher:
        return teacher

    await context.set_state(TeacherSG.waiting_name)
    await event.edit(text=ASK_NAME, attachments=[kb.cancel_only().as_markup()])
    return None


@router.message_callback(Payload(kb.CB_MINE_TODAY, kb.CB_MINE_TOMORROW))
async def cb_day(event: MessageCallback, context: BaseContext) -> None:
    teacher = await _require_teacher(event, context)
    if teacher is None:
        return

    shift = 1 if payload_of(event) == kb.CB_MINE_TOMORROW else 0
    when = date.today() + timedelta(days=shift)
    lessons = timetable.for_teacher(teacher, when.isoweekday())

    await event.edit(
        text=format_day(
            lessons,
            day=when.isoweekday(),
            when=when,
            show_group=True,
            show_teacher=False,
        ),
        attachments=[kb.mine_back().as_markup()],
    )


@router.message_callback(Payload(kb.CB_MINE_WEEK))
async def cb_week(event: MessageCallback, context: BaseContext) -> None:
    teacher = await _require_teacher(event, context)
    if teacher is None:
        return

    lessons = timetable.for_teacher(teacher)
    await event.edit(
        text=f"🗓 Расписание на неделю — {teacher}\n\n"
        + format_week(lessons, show_group=True),
        attachments=[kb.mine_back().as_markup()],
    )


@router.message_callback(Payload(kb.CB_MINE_NEXT))
async def cb_next(event: MessageCallback, context: BaseContext) -> None:
    await remember_user(event)
    _chat_id, user_id = ids_of(event)
    teacher = await teacher_of(user_id)

    if not teacher:
        user = await db.get_user(user_id or 0)
        group = (user or {}).get("group_name")
        if group:
            found = timetable.next_for_group(group)
            await event.edit(
                text=_next_text(found, title=f"Группа {group}"),
                attachments=[kb.mine_back().as_markup()],
            )
            return
        await context.set_state(TeacherSG.waiting_name)
        await event.edit(text=ASK_NAME, attachments=[kb.cancel_only().as_markup()])
        return

    found = timetable.next_for_teacher(teacher)
    await event.edit(
        text=_next_text(found, title=teacher),
        attachments=[kb.mine_back().as_markup()],
    )


def _next_text(found, *, title: str) -> str:
    if not found:
        return f"⏭ {title}\n\nБлижайших занятий на этой неделе не найдено."

    lesson, moment = found
    bells = timetable.bells
    start, end = lesson.time_range(bells)
    now = datetime.now()

    if moment.date() == now.date():
        when = "сегодня"
    elif moment.date() == (now + timedelta(days=1)).date():
        when = "завтра"
    else:
        when = f"{DAY_NAMES.get(lesson.day, '')}, {moment:%d.%m}"

    left = moment - now
    hours, remainder = divmod(int(left.total_seconds()), 3600)
    minutes = remainder // 60
    if left.days >= 1:
        countdown = ""
    elif hours:
        countdown = f"\nДо начала: {hours} ч {minutes} мин"
    else:
        countdown = f"\nДо начала: {minutes} мин"

    tail = f"\nПреподаватель: {lesson.teachers_text()}" if lesson.teachers else ""
    return (
        f"⏭ Следующий урок — {title}\n\n"
        f"{when}, {lesson.number} урок  {start}–{end}\n"
        f"{lesson.subject}\n"
        f"Группа: {lesson.group}\n"
        f"Аудитория: {lesson.room or '—'}"
        f"{tail}"
        f"{countdown}"
    )


# ── расписание группы текстом ──────────────────────────────────────────────
@router.message_callback(PayloadPrefix(kb.CB_MINE_GROUP_TEXT))
async def cb_group_text(event: MessageCallback) -> None:
    group = payload_arg(payload_of(event), kb.CB_MINE_GROUP_TEXT)
    lessons = timetable.for_group(group)

    if not lessons:
        await ack(event, "Для этой группы нет текстовых данных")
        return

    await event.edit(
        text=f"🗓 {group} — расписание на неделю\n\n" + format_week(lessons),
        attachments=[kb.mine_back().as_markup()],
    )
