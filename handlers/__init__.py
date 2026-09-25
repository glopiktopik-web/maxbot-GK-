"""Роутеры бота. Порядок подключения важен: fallback — последним."""

from __future__ import annotations

from handlers.announce import router as announce_router
from handlers.attendance import router as attendance_router
from handlers.common import router as common_router
from handlers.fallback import router as fallback_router
from handlers.materials import router as materials_router
from handlers.notes import router as notes_router
from handlers.refs import router as refs_router
from handlers.reports import router as reports_router
from handlers.schedule import router as schedule_router
from handlers.subscribe import router as subscribe_router
from handlers.teacher import router as teacher_router

routers = (
    common_router,
    schedule_router,
    teacher_router,
    subscribe_router,
    attendance_router,
    notes_router,
    materials_router,
    reports_router,
    refs_router,
    announce_router,
    fallback_router,
)

__all__ = ["routers"]
