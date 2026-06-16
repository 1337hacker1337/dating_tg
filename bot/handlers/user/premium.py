"""
bot/handlers/user/premium.py — SHROOM+ подписка через Telegram Stars.

Несколько тарифов (PREMIUM_PLANS): кнопка на тариф → инвойс. payload вида
"premium_v2:<days>" — срок берётся из payload при оплате (продлевается стопкой).

Платёжные апдейты (pre_checkout / successful_payment) пропускаются middleware
подписки/бана. И delete-анкеты, и premium ловят successful_payment — поэтому
фильтруются по payload (delete — по равенству, premium — по префиксу).
"""
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, PreCheckoutQuery, LabeledPrice,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot import logger as log
from bot.constants import (
    PREMIUM_PLANS, PREMIUM_PAYLOAD_PREFIX, PREMIUM_BADGE,
)
from bot.utils.formatting import render_premium_offer
from db.repositories.user_repo import UserRepository

_log = log.get(__name__)
router = Router(name="premium")

_PLAN_STARS = dict(PREMIUM_PLANS)   # days -> stars


def _plans_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for days, stars in PREMIUM_PLANS:
        b.button(text=f"{days} дней  ·  {stars} ⭐", callback_data=f"premium:buy:{days}")
    b.adjust(1)
    return b.as_markup()


async def _send_premium_screen(user_id: int, target, session: AsyncSession) -> None:
    repo = UserRepository(session)
    user = await repo.get_light(user_id)
    expires = user.premium_until if (user and user.is_premium) else None
    await target.answer(
        render_premium_offer(expires), parse_mode="HTML", reply_markup=_plans_kb()
    )


@router.message(Command("premium"))
async def cmd_premium(message: Message, session: AsyncSession):
    await _send_premium_screen(message.from_user.id, message, session)


@router.callback_query(F.data == "premium")
async def cb_premium(call: CallbackQuery, session: AsyncSession):
    await call.answer()
    await _send_premium_screen(call.from_user.id, call.message, session)


@router.callback_query(F.data.startswith("premium:buy:"))
async def premium_buy(call: CallbackQuery, bot: Bot):
    days  = int(call.data.split(":")[2])
    stars = _PLAN_STARS.get(days)
    if stars is None:
        await call.answer("неизвестный тариф.", show_alert=True)
        return
    await call.answer()
    pay_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"{PREMIUM_BADGE} оплатить · {stars} ⭐", pay=True),
    ]])
    await bot.send_invoice(
        chat_id=call.from_user.id,
        title="✦ SHROOM+",
        description=(
            f"{days} дней премиума:\n"
            "• свайпов гораздо больше\n"
            "• приоритет в ленте\n"
            "• возврат к анкете в ленте\n"
            "• кто смотрел анкету\n"
            f"• бейдж {PREMIUM_BADGE} в анкете\n\n"
            "продление добавляется к текущему сроку."
        ),
        payload=f"{PREMIUM_PAYLOAD_PREFIX}{days}",
        currency="XTR",
        prices=[LabeledPrice(label=f"SHROOM+ · {days} дней", amount=stars)],
        provider_token="",
        reply_markup=pay_kb,
    )


@router.pre_checkout_query(F.invoice_payload.startswith(PREMIUM_PAYLOAD_PREFIX))
async def pre_checkout_premium(query: PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment.invoice_payload.startswith(PREMIUM_PAYLOAD_PREFIX))
async def premium_paid(message: Message, session: AsyncSession):
    payload = message.successful_payment.invoice_payload
    try:
        days = int(payload.split(":")[1])
    except (IndexError, ValueError):
        days = 30

    repo  = UserRepository(session)
    until = await repo.grant_premium(message.from_user.id, days)
    await session.commit()

    _log.user(
        "premium paid: user=%s days=%d stars=%d until=%s",
        message.from_user.id, days,
        message.successful_payment.total_amount, until.isoformat(),
    )
    await message.answer(
        "✦  <b>SHROOM+ активирован</b>\n\n"
        f"тариф: {days} дней\n"
        f"действует до  {until.strftime('%d.%m.%Y %H:%M UTC')}\n\n"
        "🩸 повышенный лимит свайпов уже работает\n"
        "↩️ возврат к анкете — кнопка в ленте",
        parse_mode="HTML",
    )
