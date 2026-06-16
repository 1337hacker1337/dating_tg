"""
Админ-панель — единый роутер.
AdminMiddleware подключается ОДИН раз здесь, а не в каждом под-модуле.
"""
from aiogram import Router

from bot.middlewares.admin_guard import AdminMiddleware
from bot.handlers.admin import panel, users, broadcast, ads, reports, testing

router = Router(name="admin")
router.message.middleware(AdminMiddleware())
router.callback_query.middleware(AdminMiddleware())

for r in (panel.router, users.router, broadcast.router, ads.router, reports.router, testing.router):
    router.include_router(r)
