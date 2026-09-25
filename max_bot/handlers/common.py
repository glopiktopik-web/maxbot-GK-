"""Старт, главное меню, справка, отмена."""

from __future__ import annotations

import logging

from maxapi import Router
from maxapi.context.base import BaseContext
from maxapi.filters.command import Command, CommandStart
from maxapi.types.updates.bot_started import BotStarted
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

import db
import keyboards as kb
import texts
from config import WELCOME_IMAGE
from filters import Payload
from services.photos import upload_file
from utils import ids_of, remember_user, user_name

logger = logging.getLogger(__name__)
router = Router("common")


async def show_menu_message(event: MessageCreated) -> None:
    await event.message.answer(
        text=texts.MENU, attachments=[kb.main_menu().as_markup()]
    )


async def send_welcome(bot, chat_id: int, name: str) -> None:
    """Приветствие с баннером бота.

    Баннер и меню уходят **двумя** сообщениями. Так задумано: кнопки
    меню перерисовывают своё сообщение, и если бы картинка висела
    в том же сообщении, она пропала бы после первого же нажатия.
    Отдельным сообщением баннер остаётся в переписке навсегда.

    Баннер загружается на серверы MAX один раз и дальше уходит
    по токену. Если картинка недоступна, шлём обычное приветствие —
    приветствие важнее картинки.
    """
    text = texts.WELCOME.format(name=name)
    keyboard = kb.main_menu().as_markup()

    banner = await upload_file(bot, WELCOME_IMAGE)
    if banner is not None:
        try:
            await bot.send_message(
                chat_id=chat_id, text=text, attachments=[banner]
            )
        except Exception:  # noqa: BLE001
            logger.warning("Не удалось отправить баннер", exc_info=True)
        else:
            # Меню — отдельным сообщением, его и будут перерисовывать кнопки.
            await bot.send_message(
                chat_id=chat_id, text=texts.MENU, attachments=[keyboard]
            )
            return

    await bot.send_message(chat_id=chat_id, text=text, attachments=[keyboard])


@router.bot_started()
async def on_bot_started(event: BotStarted) -> None:
    """Пользователь открыл бота впервые."""
    await db.upsert_user(event.user.user_id, event.chat_id, user_name(event))
    await send_welcome(event.bot, event.chat_id, user_name(event))


@router.message_created(CommandStart())
async def cmd_start(event: MessageCreated, context: BaseContext) -> None:
    await context.clear()
    await remember_user(event)
    chat_id, _user_id = ids_of(event)
    if chat_id is None:
        return
    await send_welcome(event.bot, chat_id, user_name(event))


@router.message_created(Command("menu"))
async def cmd_menu(event: MessageCreated, context: BaseContext) -> None:
    await context.clear()
    await remember_user(event)
    await show_menu_message(event)


@router.message_created(Command("help"))
async def cmd_help(event: MessageCreated) -> None:
    await remember_user(event)
    await event.message.answer(
        text=texts.HELP, attachments=[kb.only_menu().as_markup()]
    )


@router.message_created(Command("cancel"))
async def cmd_cancel(event: MessageCreated, context: BaseContext) -> None:
    current = await context.get_state()
    await context.clear()
    if current is None:
        await event.message.answer(texts.NOTHING_TO_CANCEL)
        return
    await event.message.answer(
        text=texts.CANCELLED, attachments=[kb.main_menu().as_markup()]
    )


@router.message_created(Command("id"))
async def cmd_id(event: MessageCreated) -> None:
    """Подсказка для настройки администраторов."""
    _chat_id, user_id = ids_of(event)
    await event.message.answer(f"Ваш ID в MAX: {user_id}")


@router.message_callback(Payload(kb.CB_MENU))
async def cb_menu(event: MessageCallback, context: BaseContext) -> None:
    await context.clear()
    await remember_user(event)
    await event.edit(
        text=texts.MENU, attachments=[kb.main_menu().as_markup()]
    )


@router.message_callback(Payload(kb.CB_HELP))
async def cb_help(event: MessageCallback) -> None:
    await event.edit(
        text=texts.HELP, attachments=[kb.only_menu().as_markup()]
    )


@router.message_callback(Payload(kb.CB_CANCEL))
async def cb_cancel(event: MessageCallback, context: BaseContext) -> None:
    await context.clear()
    await event.edit(
        text=texts.CANCELLED, attachments=[kb.main_menu().as_markup()]
    )
