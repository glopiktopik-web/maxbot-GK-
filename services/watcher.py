"""Фоновые задачи вокруг расписания.

Две вещи, которые преподаватель иначе делает руками:
1. Замечает, что расписание группы обновили — бот сообщает сам.
2. Каждое утро открывает расписание на сегодня — бот присылает его сам.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

import db
import keyboards as kb
from services import photos
from services.groups import index
from services.timetable import format_day, timetable

if TYPE_CHECKING:
    from maxapi import Bot

logger = logging.getLogger(__name__)

#: Первый проход только запоминает состояние файлов, не рассылая ничего:
#: иначе при первом запуске бот сообщил бы об «изменении» всех 54 групп.
_initialized = False


async def check_schedule_changes(bot: Bot) -> None:
    """Сравнивает картинки расписаний с запомненным состоянием."""
    global _initialized

    index.refresh(force=True)
    groups = index.groups
    if not groups:
        return

    known = await db.known_schedule_state()
    first_run = not known and not _initialized

    for group in groups:
        previous = known.get(group.key)
        if previous is not None and abs(previous - group.mtime) < 1:
            continue

        await db.remember_schedule_state(group.key, group.name, group.mtime)

        if previous is None or first_run:
            continue  # новая группа или первый запуск — молчим

        await _notify_group_changed(bot, group)

    _initialized = True


async def _notify_group_changed(bot: Bot, group) -> None:
    recipients = await db.subscribers_of_group(group.name)
    if not recipients:
        return

    logger.info(
        "Расписание %s обновлено, получателей: %s", group.name, len(recipients)
    )
    caption = (
        f"🔔 Расписание группы {group.name} обновлено\n"
        f"Файл изменён: {group.updated}"
    )
    for user in recipients:
        chat_id = user["chat_id"]
        if not chat_id:
            continue
        try:
            await photos.send_schedule(
                bot,
                chat_id,
                group,
                caption=caption,
                keyboard=kb.schedule_result(
                    group.name, is_mine=True
                ).as_markup(),
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Не удалось отправить обновление в чат %s", chat_id, exc_info=True
            )


async def send_morning_digest(bot: Bot, now: datetime | None = None) -> None:
    """Утренняя рассылка расписания на сегодня."""
    now = now or datetime.now()
    slot = now.strftime("%H:%M")
    today = now.date()

    recipients = await db.digest_recipients(slot, today.isoformat())
    if not recipients:
        return

    logger.info("Утренняя рассылка %s: получателей %s", slot, len(recipients))
    for user in recipients:
        try:
            await _send_one_digest(bot, user, today)
        except Exception:  # noqa: BLE001
            logger.warning(
                "Не удалось отправить рассылку пользователю %s",
                user.get("user_id"),
                exc_info=True,
            )
        finally:
            await db.mark_digest_sent(user["user_id"], today.isoformat())


async def _send_one_digest(bot: Bot, user: dict, today: date) -> None:
    chat_id = user.get("chat_id")
    if not chat_id:
        return

    weekday = today.isoweekday()
    header = f"☀️ Доброе утро! Сегодня {today:%d.%m}, {_weekday_name(weekday)}"

    teacher = user.get("teacher_name")
    if teacher:
        lessons = timetable.for_teacher(teacher, weekday)
        body = format_day(
            lessons,
            day=weekday,
            when=today,
            show_group=True,
            show_teacher=False,
        )
        await bot.send_message(
            chat_id=chat_id,
            text=f"{header}\n\n{body}",
            attachments=[kb.mine_menu(teacher).as_markup()],
        )
        return

    group_name = user.get("group_name")
    if not group_name:
        return

    group = index.find(group_name)
    if group is None:
        return

    await photos.send_schedule(
        bot,
        chat_id,
        group,
        caption=f"{header}\n\nРасписание группы {group.name}",
        keyboard=kb.schedule_result(group.name, is_mine=True).as_markup(),
    )


def _weekday_name(weekday: int) -> str:
    from services.timetable import DAY_NAMES

    return DAY_NAMES.get(weekday, "")


async def tick(bot: Bot, now: datetime | None = None) -> None:
    """Один проход: изменения расписаний и утренняя рассылка."""
    await check_schedule_changes(bot)
    await send_morning_digest(bot, now)
