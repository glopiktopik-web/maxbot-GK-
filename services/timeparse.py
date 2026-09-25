"""Разбор времени напоминания, написанного человеком."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

_TIME = r"(\d{1,2})[:.\-](\d{2})"
_DATE_TIME = re.compile(
    rf"^(\d{{1,2}})[.\-/](\d{{1,2}})(?:[.\-/](\d{{2,4}}))?\s+{_TIME}$"
)
_ONLY_TIME = re.compile(rf"^{_TIME}$")
_TOMORROW = re.compile(rf"^завтра\s+{_TIME}$", re.IGNORECASE)
_TODAY = re.compile(rf"^сегодня\s+{_TIME}$", re.IGNORECASE)
_IN_MINUTES = re.compile(r"^через\s+(\d{1,4})\s*(мин\w*)$", re.IGNORECASE)
_IN_HOURS = re.compile(r"^через\s+(\d{1,3})\s*(ч\w*)$", re.IGNORECASE)
_IN_DAYS = re.compile(r"^через\s+(\d{1,3})\s*(д\w*)$", re.IGNORECASE)


def parse_when(raw: str, now: datetime | None = None) -> datetime | None:
    """Превращает текст в момент времени.

    Понимает: «18:30», «22.09 09:00», «22.09.2026 9:00», «завтра 8:45»,
    «сегодня 18:00», «через 20 минут», «через 2 часа», «через 3 дня».
    Возвращает None, если распознать не удалось.
    """
    text = (raw or "").strip().lower().replace("ё", "е")
    if not text:
        return None
    now = now or datetime.now()

    if match := _IN_MINUTES.match(text):
        return now + timedelta(minutes=int(match.group(1)))
    if match := _IN_HOURS.match(text):
        return now + timedelta(hours=int(match.group(1)))
    if match := _IN_DAYS.match(text):
        return now + timedelta(days=int(match.group(1)))

    if match := _DATE_TIME.match(text):
        day, month, year, hour, minute = match.groups()
        year_value = now.year if year is None else int(year)
        if year_value < 100:
            year_value += 2000
        try:
            return datetime(
                year_value, int(month), int(day), int(hour), int(minute)
            )
        except ValueError:
            return None

    for pattern, day_shift in ((_ONLY_TIME, 0), (_TODAY, 0), (_TOMORROW, 1)):
        if match := pattern.match(text):
            hour, minute = int(match.group(1)), int(match.group(2))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return None
            moment = now.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            ) + timedelta(days=day_shift)
            if pattern is _ONLY_TIME and moment <= now:
                # «18:30» вечером — значит, завтра.
                moment += timedelta(days=1)
            return moment

    return None


def human(moment: datetime, now: datetime | None = None) -> str:
    """Форматирует момент времени коротко и понятно."""
    now = now or datetime.now()
    if moment.date() == now.date():
        return f"сегодня в {moment:%H:%M}"
    if moment.date() == (now + timedelta(days=1)).date():
        return f"завтра в {moment:%H:%M}"
    return f"{moment:%d.%m.%Y} в {moment:%H:%M}"
