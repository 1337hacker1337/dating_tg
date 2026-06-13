"""bot/handlers/admin/ads.py — рекламный канал и таймер."""
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot import logger as log
from bot.keyboards import kb_admin_back, kb_ad_channel, kb_ad_timer
from bot.states import AdminAdChannel
from bot.utils.formatting import fmt_expires
from config import settings
from db.repositories.settings_repo import SettingsRepository

_log = log.get(__name__)
router = Router(name="admin_ads")


async def _ad_channel_text(session: AsyncSession, bot: Bot) -> str:
    repo       = SettingsRepository(session)
    ad_channel = await repo.get_ad_channel()
    ad_expires = await repo.get_ad_expires()
    own        = settings.own_channel_id

    lines = ["<b>📢 управление рекламой</b>\n"]
    if own:
        lines.append(f"🏠 свой канал:  <code>{own}</code>  <i>(постоянно, из .env)</i>")
    else:
        lines.append("🏠 свой канал:  <i>не настроен</i>")

    if ad_channel:
        try:
            chat  = await bot.get_chat(ad_channel)
            title = chat.title or ad_channel
            lines.append(f"📢 рекламный:   <code>{ad_channel}</code>  «{title}»")
        except Exception:
            lines.append(f"📢 рекламный:   <code>{ad_channel}</code>")
        lines.append(f"⏱ таймер:       {fmt_expires(ad_expires)}")
    else:
        lines.append("📢 рекламный:   <i>не установлен</i>")

    lines.append("")
    lines.append("<i>бот должен быть администратором в каналах.</i>")
    return "\n".join(lines)


async def _show_ad_menu(call: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    repo       = SettingsRepository(session)
    ad_channel = await repo.get_ad_channel()
    ad_expires = await repo.get_ad_expires()
    text       = await _ad_channel_text(session, bot)
    kb         = kb_ad_channel(bool(ad_channel), ad_expires is not None)
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "adm:ad_channel")
async def adm_ad_channel_menu(call: CallbackQuery, session: AsyncSession, bot: Bot):
    await call.answer()
    await _show_ad_menu(call, session, bot)


# ── Установить канал ──────────────────────────────────────────────

@router.callback_query(F.data == "adm:ad_set")
async def adm_ad_set_prompt(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer(
        "📢 @username или числовой ID канала.\n"
        "<i>бот должен быть администратором в канале.</i>",
        parse_mode="HTML", reply_markup=kb_admin_back(),
    )
    await state.set_state(AdminAdChannel.waiting_channel)


@router.message(AdminAdChannel.waiting_channel)
async def adm_ad_set_exec(message: Message, state: FSMContext,
                          session: AsyncSession, bot: Bot):
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("↑ введи @username или ID.")
        return

    channel_id = raw if raw.startswith("@") or raw.lstrip("-").isdigit() else f"@{raw}"

    try:
        chat  = await bot.get_chat(channel_id)
        title = chat.title or channel_id
    except Exception as e:
        await message.answer(
            f"❌ не удалось получить канал <code>{channel_id}</code>.\n"
            f"<i>убедись что бот добавлен как администратор.</i>\n\n"
            f"ошибка: <code>{e}</code>",
            parse_mode="HTML", reply_markup=kb_admin_back(),
        )
        return

    repo = SettingsRepository(session)
    await repo.set_ad_channel(channel_id)
    await session.commit()
    await state.clear()

    _log.user("admin ad_channel set: admin=%s channel=%s", message.from_user.id, channel_id)
    await message.answer(
        f"✅ канал установлен: <b>{title}</b>  <code>{channel_id}</code>\n\n"
        f"теперь задай срок действия через ⏱ таймер.",
        parse_mode="HTML", reply_markup=kb_admin_back(),
    )


# ── Таймер ────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:ad_timer")
async def adm_ad_timer_menu(call: CallbackQuery, session: AsyncSession):
    await call.answer()
    repo    = SettingsRepository(session)
    expires = await repo.get_ad_expires()
    text    = (
        f"⏱ <b>таймер рекламы</b>\n\n"
        f"сейчас: {fmt_expires(expires)}\n\n"
        "выбери новый срок:"
    )
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_ad_timer())
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=kb_ad_timer())


@router.callback_query(F.data.startswith("adm:ad_timer_set:"))
async def adm_ad_timer_set(call: CallbackQuery, session: AsyncSession, bot: Bot):
    hours   = int(call.data.split(":")[2])
    repo    = SettingsRepository(session)
    expires = await repo.set_ad_expires_hours(hours)
    await session.commit()
    _log.user("admin ad_timer set: admin=%s hours=%d expires=%s",
              call.from_user.id, hours, expires)
    await call.answer("⏱ таймер установлен", show_alert=False)
    await _show_ad_menu(call, session, bot)


# ── Отключить канал ───────────────────────────────────────────────

@router.callback_query(F.data == "adm:ad_clear")
async def adm_ad_clear(call: CallbackQuery, session: AsyncSession):
    await call.answer()
    repo = SettingsRepository(session)
    await repo.set_ad_channel(None)
    await repo.set_ad_expires(None)
    await session.commit()
    _log.user("admin ad_channel cleared: admin=%s", call.from_user.id)
    await call.message.answer(
        "🗑 рекламный канал отключён.",
        parse_mode="HTML", reply_markup=kb_admin_back(),
    )
