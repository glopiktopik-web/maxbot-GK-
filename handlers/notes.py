"""Раздел «Заметки и напоминания»."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from maxapi import Router
from maxapi.context.base import BaseContext
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

import db
import keyboards as kb
import texts
from filters import HasText, Payload, PayloadPrefix
from services.timeparse import human, parse_when
from states import NoteSG
from utils import (
    ack,
    ids_of,
    payload_arg,
    payload_of,
    remember_user,
    text_of,
)

logger = logging.getLogger(__name__)
router = Router("notes")


def _render(notes: list[dict]) -> str:
    if not notes:
        return (
            "📝 Активных задач нет.\n\n"
            "Нажмите «Новая задача», чтобы записать первую."
        )

    lines = ["📝 Ваши задачи:\n"]
    now = datetime.now()
    for position, note in enumerate(notes, start=1):
        when = ""
        if note["remind_at"]:
            moment = datetime.fromisoformat(note["remind_at"])
            mark = "⏰" if moment > now else "❗"
            when = f"  {mark} {human(moment, now)}"
        lines.append(f"{position}. {note['text']}{when}")

    lines.append("\n✅ — выполнено, 🗑 — удалить")
    return "\n".join(lines)


@router.message_callback(Payload(kb.CB_NOTES))
async def cb_notes(event: MessageCallback, context: BaseContext) -> None:
    await remember_user(event)
    await context.clear()
    _chat_id, user_id = ids_of(event)
    notes = await db.list_notes(user_id or 0)
    await event.edit(text=_render(notes), attachments=[kb.notes_menu().as_markup()])


@router.message_callback(Payload(kb.CB_NOTES_LIST))
async def cb_notes_list(event: MessageCallback) -> None:
    _chat_id, user_id = ids_of(event)
    notes = await db.list_notes(user_id or 0)
    keyboard = kb.notes_list(notes) if notes else kb.notes_menu()
    await event.edit(text=_render(notes), attachments=[keyboard.as_markup()])


@router.message_callback(Payload(kb.CB_NOTES_ADD))
async def cb_notes_add(event: MessageCallback, context: BaseContext) -> None:
    await context.set_state(NoteSG.waiting_text)
    await event.edit(
        text=texts.ASK_NOTE_TEXT, attachments=[kb.cancel_only().as_markup()]
    )


@router.message_created(NoteSG.waiting_text, HasText())
async def on_note_text(event: MessageCreated, context: BaseContext) -> None:
    text = text_of(event)
    await context.update_data(note_text=text)
    await context.set_state(NoteSG.waiting_time)
    await event.message.answer(
        text=texts.ASK_NOTE_TIME.format(text=text),
        attachments=[kb.notes_when().as_markup()],
    )


async def _save_note(
    *,
    event,
    context: BaseContext,
    when: datetime | None,
) -> None:
    chat_id, user_id = ids_of(event)
    data = await context.get_data()
    text = (data.get("note_text") or "").strip()
    await context.clear()

    if not text or not user_id:
        return

    await db.add_note(
        user_id,
        chat_id,
        text,
        when.isoformat(timespec="seconds") if when else None,
    )
    tail = f"\n⏰ Напомню {human(when)}" if when else "\nБез напоминания."
    notes = await db.list_notes(user_id)

    message = f"✅ Записал: {text}{tail}"
    if chat_id is not None:
        await event.bot.send_message(
            chat_id=chat_id,
            text=message + "\n\n" + _render(notes),
            attachments=[kb.notes_list(notes).as_markup()],
        )


@router.message_callback(NoteSG.waiting_time, PayloadPrefix(kb.CB_NOTES_WHEN))
async def cb_note_when(event: MessageCallback, context: BaseContext) -> None:
    choice = payload_arg(payload_of(event), kb.CB_NOTES_WHEN)
    now = datetime.now()

    if choice == "none":
        when = None
    elif choice == "1h":
        when = now + timedelta(hours=1)
    elif choice == "3h":
        when = now + timedelta(hours=3)
    elif choice == "tom":
        when = (now + timedelta(days=1)).replace(
            hour=8, minute=30, second=0, microsecond=0
        )
    else:
        await ack(event)
        return

    await ack(event, "Сохраняю задачу…")
    await _save_note(event=event, context=context, when=when)


@router.message_created(NoteSG.waiting_time, HasText())
async def on_note_time_typed(
    event: MessageCreated, context: BaseContext
) -> None:
    raw = text_of(event)
    when = parse_when(raw)
    if when is None:
        await event.message.answer(
            "Не понял время. Примеры: «18:30», «22.09 09:00», "
            "«завтра 8:45», «через 2 часа».",
            attachments=[kb.notes_when().as_markup()],
        )
        return
    await _save_note(event=event, context=context, when=when)


@router.message_callback(PayloadPrefix(kb.CB_NOTES_DONE))
async def cb_note_done(event: MessageCallback) -> None:
    _chat_id, user_id = ids_of(event)
    raw = payload_arg(payload_of(event), kb.CB_NOTES_DONE)
    if raw.isdigit() and user_id:
        await db.set_note_done(int(raw), user_id)

    notes = await db.list_notes(user_id or 0)
    keyboard = kb.notes_list(notes) if notes else kb.notes_menu()
    await event.answer(
        notification="Задача выполнена",
        new_text=_render(notes),
        attachments=[keyboard.as_markup()],
    )


@router.message_callback(PayloadPrefix(kb.CB_NOTES_DEL))
async def cb_note_delete(event: MessageCallback) -> None:
    _chat_id, user_id = ids_of(event)
    raw = payload_arg(payload_of(event), kb.CB_NOTES_DEL)
    if raw.isdigit() and user_id:
        await db.delete_note(int(raw), user_id)

    notes = await db.list_notes(user_id or 0)
    keyboard = kb.notes_list(notes) if notes else kb.notes_menu()
    await event.answer(
        notification="Задача удалена",
        new_text=_render(notes),
        attachments=[keyboard.as_markup()],
    )
