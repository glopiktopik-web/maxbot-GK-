"""«Арсенал мастера» — бот-помощник преподавателя для мессенджера MAX.

Запуск:
    python bot.py

Токен берётся из файла .env (переменная MAX_BOT_TOKEN).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys

from maxapi import ErrorEvent
from maxapi.types.command import BotCommand

import db
from config import ADMIN_IDS, BOT_TOKEN, DB_PATH, SCHEDULES_DIR
from handlers import routers
from loader import bot, dp
from services import reminders
from services.groups import index
from services.timetable import timetable

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("arsenal")

COMMANDS = (
    BotCommand(name="start", description="Главное меню"),
    BotCommand(name="menu", description="Главное меню"),
    BotCommand(name="schedule", description="Расписание учебных занятий"),
    BotCommand(name="me", description="Моё расписание"),
    BotCommand(name="help", description="Что умеет бот"),
    BotCommand(name="cancel", description="Отменить текущее действие"),
    BotCommand(name="id", description="Показать мой ID"),
)

dp.include_routers(*routers)


@dp.on_started()
async def on_started() -> None:
    """Подготовка при старте: БД, индекс расписаний, команды, напоминания."""
    await db.init_db()
    logger.info("База данных: %s", DB_PATH)

    index.refresh(force=True)
    if len(index):
        logger.info(
            "Расписаний загружено: %s (папка %s)", len(index), SCHEDULES_DIR
        )
    else:
        logger.warning(
            "В папке %s не найдено ни одной картинки расписания!",
            SCHEDULES_DIR,
        )

    timetable.refresh(force=True)
    if timetable.available:
        logger.info(
            "Текстовое расписание: %s групп, %s преподавателей",
            len(timetable.groups()),
            len(timetable.teachers()),
        )
    else:
        logger.warning(
            "Файл data/timetable.json не найден — разделы «Моё расписание» "
            "и «Справочники» будут работать без данных. "
            "Соберите его: python tools/build_timetable.py"
        )

    if ADMIN_IDS:
        logger.info("Администраторы: %s", ", ".join(map(str, ADMIN_IDS)))
    else:
        logger.info(
            "Администраторы не заданы — рассылка объявлений недоступна. "
            "Добавьте ADMIN_IDS в .env (свой ID покажет команда /id)."
        )

    with contextlib.suppress(Exception):
        await bot.set_commands(*COMMANDS)

    reminders.start(bot)
    logger.info("Бот «Арсенал мастера» готов к работе")


@dp.errors(Exception)
async def on_error(event: ErrorEvent) -> None:
    """Никакая ошибка не должна ронять бота."""
    logger.exception("Ошибка при обработке события: %s", event.exception)


async def main() -> None:
    if not BOT_TOKEN:
        logger.error(
            "Не найден токен бота. Укажите MAX_BOT_TOKEN в файле .env "
            "рядом с bot.py."
        )
        sys.exit(1)

    try:
        await dp.start_polling(bot)
    finally:
        await reminders.stop()
        await db.close_db()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
