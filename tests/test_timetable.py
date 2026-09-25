"""Проверка текстового расписания: группы, преподаватели, поиск.

Запуск:  python tests/test_timetable.py
Тест не требует ни maxapi, ни подключения к сети.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.groups import GroupIndex, normalize  # noqa: E402
from services.timetable import format_day, format_week, timetable  # noqa: E402

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}")
        FAILURES.append(message)


def main() -> int:
    timetable.refresh(force=True)

    if not timetable.available:
        print("Файл data/timetable.json не найден.")
        print("Соберите его: python tools/build_timetable.py")
        return 1

    groups = timetable.groups()
    teachers = timetable.teachers()
    print(f"Данные собраны: {timetable.generated}")
    print(f"Групп: {len(groups)}, преподавателей: {len(teachers)}\n")

    print("Соответствие фотографиям расписаний:")
    index = GroupIndex()
    index.refresh(force=True)
    if len(index):
        photo_keys = {group.key for group in index.groups}
        data_keys = {normalize(name) for name in groups}
        missing = photo_keys - data_keys
        extra = data_keys - photo_keys
        check(not missing, f"для каждой фотографии есть данные ({len(photo_keys)})")
        if missing:
            print("    нет данных для:", missing)
        check(not extra, "лишних групп в данных нет")
        if extra:
            print("    лишние:", extra)
    else:
        print("  (папка schedules недоступна — пропускаю)")

    print("\nЦелостность данных:")
    lessons = [l for g in groups for l in timetable.for_group(g)]
    check(
        all(1 <= l.number <= 10 for l in lessons),
        f"номера уроков в пределах 1–10 ({len(lessons)} занятий)",
    )
    check(all(l.subject for l in lessons), "у каждого занятия есть дисциплина")
    check(
        all(l.teachers for l in lessons), "у каждого занятия есть преподаватель"
    )
    check(
        all(1 <= l.day <= 6 for l in lessons), "дни недели в пределах пн–сб"
    )

    print("\nПоиск преподавателя:")
    sample = teachers[0]
    surname = sample.split()[0]
    check(timetable.find_teachers(surname) != [], f"по фамилии «{surname}»")
    check(
        timetable.find_teachers(surname.lower()) != [],
        "регистр не важен",
    )
    check(timetable.find_teachers(sample) == [sample], "по полному ФИО")
    check(timetable.find_teachers("Несуществующий") == [], "чужая фамилия не найдена")

    print("\nЛичное расписание:")
    busiest = max(teachers, key=lambda t: len(timetable.for_teacher(t)))
    personal = timetable.for_teacher(busiest)
    used_groups = {lesson.group for lesson in personal}
    check(
        len(used_groups) > 1,
        f"{busiest}: {len(personal)} занятий в {len(used_groups)} группах",
    )

    found = timetable.next_for_teacher(busiest, datetime(2026, 9, 21, 7, 0))
    check(found is not None, "ближайший урок находится")
    if found:
        lesson, moment = found
        print(
            f"       {moment:%d.%m %H:%M} — {lesson.subject}, "
            f"группа {lesson.group}, ауд. {lesson.room}"
        )

    print("\nФорматирование:")
    check(bool(format_day(personal[:3], day=1)), "день оформляется")
    check(bool(format_week(personal)), "неделя оформляется")

    print("\nАудитории:")
    check(bool(timetable.rooms()), f"аудиторий в расписании: {len(timetable.rooms())}")
    free = timetable.free_rooms(1, 1)
    check(
        len(free) < len(timetable.rooms()),
        f"в понедельник на 1 уроке свободно {len(free)} аудиторий",
    )

    print()
    if FAILURES:
        print(f"ПРОВАЛЕНО проверок: {len(FAILURES)}")
        return 1
    print("Все проверки пройдены ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
