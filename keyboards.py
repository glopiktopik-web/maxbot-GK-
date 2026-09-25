"""Инлайн-клавиатуры бота."""

from __future__ import annotations

from typing import TYPE_CHECKING

from maxapi.types.attachments.buttons.callback_button import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

if TYPE_CHECKING:
    from services.groups import Group

# ── payload'ы ──────────────────────────────────────────────────────────────
CB_MENU = "menu"
CB_HELP = "help"

CB_SCHEDULE = "sched"
CB_SCHEDULE_LIST = "sched:list"
CB_SCHEDULE_MINE = "sched:mine"
CB_SCHEDULE_GROUP = "sched:g:"  # + название группы
CB_SCHEDULE_SAVE = "sched:save:"  # + название группы
CB_SCHEDULE_COURSE = "sched:course:"  # + номер курса

CB_NOTES = "notes"
CB_NOTES_ADD = "notes:add"
CB_NOTES_LIST = "notes:list"
CB_NOTES_DONE = "notes:done:"  # + id
CB_NOTES_DEL = "notes:del:"  # + id
CB_NOTES_WHEN = "notes:when:"  # + none|1h|3h|tom|custom

CB_MATERIALS = "mat"
CB_MATERIALS_ADD = "mat:add"
CB_MATERIALS_FIND = "mat:find"
CB_MATERIALS_ALL = "mat:all"
CB_MATERIALS_GET = "mat:get:"  # + id

CB_REPORTS = "rep"
CB_REPORTS_GET = "rep:get:"  # + id
CB_REPORTS_ADD = "rep:add"
CB_REPORTS_WEEK = "rep:week"

CB_ANNOUNCE = "ann"
CB_ANNOUNCE_NEW = "ann:new"

# Личное расписание преподавателя
CB_MINE = "me"
CB_MINE_SET = "me:set"
CB_MINE_PICK = "me:pick:"  # + ФИО
CB_MINE_TODAY = "me:today"
CB_MINE_TOMORROW = "me:tomorrow"
CB_MINE_WEEK = "me:week"
CB_MINE_NEXT = "me:next"
CB_MINE_GROUP_TEXT = "me:gtext:"  # + группа

# Подписки на расписание
CB_SUB = "sub"
CB_SUB_TOGGLE = "sub:toggle"
CB_SUB_DIGEST = "sub:digest:"  # + off|06:30|07:00|07:30|08:00

# Посещаемость
CB_ATT = "att"
CB_ATT_NEW = "att:new"
CB_ATT_GROUP = "att:g:"  # + группа
CB_ATT_LESSON = "att:l:"  # + номер урока
CB_ATT_ALL_PRESENT = "att:all"
CB_ATT_REPORT = "att:report:"  # + week|month|all
CB_ATT_LIST = "att:list"

# Справочники
CB_REFS = "refs"
CB_REFS_BELLS = "refs:bells"
CB_REFS_ROOMS = "refs:rooms"
CB_REFS_TEACHERS = "refs:teachers"
CB_REFS_FREE = "refs:free"

CB_REPORTS_DOCX = "rep:docx:"  # + id шаблона

CB_CANCEL = "cancel"


def _back_row(kb: InlineKeyboardBuilder) -> InlineKeyboardBuilder:
    kb.row(CallbackButton(text="🏠 Главное меню", payload=CB_MENU))
    return kb


# ── главное меню ───────────────────────────────────────────────────────────
def main_menu() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="📅 Расписание учебных занятий", payload=CB_SCHEDULE))
    kb.row(
        CallbackButton(text="👤 Моё расписание", payload=CB_MINE),
        CallbackButton(text="⏭ Следующий урок", payload=CB_MINE_NEXT),
    )
    kb.row(
        CallbackButton(text="📝 Заметки и напоминания", payload=CB_NOTES),
        CallbackButton(text="✅ Посещаемость", payload=CB_ATT),
    )
    kb.row(
        CallbackButton(text="📚 База материалов", payload=CB_MATERIALS),
        CallbackButton(text="📊 Отчёты и шаблоны", payload=CB_REPORTS),
    )
    kb.row(
        CallbackButton(text="📖 Справочники", payload=CB_REFS),
        CallbackButton(text="📢 Объявления", payload=CB_ANNOUNCE),
    )
    kb.row(CallbackButton(text="ℹ️ Что я умею", payload=CB_HELP))
    return kb


def only_menu() -> InlineKeyboardBuilder:
    return _back_row(InlineKeyboardBuilder())


# ── расписание ─────────────────────────────────────────────────────────────
def schedule_prompt(my_group: str | None) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    if my_group:
        kb.row(
            CallbackButton(
                text=f"⭐ Моя группа — {my_group}",
                payload=f"{CB_SCHEDULE_GROUP}{my_group}",
            )
        )
    kb.row(CallbackButton(text="📋 Список всех групп", payload=CB_SCHEDULE_LIST))
    kb.row(CallbackButton(text="🔔 Подписка и рассылка", payload=CB_SUB))
    return _back_row(kb)


