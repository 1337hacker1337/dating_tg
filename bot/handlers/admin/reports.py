"""bot/handlers/admin/reports.py — раздел репортов в админ-панели."""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot import logger as log
from bot.constants import REASON_LABELS
from bot.keyboards import kb_admin_back, kb_report_actions
from db.repositories.report_repo import ReportRepository
from db.repositories.user_repo import UserRepository

_log = log.get(__name__)
router = Router(name="admin_reports")


async def _show_report_page(call: CallbackQuery, session: AsyncSession, page: int) -> None:
    repo  = ReportRepository(session)
    total = await repo.count_pending()

    if total == 0:
        text = "🚩  нет новых репортов."
        try:
            await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_admin_back())
        except Exception:
            await call.message.answer(text, parse_mode="HTML", reply_markup=kb_admin_back())
        return

    page   = max(0, min(page, total - 1))
    report = await repo.get_pending_at(page)
    if report is None:
        return

    user_repo   = UserRepository(session)
    reporter    = await user_repo.get_light(report.reporter_id)
    target_user = await user_repo.get_light(report.target_id)

    def _fmt(u):
        if u is None:
            return "<i>удалён</i>"
        mention = f"@{u.username}" if u.username else "нет username"
        status  = "🚷" if u.is_banned else ("✅" if u.is_active else "🙈")
        return f"<b>{u.name}</b>, {u.age}  {status}\n         <code>{u.id}</code>  ·  {mention}"

    reason_val   = report.reason.value if hasattr(report.reason, "value") else str(report.reason)
    reason_label = REASON_LABELS.get(reason_val, reason_val)
    ts           = report.created_at.strftime("%d.%m.%Y %H:%M UTC")

    text = (
        f"🚩  <b>репорты</b>\n\n"
        f"от:      {_fmt(reporter)}\n\n"
        f"на:      {_fmt(target_user)}\n\n"
        f"причина: {reason_label}\n"
        f"время:   {ts}"
    )

    is_banned = target_user.is_banned if target_user else True
    kb        = kb_report_actions(report.id, report.target_id, is_banned, page, total)

    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=kb)


# ── Вход ──────────────────────────────────────────────────────────
# Ловим оба формата: "adm:reports" и устаревший "adm:reports:N"

@router.callback_query(F.data.startswith("adm:reports"))
async def adm_reports_entry(call: CallbackQuery, session: AsyncSession):
    await call.answer()
    parts = call.data.split(":")
    page  = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    try:
        await _show_report_page(call, session, page)
    except Exception as e:
        _log.error("adm_reports_entry error: %s", e, exc_info=True)
        try:
            await call.message.answer(
                f"⚠️ ошибка: <code>{e}</code>",
                parse_mode="HTML", reply_markup=kb_admin_back(),
            )
        except Exception:
            pass


# ── Навигация ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:rep_page:"))
async def adm_reports_nav(call: CallbackQuery, session: AsyncSession):
    await call.answer()
    try:
        page = int(call.data.split(":")[2])
        await _show_report_page(call, session, page)
    except Exception as e:
        _log.error("adm_reports_nav error: %s", e, exc_info=True)


# ── Забанить + закрыть ────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:rep_ban:"))
async def adm_rep_ban(call: CallbackQuery, session: AsyncSession):
    parts     = call.data.split(":")
    report_id = int(parts[2])
    page      = int(parts[3])

    repo = ReportRepository(session)
    # БАГФИКС: репорт берём по id, а не по offset страницы —
    # offset сдвигается, если другой админ параллельно закрыл репорты,
    # и раньше бан мог молча не выполниться при показанном «забанено».
    report = await repo.get_by_id(report_id)

    if report is None or report.is_reviewed:
        try:
            await call.answer("репорт уже обработан.", show_alert=True)
        except Exception:
            pass
        await _show_report_page(call, session, page)
        return

    await UserRepository(session).set_banned(report.target_id, True)
    await repo.mark_reviewed(report_id)
    await session.commit()
    _log.user("admin rep_ban: admin=%s target=%s", call.from_user.id, report.target_id)

    try:
        await call.answer("🚷 забанено.", show_alert=False)
    except Exception:
        pass
    await _show_report_page(call, session, page)


# ── Отклонить ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:rep_dismiss:"))
async def adm_rep_dismiss(call: CallbackQuery, session: AsyncSession):
    parts     = call.data.split(":")
    report_id = int(parts[2])
    page      = int(parts[3])

    repo = ReportRepository(session)
    await repo.mark_reviewed(report_id)
    await session.commit()
    _log.user("admin rep_dismiss: admin=%s report=%s", call.from_user.id, report_id)
    try:
        await call.answer("✅ отклонено.", show_alert=False)
    except Exception:
        pass
    # После отклонения total--; если были не на первой странице — сдвигаемся назад
    await _show_report_page(call, session, max(0, page - 1))
