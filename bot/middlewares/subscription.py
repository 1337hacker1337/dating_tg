"""
bot/middlewares/subscription.py
Регистрируется на dp.update.middleware — event это Update.
Достаём callback/message через атрибуты Update напрямую.
"""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import TelegramObject, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import logger as log
from bot.keyboards import kb_main_menu
from config import settings
from db.repositories.admin_repo import AdminRepository
from db.repositories.settings_repo import SettingsRepository

_log = log.get(__name__)

_BYPASS_COMMANDS = {"/start", "/admin"}

_BLOCKED_TEXT = (
    "🔒  доступ закрыт.\n\n"
    "подпишись на {channels} — и нажми кнопку ниже."
)


def _sub_keyboard(channels: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        if ch["url"]:
            b.button(text=f"📢  {ch['title']}", url=ch["url"])
        else:
            b.button(text=f"📢  {ch['title']} (приватный)", callback_data="sub:noop")
    b.button(text="✅  проверить подписку", callback_data="sub:check")
    b.adjust(1)
    return b.as_markup()


async def get_channels(session, bot: Bot) -> list[dict]:
    ids = []
    if settings.own_channel_id:
        ids.append(settings.own_channel_id)

    repo = SettingsRepository(session)
    if await repo.is_ad_active():
        ad = await repo.get_ad_channel()
        if ad:
            ids.append(ad)

    _log.info("sub: channels to check: %s", ids)

    result = []
    for chat_id in ids:
        try:
            chat  = await bot.get_chat(chat_id)
            title = chat.title or str(chat_id)
            url   = chat.invite_link or (
                f"https://t.me/{chat.username}" if chat.username else None
            )
            result.append({"chat_id": chat_id, "title": title, "url": url})
        except Exception as e:
            _log.warning("sub: can't get channel info %s: %s", chat_id, e)
            result.append({"chat_id": chat_id, "title": str(chat_id), "url": None})

    return result


async def get_missing(bot: Bot, user_id: int, channels: list[dict]) -> list[dict]:
    result = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch["chat_id"], user_id)
            ok = member.status not in ("left", "kicked", "banned")
            _log.info("sub: user=%s channel=%s status=%s ok=%s",
                      user_id, ch["chat_id"], member.status, ok)
            if not ok:
                result.append(ch)
        except TelegramForbiddenError:
            _log.warning("sub: bot not admin in %s — skip", ch["chat_id"])
        except TelegramBadRequest as e:
            _log.warning("sub: bad request %s: %s — skip", ch["chat_id"], e)
        except Exception as e:
            _log.warning("sub: check error %s: %s — skip", ch["chat_id"], e)
    return result


async def send_block(bot: Bot, user_id: int, missing: list[dict], cb=None) -> None:
    names = " и ".join(f"«{ch['title']}»" for ch in missing)
    text  = _BLOCKED_TEXT.format(channels=names)
    kb    = _sub_keyboard(missing)
    if cb is not None:
        try:
            await cb.answer("🔒 подпишись на каналы.", show_alert=True)
        except Exception:
            pass
    try:
        await bot.send_message(user_id, text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        _log.error("sub: failed to send block to user=%s: %s", user_id, e)


class SubscriptionMiddleware(BaseMiddleware):
    """Один класс, регистрируется на dp.update.middleware."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        bot: Bot  = data["bot"]
        session   = data.get("session")

        # Достаём callback и message прямо из атрибутов Update
        cb  = getattr(event, "callback_query", None)
        msg = getattr(event, "message", None) or getattr(event, "edited_message", None)

        # ── Кнопка проверки подписки ──────────────────────────────
        if cb is not None and cb.data == "sub:check":
            _log.info("sub:check received from user=%s", user.id)
            await self._handle_check(cb, session, bot, user.id)
            return

        # ── Заглушка приватного канала ────────────────────────────
        if cb is not None and cb.data == "sub:noop":
            await cb.answer()
            return

        # ── Пропускаем /start и /admin ────────────────────────────
        if msg is not None and msg.text:
            cmd = msg.text.split()[0].lower().split("@")[0]
            if cmd in _BYPASS_COMMANDS:
                return await handler(event, data)

        if session is None:
            return await handler(event, data)

        # ── Администраторы не блокируются ─────────────────────────
        if await AdminRepository(session).is_admin(user.id):
            return await handler(event, data)

        # ── Проверка подписки ─────────────────────────────────────
        channels = await get_channels(session, bot)
        if not channels:
            return await handler(event, data)

        missing = await get_missing(bot, user.id, channels)
        if not missing:
            return await handler(event, data)

        _log.user("sub: blocking user=%s missing=%s",
                  user.id, [ch["title"] for ch in missing])
        await send_block(bot, user.id, missing, cb=cb)

    async def _handle_check(self, cb, session, bot: Bot, user_id: int) -> None:
        await cb.answer()  # сразу убираем крутилку
        _log.info("sub:check processing user=%s", user_id)

        if session is None:
            await bot.send_message(user_id, "⚠️ ошибка сессии, попробуй позже.")
            return

        channels = await get_channels(session, bot)
        missing  = await get_missing(bot, user_id, channels)

        if not missing:
            _log.info("sub:check PASSED user=%s", user_id)
            try:
                await cb.message.delete()
            except Exception:
                pass
            await bot.send_message(
                user_id,
                "✅ подписка подтверждена.\n\nдобро пожаловать.",
                reply_markup=kb_main_menu(),
                parse_mode="HTML",
            )
        else:
            _log.info("sub:check FAILED user=%s missing=%s",
                      user_id, [ch["title"] for ch in missing])
            await send_block(bot, user_id, missing)