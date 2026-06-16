"""bot/handlers/admin/panel.py — вход в панель, меню, статистика."""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot import logger as log
from bot.keyboards import kb_admin_main, kb_admin_back
from db.models import Like, Match
from db.repositories.user_repo import UserRepository

_log = log.get(__name__)
router = Router(name="admin_panel")


async def _stats_text(session: AsyncSession) -> str:
    repo = UserRepository(session)
    total  = await repo.count_total()
    active = await repo.count_active()
    banned = await repo.count_banned()
    premium = await repo.count_premium()
    likes_r   = await session.execute(
        select(func.count()).select_from(Like).where(Like.value.is_(True))
    )
    matches_r = await session.execute(select(func.count()).select_from(Match))
    return (
        "<b>📊 статистика</b>\n\n"
        f"👥 <code>{total}</code>  ·  ✅ <code>{active}</code>  ·  🚷 <code>{banned}</code>\n"
        f"✦ <code>{premium}</code> с SHROOM+\n\n"
        f"🩸 <code>{likes_r.scalar()}</code>  ·  ⚔️ <code>{matches_r.scalar()}</code>"
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("👑 <b>панель администратора</b>",
                         parse_mode="HTML", reply_markup=kb_admin_main())
    _log.user("admin panel opened: user=%s", message.from_user.id)


@router.callback_query(F.data == "adm:menu")
async def adm_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    try:
        await call.message.edit_text("👑 <b>панель администратора</b>",
                                     parse_mode="HTML", reply_markup=kb_admin_main())
    except Exception:
        await call.message.answer("👑 <b>панель администратора</b>",
                                  parse_mode="HTML", reply_markup=kb_admin_main())


@router.callback_query(F.data == "adm:stats")
async def adm_stats(call: CallbackQuery, session: AsyncSession):
    await call.answer()
    text = await _stats_text(session)
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_admin_back())
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=kb_admin_back())
