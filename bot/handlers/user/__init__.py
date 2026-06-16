"""Пользовательская часть бота — единый роутер."""
from aiogram import Router

from bot.handlers.user import start, browse, profile, report, rules, referral, premium, filters

router = Router(name="user")
for r in (
    rules.router, report.router, start.router, browse.router,
    profile.router, referral.router, premium.router, filters.router,
):
    router.include_router(r)
