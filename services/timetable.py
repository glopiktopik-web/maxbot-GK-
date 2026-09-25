"""Расписание в структурированном виде: запросы по группе и преподавателю.

Данные лежат в ``data/timetable.json`` и собираются скриптом
``tools/build_timetable.py`` из выгрузок расписаний. Картинка из папки
``schedules`` остаётся первоисточником, а эти данные дают то, чего
картинка не умеет: личное расписание преподавателя, следующий урок,
занятость аудиторий.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from config import BASE_DIR

logger = logging.getLogger(__name__)

DATA_PATH = BASE_DIR / "data" / "timetable.json"

DAY_NAMES = {
    1: "понедельник",
    2: "вторник",
    3: "среда",
    4: "четверг",
    5: "пятница",
    6: "суббота",
    7: "воскресенье",
}

DEFAULT_BELLS = [
    ("08:30", "09:15"),
    ("09:20", "10:05"),
    ("10:15", "11:00"),
    ("11:05", "11:50"),
    ("12:40", "13:25"),
    ("13:30", "14:15"),
    ("14:25", "15:10"),
    ("15:15", "16:00"),
    ("16:05", "16:50"),
    ("16:55", "17:40"),
]


@dataclass(frozen=True)
class Lesson:
    """Одно занятие в расписании."""

    group: str
    day: int  #: 1 = понедельник
    number: int  #: номер урока
    subject: str
    room: str
    teachers: tuple[str, ...]

    def time_range(self, bells: list[tuple[str, str]]) -> tuple[str, str]:
        if 1 <= self.number <= len(bells):
            return bells[self.number - 1]
        return ("", "")

    def starts_at(self, bells: list[tuple[str, str]]) -> time | None:
        start, _end = self.time_range(bells)
        if not start:
            return None
        hour, minute = start.split(":")
        return time(int(hour), int(minute))

    def ends_at(self, bells: list[tuple[str, str]]) -> time | None:
        _start, end = self.time_range(bells)
        if not end:
            return None
        hour, minute = end.split(":")
        return time(int(hour), int(minute))

    def teachers_text(self) -> str:
        if len(self.teachers) > 1:
            return " / ".join(
                f"{i} п/г {name}"
                for i, name in enumerate(self.teachers, start=1)
            )
        return self.teachers[0] if self.teachers else ""


def _surname(full_name: str) -> str:
    return full_name.split()[0].lower().replace("ё", "е") if full_name else ""


class Timetable:
    """Загруженное расписание с автоматическим обновлением при изменении."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or DATA_PATH)
        self._mtime: float | None = None
        self._lessons: list[Lesson] = []
        self._bells: list[tuple[str, str]] = list(DEFAULT_BELLS)
        self._generated: str = ""

    # ── загрузка ──────────────────────────────────────────────────────
    def refresh(self, *, force: bool = False) -> None:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            self._lessons = []
            return

        if not force and self._mtime == mtime and self._lessons:
            return

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("Не удалось прочитать %s", self.path, exc_info=True)
            self._lessons = []
            return

        self._bells = [tuple(pair) for pair in payload.get("bells", DEFAULT_BELLS)]
        self._generated = payload.get("generated", "")
        self._lessons = [
            Lesson(
                group=item["g"],
                day=int(item["d"]),
                number=int(item["n"]),
                subject=item["s"],
                room=item.get("r", ""),
                teachers=tuple(item.get("t", [])),
            )
            for item in payload.get("lessons", [])
        ]
        self._mtime = mtime
        logger.info(
            "Расписание загружено: %s занятий, %s групп",
            len(self._lessons),
            len(self.groups()),
        )

    @property
    def available(self) -> bool:
        self.refresh()
        return bool(self._lessons)

    @property
    def generated(self) -> str:
        self.refresh()
        return self._generated

    @property
    def bells(self) -> list[tuple[str, str]]:
        self.refresh()
        return self._bells

    # ── справочники ───────────────────────────────────────────────────
    def groups(self) -> list[str]:
        self.refresh()
        return sorted({lesson.group for lesson in self._lessons})

    def teachers(self) -> list[str]:
        self.refresh()
        return sorted({name for l in self._lessons for name in l.teachers})

    def rooms(self) -> list[str]:
        self.refresh()
        return sorted({l.room for l in self._lessons if l.room})

    def find_teachers(self, query: str) -> list[str]:
        """Преподаватели, подходящие под запрос (фамилия целиком или начало)."""
        self.refresh()
        text = re.sub(r"\s+", " ", (query or "").strip().lower()).replace("ё", "е")
        if not text:
            return []

        exact = [t for t in self.teachers() if t.lower().replace("ё", "е") == text]
        if exact:
            return exact

        starts = [
            t
            for t in self.teachers()
            if t.lower().replace("ё", "е").startswith(text)
            or _surname(t).startswith(text)
        ]
        if starts:
            return sorted(starts)

        return sorted(
            t for t in self.teachers() if text in t.lower().replace("ё", "е")
        )

    # ── выборки ───────────────────────────────────────────────────────
    def for_group(self, group: str, day: int | None = None) -> list[Lesson]:
        self.refresh()
        target = group.strip().lower()
        found = [l for l in self._lessons if l.group.lower() == target]
        if day is not None:
            found = [l for l in found if l.day == day]
        return sorted(found, key=lambda l: (l.day, l.number))

    def for_teacher(self, teacher: str, day: int | None = None) -> list[Lesson]:
        self.refresh()
        target = teacher.strip().lower().replace("ё", "е")
        found = [
            l
            for l in self._lessons
            if any(name.lower().replace("ё", "е") == target for name in l.teachers)
        ]
        if day is not None:
            found = [l for l in found if l.day == day]
        return sorted(found, key=lambda l: (l.day, l.number))

    def next_for_teacher(
        self, teacher: str, now: datetime | None = None
    ) -> tuple[Lesson, datetime] | None:
        """Ближайшее занятие преподавателя и его дата-время начала."""
        return self._next(self.for_teacher(teacher), now)

    def next_for_group(
        self, group: str, now: datetime | None = None
    ) -> tuple[Lesson, datetime] | None:
        return self._next(self.for_group(group), now)

    def _next(
        self, lessons: list[Lesson], now: datetime | None
    ) -> tuple[Lesson, datetime] | None:
        if not lessons:
            return None
        now = now or datetime.now()
        bells = self.bells

        for offset in range(0, 8):  # неделя вперёд
            day = now.date() + timedelta(days=offset)
            weekday = day.isoweekday()
            for lesson in sorted(
                (l for l in lessons if l.day == weekday),
                key=lambda l: l.number,
            ):
                start = lesson.starts_at(bells)
                if start is None:
                    continue
                moment = datetime.combine(day, start)
                if moment > now:
                    return lesson, moment
        return None

    def room_busy(self, room: str, day: int, number: int) -> list[Lesson]:
        self.refresh()
        target = room.strip().lower()
        return [
            l
            for l in self._lessons
            if l.room.lower() == target and l.day == day and l.number == number
        ]

    def free_rooms(self, day: int, number: int) -> list[str]:
        self.refresh()
        busy = {
            l.room
            for l in self._lessons
            if l.day == day and l.number == number and l.room
        }
        return [room for room in self.rooms() if room not in busy]


