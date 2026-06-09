"""
bot/handlers/admin.py — Telegram-админ панель.
"""
import asyncio
from datetime import datetime, timezone

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot import logger as log
from bot.keyboards_admin import (
    kb_admin_main, kb_admin_back, kb_admin_confirm,
    kb_admin_user_actions, kb_admins_list,
    kb_ad_channel, kb_ad_timer,
)
from bot.middlewares.admin_guard import AdminMiddleware
from bot.states_admin import (
    AdminBan, AdminUnban, AdminLookup, AdminBroadcast,
    AdminCalibration, AdminAdChannel,
)
from config import settings
from db.models import User, Like, Match
from db.repositories.admin_repo import AdminRepository
from db.repositories.settings_repo import SettingsRepository
from db.repositories.user_repo import UserRepository
from bot.rating import format_rating_line

_log = log.get(__name__)

router = Router(name="admin")
router.message.middleware(AdminMiddleware())
router.callback_query.middleware(AdminMiddleware())


# ════════════════════════════════════════════════════════════════
# Вспомогательные
# ════════════════════════════════════════════════════════════════

async def _stats_text(session: AsyncSession) -> str:
    repo = UserRepository(session)
    total  = await repo.count_total()
    active = await repo.count_active()
    banned = await repo.count_banned()
    likes_r   = await session.execute(
        select(func.count()).select_from(Like).where(Like.value.is_(True))
    )
    matches_r = await session.execute(select(func.count()).select_from(Match))
    return (
        "<b>📊 статистика</b>\n\n"
        f"👥 <code>{total}</code>  ·  ✅ <code>{active}</code>  ·  🚷 <code>{banned}</code>\n\n"
        f"🩸 <code>{likes_r.scalar()}</code>  ·  ⚔️ <code>{matches_r.scalar()}</code>"
    )


async def _user_card(user: User, session: AsyncSession) -> str:
    repo  = UserRepository(session)
    stats = await repo.get_profile_stats(user.id)
    status  = "🚷 забанен" if user.is_banned else ("✅ активен" if user.is_active else "🙈 скрыт")
    geo     = (
        f"{user.latitude:.4f}, {user.longitude:.4f}"
        if user.latitude is not None and user.longitude is not None
        else "нет"
    )
    mention = f"@{user.username}" if user.username else "нет username"
    return (
        f"<b>#{user.id}</b>  <b>{user.name}</b>, {user.age}\n"
        f"<code>{user.id}</code>  ·  {mention}\n"
        f"{user.gender.value}  ·  {user.looking_for.value}  ·  {status}\n"
        f"📡 {geo}\n\n"
        f"{format_rating_line(user.avg_rating, user.rating_count)}\n\n"
        f"🩸 <code>{stats['likes']}</code>  ·  "
        f"🤮 <code>{stats['dislikes']}</code>  ·  "
        f"⚔️ <code>{stats['matches']}</code>"
    )


