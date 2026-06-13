"""bot/middlewares/session.py — выдаёт AsyncSession каждому апдейту."""
from aiogram import BaseMiddleware

from db.session import AsyncSessionFactory


class SessionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        async with AsyncSessionFactory() as session:
            data["session"] = session
            try:
                return await handler(event, data)
            except Exception:
                await session.rollback()
                raise