def schedule_result(group_name: str, *, is_mine: bool) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    if not is_mine:
        kb.row(
            CallbackButton(
                text="⭐ Запомнить как мою группу",
                payload=f"{CB_SCHEDULE_SAVE}{group_name}",
            )
        )
    kb.row(
        CallbackButton(
            text="📝 Текстом", payload=f"{CB_MINE_GROUP_TEXT}{group_name}"
        ),
        CallbackButton(text="🔔 Подписка", payload=CB_SUB),
    )
    kb.row(
        CallbackButton(text="🔁 Другая группа", payload=CB_SCHEDULE),
        CallbackButton(text="🏠 Меню", payload=CB_MENU),
    )
    return kb


def schedule_suggestions(groups: list[Group]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for group in groups:
        kb.row(
            CallbackButton(
                text=group.name, payload=f"{CB_SCHEDULE_GROUP}{group.name}"
            )
        )
    kb.adjust(3)
    kb.row(CallbackButton(text="📋 Список всех групп", payload=CB_SCHEDULE_LIST))
    return _back_row(kb)


def schedule_courses(courses: list[int | None]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for course in courses:
        if course is None:
            continue
        kb.row(
            CallbackButton(
                text=f"{course} курс", payload=f"{CB_SCHEDULE_COURSE}{course}"
            )
        )
    kb.adjust(4)
    return _back_row(kb)


def schedule_group_buttons(groups: list[Group]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for group in groups:
        kb.row(
            CallbackButton(
                text=group.name, payload=f"{CB_SCHEDULE_GROUP}{group.name}"
            )
        )
    kb.adjust(3)
    kb.row(CallbackButton(text="◀️ К списку курсов", payload=CB_SCHEDULE_LIST))
    return _back_row(kb)


# ── заметки ────────────────────────────────────────────────────────────────
def notes_menu() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="➕ Новая задача", payload=CB_NOTES_ADD),
        CallbackButton(text="📋 Мои задачи", payload=CB_NOTES_LIST),
    )
    return _back_row(kb)


def notes_when() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="Без напоминания", payload=f"{CB_NOTES_WHEN}none"),
        CallbackButton(text="Через час", payload=f"{CB_NOTES_WHEN}1h"),
    )
    kb.row(
        CallbackButton(text="Через 3 часа", payload=f"{CB_NOTES_WHEN}3h"),
        CallbackButton(text="Завтра в 8:30", payload=f"{CB_NOTES_WHEN}tom"),
    )
    kb.row(CallbackButton(text="❌ Отмена", payload=CB_CANCEL))
    return kb


def notes_list(notes: list[dict]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for position, note in enumerate(notes, start=1):
        kb.row(
            CallbackButton(
                text=f"✅ {position}", payload=f"{CB_NOTES_DONE}{note['id']}"
            ),
            CallbackButton(
                text=f"🗑 {position}", payload=f"{CB_NOTES_DEL}{note['id']}"
            ),
        )
    kb.row(
        CallbackButton(text="➕ Новая задача", payload=CB_NOTES_ADD),
        CallbackButton(text="🔄 Обновить", payload=CB_NOTES_LIST),
    )
    return _back_row(kb)


def note_reminder_keyboard(note_id: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="✅ Выполнено", payload=f"{CB_NOTES_DONE}{note_id}"),
        CallbackButton(text="📋 Мои задачи", payload=CB_NOTES_LIST),
    )
    return kb


# ── материалы ──────────────────────────────────────────────────────────────
def materials_menu() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="🔍 Найти", payload=CB_MATERIALS_FIND),
        CallbackButton(text="➕ Добавить", payload=CB_MATERIALS_ADD),
    )
    kb.row(CallbackButton(text="📂 Последние", payload=CB_MATERIALS_ALL))
    return _back_row(kb)


def materials_results(materials: list[dict]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for material in materials:
        title = material["title"]
        label = title if len(title) <= 40 else title[:39] + "…"
        kb.row(
            CallbackButton(
                text=label, payload=f"{CB_MATERIALS_GET}{material['id']}"
            )
        )
    kb.row(
        CallbackButton(text="🔍 Искать ещё", payload=CB_MATERIALS_FIND),
        CallbackButton(text="➕ Добавить", payload=CB_MATERIALS_ADD),
    )
    return _back_row(kb)


# ── отчёты ─────────────────────────────────────────────────────────────────
def reports_menu(templates: list[dict]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for template in templates:
        title = template["title"]
        label = title if len(title) <= 40 else title[:39] + "…"
        kb.row(
            CallbackButton(text=label, payload=f"{CB_REPORTS_GET}{template['id']}")
        )
    kb.row(CallbackButton(text="📈 Сводка по моим задачам", payload=CB_REPORTS_WEEK))
    kb.row(CallbackButton(text="➕ Свой шаблон", payload=CB_REPORTS_ADD))
    return _back_row(kb)


def reports_back() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="◀️ К шаблонам", payload=CB_REPORTS),
        CallbackButton(text="🏠 Меню", payload=CB_MENU),
    )
    return kb


# ── объявления ─────────────────────────────────────────────────────────────
def announce_menu(is_admin: bool) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    if is_admin:
        kb.row(CallbackButton(text="📨 Написать объявление", payload=CB_ANNOUNCE_NEW))
    return _back_row(kb)


