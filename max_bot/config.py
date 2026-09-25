"""Конфигурация бота «Арсенал мастера» для мессенджера MAX."""

from __future__ import annotations

import contextlib
import os
import re
from pathlib import Path

# Необязательная поддержка .env
with contextlib.suppress(ImportError):
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")

BASE_DIR = Path(__file__).resolve().parent


BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "").strip()


def _resolve_schedules_dir() -> Path:
    """Папка с фотографиями расписаний.

    По умолчанию — соседняя с проектом папка ``schedules``
    (C:\\Users\\...\\konkurs\\schedules). Можно переопределить
    переменной окружения ``SCHEDULES_DIR``.
    """
    raw = os.getenv("SCHEDULES_DIR", "").strip().strip('"')
    if raw:
        return Path(raw).expanduser()
    return BASE_DIR.parent / "schedules"


SCHEDULES_DIR = _resolve_schedules_dir()

#: Расширения, которые считаем картинкой расписания.
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

#: Картинки бота: приветственный баннер и аватар.
ASSETS_DIR = BASE_DIR / "assets"
WELCOME_IMAGE = ASSETS_DIR / "welcome.png"

#: Каталог для служебных данных (БД).
DATA_DIR = Path(os.getenv("DATA_DIR", "").strip() or (BASE_DIR / "data"))
DB_PATH = DATA_DIR / "arsenal.sqlite3"

#: Администраторы (id пользователей MAX через запятую в .env).
#: Им доступна рассылка объявлений.
ADMIN_IDS: set[int] = {
    int(x) for x in re.findall(r"\d+", os.getenv("ADMIN_IDS", ""))
}

#: Название образовательной организации — подставляется в шаблоны отчётов.
ORG_NAME = os.getenv("ORG_NAME", "").strip() or "образовательной организации"

#: Как часто проверять напоминания (секунды).
REMINDER_TICK_SECONDS = 30

#: Сколько подсказок показывать, если группа не найдена.
SUGGEST_LIMIT = 6
