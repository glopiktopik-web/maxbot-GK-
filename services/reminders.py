"""Фоновая задача: рассылка напоминаний о задачах."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime
from typing import TYPE_CHECKING

import db
from config import REMINDER_TICK_SECONDS

if TYPE_CHECKING:
    from maxapi import Bot

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


async def _tick(bot: Bot) -> None:
    now_iso = datetime.now().isoformat(timespec="seconds")
    for note in await db.due_notes(now_iso):
        chat_id = note.get("chat_id")
        if not chat_id:
            await db.mark_notified(note["id"])
            continue

        from keyboards import note_reminder_keyboard

        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f"⏰ Напоминание\n\n{note['text']}",
                attachments=[note_reminder_keyboard(note["id"]).as_markup()],
            )
        except Exception:  # noqa: BLE001 — один сбой не должен ронять цикл
            logger.warning(
                "Не удалось отправить напоминание #%s", note["id"], exc_info=True
            )
        finally:
            await db.mark_notified(note["id"])


async def _loop(bot: Bot) -> None:
    from services import watcher

    while True:
        try:
            await _tick(bot)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка в цикле напоминаний")

        try:
            await watcher.tick(bot)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка в цикле наблюдения за расписанием")

        await asyncio.sleep(REMINDER_TICK_SECONDS)


def start(bot: Bot) -> None:
    """Запускает фоновый цикл напоминаний."""
    global _task
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_loop(bot), name="reminders")
    logger.info("Цикл напоминаний запущен")


async def stop() -> None:
    """Останавливает фоновый цикл."""
    global _task
    if _task is None:
        return
    _task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _task
    _task = None
