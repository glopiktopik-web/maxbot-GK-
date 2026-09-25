"""Индекс групп: сопоставление названия группы и файла с расписанием.

Имя файла = название группы (11А.JPG, 21П.JPG, 41ТЭ.JPG …).
Главная задача модуля — понять пользователя, как бы он ни написал
название: «21п», « 21 П », «21P» (латинская P) — это одна и та же группа.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config import IMAGE_SUFFIXES, SCHEDULES_DIR, SUGGEST_LIMIT

#: Латинские буквы, неотличимые на вид от кириллических.
#: Приводим всё к кириллице — так «21A» и «21А» станут одним ключом.
_LOOKALIKE = {
    "A": "А",
    "B": "В",
    "C": "С",
    "E": "Е",
    "H": "Н",
    "K": "К",
    "M": "М",
    "O": "О",
    "P": "Р",
    "T": "Т",
    "X": "Х",
    "Y": "У",
    "I": "І",
    "3": "3",
}

_TRASH_RE = re.compile(r"[\s\-_.,:;!?'\"«»()\[\]/\\]+")
_LEAD_NUM_RE = re.compile(r"^(\d+)")


def normalize(text: str) -> str:
    """Приводит название группы к каноническому виду.

    >>> normalize(" 21 п ")
    '21П'
    >>> normalize("21P")  # латинская P
    '21Р'
    """
    cleaned = _TRASH_RE.sub("", (text or "").strip()).upper().replace("Ё", "Е")
    return "".join(_LOOKALIKE.get(ch, ch) for ch in cleaned)


@dataclass(frozen=True)
class Group:
    """Одна группа и её файл с расписанием."""

    key: str  #: нормализованное название (для поиска)
    name: str  #: название как в имени файла
    path: Path  #: путь к картинке
    mtime: float  #: время изменения файла

    @property
    def course(self) -> int | None:
        """Номер курса — первая цифра названия (11А → 1, 21П → 2)."""
        match = _LEAD_NUM_RE.match(self.name)
        if not match:
            return None
        return int(match.group(1)[0])

    @property
    def updated(self) -> str:
        """Дата обновления файла расписания в читаемом виде."""
        return datetime.fromtimestamp(self.mtime).strftime("%d.%m.%Y")

    def sort_key(self) -> tuple[int, str]:
        match = _LEAD_NUM_RE.match(self.name)
        number = int(match.group(1)) if match else 9999
        return number, self.name.upper()


class GroupIndex:
    """Кэширующий индекс папки с расписаниями.

    Папку можно пополнять и обновлять на лету: индекс сам замечает
    изменения (по времени модификации каталога) и перечитывает её.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = Path(directory or SCHEDULES_DIR)
        self._groups: dict[str, Group] = {}
        self._dir_mtime: float | None = None

    # ── построение индекса ────────────────────────────────────────────
    def refresh(self, *, force: bool = False) -> None:
        """Перечитывает папку, если она изменилась."""
        try:
            dir_mtime = self.directory.stat().st_mtime
        except OSError:
            self._groups = {}
            self._dir_mtime = None
            return

        if not force and self._dir_mtime == dir_mtime and self._groups:
            return

        groups: dict[str, Group] = {}
        for path in sorted(self.directory.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in IMAGE_SUFFIXES:
                continue

            name = path.stem.strip()
            key = normalize(name)
            if not key:
                continue

            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue

            existing = groups.get(key)
            if existing is not None and existing.mtime >= mtime:
                # Дубль (например, 21A.JPG и 21А.JPG) — оставляем свежий.
                continue

            groups[key] = Group(key=key, name=name, path=path, mtime=mtime)

        self._groups = groups
        self._dir_mtime = dir_mtime

    # ── доступ ────────────────────────────────────────────────────────
    @property
    def groups(self) -> list[Group]:
        self.refresh()
        return sorted(self._groups.values(), key=Group.sort_key)

    def __len__(self) -> int:
        self.refresh()
        return len(self._groups)

    def find(self, query: str) -> Group | None:
        """Точное совпадение по нормализованному названию."""
        self.refresh()
        return self._groups.get(normalize(query))

    def suggest(self, query: str, limit: int = SUGGEST_LIMIT) -> list[Group]:
        """Похожие группы — на случай опечатки или частичного ввода."""
        self.refresh()
        key = normalize(query)
        if not key:
            return []

        ranked: list[tuple[float, Group]] = []
        for group in self._groups.values():
            if group.key == key:
                score = 3.0
            elif group.key.startswith(key) or key.startswith(group.key):
                score = 2.0 + len(key) / max(len(group.key), 1) / 10
            elif key in group.key or group.key in key:
                score = 1.5
            else:
                ratio = difflib.SequenceMatcher(None, key, group.key).ratio()
                if ratio < 0.5:
                    continue
                score = ratio
            ranked.append((score, group))

        ranked.sort(key=lambda item: (-item[0], item[1].sort_key()))
        return [group for _score, group in ranked[:limit]]

    def by_course(self) -> dict[int | None, list[Group]]:
        """Группы, разложенные по курсам — для списка и клавиатур."""
        result: dict[int | None, list[Group]] = {}
        for group in self.groups:
            result.setdefault(group.course, []).append(group)
        return dict(sorted(result.items(), key=lambda kv: (kv[0] is None, kv[0])))

    def as_text(self) -> str:
        """Человекочитаемый список всех групп по курсам."""
        chunks: list[str] = []
        for course, groups in self.by_course().items():
            title = f"{course} курс" if course else "Прочие"
            names = "  ".join(group.name for group in groups)
            chunks.append(f"▫️ {title}:\n{names}")
        return "\n\n".join(chunks)


#: Общий индекс на всё приложение.
index = GroupIndex()
