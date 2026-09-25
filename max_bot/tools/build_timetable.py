"""Сборка data/timetable.json из текстовых выгрузок расписаний.

Исходные файлы лежат в tools/raw/*.txt и имеют вид:

    GROUP 21П
    ПН 1 Осн.фин.грам.|315|Мартынова И.М.
    ЧТ 5 Иностранный язык|314а|Ковешникова С.В.//Балыкова Л.С.

где «//» разделяет преподавателей первой и второй подгрупп.

Запуск:  python tools/build_timetable.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = Path(__file__).resolve().parent / "raw"
OUT_PATH = BASE_DIR / "data" / "timetable.json"

DAYS = {"ПН": 1, "ВТ": 2, "СР": 3, "ЧТ": 4, "ПТ": 5, "СБ": 6}

#: Расписание звонков — одинаково для всех групп.
BELLS = [
    ["08:30", "09:15"],
    ["09:20", "10:05"],
    ["10:15", "11:00"],
    ["11:05", "11:50"],
    ["12:40", "13:25"],
    ["13:30", "14:15"],
    ["14:25", "15:10"],
    ["15:15", "16:00"],
    ["16:05", "16:50"],
    ["16:55", "17:40"],
]

_LINE = re.compile(r"^(ПН|ВТ|СР|ЧТ|ПТ|СБ)\s+(\d{1,2})\s+(.+)$")


def parse_file(path: Path) -> list[dict]:
    lessons: list[dict] = []
    group: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("GROUP "):
            group = line[6:].strip()
            continue

        match = _LINE.match(line)
        if not match:
            print(f"  ? пропущена строка в {path.name}: {line}")
            continue

        if group is None:
            raise ValueError(f"{path.name}: урок до объявления группы")

        day_name, number, rest = match.groups()
        parts = rest.split("|")
        subject = parts[0].strip()
        room = parts[1].strip() if len(parts) > 1 else ""
        teachers_raw = parts[2].strip() if len(parts) > 2 else ""
        teachers = [t.strip() for t in teachers_raw.split("//") if t.strip()]

        lessons.append(
            {
                "g": group,
                "d": DAYS[day_name],
                "n": int(number),
                "s": subject,
                "r": room,
                "t": teachers,
            }
        )

    return lessons


def main() -> int:
    if not RAW_DIR.is_dir():
        print(f"Нет папки с исходными данными: {RAW_DIR}")
        return 1

    lessons: list[dict] = []
    for path in sorted(RAW_DIR.glob("*.txt")):
        found = parse_file(path)
        print(f"{path.name}: {len(found)} занятий")
        lessons.extend(found)

    lessons.sort(key=lambda item: (item["g"], item["d"], item["n"]))

    groups = sorted({item["g"] for item in lessons})
    teachers = sorted({name for item in lessons for name in item["t"]})
    rooms = sorted({item["r"] for item in lessons if item["r"]})

    payload = {
        "generated": date.today().isoformat(),
        "bells": BELLS,
        "groups": groups,
        "teachers": teachers,
        "rooms": rooms,
        "lessons": lessons,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print()
    print(f"Групп: {len(groups)}")
    print(f"Преподавателей: {len(teachers)}")
    print(f"Аудиторий: {len(rooms)}")
    print(f"Занятий: {len(lessons)}")
    print(f"Записано: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
