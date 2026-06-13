"""bot/handlers/admin/broadcast.py — рассылка всем активным."""
import asyncio

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot import logger as log
from bot.keyboards import kb_admin_back, kb_admin_confirm
from bot.states import AdminBroadcast
from db.models import User

_log = log.get(__name__)
router = Router(name="admin_broadcast")


@router.callback_query(F.data == "adm:broadcast")
async def adm_broadcast_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer(
        "📣 текст рассылки.  <i>поддерживается HTML</i>",
        parse_mode="HTML", reply_markup=kb_admin_back(),
    )
    await state.set_state(AdminBroadcast.waiting_text)


@router.message(AdminBroadcast.waiting_text)
async def adm_broadcast_preview(message: Message, state: FSMContext):
    text = message.text or message.caption or ""
    if not text.strip():
        await message.answer("↑ текст не может быть пустым.")
        return
    await state.update_data(broadcast_text=text)
    await message.answer(
        f"<b>предпросмотр:</b>\n\n{text}\n\nотправить всем активным?",
        parse_mode="HTML", reply_markup=kb_admin_confirm("broadcast"),
    )
    await state.set_state(AdminBroadcast.confirm)


@router.callback_query(F.data == "adm:confirm:broadcast", AdminBroadcast.confirm)
async def adm_broadcast_exec(call: CallbackQuery, state: FSMContext, bot: Bot,
                             session: AsyncSession):
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    await state.clear()
    await call.answer()
    result   = await session.execute(
        select(User.id).where(User.is_active.is_(True), User.is_banned.is_(False))
    )
    user_ids = [row[0] for row in result.fetchall()]
    await call.message.answer(f"⏳ {len(user_ids)} получателей...", parse_mode="HTML")
    ok = fail = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    _log.user("admin broadcast: admin=%s sent=%d fail=%d", call.from_user.id, ok, fail)
    await call.message.answer(
        f"готово.\n✅ <code>{ok}</code>  ·  ✗ <code>{fail}</code>",
        parse_mode="HTML", reply_markup=kb_admin_back(),
    )
