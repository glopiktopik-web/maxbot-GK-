"""Раздел «Посещаемость»: отметка отсутствующих и выгрузка в Excel.

Занятие отмечается в три касания: группа → урок → фамилии. Дисциплина
и номер урока подставляются из расписания, так что чаще всего
преподавателю остаётся только прислать список отсутствующих.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from maxapi import Router
from maxapi.context.base import BaseContext
from maxapi.types.input_media import InputMedia
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

import db
import keyboards as kb
from filters import HasText, Payload, PayloadPrefix
from services import exports
from services.groups import index
from services.timetable import timetable
from states import AttendanceSG
from utils import (
    ack,
    ids_of,
    payload_arg,
    payload_of,
    remember_user,
    text_of,
    user_name,
)

logger = logging.getLogger(__name__)
router = Router("attendance")

_SPLIT = re.compile(r"[,;\n]+")

PERIODS = {
    "week": ("неделю", 7),
    "month": ("месяц", 30),
    "all": ("всё время", 3650),
}


def _parse_students(raw: str) -> list[str]:
    names = [part.strip(" .-—·\t") for part in _SPLIT.split(raw or "")]
    return [name for name in names if name]


async def _menu_text(user_id: int | None) -> str:
    since = (date.today() - timedelta(days=7)).isoformat()
    records = await db.attendance_records(
        user_id=user_id, since=since, until=date.today().isoformat()
    )
    absent = sum(record["absent_count"] for record in records)
    return (
        "✅ Посещаемость\n\n"
        f"За последние 7 дней отмечено занятий: {len(records)}\n"
        f"Всего пропусков: {absent}\n\n"
        "Отметьте занятие сразу после урока — в конце месяца отчёт "
        "соберётся сам."
    )


@router.message_callback(Payload(kb.CB_ATT))
async def cb_attendance(event: MessageCallback, context: BaseContext) -> None:
    await remember_user(event)
    await context.clear()
    _chat_id, user_id = ids_of(event)
    await event.edit(
        text=await _menu_text(user_id),
        attachments=[kb.attendance_menu().as_markup()],
    )


# ── шаг 1: группа ──────────────────────────────────────────────────────────
@router.message_callback(Payload(kb.CB_ATT_NEW))
async def cb_new(event: MessageCallback, context: BaseContext) -> None:
    _chat_id, user_id = ids_of(event)
    user = await db.get_user(user_id or 0)
    mine = (user or {}).get("group_name")

    groups = [group.name for group in index.groups] or timetable.groups()
    if not groups:
        await ack(event, "Список групп пуст")
        return

    await context.set_state(AttendanceSG.waiting_group)
    await event.edit(
        text=(
            "Какая группа?\n\n"
            "Выберите кнопкой или напишите название сообщением."
        ),
        attachments=[kb.attendance_groups(groups, mine).as_markup()],
    )


@router.message_callback(AttendanceSG.waiting_group, PayloadPrefix(kb.CB_ATT_GROUP))
async def cb_group(event: MessageCallback, context: BaseContext) -> None:
    group = payload_arg(payload_of(event), kb.CB_ATT_GROUP)
    await ack(event, group)
    await _ask_lesson(event, context, group)


@router.message_created(AttendanceSG.waiting_group, HasText())
async def on_group_typed(event: MessageCreated, context: BaseContext) -> None:
    query = text_of(event)
    found = index.find(query)
    group = found.name if found else query.strip()

    if not group:
        return
    await _ask_lesson(event, context, group)


async def _ask_lesson(event, context: BaseContext, group: str) -> None:
    chat_id, _user_id = ids_of(event)
    if chat_id is None:
        return

    await context.update_data(att_group=group)
    await context.set_state(AttendanceSG.waiting_lesson)

    weekday = date.today().isoweekday()
    lessons = timetable.for_group(group, weekday)
    bells = timetable.bells

    options: list[tuple[int, str]] = []
    for lesson in lessons:
        start, _end = lesson.time_range(bells)
        subject = lesson.subject
        label = f"{lesson.number}. {start} {subject[:22]}"
        options.append((lesson.number, label))

    if not options:
        options = [(number, f"{number} урок") for number in range(1, 9)]
        hint = "На сегодня расписания нет — выберите номер урока."
    else:
        hint = "Занятия этой группы сегодня:"

    await event.bot.send_message(
        chat_id=chat_id,
        text=f"Группа {group}. {hint}",
        attachments=[kb.attendance_lessons(options).as_markup()],
    )


# ── шаг 2: урок ────────────────────────────────────────────────────────────
@router.message_callback(AttendanceSG.waiting_lesson, PayloadPrefix(kb.CB_ATT_LESSON))
async def cb_lesson(event: MessageCallback, context: BaseContext) -> None:
    raw = payload_arg(payload_of(event), kb.CB_ATT_LESSON)
    if not raw.isdigit():
        await ack(event)
        return

    number = int(raw)
    data = await context.get_data()
    group = data.get("att_group", "")

    weekday = date.today().isoweekday()
    lessons = timetable.for_group(group, weekday)
    subject = next(
        (lesson.subject for lesson in lessons if lesson.number == number), ""
    )

    await context.update_data(att_lesson=number, att_subject=subject)
    await context.set_state(AttendanceSG.waiting_absent)
    await ack(event, f"{number} урок")

    chat_id, _user_id = ids_of(event)
    if chat_id is None:
        return

    title = f"{group}, {number} урок"
    if subject:
        title += f" — {subject}"

    await event.bot.send_message(
        chat_id=chat_id,
        text=(
            f"{title}\n\n"
            "Пришлите фамилии отсутствующих — через запятую или с новой "
            "строки.\n\n"
            "Например:\nИванов\nПетрова\nСидоров"
        ),
        attachments=[kb.attendance_absent().as_markup()],
    )


# ── шаг 3: отсутствующие ───────────────────────────────────────────────────
@router.message_callback(AttendanceSG.waiting_absent, Payload(kb.CB_ATT_ALL_PRESENT))
async def cb_all_present(event: MessageCallback, context: BaseContext) -> None:
    await ack(event, "Все на месте")
    await _save(event, context, [])


@router.message_created(AttendanceSG.waiting_absent, HasText())
async def on_absent(event: MessageCreated, context: BaseContext) -> None:
    await _save(event, context, _parse_students(text_of(event)))


async def _save(event, context: BaseContext, students: list[str]) -> None:
    chat_id, user_id = ids_of(event)
    data = await context.get_data()
    group = data.get("att_group", "")
    number = data.get("att_lesson")
    subject = data.get("att_subject", "")
    await context.clear()

    if not user_id or chat_id is None or not group:
        return

    today = date.today()
    await db.add_attendance(
        user_id=user_id,
        author=user_name(event),
        group_name=group,
        lesson_date=today.isoformat(),
        lesson_no=number,
        subject=subject,
        students=students,
    )

    if students:
        listing = "\n".join(f"• {name}" for name in students)
        body = f"Отсутствовали ({len(students)}):\n{listing}"
    else:
        body = "Отсутствующих нет 👍"

    await event.bot.send_message(
        chat_id=chat_id,
        text=(
            f"✅ Записано\n\n"
            f"{today:%d.%m.%Y} · {group}"
            + (f" · {number} урок" if number else "")
            + (f"\n{subject}" if subject else "")
            + f"\n\n{body}"
        ),
        attachments=[kb.attendance_back().as_markup()],
    )


# ── просмотр и отчёт ───────────────────────────────────────────────────────
@router.message_callback(Payload(kb.CB_ATT_LIST))
async def cb_list(event: MessageCallback) -> None:
    _chat_id, user_id = ids_of(event)
    since = (date.today() - timedelta(days=14)).isoformat()
    records = await db.attendance_records(
        user_id=user_id, since=since, until=date.today().isoformat()
    )

    if not records:
        await event.edit(
            text="Записей за две недели нет.",
            attachments=[kb.attendance_menu().as_markup()],
        )
        return

    absences = await db.absences_of([record["id"] for record in records])
    lines = ["📋 Последние отметки", ""]
    for record in records[-15:]:
        names = absences.get(record["id"], [])
        when = record["lesson_date"][8:10] + "." + record["lesson_date"][5:7]
        head = f"{when} · {record['group_name']}"
        if record["lesson_no"]:
            head += f" · {record['lesson_no']} урок"
        lines.append(head)
        lines.append(
            "   " + (", ".join(names) if names else "все на месте")
        )
    await event.edit(
        text="\n".join(lines), attachments=[kb.attendance_menu().as_markup()]
    )


@router.message_callback(PayloadPrefix(kb.CB_ATT_REPORT))
async def cb_report(event: MessageCallback) -> None:
    choice = payload_arg(payload_of(event), kb.CB_ATT_REPORT)
    label, days = PERIODS.get(choice, PERIODS["week"])
    chat_id, user_id = ids_of(event)
    await ack(event, "Собираю отчёт…")

    if chat_id is None or not user_id:
        return

    until = date.today()
    since = until - timedelta(days=days)
    records = await db.attendance_records(
        user_id=user_id, since=since.isoformat(), until=until.isoformat()
    )

    if not records:
        await event.bot.send_message(
            chat_id=chat_id,
            text=f"За {label} отметок нет — отчёт собирать не из чего.",
            attachments=[kb.attendance_menu().as_markup()],
        )
        return

    absences = await db.absences_of([record["id"] for record in records])
    title = f"{since:%d.%m.%Y}-{until:%d.%m.%Y}"

    try:
        path = exports.attendance_xlsx(
            records, absences, title=title, author=user_name(event)
        )
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось собрать отчёт по посещаемости")
        await event.bot.send_message(
            chat_id=chat_id,
            text=(
                "Не удалось собрать файл отчёта.\n"
                "Проверьте, что установлена библиотека openpyxl:\n"
                "pip install -r requirements.txt"
            ),
            attachments=[kb.attendance_menu().as_markup()],
        )
        return

    total_absent = sum(record["absent_count"] for record in records)
    await event.bot.send_message(
        chat_id=chat_id,
        text=(
            f"📊 Отчёт по посещаемости за {label}\n\n"
            f"Период: {title}\n"
            f"Занятий: {len(records)}\n"
            f"Пропусков: {total_absent}\n\n"
            "Внутри три листа: журнал, сводка по студентам и по группам."
        ),
        attachments=[InputMedia(path=str(path)), kb.attendance_back().as_markup()],
    )
