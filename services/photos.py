"""Отправка картинок расписания с кэшем загрузок.

Одно и то же расписание спрашивают десятки раз в день. Чтобы не
загружать файл на серверы MAX при каждом запросе, запоминаем токен
вложения и переиспользуем его, пока файл не изменился.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maxapi.types.input_media import InputMedia

if TYPE_CHECKING:
    from maxapi import Bot

    from services.groups import Group

logger = logging.getLogger(__name__)

#: group.key -> (mtime файла, объект загруженного вложения)
_cache: dict[str, tuple[float, Any]] = {}


async def _upload(bot: Bot, group: Group) -> Any | None:
    """Загружает файл на серверы MAX и возвращает вложение с токеном."""
    cached = _cache.get(group.key)
    if cached and cached[0] == group.mtime:
        return cached[1]

    try:
        uploaded = await bot.upload_media(InputMedia(path=str(group.path)))
    except Exception:  # noqa: BLE001 — падать из-за кэша не будем
        logger.warning("Не удалось предзагрузить %s", group.path, exc_info=True)
        return None

    _cache[group.key] = (group.mtime, uploaded)
    return uploaded


async def upload_file(bot: Bot, path: Path) -> Any | None:
    """Загружает файл на серверы MAX один раз и дальше отдаёт токен.

    Нужна для картинок, которые бот шлёт часто и всем подряд, —
    например, приветственного баннера.
    """
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None

    key = f"file:{path}"
    cached = _cache.get(key)
    if cached and cached[0] == mtime:
        return cached[1]

    try:
        uploaded = await bot.upload_media(InputMedia(path=str(path)))
    except Exception:  # noqa: BLE001
        logger.warning("Не удалось загрузить %s", path, exc_info=True)
        return None

    _cache[key] = (mtime, uploaded)
    return uploaded


def forget(group_key: str) -> None:
    """Сбрасывает кэш для группы (например, после ошибки отправки)."""
    _cache.pop(group_key, None)


async def send_schedule(
    bot: Bot,
    chat_id: int,
    group: Group,
    *,
    caption: str,
    keyboard: Any | None = None,
) -> None:
    """Отправляет расписание группы в чат.

    Сначала пробуем отправить по сохранённому токену; если токен
    протух — грузим файл заново. Если MAX не принимает картинку вместе
    с клавиатурой, отправляем их двумя сообщениями.
    """
    uploaded = await _upload(bot, group)
    attachments: list[Any] = []
    if uploaded is not None:
        attachments.append(uploaded)
    else:
        attachments.append(InputMedia(path=str(group.path)))

    if keyboard is not None:
        attachments.append(keyboard)

    try:
        await bot.send_message(
            chat_id=chat_id, text=caption, attachments=attachments
        )
        return
    except Exception:  # noqa: BLE001
        logger.warning(
            "Не удалось отправить расписание %s одним сообщением",
            group.name,
            exc_info=True,
        )
        forget(group.key)

    # Запасной путь: файл напрямую, клавиатура — отдельным сообщением.
    await bot.send_message(
        chat_id=chat_id,
        text=caption,
        attachments=[InputMedia(path=str(group.path))],
    )
    if keyboard is not None:
        await bot.send_message(
            chat_id=chat_id,
            text="Что дальше?",
            attachments=[keyboard],
        )
