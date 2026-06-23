"""
bot/middlewares/ban_check.py — блокировка забаненных + обновление last_seen / username.

БАГФИКСЫ:
1. Платёжные апдейты (pre_checkout_query, successful_payment) пропускаются всегда:
   Telegram требует ответ на pre_checkout в течение 10 секунд, а проглоченный
   successful_payment = списанные деньги без удаления анкеты.
2. username теперь синхронизируется с Telegram при каждом апдейте — раньше он
   сохранялся один раз при регистрации и кнопка «написать» вела в никуда
   после смены ника.
"""
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from bot import logger as log
from db.repositories.user_repo import UserRepository

_log = log.get(__name__)


def _is_payment_update(event) -> bool:
    if getattr(event, "pre_checkout_query", None) is not None:
        return True
    msg = getattr(event, "message", None)
    return msg is not None and getattr(msg, "successful_payment", None) is not None


class BanCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if _is_payment_update(event):
            return await handler(event, data)

        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)
        session = data.get("session")
        if session is None:
            return await handler(event, data)

        repo = UserRepository(session)
        db_user = await repo.get_light(user.id)

        if db_user and db_user.is_banned:
            if isinstance(event, CallbackQuery):
                await event.answer("🚷  доступ закрыт.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("🚷  доступ закрыт.\n<i>аккаунт заблокирован.</i>", parse_mode="HTML")
            elif hasattr(event, "message") and event.message:
                await event.message.answer("🚷  доступ закрыт.\n<i>аккаунт заблокирован.</i>", parse_mode="HTML")
            _log.warning("banned user blocked: user=%s", user.id)
            return

        if db_user:
            if db_user.username != user.username:
                await repo.update_username(user.id, user.username)
                db_user.username = user.username
            await repo.update_last_seen(user.id)
            await session.commit()

        data["db_user"] = db_user
        return await handler(event, data)
