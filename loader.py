"""Единые экземпляры Bot и Dispatcher — чтобы избежать циклических импортов."""

from __future__ import annotations

from maxapi import Bot, Dispatcher

from config import BOT_TOKEN

bot = Bot(BOT_TOKEN or None)
dp = Dispatcher()
