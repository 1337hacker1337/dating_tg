"""
bot/handlers/user/referral.py — реферальная программа.

Юзер получает диплинк ?start=ref_<свой_id>. Каждый, кто регистрируется
по нему, приносит обоим бонусные свайпы (см. bot/constants.py).
Начисление и привязка реферера происходят в handlers/user/start.py.
"""
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, LinkPreviewOptions
from sqlalchemy.ext.asyncio import AsyncSession

from bot import logger as log
from bot.constants import (
    REFERRAL_PREFIX, REFERRAL_BONUS_SWIPES, SWIPE_LIMIT, SWIPE_WINDOW_HOURS,
)
from db.repositories.user_repo import UserRepository

_log = log.get(__name__)
router = Router(name="referral")

_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


async def _invite_text(user_id: int, bot: Bot, session: AsyncSession) -> str:
    repo = UserRepository(session)
    user = await repo.get_light(user_id)

    me   = await bot.get_me()
    link = f"https://t.me/{me.username}?start={REFERRAL_PREFIX}{user_id}"

    count = await repo.count_referrals(user_id)
    bonus = user.bonus_swipes if user else 0
    limit = SWIPE_LIMIT + bonus

    return (
        "🔗  <b>приглашай — получай свайпы</b>\n\n"
        f"за каждого, кто зарегается по твоей ссылке:  <b>+{REFERRAL_BONUS_SWIPES}</b> свайпов.\n\n"
        f"приглашено:        <code>{count}</code>\n"
        f"бонусных свайпов:  <code>{bonus}</code>\n"
        f"твой лимит сейчас: <code>{limit}</code> свайпов / {SWIPE_WINDOW_HOURS}ч\n\n"
        f"<b>твоя ссылка:</b>\n{link}"
    )


@router.message(Command("invite"))
async def cmd_invite(message: Message, bot: Bot, session: AsyncSession):
    text = await _invite_text(message.from_user.id, bot, session)
    await message.answer(text, parse_mode="HTML", link_preview_options=_NO_PREVIEW)


@router.callback_query(F.data == "invite")
async def cb_invite(call: CallbackQuery, bot: Bot, session: AsyncSession):
    await call.answer()
    text = await _invite_text(call.from_user.id, bot, session)
    await call.message.answer(text, parse_mode="HTML", link_preview_options=_NO_PREVIEW)
