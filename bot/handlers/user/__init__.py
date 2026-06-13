"""Пользовательская часть бота — единый роутер."""
from aiogram import Router

from bot.handlers.user import start, browse, profile, report, rules

router = Router(name="user")
for r in (rules.router, report.router, start.router, browse.router, profile.router):
    router.include_router(r)
