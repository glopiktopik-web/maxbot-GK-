"""Раздел «Отчёты и шаблоны»."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from maxapi import Router
from maxapi.context.base import BaseContext
from maxapi.types.input_media import InputMedia
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

import db
import keyboards as kb
import texts
from config import ORG_NAME
from filters import HasText, Payload, PayloadPrefix
from services import exports
from states import TemplateSG
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
router = Router("reports")


@router.message_callback(Payload(kb.CB_REPORTS))
async def cb_reports(event: MessageCallback, context: BaseContext) -> None:
    await remember_user(event)
    await context.clear()
    _chat_id, user_id = ids_of(event)
    templates = await db.list_templates(user_id or 0)
    await event.edit(
        text=(
            "📊 Отчёты и шаблоны\n\n"
            "Выберите форму — пришлю готовый текст, останется "
            "подставить данные и скопировать."
        ),
        attachments=[kb.reports_menu(templates).as_markup()],
    )


@router.message_callback(PayloadPrefix(kb.CB_REPORTS_GET))
async def cb_template(event: MessageCallback) -> None:
    raw = payload_arg(payload_of(event), kb.CB_REPORTS_GET)
    chat_id, _user_id = ids_of(event)
    await ack(event, "Отправляю шаблон…")

    if not raw.isdigit() or chat_id is None:
        return

    template = await db.get_template(int(raw))
    if template is None:
        return

    body = template["body"].replace("{org}", ORG_NAME)
    await event.bot.send_message(
        chat_id=chat_id,
        text=body,
        attachments=[kb.report_formats(template["id"]).as_markup()],
    )


@router.message_callback(PayloadPrefix(kb.CB_REPORTS_DOCX))
async def cb_template_docx(event: MessageCallback) -> None:
    """Тот же шаблон, но готовым документом Word."""
    raw = payload_arg(payload_of(event), kb.CB_REPORTS_DOCX)
    chat_id, _user_id = ids_of(event)
    await ack(event, "Готовлю документ…")

    if not raw.isdigit() or chat_id is None:
        return

    template = await db.get_template(int(raw))
    if template is None:
        return

    body = template["body"].replace("{org}", ORG_NAME)
    try:
        path = exports.template_docx(
            template["title"], body, author=user_name(event)
        )
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось собрать документ Word")
        await event.bot.send_message(
            chat_id=chat_id,
            text=(
                "Не удалось собрать файл Word.\n"
                "Проверьте, что установлена библиотека python-docx:\n"
                "pip install -r requirements.txt"
            ),
            attachments=[kb.reports_back().as_markup()],
        )
        return

    await event.bot.send_message(
        chat_id=chat_id,
        text=f"📄 {template['title']} — документ готов к заполнению.",
        attachments=[InputMedia(path=str(path)), kb.reports_back().as_markup()],
    )


@router.message_callback(Payload(kb.CB_REPORTS_WEEK))
async def cb_week(event: MessageCallback) -> None:
    """Короткая сводка по задачам преподавателя за неделю."""
    _chat_id, user_id = ids_of(event)
    since = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
    notes = await db.notes_for_period(user_id or 0, since)

    done = [note for note in notes if note["done"]]
    active = [note for note in notes if not note["done"]]

    lines = [
        "📈 Сводка за 7 дней",
        "",
        f"Задач поставлено: {len(notes)}",
        f"Выполнено: {len(done)}",
        f"В работе: {len(active)}",
    ]
    if done:
        lines += ["", "Выполнено:"] + [f"✅ {n['text']}" for n in done[:15]]
    if active:
        lines += ["", "В работе:"] + [f"• {n['text']}" for n in active[:15]]
    if not notes:
        lines += ["", "За неделю задач не было."]

    await event.edit(
        text="\n".join(lines), attachments=[kb.reports_back().as_markup()]
    )


@router.message_callback(Payload(kb.CB_REPORTS_ADD))
async def cb_add_template(event: MessageCallback, context: BaseContext) -> None:
    await context.set_state(TemplateSG.waiting_title)
    await event.edit(
        text=texts.ASK_TEMPLATE_TITLE,
        attachments=[kb.cancel_only().as_markup()],
    )


@router.message_created(TemplateSG.waiting_title, HasText())
async def on_template_title(
    event: MessageCreated, context: BaseContext
) -> None:
    await context.update_data(template_title=text_of(event))
    await context.set_state(TemplateSG.waiting_body)
    await event.message.answer(
        text=texts.ASK_TEMPLATE_BODY,
        attachments=[kb.cancel_only().as_markup()],
    )


@router.message_created(TemplateSG.waiting_body, HasText())
async def on_template_body(
    event: MessageCreated, context: BaseContext
) -> None:
    _chat_id, user_id = ids_of(event)
    data = await context.get_data()
    title = (data.get("template_title") or "Мой шаблон").strip()
    await context.clear()

    if not user_id:
        return

    await db.add_template(user_id, title, text_of(event))
    templates = await db.list_templates(user_id)
    await event.message.answer(
        text=f"✅ Шаблон «{title}» сохранён.",
        attachments=[kb.reports_menu(templates).as_markup()],
    )
