"""
bot/handlers/admin.py
─────────────────────
Telegram-админ панель. Доступ — только через таблицу admins.
Команда входа: /admin

Функции:
  📊 Статистика      — юзеры / лайки / мэтчи / забанены
  👤 Найти юзера     — просмотр анкеты по telegram_id
  🚷 Забанить        — бан по telegram_id
  ✅ Разбанить       — разбан по telegram_id
  📣 Рассылка        — отправка сообщения всем активным юзерам
  🧬 Калибровка      — ручной сброс/редактирование rating_count юзера
  👑 Администраторы  — список и управление (добавить / удалить)
"""
import asyncio

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
)
from bot.middlewares.admin_guard import AdminMiddleware
from bot.states_admin import (
    AdminBan, AdminUnban, AdminLookup,
    AdminBroadcast, AdminCalibration,
)
from db.models import User, Like, Match
from db.repositories.admin_repo import AdminRepository
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
    user_repo = UserRepository(session)

    total   = await user_repo.count_total()
    active  = await user_repo.count_active()
    banned  = await user_repo.count_banned()

    likes_r = await session.execute(
        select(func.count()).select_from(Like).where(Like.value.is_(True))
    )
    total_likes = likes_r.scalar()

    matches_r = await session.execute(select(func.count()).select_from(Match))
    total_matches = matches_r.scalar()

    return (
        "<b>📊 Статистика</b>\n\n"
        f"├ 👥 Всего юзеров:   <code>{total}</code>\n"
        f"├ ✅ Активных:        <code>{active}</code>\n"
        f"├ 🚷 Забанено:        <code>{banned}</code>\n"
        f"├ 🩸 Лайков всего:    <code>{total_likes}</code>\n"
        f"└ ⚔️  Мэтчей всего:   <code>{total_matches}</code>"
    )


async def _user_card(user: User, session: AsyncSession) -> str:
    likes_r = await session.execute(
        select(func.count()).where(Like.to_user == user.id, Like.value.is_(True))
    )
    dislikes_r = await session.execute(
        select(func.count()).where(Like.to_user == user.id, Like.value.is_(False))
    )
    matches_r = await session.execute(
        select(func.count()).select_from(Match).where(
            (Match.user1_id == user.id) | (Match.user2_id == user.id)
        )
    )

    status  = "🚷 ЗАБАНЕН" if user.is_banned else ("✅ активен" if user.is_active else "🙈 скрыт")
    geo     = f"{user.latitude:.4f}, {user.longitude:.4f}" if user.latitude else "не указана"
    mention = f"@{user.username}" if user.username else "нет username"

    return (
        f"<b>👤 Анкета #{user.id}</b>\n\n"
        f"├ Имя:       <b>{user.name}</b>, {user.age}\n"
        f"├ Telegram:  <code>{user.id}</code> · {mention}\n"
        f"├ Пол:       {user.gender.value}\n"
        f"├ Ищет:      {user.looking_for.value}\n"
        f"├ Статус:    {status}\n"
        f"├ Геолокация: {geo}\n"
        f"├ Рейтинг:   {format_rating_line(user.avg_rating, user.rating_count)}\n"
        f"├ 🩸 Лайков:  <code>{likes_r.scalar()}</code>\n"
        f"├ ⚰️ Дизов:   <code>{dislikes_r.scalar()}</code>\n"
        f"└ ⚔️ Мэтчей:  <code>{matches_r.scalar()}</code>"
    )


# ════════════════════════════════════════════════════════════════
# /admin  — вход в панель
# ════════════════════════════════════════════════════════════════

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👑 <b>Панель администратора</b>",
        parse_mode="HTML",
        reply_markup=kb_admin_main(),
    )
    _log.user("admin panel opened: user=%s", message.from_user.id)


# ════════════════════════════════════════════════════════════════
# Главное меню (callback)
# ════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:menu")
async def adm_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    try:
        await call.message.edit_text(
            "👑 <b>Панель администратора</b>",
            parse_mode="HTML",
            reply_markup=kb_admin_main(),
        )
    except Exception:
        await call.message.answer(
            "👑 <b>Панель администратора</b>",
            parse_mode="HTML",
            reply_markup=kb_admin_main(),
        )


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
# 👤 Найти юзера
# ════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:lookup")
async def adm_lookup_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer(
        "🔍 Введи <b>Telegram ID</b> пользователя:",
        parse_mode="HTML",
        reply_markup=kb_admin_back(),
    )
    await state.set_state(AdminLookup.waiting_id)


