"""Раздел «База материалов» — общая копилка файлов и ссылок."""

from __future__ import annotations

import logging
import re

from maxapi import Router
from maxapi.context.base import BaseContext
from maxapi.enums.upload_type import UploadType
from maxapi.types.attachments.upload import AttachmentPayload, AttachmentUpload
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated

import db
import keyboards as kb
import texts
from filters import Payload, PayloadPrefix
from states import MaterialSG
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
router = Router("materials")

_TAG_RE = re.compile(r"#([\w\-]+)", re.UNICODE)
_URL_RE = re.compile(r"https?://\S+")

#: Соответствие типа вложения MAX и типа загрузки для пересылки.
_KIND_TO_UPLOAD = {
    "image": UploadType.IMAGE,
    "video": UploadType.VIDEO,
    "audio": UploadType.AUDIO,
    "file": UploadType.FILE,
}


def _title_and_tags(raw: str, fallback: str) -> tuple[str, str]:
    tags = " ".join(sorted({tag.lower() for tag in _TAG_RE.findall(raw)}))
    title = _TAG_RE.sub("", raw).strip(" \n-—·")
    return (title or fallback), tags


def _describe(material: dict) -> str:
    icon = {
        "image": "🖼",
        "video": "🎬",
        "audio": "🎧",
        "file": "📎",
        "link": "🔗",
        "text": "📄",
    }.get(material["kind"], "📎")
    parts = [f"{icon} {material['title']}"]
    if material["tags"]:
        parts.append("Теги: " + " ".join(
            f"#{tag}" for tag in material["tags"].split()
        ))
    if material["author"]:
        parts.append(f"Добавил(а): {material['author']}")
    if material["url"]:
        parts.append(material["url"])
    if material["body"]:
        parts.append("\n" + material["body"])
    return "\n".join(parts)


@router.message_callback(Payload(kb.CB_MATERIALS))
async def cb_materials(event: MessageCallback, context: BaseContext) -> None:
    await remember_user(event)
    await context.clear()
    materials = await db.list_materials(limit=5)
    total = len(await db.list_materials(limit=1000))
    text = (
        "📚 База материалов\n\n"
        f"Сейчас в копилке: {total}.\n"
        "Добавляйте презентации, методички и ссылки — коллеги найдут "
        "их по ключевому слову."
    )
    if materials:
        text += "\n\nПоследнее добавленное:\n" + "\n".join(
            f"• {item['title']}" for item in materials
        )
    await event.edit(text=text, attachments=[kb.materials_menu().as_markup()])


@router.message_callback(Payload(kb.CB_MATERIALS_ADD))
async def cb_add(event: MessageCallback, context: BaseContext) -> None:
    await context.set_state(MaterialSG.waiting_content)
    await event.edit(
        text=texts.ASK_MATERIAL, attachments=[kb.cancel_only().as_markup()]
    )


@router.message_callback(Payload(kb.CB_MATERIALS_FIND))
async def cb_find(event: MessageCallback, context: BaseContext) -> None:
    await context.set_state(MaterialSG.waiting_query)
    await event.edit(
        text=texts.ASK_MATERIAL_QUERY,
        attachments=[kb.cancel_only().as_markup()],
    )


@router.message_callback(Payload(kb.CB_MATERIALS_ALL))
async def cb_all(event: MessageCallback) -> None:
    materials = await db.list_materials(limit=15)
    if not materials:
        await event.edit(
            text="Пока пусто. Добавьте первый материал 🙂",
            attachments=[kb.materials_menu().as_markup()],
        )
        return
    await event.edit(
        text="📂 Последние материалы — выберите нужный:",
        attachments=[kb.materials_results(materials).as_markup()],
    )


@router.message_created(MaterialSG.waiting_query)
async def on_query(event: MessageCreated, context: BaseContext) -> None:
    query = text_of(event)
    if not query:
        return
    await context.clear()

    found = await db.search_materials(query)
    if not found:
        await event.message.answer(
            text=f"По запросу «{query}» ничего не нашлось.",
            attachments=[kb.materials_menu().as_markup()],
        )
        return

    await event.message.answer(
        text=f"Нашёл {len(found)} — выберите материал:",
        attachments=[kb.materials_results(found).as_markup()],
    )


@router.message_created(MaterialSG.waiting_content)
async def on_material(event: MessageCreated, context: BaseContext) -> None:
    """Принимает файл, ссылку или текст и кладёт его в базу."""
    await remember_user(event)
    chat_id, user_id = ids_of(event)
    if not user_id:
        return

    body = event.message.body
    caption = (getattr(body, "text", None) or "").strip()
    attachments = list(getattr(body, "attachments", None) or [])

    kind = "text"
    token: str | None = None
    url: str | None = None
    note: str | None = None
    fallback_title = "Материал"

    if attachments:
        attachment = attachments[0]
        kind = str(getattr(attachment, "type", "file"))
        payload = getattr(attachment, "payload", None)
        token = getattr(payload, "token", None)
        url = getattr(payload, "url", None)
        fallback_title = (
            getattr(attachment, "filename", None) or "Файл без названия"
        )
        if kind not in _KIND_TO_UPLOAD:
            kind = "file"
    elif match := _URL_RE.search(caption):
        kind = "link"
        url = match.group(0)
        caption = caption.replace(url, "").strip()
        fallback_title = url
    else:
        kind = "text"
        note = caption
        fallback_title = caption[:60] or "Заметка"

    title, tags = _title_and_tags(caption, fallback_title)
    await context.clear()

    material_id = await db.add_material(
        user_id=user_id,
        author=user_name(event),
        title=title,
        tags=tags,
        kind=kind,
        token=token,
        url=url,
        body=note,
    )

    await event.message.answer(
        text=(
            "✅ Материал добавлен в общую базу\n\n"
            f"Название: {title}\n"
            + (f"Теги: {tags}\n" if tags else "")
            + f"Номер: {material_id}"
        ),
        attachments=[kb.materials_menu().as_markup()],
    )


@router.message_callback(PayloadPrefix(kb.CB_MATERIALS_GET))
async def cb_get(event: MessageCallback) -> None:
    raw = payload_arg(payload_of(event), kb.CB_MATERIALS_GET)
    chat_id, _user_id = ids_of(event)
    await ack(event, "Отправляю материал…")

    if not raw.isdigit() or chat_id is None:
        return

    material = await db.get_material(int(raw))
    if material is None:
        await event.bot.send_message(
            chat_id=chat_id, text="Материал не найден — возможно, он удалён."
        )
        return

    attachments = []
    upload_type = _KIND_TO_UPLOAD.get(material["kind"])
    if material["token"] and upload_type is not None:
        attachments.append(
            AttachmentUpload(
                type=upload_type,
                payload=AttachmentPayload(token=material["token"]),
            )
        )
    attachments.append(kb.materials_menu().as_markup())

    try:
        await event.bot.send_message(
            chat_id=chat_id, text=_describe(material), attachments=attachments
        )
    except Exception:  # noqa: BLE001
        logger.warning("Не удалось отправить материал %s", raw, exc_info=True)
        text = _describe(material)
        if material["url"]:
            text += f"\n\nСсылка на файл: {material['url']}"
        await event.bot.send_message(
            chat_id=chat_id,
            text=text,
            attachments=[kb.materials_menu().as_markup()],
        )