def cancel_only() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="❌ Отмена", payload=CB_CANCEL))
    return kb


# ── личное расписание преподавателя ────────────────────────────────────────
def mine_menu(teacher: str | None) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    if teacher:
        kb.row(
            CallbackButton(text="Сегодня", payload=CB_MINE_TODAY),
            CallbackButton(text="Завтра", payload=CB_MINE_TOMORROW),
        )
        kb.row(
            CallbackButton(text="🗓 Вся неделя", payload=CB_MINE_WEEK),
            CallbackButton(text="⏭ Следующий урок", payload=CB_MINE_NEXT),
        )
        kb.row(CallbackButton(text="✏️ Сменить фамилию", payload=CB_MINE_SET))
    else:
        kb.row(CallbackButton(text="✏️ Указать фамилию", payload=CB_MINE_SET))
    return _back_row(kb)


def mine_pick(names: list[str]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for name in names[:12]:
        kb.row(CallbackButton(text=name, payload=f"{CB_MINE_PICK}{name}"))
    kb.adjust(2)
    return _back_row(kb)


def mine_back() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="◀️ Моё расписание", payload=CB_MINE),
        CallbackButton(text="🏠 Меню", payload=CB_MENU),
    )
    return kb


# ── подписки ───────────────────────────────────────────────────────────────
def subscriptions(
    *, group: str | None, notify: bool, digest_time: str | None
) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    mark = "включены ✅" if notify else "выключены ❌"
    kb.row(
        CallbackButton(
            text=f"Уведомления об изменениях: {mark}", payload=CB_SUB_TOGGLE
        )
    )
    for label, value in (
        ("06:30", "06:30"),
        ("07:00", "07:00"),
        ("07:30", "07:30"),
        ("08:00", "08:00"),
    ):
        mark = " ✅" if digest_time == value else ""
        kb.row(
            CallbackButton(text=f"{label}{mark}", payload=f"{CB_SUB_DIGEST}{value}")
        )
    kb.adjust(4)
    kb.row(
        CallbackButton(
            text="Не присылать утром" + (" ✅" if not digest_time else ""),
            payload=f"{CB_SUB_DIGEST}off",
        )
    )
    if not group:
        kb.row(
            CallbackButton(
                text="⭐ Сначала выберите группу", payload=CB_SCHEDULE
            )
        )
    return _back_row(kb)


# ── посещаемость ───────────────────────────────────────────────────────────
def attendance_menu() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="➕ Отметить занятие", payload=CB_ATT_NEW))
    kb.row(
        CallbackButton(text="📋 Последние записи", payload=CB_ATT_LIST),
    )
    kb.row(
        CallbackButton(text="📊 Отчёт за неделю", payload=f"{CB_ATT_REPORT}week"),
        CallbackButton(text="📊 За месяц", payload=f"{CB_ATT_REPORT}month"),
    )
    return _back_row(kb)


def attendance_groups(groups: list[str], mine: str | None) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    if mine:
        kb.row(
            CallbackButton(text=f"⭐ {mine}", payload=f"{CB_ATT_GROUP}{mine}")
        )
    for name in groups[:24]:
        kb.row(CallbackButton(text=name, payload=f"{CB_ATT_GROUP}{name}"))
    kb.adjust(4)
    kb.row(CallbackButton(text="❌ Отмена", payload=CB_CANCEL))
    return kb


def attendance_lessons(options: list[tuple[int, str]]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for number, label in options:
        kb.row(CallbackButton(text=label, payload=f"{CB_ATT_LESSON}{number}"))
    kb.adjust(2)
    kb.row(CallbackButton(text="❌ Отмена", payload=CB_CANCEL))
    return kb


def attendance_absent() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="✅ Все на месте", payload=CB_ATT_ALL_PRESENT))
    kb.row(CallbackButton(text="❌ Отмена", payload=CB_CANCEL))
    return kb


def attendance_back() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="➕ Ещё занятие", payload=CB_ATT_NEW),
        CallbackButton(text="◀️ Посещаемость", payload=CB_ATT),
    )
    return _back_row(kb)


# ── справочники ────────────────────────────────────────────────────────────
def refs_menu() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="🔔 Расписание звонков", payload=CB_REFS_BELLS),
        CallbackButton(text="🚪 Аудитории", payload=CB_REFS_ROOMS),
    )
    kb.row(
        CallbackButton(text="👥 Преподаватели", payload=CB_REFS_TEACHERS),
        CallbackButton(text="🔍 Свободные аудитории", payload=CB_REFS_FREE),
    )
    return _back_row(kb)


def refs_back() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="◀️ Справочники", payload=CB_REFS),
        CallbackButton(text="🏠 Меню", payload=CB_MENU),
    )
    return kb


def report_formats(template_id: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(
            text="📄 Скачать как Word", payload=f"{CB_REPORTS_DOCX}{template_id}"
        )
    )
    kb.row(
        CallbackButton(text="◀️ К шаблонам", payload=CB_REPORTS),
        CallbackButton(text="🏠 Меню", payload=CB_MENU),
    )
    return kb
