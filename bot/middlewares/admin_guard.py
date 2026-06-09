from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from db.repositories.admin_repo import AdminRepository
from bot import logger as log

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
