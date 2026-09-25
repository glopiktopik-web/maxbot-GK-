"""Небольшой асинхронный слой поверх sqlite3 (без внешних зависимостей).

Все обращения к БД выполняются в отдельном потоке через
``asyncio.to_thread`` и сериализуются одним ``asyncio.Lock``.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime
from typing import Any

from config import DATA_DIR, DB_PATH

_lock = asyncio.Lock()
_conn: sqlite3.Connection | None = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    chat_id     INTEGER,
    full_name   TEXT,
    group_name  TEXT,
    created_at  TEXT NOT NULL
);

-- Отслеживание изменений файлов расписания, чтобы уведомлять подписчиков.
CREATE TABLE IF NOT EXISTS schedule_state (
    group_key   TEXT PRIMARY KEY,
    group_name  TEXT NOT NULL,
    mtime       REAL NOT NULL,
    checked_at  TEXT NOT NULL
);

-- Учёт посещаемости: одна запись = одно занятие.
CREATE TABLE IF NOT EXISTS attendance (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    author       TEXT,
    group_name   TEXT NOT NULL,
    lesson_date  TEXT NOT NULL,           -- YYYY-MM-DD
    lesson_no    INTEGER,
    subject      TEXT,
    absent_count INTEGER NOT NULL DEFAULT 0,
    note         TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS absences (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id  INTEGER NOT NULL,
    student    TEXT NOT NULL,
    FOREIGN KEY (record_id) REFERENCES attendance(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_att_user ON attendance(user_id);
CREATE INDEX IF NOT EXISTS idx_att_date ON attendance(lesson_date);
CREATE INDEX IF NOT EXISTS idx_abs_record ON absences(record_id);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    chat_id     INTEGER,
    text        TEXT NOT NULL,
    remind_at   TEXT,
    notified    INTEGER NOT NULL DEFAULT 0,
    done        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    done_at     TEXT
);

CREATE TABLE IF NOT EXISTS materials (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    author      TEXT,
    title       TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL,           -- file | image | video | audio | link | text
    token       TEXT,                    -- токен вложения MAX
    url         TEXT,
    body        TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS templates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,                 -- NULL = общий шаблон
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id);
CREATE INDEX IF NOT EXISTS idx_notes_remind ON notes(remind_at);
CREATE INDEX IF NOT EXISTS idx_materials_user ON materials(user_id);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


#: Колонки, добавленные после первого выпуска бота.
#: Дописываются в уже существующую базу, чтобы обновление не требовало
#: удаления файла с данными.
_MIGRATIONS = {
    "users": {
        "teacher_name": "TEXT",
        "notify_changes": "INTEGER NOT NULL DEFAULT 1",
        "digest_time": "TEXT",
        "digest_sent": "TEXT",
    },
}


def _migrate(conn: sqlite3.Connection) -> None:
    for table, columns in _MIGRATIONS.items():
        existing = {
            row["name"] for row in conn.execute(f"PRAGMA table_info({table})")
        }
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                )


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def _run(sql: str, params: tuple = (), *, fetch: str | None = None) -> Any:
    assert _conn is not None
    cur = _conn.execute(sql, params)
    if fetch == "one":
        row = cur.fetchone()
        result = dict(row) if row else None
    elif fetch == "all":
        result = [dict(r) for r in cur.fetchall()]
    else:
        result = cur.lastrowid
    _conn.commit()
    return result


async def _exec(sql: str, params: tuple = (), *, fetch: str | None = None):
    async with _lock:
        return await asyncio.to_thread(_run, sql, params, fetch=fetch)


async def init_db() -> None:
    """Создаёт файл БД, таблицы и наполняет общие шаблоны отчётов."""
    global _conn
    if _conn is None:
        _conn = await asyncio.to_thread(_connect)
    await _seed_templates()


async def close_db() -> None:
    global _conn
    if _conn is not None:
        conn, _conn = _conn, None
        await asyncio.to_thread(conn.close)


# ── Пользователи ───────────────────────────────────────────────────────────


async def upsert_user(
    user_id: int, chat_id: int | None, full_name: str | None
) -> None:
    await _exec(
        """
        INSERT INTO users (user_id, chat_id, full_name, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            chat_id   = COALESCE(excluded.chat_id, users.chat_id),
            full_name = COALESCE(excluded.full_name, users.full_name)
        """,
        (user_id, chat_id, full_name, _now()),
    )


async def get_user(user_id: int) -> dict | None:
    return await _exec(
        "SELECT * FROM users WHERE user_id = ?", (user_id,), fetch="one"
    )


async def set_user_group(user_id: int, group_name: str | None) -> None:
    await _exec(
        "UPDATE users SET group_name = ? WHERE user_id = ?",
        (group_name, user_id),
    )


async def set_user_teacher(user_id: int, teacher_name: str | None) -> None:
    await _exec(
        "UPDATE users SET teacher_name = ? WHERE user_id = ?",
        (teacher_name, user_id),
    )


async def set_notify_changes(user_id: int, enabled: bool) -> None:
    await _exec(
        "UPDATE users SET notify_changes = ? WHERE user_id = ?",
        (int(enabled), user_id),
    )


async def set_digest_time(user_id: int, digest_time: str | None) -> None:
    """Время ежедневной рассылки расписания, «ЧЧ:ММ» или None."""
    await _exec(
        "UPDATE users SET digest_time = ? WHERE user_id = ?",
        (digest_time, user_id),
    )


async def all_users() -> list[dict]:
    return await _exec(
        "SELECT * FROM users WHERE chat_id IS NOT NULL", fetch="all"
    )


async def subscribers_of_group(group_name: str) -> list[dict]:
    """Кому сообщать об изменении расписания этой группы."""
    return await _exec(
        """
        SELECT * FROM users
        WHERE chat_id IS NOT NULL AND notify_changes = 1
          AND group_name = ?
        """,
        (group_name,),
        fetch="all",
    )


async def digest_recipients(digest_time: str, today: str) -> list[dict]:
    """Кому пора отправить утреннюю рассылку и кому её ещё не слали."""
    return await _exec(
        """
        SELECT * FROM users
        WHERE chat_id IS NOT NULL AND digest_time = ?
          AND (digest_sent IS NULL OR digest_sent <> ?)
        """,
        (digest_time, today),
        fetch="all",
    )


async def mark_digest_sent(user_id: int, today: str) -> None:
    await _exec(
        "UPDATE users SET digest_sent = ? WHERE user_id = ?", (today, user_id)
    )


# ── Состояние файлов расписания ────────────────────────────────────────────


async def known_schedule_state() -> dict[str, float]:
    rows = await _exec("SELECT group_key, mtime FROM schedule_state", fetch="all")
    return {row["group_key"]: row["mtime"] for row in rows}


async def remember_schedule_state(
    group_key: str, group_name: str, mtime: float
) -> None:
    await _exec(
        """
        INSERT INTO schedule_state (group_key, group_name, mtime, checked_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(group_key) DO UPDATE SET
            group_name = excluded.group_name,
            mtime      = excluded.mtime,
            checked_at = excluded.checked_at
        """,
        (group_key, group_name, mtime, _now()),
    )


# ── Посещаемость ───────────────────────────────────────────────────────────


async def add_attendance(
    *,
    user_id: int,
    author: str | None,
    group_name: str,
    lesson_date: str,
    lesson_no: int | None,
    subject: str | None,
    students: list[str],
    note: str | None = None,
) -> int:
    record_id = await _exec(
        """
        INSERT INTO attendance
            (user_id, author, group_name, lesson_date, lesson_no, subject,
             absent_count, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            author,
            group_name,
            lesson_date,
            lesson_no,
            subject,
            len(students),
            note,
            _now(),
        ),
    )
    for student in students:
        await _exec(
            "INSERT INTO absences (record_id, student) VALUES (?, ?)",
            (record_id, student),
        )
    return record_id


async def attendance_records(
    *, user_id: int | None, since: str, until: str
) -> list[dict]:
    if user_id is None:
        return await _exec(
            """
            SELECT * FROM attendance
            WHERE lesson_date BETWEEN ? AND ?
            ORDER BY lesson_date, group_name, lesson_no
            """,
            (since, until),
            fetch="all",
        )
    return await _exec(
        """
        SELECT * FROM attendance
        WHERE user_id = ? AND lesson_date BETWEEN ? AND ?
        ORDER BY lesson_date, group_name, lesson_no
        """,
        (user_id, since, until),
        fetch="all",
    )


async def absences_of(record_ids: list[int]) -> dict[int, list[str]]:
    if not record_ids:
        return {}
    placeholders = ",".join("?" * len(record_ids))
    rows = await _exec(
        f"SELECT record_id, student FROM absences "
        f"WHERE record_id IN ({placeholders}) ORDER BY student",
        tuple(record_ids),
        fetch="all",
    )
    result: dict[int, list[str]] = {}
    for row in rows:
        result.setdefault(row["record_id"], []).append(row["student"])
    return result


async def delete_attendance(record_id: int, user_id: int) -> None:
    await _exec(
        "DELETE FROM absences WHERE record_id = ?", (record_id,)
    )
    await _exec(
        "DELETE FROM attendance WHERE id = ? AND user_id = ?",
        (record_id, user_id),
    )


# ── Заметки и напоминания ──────────────────────────────────────────────────


async def add_note(
    user_id: int, chat_id: int | None, text: str, remind_at: str | None
) -> int:
    return await _exec(
        """
        INSERT INTO notes (user_id, chat_id, text, remind_at, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, chat_id, text, remind_at, _now()),
    )


async def list_notes(user_id: int, *, done: bool = False) -> list[dict]:
    return await _exec(
        """
        SELECT * FROM notes
        WHERE user_id = ? AND done = ?
        ORDER BY (remind_at IS NULL), remind_at, id
        """,
        (user_id, int(done)),
        fetch="all",
    )


async def get_note(note_id: int, user_id: int) -> dict | None:
    return await _exec(
        "SELECT * FROM notes WHERE id = ? AND user_id = ?",
        (note_id, user_id),
        fetch="one",
    )


async def set_note_done(note_id: int, user_id: int) -> None:
    await _exec(
        "UPDATE notes SET done = 1, done_at = ? WHERE id = ? AND user_id = ?",
        (_now(), note_id, user_id),
    )


async def delete_note(note_id: int, user_id: int) -> None:
    await _exec(
        "DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id)
    )


async def due_notes(now_iso: str) -> list[dict]:
    return await _exec(
        """
        SELECT * FROM notes
        WHERE done = 0 AND notified = 0
          AND remind_at IS NOT NULL AND remind_at <= ?
        ORDER BY remind_at
        """,
        (now_iso,),
        fetch="all",
    )


async def mark_notified(note_id: int) -> None:
    await _exec("UPDATE notes SET notified = 1 WHERE id = ?", (note_id,))


async def notes_for_period(user_id: int, since_iso: str) -> list[dict]:
    return await _exec(
        """
        SELECT * FROM notes
        WHERE user_id = ? AND created_at >= ?
        ORDER BY done, created_at
        """,
        (user_id, since_iso),
        fetch="all",
    )


# ── Материалы ──────────────────────────────────────────────────────────────


async def add_material(
    *,
    user_id: int,
    author: str | None,
    title: str,
    tags: str,
    kind: str,
    token: str | None = None,
    url: str | None = None,
    body: str | None = None,
) -> int:
    return await _exec(
        """
        INSERT INTO materials
            (user_id, author, title, tags, kind, token, url, body, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, author, title, tags, kind, token, url, body, _now()),
    )


async def search_materials(query: str, limit: int = 20) -> list[dict]:
    like = f"%{query.lower()}%"
    return await _exec(
        """
        SELECT * FROM materials
        WHERE lower(title) LIKE ? OR lower(tags) LIKE ?
           OR lower(COALESCE(body, '')) LIKE ?
        ORDER BY id DESC LIMIT ?
        """,
        (like, like, like, limit),
        fetch="all",
    )


async def list_materials(limit: int = 20) -> list[dict]:
    return await _exec(
        "SELECT * FROM materials ORDER BY id DESC LIMIT ?",
        (limit,),
        fetch="all",
    )


async def get_material(material_id: int) -> dict | None:
    return await _exec(
        "SELECT * FROM materials WHERE id = ?", (material_id,), fetch="one"
    )


async def delete_material(material_id: int, user_id: int) -> None:
    await _exec(
        "DELETE FROM materials WHERE id = ? AND user_id = ?",
        (material_id, user_id),
    )


# ── Шаблоны отчётов ────────────────────────────────────────────────────────


async def list_templates(user_id: int) -> list[dict]:
    return await _exec(
        """
        SELECT * FROM templates
        WHERE user_id IS NULL OR user_id = ?
        ORDER BY (user_id IS NOT NULL), id
        """,
        (user_id,),
        fetch="all",
    )


async def get_template(template_id: int) -> dict | None:
    return await _exec(
        "SELECT * FROM templates WHERE id = ?", (template_id,), fetch="one"
    )


async def add_template(user_id: int | None, title: str, body: str) -> int:
    return await _exec(
        "INSERT INTO templates (user_id, title, body, created_at) "
        "VALUES (?, ?, ?, ?)",
        (user_id, title, body, _now()),
    )


async def delete_template(template_id: int, user_id: int) -> None:
    await _exec(
        "DELETE FROM templates WHERE id = ? AND user_id = ?",
        (template_id, user_id),
    )


async def _seed_templates() -> None:
    """Однократно добавляет базовый набор общих шаблонов."""
    existing = await _exec(
        "SELECT COUNT(*) AS n FROM templates WHERE user_id IS NULL",
        fetch="one",
    )
    if existing and existing["n"]:
        return

    from texts import DEFAULT_TEMPLATES

    for title, body in DEFAULT_TEMPLATES:
        await add_template(None, title, body)