#: Общее расписание на всё приложение.
timetable = Timetable()


# ── форматирование ─────────────────────────────────────────────────────────
def day_header(day: int, when: date | None = None) -> str:
    name = DAY_NAMES.get(day, "")
    if when is not None:
        return f"{name.capitalize()}, {when:%d.%m}"
    return name.capitalize()


def format_day(
    lessons: list[Lesson],
    *,
    day: int,
    when: date | None = None,
    show_group: bool = False,
    show_teacher: bool = True,
) -> str:
    """Расписание одного дня в виде текста."""
    bells = timetable.bells
    if not lessons:
        return f"{day_header(day, when)} — занятий нет 🎉"

    lines = [day_header(day, when), ""]
    for lesson in sorted(lessons, key=lambda l: l.number):
        start, end = lesson.time_range(bells)
        head = f"{lesson.number} урок  {start}–{end}"
        body = lesson.subject
        if show_group:
            body = f"{lesson.group} · {body}"
        tail = []
        if lesson.room:
            tail.append(f"ауд. {lesson.room}")
        if show_teacher and lesson.teachers:
            tail.append(lesson.teachers_text())
        lines.append(head)
        lines.append(f"   {body}" + (f"\n   {' · '.join(tail)}" if tail else ""))
    return "\n".join(lines)


def format_week(
    lessons: list[Lesson], *, show_group: bool = False, show_teacher: bool = False
) -> str:
    """Расписание на неделю."""
    if not lessons:
        return "Занятий не найдено."

    chunks: list[str] = []
    for day in range(1, 7):
        day_lessons = [l for l in lessons if l.day == day]
        if not day_lessons:
            continue
        chunks.append(
            format_day(
                day_lessons,
                day=day,
                show_group=show_group,
                show_teacher=show_teacher,
            )
        )
    return "\n\n".join(chunks) if chunks else "Занятий не найдено."


def format_bells() -> str:
    lines = ["🔔 Расписание звонков", ""]
    for number, (start, end) in enumerate(timetable.bells, start=1):
        lines.append(f"{number} урок   {start} – {end}")
    lines.append("")
    lines.append("Большая перемена после 4 урока: 11:50 – 12:40")
    return "\n".join(lines)
