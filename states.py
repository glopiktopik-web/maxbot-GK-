"""Состояния диалогов (FSM)."""

from __future__ import annotations

from maxapi.context.state_machine import State, StatesGroup


class ScheduleSG(StatesGroup):
    """Диалог «Расписание учебных занятий»."""

    waiting_group = State()


class NoteSG(StatesGroup):
    """Диалог создания заметки/напоминания."""

    waiting_text = State()
    waiting_time = State()


class MaterialSG(StatesGroup):
    """Диалог работы с базой материалов."""

    waiting_content = State()
    waiting_query = State()


class TemplateSG(StatesGroup):
    """Диалог создания своего шаблона отчёта."""

    waiting_title = State()
    waiting_body = State()


class AnnounceSG(StatesGroup):
    """Диалог рассылки объявления."""

    waiting_text = State()


class TeacherSG(StatesGroup):
    """Диалог «Моё расписание» — поиск преподавателя по фамилии."""

    waiting_name = State()


class AttendanceSG(StatesGroup):
    """Диалог отметки посещаемости."""

    waiting_group = State()
    waiting_lesson = State()
    waiting_absent = State()


class RefsSG(StatesGroup):
    """Диалог справочников."""

    waiting_room_query = State()
