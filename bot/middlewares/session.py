from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from db.session import AsyncSessionFactory
from db.repositories.user_repo import UserRepository
from bot import logger as log

_log = log.get(__name__)


class SessionMiddleware(BaseMiddleware):
    """Пробрасывает сессию БД в хэндлеры через data['session']."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with AsyncSessionFactory() as session:
            data["session"] = session
            try:
                return await handler(event, data)
            except Exception:
                await session.rollback()
                raise


class BanCheckMiddleware(BaseMiddleware):
    """
    Блокирует забаненных пользователей.

    Оптимизация: используем get_light() — без selectinload фото,
    так как здесь нужны только is_banned / is_active / id.
    db_user кладём в data, чтобы хэндлеры не делали повторный SELECT.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        session = data.get("session")
        if session is None:
            return await handler(event, data)

        repo    = UserRepository(session)
        db_user = await repo.get_light(user.id)   # ← без фото, быстрее

        if db_user and db_user.is_banned:
            if isinstance(event, CallbackQuery):
                await event.answer("🚷 Ваш аккаунт заблокирован. Вход воспрещён.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("🚷 Ваш аккаунт заблокирован. Вход воспрещён.")
            elif hasattr(event, "message") and event.message:
                await event.message.answer("🚷 Ваш аккаунт заблокирован. Вход воспрещён.")
            _log.warning("banned user blocked: user=%s", user.id)
            return

        if db_user:
            # fire-and-forget через отдельный UPDATE — не блокируем основной поток
            await repo.update_last_seen(user.id)
            await session.commit()

        data["db_user"] = db_user
        return await handler(event, data)