def _fmt_expires(expires: datetime | None) -> str:
    """Форматирует время истечения в читаемый вид с остатком."""
    if expires is None:
        return "постоянно ♾"
    now = datetime.now(tz=timezone.utc)
    if now >= expires:
        return "истёк ❌"
    delta = expires - now
    total_minutes = int(delta.total_seconds() // 60)
    days    = total_minutes // 1440
    hours   = (total_minutes % 1440) // 60
    minutes = total_minutes % 60
    parts = []
    if days:    parts.append(f"{days}д")
    if hours:   parts.append(f"{hours}ч")
    if minutes: parts.append(f"{minutes}м")
    remaining = " ".join(parts) or "< 1м"
    ts = expires.strftime("%d.%m.%Y %H:%M UTC")
    return f"{ts}  (осталось {remaining})"


async def _ad_channel_text(session: AsyncSession, bot: Bot) -> str:
    repo       = SettingsRepository(session)
    ad_channel = await repo.get_ad_channel()
    ad_expires = await repo.get_ad_expires()
    own        = settings.own_channel_id

    lines = ["<b>📢 управление рекламой</b>\n"]

    # Свой канал
    if own:
        lines.append(f"🏠 свой канал:  <code>{own}</code>  <i>(постоянно, из .env)</i>")
    else:
        lines.append("🏠 свой канал:  <i>не настроен</i>")

    # Рекламный канал
    if ad_channel:
        try:
            chat  = await bot.get_chat(ad_channel)
            title = chat.title or ad_channel
            lines.append(f"📢 рекламный:   <code>{ad_channel}</code>  «{title}»")
        except Exception:
            lines.append(f"📢 рекламный:   <code>{ad_channel}</code>")
        lines.append(f"⏱ таймер:       {_fmt_expires(ad_expires)}")
    else:
        lines.append("📢 рекламный:   <i>не установлен</i>")

    lines.append("")
    lines.append("<i>бот должен быть администратором в каналах.</i>")
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════
# /admin — вход
# ════════════════════════════════════════════════════════════════

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


# ════════════════════════════════════════════════════════════════
# 📊 Статистика
# ════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:stats")
async def adm_stats(call: CallbackQuery, session: AsyncSession):
    await call.answer()
    text = await _stats_text(session)
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_admin_back())
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=kb_admin_back())


# ════════════════════════════════════════════════════════════════
# 👤 Найти юзера / ➕ Добавить админа
# ════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:lookup")
async def adm_lookup_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("🔍 telegram ID пользователя:",
                               parse_mode="HTML", reply_markup=kb_admin_back())
    await state.set_state(AdminLookup.waiting_id)
    await state.update_data(add_admin_mode=False)