@router.message(AdminLookup.waiting_id)
async def adm_lookup_exec(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("⚠️ Нужен числовой ID.")
        return

    user_id = int(raw)
    repo    = UserRepository(session)
    user    = await repo.get(user_id)
    await state.clear()

    if user is None:
        await message.answer("❌ Пользователь не найден.", reply_markup=kb_admin_back())
        return

    text = await _user_card(user, session)
    kb   = kb_admin_user_actions(user.id, user.is_banned)

    if user.photos:
        await message.answer_photo(
            photo=user.photos[0].file_id,
            caption=text,
            reply_markup=kb,
            parse_mode="HTML",
        )
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

    _log.user("admin lookup: admin=%s target=%s", message.from_user.id, user_id)


# ════════════════════════════════════════════════════════════════
# 🚷 Бан — ввод ID
# ════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:ban")
async def adm_ban_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer(
        "🚷 Введи <b>Telegram ID</b> для бана:",
        parse_mode="HTML",
        reply_markup=kb_admin_back(),
    )
    await state.set_state(AdminBan.waiting_id)


@router.message(AdminBan.waiting_id)
async def adm_ban_exec(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("⚠️ Нужен числовой ID.")
        return

    user_id = int(raw)
    await _do_ban(user_id, message.from_user.id, session, message)
    await state.clear()


# Бан напрямую с карточки юзера
@router.callback_query(F.data.startswith("adm:do_ban:"))
async def adm_ban_inline(call: CallbackQuery, session: AsyncSession):
    user_id = int(call.data.split(":")[2])
    await call.answer()
    await _do_ban(user_id, call.from_user.id, session, call.message)


async def _do_ban(
    target_id: int,
    admin_id: int,
    session: AsyncSession,
    reply_to,
) -> None:
    repo = UserRepository(session)
    user = await repo.get(target_id)
    if user is None:
        await reply_to.answer("❌ Пользователь не найден.", reply_markup=kb_admin_back())
        return
    if user.is_banned:
        await reply_to.answer("ℹ️ Уже забанен.", reply_markup=kb_admin_back())
        return

    await repo.set_banned(target_id, True)
    await session.commit()
    _log.user("admin ban: admin=%s target=%s", admin_id, target_id)
    await reply_to.answer(
        f"🚷 Пользователь <code>{target_id}</code> забанен.",
        parse_mode="HTML",
        reply_markup=kb_admin_back(),
    )


# ════════════════════════════════════════════════════════════════
# ✅ Разбан — ввод ID
# ════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:unban")
async def adm_unban_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer(
        "✅ Введи <b>Telegram ID</b> для разбана:",
        parse_mode="HTML",
        reply_markup=kb_admin_back(),
    )
    await state.set_state(AdminUnban.waiting_id)


@router.message(AdminUnban.waiting_id)
async def adm_unban_exec(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("⚠️ Нужен числовой ID.")
        return

    user_id = int(raw)
    await _do_unban(user_id, message.from_user.id, session, message)
    await state.clear()


@router.callback_query(F.data.startswith("adm:do_unban:"))
async def adm_unban_inline(call: CallbackQuery, session: AsyncSession):
    user_id = int(call.data.split(":")[2])
    await call.answer()
    await _do_unban(user_id, call.from_user.id, session, call.message)


async def _do_unban(
    target_id: int,
    admin_id: int,
    session: AsyncSession,
    reply_to,
) -> None:
    repo = UserRepository(session)
    user = await repo.get(target_id)
    if user is None:
        await reply_to.answer("❌ Пользователь не найден.", reply_markup=kb_admin_back())
        return
    if not user.is_banned:
        await reply_to.answer("ℹ️ Пользователь не забанен.", reply_markup=kb_admin_back())
        return

    await repo.set_banned(target_id, False)
    await session.commit()
    _log.user("admin unban: admin=%s target=%s", admin_id, target_id)
    await reply_to.answer(
        f"✅ Пользователь <code>{target_id}</code> разбанен.",
        parse_mode="HTML",
        reply_markup=kb_admin_back(),
    )


# ════════════════════════════════════════════════════════════════
# 📣 Рассылка
# ════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:broadcast")
async def adm_broadcast_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer(
        "📣 Введи текст рассылки.\n"
        "<i>Поддерживается HTML-разметка.</i>",
        parse_mode="HTML",
        reply_markup=kb_admin_back(),
    )
    await state.set_state(AdminBroadcast.waiting_text)


@router.message(AdminBroadcast.waiting_text)
async def adm_broadcast_preview(message: Message, state: FSMContext):
    text = message.text or message.caption or ""
    if not text.strip():
        await message.answer("⚠️ Текст не может быть пустым.")
        return

    await state.update_data(broadcast_text=text)
    await message.answer(
        f"<b>Предпросмотр:</b>\n\n{text}\n\n"
        "Отправить всем активным пользователям?",
        parse_mode="HTML",
        reply_markup=kb_admin_confirm("broadcast"),
    )
    await state.set_state(AdminBroadcast.confirm)


@router.callback_query(F.data == "adm:confirm:broadcast", AdminBroadcast.confirm)
async def adm_broadcast_exec(call: CallbackQuery, state: FSMContext, bot: Bot, session: AsyncSession):
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    await state.clear()
    await call.answer()

    # Получаем всех активных незабаненных
    result = await session.execute(
        select(User.id)
        .where(User.is_active.is_(True), User.is_banned.is_(False))
    )
    user_ids = [row[0] for row in result.fetchall()]

    await call.message.answer(
        f"⏳ Отправляю {len(user_ids)} пользователям...",
        parse_mode="HTML",
    )

    ok = fail = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)   # ~20 msg/s — в рамках лимитов TG

    _log.user(
        "admin broadcast: admin=%s sent=%d fail=%d",
        call.from_user.id, ok, fail,
    )
    await call.message.answer(
        f"✅ Рассылка завершена.\n"
        f"├ Доставлено: <code>{ok}</code>\n"
        f"└ Ошибок:     <code>{fail}</code>",
        parse_mode="HTML",
        reply_markup=kb_admin_back(),
    )


# ════════════════════════════════════════════════════════════════
# 🧬 Калибровка рейтинга
# ════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:calibration")
async def adm_cal_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer(
        "🧬 <b>Калибровка рейтинга</b>\n\n"
        "Введи <b>Telegram ID</b> пользователя:",
        parse_mode="HTML",
        reply_markup=kb_admin_back(),
    )
    await state.set_state(AdminCalibration.waiting_id)


@router.message(AdminCalibration.waiting_id)
async def adm_cal_user(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("⚠️ Нужен числовой ID.")
        return

    user_id = int(raw)
    repo    = UserRepository(session)
    user    = await repo.get(user_id)
    if user is None:
        await message.answer("❌ Пользователь не найден.", reply_markup=kb_admin_back())
        await state.clear()
        return

    await state.update_data(cal_target_id=user_id)
    await message.answer(
        f"Юзер: <b>{user.name}</b> (<code>{user_id}</code>)\n"
        f"Текущий рейтинг: {format_rating_line(user.avg_rating, user.rating_count)}\n\n"
        "Введи новое значение <b>rating_count</b> (число голосов).\n"
        "<i>Введи 0 — чтобы полностью сбросить в калибровку.</i>",
        parse_mode="HTML",
        reply_markup=kb_admin_back(),
    )
    await state.set_state(AdminCalibration.waiting_votes)


@router.message(AdminCalibration.waiting_votes)
async def adm_cal_apply(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("⚠️ Введи неотрицательное целое число.")
        return

    data      = await state.get_data()
    target_id = data["cal_target_id"]
    new_count = int(raw)

    await session.execute(
        update(User)
        .where(User.id == target_id)
        .values(rating_count=new_count)
    )
    await session.commit()
    await state.clear()

    _log.user(
        "admin calibration: admin=%s target=%s new_count=%d",
        message.from_user.id, target_id, new_count,
    )
    await message.answer(
        f"✅ Готово. <code>rating_count</code> для юзера <code>{target_id}</code> "
        f"установлен в <code>{new_count}</code>.",
        parse_mode="HTML",
        reply_markup=kb_admin_back(),
    )


# Сброс калибровки прямо с карточки юзера
@router.callback_query(F.data.startswith("adm:do_reset_cal:"))
async def adm_reset_cal_inline(call: CallbackQuery, session: AsyncSession):
    target_id = int(call.data.split(":")[2])
    await session.execute(
        update(User)
        .where(User.id == target_id)
        .values(rating_count=0, avg_rating=0.0)
    )
    await session.commit()
    await call.answer("🧬 Калибровка сброшена.", show_alert=True)
    _log.user("admin reset_cal inline: admin=%s target=%s", call.from_user.id, target_id)


# ════════════════════════════════════════════════════════════════
# 👑 Управление администраторами
# ════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:admins")
async def adm_admins_list(call: CallbackQuery, session: AsyncSession):
    await call.answer()
    repo   = AdminRepository(session)
    admins = await repo.list_all()

    lines = ["<b>👑 Администраторы</b>\n"]
    for a in admins:
        label = f"@{a.username}" if a.username else str(a.telegram_id)
        lines.append(f"├ <code>{a.telegram_id}</code> · {label}")

    text = "\n".join(lines) if admins else "Список пуст."
    try:
        await call.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=kb_admins_list(admins),
        )
    except Exception:
        await call.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=kb_admins_list(admins),
        )


# Добавить нового администратора
@router.callback_query(F.data == "adm:add_admin")
async def adm_add_admin_prompt(call: CallbackQuery, state: FSMContext):
    await call.answer()
    # Переиспользуем AdminLookup.waiting_id для ввода ID
    await call.message.answer(
        "➕ Введи <b>Telegram ID</b> нового администратора:",
        parse_mode="HTML",
        reply_markup=kb_admin_back(),
    )
    await state.set_state(AdminLookup.waiting_id)
    await state.update_data(add_admin_mode=True)


@router.message(AdminLookup.waiting_id)
async def adm_lookup_or_add(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("⚠️ Нужен числовой ID.")
        return

    data       = await state.get_data()
    add_mode   = data.get("add_admin_mode", False)
    target_id  = int(raw)
    await state.clear()

    if add_mode:
        # Добавляем администратора
        repo = AdminRepository(session)
        if await repo.is_admin(target_id):
            await message.answer("ℹ️ Уже администратор.", reply_markup=kb_admin_back())
            return
        # Пробуем взять username из таблицы users
        user_repo = UserRepository(session)
        user      = await user_repo.get(target_id)
        username  = user.username if user else None

        await repo.add(
            telegram_id=target_id,
            username=username,
            added_by=None,   # упрощённо; можно передать id текущего админа
        )
        await session.commit()
        _log.user("admin add_admin: admin=%s new=%s", message.from_user.id, target_id)
        await message.answer(
            f"✅ <code>{target_id}</code> добавлен как администратор.",
            parse_mode="HTML",
            reply_markup=kb_admin_back(),
        )
    else:
        # Обычный lookup
        user_repo = UserRepository(session)
        user      = await user_repo.get(target_id)
        if user is None:
            await message.answer("❌ Пользователь не найден.", reply_markup=kb_admin_back())
            return

        text = await _user_card(user, session)
        kb   = kb_admin_user_actions(user.id, user.is_banned)
        if user.photos:
            await message.answer_photo(
                photo=user.photos[0].file_id,
                caption=text, reply_markup=kb, parse_mode="HTML",
            )
        else:
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
        _log.user("admin lookup: admin=%s target=%s", message.from_user.id, target_id)


# Удалить администратора
@router.callback_query(F.data.startswith("adm:rm_admin:"))
async def adm_remove_admin(call: CallbackQuery, session: AsyncSession):
    target_id = int(call.data.split(":")[2])

    if target_id == call.from_user.id:
        await call.answer("⚠️ Нельзя удалить самого себя.", show_alert=True)
        return

    repo = AdminRepository(session)
    await repo.remove(target_id)
    await session.commit()
    await call.answer(f"Администратор {target_id} удалён.", show_alert=True)
    _log.user("admin rm_admin: admin=%s removed=%s", call.from_user.id, target_id)

    # Обновляем список
    admins = await repo.list_all()
    lines  = ["<b>👑 Администраторы</b>\n"]
    for a in admins:
        label = f"@{a.username}" if a.username else str(a.telegram_id)
        lines.append(f"├ <code>{a.telegram_id}</code> · {label}")
    text = "\n".join(lines) if admins else "Список пуст."
    try:
        await call.message.edit_text(
            text, parse_mode="HTML", reply_markup=kb_admins_list(admins)
        )
    except Exception:
        await call.message.answer(
            text, parse_mode="HTML", reply_markup=kb_admins_list(admins)
        )
