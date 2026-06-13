"""bot/middlewares/admin_guard.py — пускает в админ-роутеры только админов."""
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from bot import logger as log
from db.repositories.admin_repo import AdminRepository

_log = log.get(__name__)


class AdminMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user is None:
            return
        session = data.get("session")
        if session is None:
            return
        repo = AdminRepository(session)
        if not await repo.is_admin(user.id):
            if isinstance(event, CallbackQuery):
                await event.answer("⛔ Нет доступа.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("⛔ Нет доступа.")
            _log.warning("non-admin tried admin panel: user=%s", user.id)
            return
        data["admin_repo"] = repo
        return await handler(event, data)