@router.callback_query(F.data == "adm:add_admin")
async def adm_add_admin_prompt(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("➕ telegram ID нового администратора:",
                               parse_mode="HTML", reply_markup=kb_admin_back())
    await state.set_state(AdminLookup.waiting_id)
    await state.update_data(add_admin_mode=True)


@router.message(AdminLookup.waiting_id)
async def adm_lookup_handler(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("↑ числовой ID.")
        return

    data      = await state.get_data()
    add_mode  = data.get("add_admin_mode", False)
    target_id = int(raw)
    await state.clear()

    repo = UserRepository(session)
    user = await repo.get(target_id)

    if add_mode:
        admin_repo = AdminRepository(session)
        if await admin_repo.is_admin(target_id):
            await message.answer("уже администратор.", reply_markup=kb_admin_back())
            return
        username = user.username if user else None
        await admin_repo.add(telegram_id=target_id, username=username)
        await session.commit()
        _log.user("admin add_admin: admin=%s new=%s", message.from_user.id, target_id)
        await message.answer(f"✅ <code>{target_id}</code> добавлен.",
                             parse_mode="HTML", reply_markup=kb_admin_back())
    else:
        if user is None:
            await message.answer("не найдено.", reply_markup=kb_admin_back())
            return
        text = await _user_card(user, session)
        kb   = kb_admin_user_actions(user.id, user.is_banned)
        if user.photos:
            await message.answer_photo(photo=user.photos[0].file_id,
                                       caption=text, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
        _log.user("admin lookup: admin=%s target=%s", message.from_user.id, target_id)


# ════════════════════════════════════════════════════════════════
# 🚷 Бан / ✅ Разбан
# ════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:ban")
async def adm_ban_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("🚷 telegram ID для бана:",
                               parse_mode="HTML", reply_markup=kb_admin_back())
    await state.set_state(AdminBan.waiting_id)


@router.message(AdminBan.waiting_id)
async def adm_ban_exec(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("↑ числовой ID.")
        return
    await _do_ban(int(raw), message.from_user.id, session, message)
    await state.clear()


@router.callback_query(F.data.startswith("adm:do_ban:"))
async def adm_ban_inline(call: CallbackQuery, session: AsyncSession):
    await call.answer()
    await _do_ban(int(call.data.split(":")[2]), call.from_user.id, session, call.message)


async def _do_ban(target_id: int, admin_id: int, session: AsyncSession, reply_to) -> None:
    repo = UserRepository(session)
    user = await repo.get_light(target_id)
    if user is None:
        await reply_to.answer("не найдено.", reply_markup=kb_admin_back())
        return
    if user.is_banned:
        await reply_to.answer("уже забанен.", reply_markup=kb_admin_back())
        return
    await repo.set_banned(target_id, True)
    await session.commit()
    _log.user("admin ban: admin=%s target=%s", admin_id, target_id)
    await reply_to.answer(f"🚷 <code>{target_id}</code> забанен.",
                          parse_mode="HTML", reply_markup=kb_admin_back())


@router.callback_query(F.data == "adm:unban")
async def adm_unban_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("✅ telegram ID для разбана:",
                               parse_mode="HTML", reply_markup=kb_admin_back())
    await state.set_state(AdminUnban.waiting_id)


@router.message(AdminUnban.waiting_id)
async def adm_unban_exec(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("↑ числовой ID.")
        return
    await _do_unban(int(raw), message.from_user.id, session, message)
    await state.clear()


@router.callback_query(F.data.startswith("adm:do_unban:"))
async def adm_unban_inline(call: CallbackQuery, session: AsyncSession):
    await call.answer()
    await _do_unban(int(call.data.split(":")[2]), call.from_user.id, session, call.message)


async def _do_unban(target_id: int, admin_id: int, session: AsyncSession, reply_to) -> None:
    repo = UserRepository(session)
    user = await repo.get_light(target_id)
    if user is None:
        await reply_to.answer("не найдено.", reply_markup=kb_admin_back())
        return
    if not user.is_banned:
        await reply_to.answer("не забанен.", reply_markup=kb_admin_back())
        return
    await repo.set_banned(target_id, False)
    await session.commit()
    _log.user("admin unban: admin=%s target=%s", admin_id, target_id)
    await reply_to.answer(f"✅ <code>{target_id}</code> разбанен.",
                          parse_mode="HTML", reply_markup=kb_admin_back())


# ════════════════════════════════════════════════════════════════
# 📣 Рассылка
# ════════════════════════════════════════════════════════════════

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


# ════════════════════════════════════════════════════════════════
# 🧬 Калибровка
# ════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:calibration")
async def adm_cal_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer(
        "🧬 <b>калибровка</b>  — telegram ID:",
        parse_mode="HTML", reply_markup=kb_admin_back(),
    )
    await state.set_state(AdminCalibration.waiting_id)


@router.message(AdminCalibration.waiting_id)
async def adm_cal_user(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("↑ числовой ID.")
        return
    user_id = int(raw)
    repo    = UserRepository(session)
    user    = await repo.get_light(user_id)
    if user is None:
        await message.answer("не найдено.", reply_markup=kb_admin_back())
        await state.clear()
        return
    await state.update_data(cal_target_id=user_id)
    await message.answer(
        f"<b>{user.name}</b>  <code>{user_id}</code>\n"
        f"{format_rating_line(user.avg_rating, user.rating_count)}\n\n"
        "новый <b>rating_count</b>.\n<i>0 — полный сброс</i>",
        parse_mode="HTML", reply_markup=kb_admin_back(),
    )
    await state.set_state(AdminCalibration.waiting_votes)


@router.message(AdminCalibration.waiting_votes)
async def adm_cal_apply(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("↑ неотрицательное число.")
        return
    data      = await state.get_data()
    target_id = data["cal_target_id"]
    new_count = int(raw)
    await session.execute(
        update(User).where(User.id == target_id).values(rating_count=new_count)
    )
    await session.commit()
    await state.clear()
    _log.user("admin calibration: admin=%s target=%s new_count=%d",
              message.from_user.id, target_id, new_count)
    await message.answer(
        f"🧬 <code>{target_id}</code>  →  <code>{new_count}</code>",
        parse_mode="HTML", reply_markup=kb_admin_back(),
    )


@router.callback_query(F.data.startswith("adm:do_reset_cal:"))
async def adm_reset_cal_inline(call: CallbackQuery, session: AsyncSession):
    target_id = int(call.data.split(":")[2])
    await session.execute(
        update(User).where(User.id == target_id).values(rating_count=0, avg_rating=0.0)
    )
    await session.commit()
    await call.answer("🧬 сброшено.", show_alert=True)
    _log.user("admin reset_cal inline: admin=%s target=%s", call.from_user.id, target_id)


# ════════════════════════════════════════════════════════════════
# 👑 Администраторы
# ════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:admins")
async def adm_admins_list(call: CallbackQuery, session: AsyncSession):
    await call.answer()
    repo   = AdminRepository(session)
    admins = await repo.list_all()
    lines  = ["<b>👑 администраторы</b>\n"]
    for a in admins:
        label = f"@{a.username}" if a.username else str(a.telegram_id)
        lines.append(f"<code>{a.telegram_id}</code>  ·  {label}")
    text = "\n".join(lines) if admins else "список пуст."
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_admins_list(admins))
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=kb_admins_list(admins))


@router.callback_query(F.data.startswith("adm:rm_admin:"))
async def adm_remove_admin(call: CallbackQuery, session: AsyncSession):
    target_id = int(call.data.split(":")[2])
    if target_id == call.from_user.id:
        await call.answer("нельзя удалить себя.", show_alert=True)
        return
    repo = AdminRepository(session)
    await repo.remove(target_id)
    await session.commit()
    await call.answer(f"{target_id} удалён.", show_alert=True)
    _log.user("admin rm_admin: admin=%s removed=%s", call.from_user.id, target_id)
    admins = await repo.list_all()
    lines  = ["<b>👑 администраторы</b>\n"]
    for a in admins:
        label = f"@{a.username}" if a.username else str(a.telegram_id)
        lines.append(f"<code>{a.telegram_id}</code>  ·  {label}")
    text = "\n".join(lines) if admins else "список пуст."
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_admins_list(admins))
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=kb_admins_list(admins))


# ════════════════════════════════════════════════════════════════
# 📢 Рекламный канал + ⏱ Таймер
# ════════════════════════════════════════════════════════════════

async def _show_ad_menu(target, session: AsyncSession, bot: Bot) -> None:
    """target — CallbackQuery или Message."""
    repo       = SettingsRepository(session)
    ad_channel = await repo.get_ad_channel()
    ad_expires = await repo.get_ad_expires()
    text       = await _ad_channel_text(session, bot)
    kb         = kb_ad_channel(bool(ad_channel), ad_expires is not None)
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await target.message.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "adm:ad_channel")
async def adm_ad_channel_menu(call: CallbackQuery, session: AsyncSession, bot: Bot):
    await call.answer()
    await _show_ad_menu(call, session, bot)


# ── Установить канал ─────────────────────────────────────────────

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


# ── Таймер ───────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:ad_timer")
async def adm_ad_timer_menu(call: CallbackQuery, session: AsyncSession):
    await call.answer()
    repo    = SettingsRepository(session)
    expires = await repo.get_ad_expires()
    text    = (
        f"⏱ <b>таймер рекламы</b>\n\n"
        f"сейчас: {_fmt_expires(expires)}\n\n"
        "выбери новый срок:"
    )
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_ad_timer())
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=kb_ad_timer())


@router.callback_query(F.data.startswith("adm:ad_timer_set:"))
async def adm_ad_timer_set(call: CallbackQuery, session: AsyncSession, bot: Bot):
    hours = int(call.data.split(":")[2])
    repo  = SettingsRepository(session)
    expires = await repo.set_ad_expires_hours(hours)
    await session.commit()

    if hours == 0:
        label = "постоянно ♾"
    else:
        label = _fmt_expires(expires)

    _log.user("admin ad_timer set: admin=%s hours=%d expires=%s",
              call.from_user.id, hours, expires)
    await call.answer(f"⏱ таймер установлен", show_alert=False)

    # Возвращаемся в меню рекламы с обновлёнными данными
    await _show_ad_menu(call, session, bot)


# ── Отключить канал ──────────────────────────────────────────────

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
