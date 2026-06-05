from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from db.session import AsyncSessionFactory
from db.repositories.user_repo import UserRepository


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
            return await handler(event, data)


class BanCheckMiddleware(BaseMiddleware):
    """Блокирует забаненных пользователей."""

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

        repo = UserRepository(session)
        db_user = await repo.get(user.id)

        if db_user and db_user.is_banned:
            # Отвечаем и прерываем цепочку
            if hasattr(event, "answer"):
                await event.answer("🚫 Ваш аккаунт заблокирован.")
            elif hasattr(event, "message") and event.message:
                await event.message.answer("🚫 Ваш аккаунт заблокирован.")
            return  # не вызываем handler

        # Обновляем last_seen для зарегистрированных
        if db_user:
            await repo.update_last_seen(user.id)
            await session.commit()

        data["db_user"] = db_user
        return await handler(event, data)
