"""Проверка поиска групп на реальной папке schedules.

Запуск:  python tests/test_groups.py
Тест не требует ни maxapi, ни подключения к сети.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.groups import GroupIndex, normalize  # noqa: E402

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}")
        FAILURES.append(message)


def main() -> int:
    index = GroupIndex()
    index.refresh(force=True)
    groups = index.groups

    print(f"Папка: {index.directory}")
    print(f"Найдено групп: {len(groups)}\n")
    if not groups:
        print("Папка с расписаниями пуста — проверять нечего.")
        return 1

    print("Нормализация:")
    check(normalize(" 21 п ") == "21П", "пробелы и регистр")
    check(normalize("21P") == normalize("21Р"), "латинская P = русская Р")
    check(normalize("11a") == normalize("11А"), "латинская a = русская А")
    check(normalize("41-ТЭ") == "41ТЭ", "дефис отбрасывается")

    print("\nПоиск каждой группы по её названию:")
    missed = [g.name for g in groups if index.find(g.name) is None]
    check(not missed, f"все {len(groups)} групп находятся точно")
    if missed:
        print("    не найдены:", ", ".join(missed))

    print("\nПоиск при «человеческом» вводе:")
    sample = groups[0]
    variants = [
        sample.name.lower(),
        f"  {sample.name}  ",
        sample.name.replace("А", "A").replace("Р", "P").replace("К", "K"),
    ]
    for variant in variants:
        found = index.find(variant)
        check(
            found is not None and found.name == sample.name,
            f"«{variant}» → {sample.name}",
        )

    print("\nПодсказки при опечатке:")
    typo = sample.name[:-1] if len(sample.name) > 2 else sample.name
    suggestions = index.suggest(typo)
    check(bool(suggestions), f"«{typo}» даёт подсказки: "
          + ", ".join(g.name for g in suggestions[:5]))

    print("\nРаспределение по курсам:")
    for course, items in index.by_course().items():
        title = f"{course} курс" if course else "прочие"
        print(f"  {title}: {len(items)} — {' '.join(g.name for g in items)}")

    print()
    if FAILURES:
        print(f"ПРОВАЛЕНО проверок: {len(FAILURES)}")
        return 1
    print("Все проверки пройдены ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
