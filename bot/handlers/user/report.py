"""
bot/handlers/user/report.py — жалоба на анкету. Доступна из ленты, лайков и мэтчей.

Схема callback_data (без FSM — target_id прямо в данных):
  report:start:{target_id}        — показать выбор причины
  report:do:{target_id}:{reason}  — сохранить и подтвердить
  report:cancel                   — отмена
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot import logger as log
from bot.constants import REPORT_LIMIT_PER_HOUR, REASON_LABELS
from bot.keyboards import kb_report_reasons
from db.repositories.report_repo import ReportRepository

_log = log.get(__name__)
router = Router(name="report")


@router.callback_query(F.data.startswith("report:start:"))
async def report_start(call: CallbackQuery):
    target_id = int(call.data.split(":")[2])

    if target_id == call.from_user.id:
        await call.answer("нельзя пожаловаться на себя.", show_alert=True)
        return

    await call.answer()
    await call.message.answer(
        "🚩  причина жалобы:",
        reply_markup=kb_report_reasons(target_id),
    )


@router.callback_query(F.data.startswith("report:do:"))
async def report_do(call: CallbackQuery, session: AsyncSession):
    _, _, target_id_str, reason = call.data.split(":")
    target_id = int(target_id_str)

    repo = ReportRepository(session)

    # Антиспам: не больше N репортов в час
    recent = await repo.count_recent_by_reporter(call.from_user.id)
    if recent >= REPORT_LIMIT_PER_HOUR:
        try:
            await call.answer("⏳  лимит репортов.  попробуй через час.", show_alert=True)
        except Exception:
            pass
        return

    is_new = await repo.add(call.from_user.id, target_id, reason)
    await session.commit()

    _log.user("report: reporter=%s target=%s reason=%s new=%s",
              call.from_user.id, target_id, reason, is_new)

    label = REASON_LABELS.get(reason, reason)
    if is_new:
        text = f"🚩  жалоба отправлена.\nпричина: {label}"
    else:
        text = "ты уже отправлял жалобу на этого пользователя."

    try:
        await call.answer(text, show_alert=True)
    except Exception:
        pass

    try:
        await call.message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "report:cancel")
async def report_cancel(call: CallbackQuery):
    await call.answer()
    try:
        await call.message.delete()
    except Exception:
        pass
