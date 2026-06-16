"""bot/handlers/user/browse.py — лента, лайки, мэтчи."""
from datetime import datetime, timezone, timedelta

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import logger as log
from bot.constants import (
    SWIPE_LIMIT, SWIPE_WINDOW_HOURS, PREMIUM_SWIPE_LIMIT,
    LIKE_MSG_LIMIT_PER_HOUR, LIKE_MSG_MAX_LEN, MENU_BUTTON_TEXTS,
)
from bot.keyboards import kb_main_menu, kb_match, kb_swipe
from bot.services import BrowseService
from bot.utils.formatting import fmt_delta, fmt_ago, profile_caption
from bot.states import LikeMsgState
from config import settings
from db.repositories.admin_repo import AdminRepository
from db.repositories.user_repo import UserRepository
from db.repositories.like_repo import LikeRepository, MatchRepository, LikeMessageRepository
from db.repositories.view_repo import ProfileViewRepository

_log = log.get(__name__)
router = Router(name="browse")


# ── Лимит свайпов ─────────────────────────────────────────────────

async def _swipe_limit_exceeded(user_id: int, session) -> tuple[bool, str]:
    """Возвращает (exceeded, alert_text). Админы пропускаются всегда; у SHROOM+ — повышенный лимит."""
    if await AdminRepository(session).is_admin(user_id):
        return False, ""

    user = await UserRepository(session).get_light(user_id)
    base = PREMIUM_SWIPE_LIMIT if (user and user.is_premium) else SWIPE_LIMIT

    repo  = LikeRepository(session)
    count = await repo.count_recent_swipes(user_id, SWIPE_WINDOW_HOURS)

    # лимит = базовый (или премиум) + бонусные свайпы за рефералов
    limit = base + (user.bonus_swipes if user else 0)
    if count < limit:
        return False, ""

    oldest = await repo.get_oldest_swipe_in_window(user_id, SWIPE_WINDOW_HOURS)
    timer  = ""
    if oldest:
        next_slot = oldest + timedelta(hours=SWIPE_WINDOW_HOURS)
        delta = next_slot - datetime.now(tz=timezone.utc)
        if delta.total_seconds() > 0:
            timer = f"\nследующий слот через {fmt_delta(delta)}."

    text = (
        f"⏳  лимит.\n"
        f"{count}/{limit} свайпов за {SWIPE_WINDOW_HOURS}ч.{timer}"
    )
    if not (user and user.is_premium):
        text += "\nбольше свайпов — в SHROOM+ (/premium) или пригласи друзей."
    return True, text


# ── Отправка карточки ─────────────────────────────────────────────

async def _send_card(user_id, bot, candidate, session, viewer=None):
    caption = await profile_caption(candidate, session, viewer)
    kb = kb_swipe(candidate.id)
    if candidate.photos:
        await bot.send_photo(
            user_id, photo=candidate.photos[0].file_id,
            caption=caption, reply_markup=kb, parse_mode="HTML",
        )
    else:
        await bot.send_message(
            user_id, caption + "\n\n<i>нет фото</i>",
            parse_mode="HTML", reply_markup=kb,
        )
    # фиксируем просмотр: user_id посмотрел анкету candidate
    try:
        await ProfileViewRepository(session).add(user_id, candidate.id)
        await session.commit()
    except Exception:
        pass


async def _edit_to_card(user_id, bot, session, message_id, candidate, viewer) -> bool:
    """Редактирует существующее сообщение-карточку под новую анкету (без скачка).
    Возвращает False, если редактировать нельзя (нет фото / тип сообщения)."""
    if not candidate.photos:
        return False
    caption = await profile_caption(candidate, session, viewer)
    try:
        await bot.edit_message_media(
            chat_id=user_id, message_id=message_id,
            media=InputMediaPhoto(
                media=candidate.photos[0].file_id, caption=caption, parse_mode="HTML",
            ),
            reply_markup=kb_swipe(candidate.id),
        )
    except Exception:
        return False
    try:
        await ProfileViewRepository(session).add(user_id, candidate.id)
        await session.commit()
    except Exception:
        pass
    return True


async def _advance_card(user_id, bot, session, message_id, viewer=None):
    """Следующая анкета РЕДАКТИРОВАНИЕМ текущего сообщения (убирает «скачки»).
    Фолбэк на delete+send для несовместимых сообщений."""
    repo = UserRepository(session)
    if viewer is None:
        viewer = await repo.get(user_id)
    candidate = (
        await repo.get_next_candidate(viewer, nearby_radius_km=settings.nearby_radius_km)
        if viewer else None
    )
    if candidate is None:
        ended = "🍄  на сегодня анкеты закончились.\n<i>загляни позже.</i>"
        try:
            await bot.edit_message_caption(
                chat_id=user_id, message_id=message_id,
                caption=ended, parse_mode="HTML", reply_markup=None,
            )
        except Exception:
            try:
                await bot.edit_message_text(
                    chat_id=user_id, message_id=message_id,
                    text=ended, parse_mode="HTML",
                )
            except Exception:
                pass
        return

    if await _edit_to_card(user_id, bot, session, message_id, candidate, viewer):
        return
    # фолбэк: старое поведение
    try:
        await bot.delete_message(user_id, message_id)
    except Exception:
        pass
    await _send_card(user_id, bot, candidate, session, viewer=viewer)


async def show_next(user_id, bot, session, delete_msg_id=None, viewer=None):
    if delete_msg_id:
        try:
            await bot.delete_message(user_id, delete_msg_id)
        except Exception:
            pass
    repo = UserRepository(session)
    if viewer is None:
        viewer = await repo.get(user_id)
    if viewer is None:
        await bot.send_message(user_id, "анкеты нет.\n\n/start")
        return
    candidate = await repo.get_next_candidate(viewer, nearby_radius_km=settings.nearby_radius_km)
    if candidate is None:
        await bot.send_message(
            user_id, "пусто.\n\n<i>загляни позже.</i>",
            parse_mode="HTML", reply_markup=kb_main_menu(),
        )
        return
    await _send_card(user_id, bot, candidate, session, viewer=viewer)


# ── Лента ─────────────────────────────────────────────────────────

@router.message(F.text.in_({"🕯️ лента", "🕯️ Лента"}))
async def handle_browse_msg(message: Message, bot: Bot, session, state: FSMContext, db_user=None):
    await state.clear()
    await show_next(message.from_user.id, bot, session, viewer=db_user)


# ── Лайк ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("like:"))
async def handle_like(call: CallbackQuery, bot: Bot, session, state: FSMContext, db_user=None):
    exceeded, limit_text = await _swipe_limit_exceeded(call.from_user.id, session)
    if exceeded:
        await call.answer(limit_text, show_alert=True)
        return

    candidate_id = int(call.data.split(":")[1])
    svc    = BrowseService(session)
    result = await svc.react(call.from_user.id, candidate_id, liked=True)
    # запоминаем для «↩️ вернуть» — только в рамках текущего захода в ленту
    await state.update_data(rewind_target=candidate_id)
    await call.answer("🩸")
    _log.user("like: user=%s → %s", call.from_user.id, candidate_id)

    if result.is_new_match and result.partner:
        await _send_match_notification(call.from_user.id, result.partner, bot, session)
        viewer = await svc.users.get(call.from_user.id)  # полный (с фото!)
        if viewer:
            await _send_match_notification(result.partner.id, viewer, bot, session)
    elif result.notify_like:
        await _notify_liked(candidate_id, bot, session)

    await _advance_card(call.from_user.id, bot, session, call.message.message_id, viewer=db_user)


# ── Дизлайк ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("dislike:"))
async def handle_dislike(call: CallbackQuery, bot: Bot, session, state: FSMContext, db_user=None):
    exceeded, limit_text = await _swipe_limit_exceeded(call.from_user.id, session)
    if exceeded:
        await call.answer(limit_text, show_alert=True)
        return

    candidate_id = int(call.data.split(":")[1])
    svc = BrowseService(session)
    await svc.react(call.from_user.id, candidate_id, liked=False)
    await state.update_data(rewind_target=candidate_id)  # для «↩️ вернуть» (в рамках захода)
    await call.answer("🤮")
    await _advance_card(call.from_user.id, bot, session, call.message.message_id, viewer=db_user)


# ── Лайки (входящие) ──────────────────────────────────────────────

@router.message(F.text.in_({"🩸 лайки", "🩸 Лайки"}))
async def show_likes_msg(message: Message, bot: Bot, session, state: FSMContext):
    await state.clear()
    await _show_likes_page(message.from_user.id, bot, session, page=0)


@router.callback_query(F.data.startswith("likes_page:"))
async def likes_page(call: CallbackQuery, bot: Bot, session):
    await call.answer()
    await _show_likes_page(
        call.from_user.id, bot, session,
        page=int(call.data.split(":")[1]),
        delete_msg_id=call.message.message_id,
    )


async def _show_likes_page(user_id, bot, session, page, delete_msg_id=None):
    if delete_msg_id:
        try:
            await bot.delete_message(user_id, delete_msg_id)
        except Exception:
            pass

    like_repo = LikeRepository(session)
    total = await like_repo.count_unanswered_likers(user_id)
    if total == 0:
        await bot.send_message(user_id, "лайков нет.")
        return

    page     = max(0, min(page, total - 1))
    liker_id = await like_repo.get_unanswered_liker_at(user_id, page)
    if liker_id is None:
        await bot.send_message(user_id, "анкета удалена.")
        return

    repo  = UserRepository(session)
    liker = await repo.get(liker_id)
    if not liker:
        await bot.send_message(user_id, "анкета удалена.")
        return

    viewer  = await repo.get(user_id)
    note    = await LikeMessageRepository(session).latest_from(liker_id, user_id)

    caption = f"🩸  {page + 1} / {total}\n\n"
    if note:
        caption += f"💬  «{note}»\n\n"
    caption += await profile_caption(liker, session, viewer)

    b = InlineKeyboardBuilder()
    if page > 0:
        b.button(text="←", callback_data=f"likes_page:{page - 1}")
    b.button(text=f"{page + 1}/{total}", callback_data="noop")
    if page < total - 1:
        b.button(text="→", callback_data=f"likes_page:{page + 1}")
    b.button(text="🩸", callback_data=f"likes_react:like:{liker.id}:{page}")
    b.button(text="🤮", callback_data=f"likes_react:dislike:{liker.id}:{page}")
    b.button(text="🚩", callback_data=f"report:start:{liker.id}")
    b.adjust(3, 2, 1)

    if liker.photos:
        await bot.send_photo(
            user_id, photo=liker.photos[0].file_id,
            caption=caption, reply_markup=b.as_markup(), parse_mode="HTML",
        )
    else:
        await bot.send_message(user_id, caption, reply_markup=b.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("likes_react:"))
async def likes_react(call: CallbackQuery, bot: Bot, session):
    exceeded, limit_text = await _swipe_limit_exceeded(call.from_user.id, session)
    if exceeded:
        await call.answer(limit_text, show_alert=True)
        return

    _, action, liker_id_str, page_str = call.data.split(":")
    liker_id = int(liker_id_str)
    page     = int(page_str)
    liked    = action == "like"

    svc    = BrowseService(session)
    result = await svc.react(call.from_user.id, liker_id, liked=liked)
    await call.answer("🩸" if liked else "🤮")

    if result.is_new_match and result.partner:
        await _send_match_notification(call.from_user.id, result.partner, bot, session)
        viewer = await svc.users.get(call.from_user.id)
        if viewer:
            await _send_match_notification(result.partner.id, viewer, bot, session)

    like_repo = LikeRepository(session)
    total     = await like_repo.count_unanswered_likers(call.from_user.id)
    if total == 0:
        try:
            await bot.delete_message(call.from_user.id, call.message.message_id)
        except Exception:
            pass
        await bot.send_message(call.from_user.id, "всё.")
        return

    await _show_likes_page(
        call.from_user.id, bot, session,
        page=min(page, total - 1),
        delete_msg_id=call.message.message_id,
    )


# ── Мэтчи ─────────────────────────────────────────────────────────

@router.message(F.text.in_({"💬 мэтчи", "💬 Мэтчи"}))
async def show_matches_msg(message: Message, bot: Bot, session, state: FSMContext):
    await state.clear()
    await _show_matches_page(message.from_user.id, bot, session, page=0)


@router.callback_query(F.data.startswith("matches_page:"))
async def matches_page(call: CallbackQuery, bot: Bot, session):
    await call.answer()
    await _show_matches_page(
        call.from_user.id, bot, session,
        page=int(call.data.split(":")[1]),
        delete_msg_id=call.message.message_id,
    )


async def _show_matches_page(user_id, bot, session, page, delete_msg_id=None):
    if delete_msg_id:
        try:
            await bot.delete_message(user_id, delete_msg_id)
        except Exception:
            pass

    svc     = BrowseService(session)
    matches = await svc.get_matches(user_id)
    if not matches:
        await bot.send_message(user_id, "мэтчей нет.")
        return

    page    = max(0, min(page, len(matches) - 1))
    partner = matches[page]
    viewer  = await UserRepository(session).get(user_id)
    caption = f"⚔️  {page + 1} / {len(matches)}\n\n" + await profile_caption(partner, session, viewer)

    b = InlineKeyboardBuilder()
    if page > 0:
        b.button(text="←", callback_data=f"matches_page:{page - 1}")
    b.button(text=f"{page + 1}/{len(matches)}", callback_data="noop")
    if page < len(matches) - 1:
        b.button(text="→", callback_data=f"matches_page:{page + 1}")
    if partner.username:
        b.button(text="💬 написать", url=f"https://t.me/{partner.username}")
    else:
        b.button(text="💬 написать", callback_data=f"try_write:{partner.id}")
    b.button(text="🚩", callback_data=f"report:start:{partner.id}")
    b.adjust(3, 1, 1)

    if partner.photos:
        await bot.send_photo(
            user_id, photo=partner.photos[0].file_id,
            caption=caption, reply_markup=b.as_markup(), parse_mode="HTML",
        )
    else:
        await bot.send_message(user_id, caption, reply_markup=b.as_markup(), parse_mode="HTML")


# ── Уведомления ───────────────────────────────────────────────────

async def _send_match_notification(user_id, partner, bot, session):
    """
    БАГФИКС: раньше при отправке партнёру (write_to=...) его username
    принудительно обнулялся — кнопка «написать» всегда вела в тупик
    «закрытый профиль». Теперь username партнёра используется всегда.
    """
    if user_id < 0:          # тестовый фейк — у него нет чата, не шлём
        return
    caption = "⚔️  мэтч.\n\n" + await profile_caption(partner, session)
    kb      = kb_match(partner.id, username=partner.username)
    try:
        if partner.photos:
            await bot.send_photo(
                user_id, photo=partner.photos[0].file_id,
                caption=caption, reply_markup=kb, parse_mode="HTML",
            )
        else:
            await bot.send_message(user_id, caption, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        _log.warning("match notify failed user_id=%s: %s", user_id, e)


async def _notify_liked(user_id: int, bot: Bot, session=None) -> None:
    if user_id < 0:          # тестовый фейк — пропускаем
        return
    if session is not None:
        u = await UserRepository(session).get_light(user_id)
        if u and not u.notifications_enabled:
            return
    try:
        await bot.send_message(
            user_id, "🩸  тебя лайкнули.\n<i>загляни в лайки.</i>",
            parse_mode="HTML",
        )
    except Exception as e:
        _log.warning("like notify failed user_id=%s: %s", user_id, e)


# ── Возврат к прошлой анкете (SHROOM+) — кнопка ↩️ ────────────────

@router.callback_query(F.data == "rewind")
async def rewind(call: CallbackQuery, bot: Bot, session, state: FSMContext, db_user=None):
    repo = UserRepository(session)
    me   = await repo.get_light(call.from_user.id)
    if not (me and me.is_premium):
        await call.answer(
            "↩️ возврат к анкете — фича 🔱 SHROOM+ (/premium).", show_alert=True
        )
        return

    # только последний свайп из ЛЕНТЫ и только в текущем заходе (сессионный FSM)
    data      = await state.get_data()
    target_id = data.get("rewind_target")
    if target_id is None:
        await call.answer("нечего возвращать — это первая анкета в заходе.", show_alert=True)
        return

    likes   = LikeRepository(session)
    matches = MatchRepository(session)

    last = await likes.get_last_swipe_to(call.from_user.id, target_id)
    if await matches.exists(call.from_user.id, target_id):
        await matches.delete_pair(call.from_user.id, target_id)
    if last is not None:
        await likes.delete_swipe(last.id)
        await likes.recalc_rating(target_id)

    await state.update_data(rewind_target=None)  # вернуть можно только один раз
    await session.commit()
    _log.user("rewind: user=%s restored=%s", call.from_user.id, target_id)
    await call.answer("↩️ вернул")

    restored = await repo.get(target_id)
    viewer   = db_user or await repo.get(call.from_user.id)
    if restored and restored.is_active and not restored.is_banned:
        if not await _edit_to_card(call.from_user.id, bot, session, call.message.message_id, restored, viewer):
            try:
                await bot.delete_message(call.from_user.id, call.message.message_id)
            except Exception:
                pass
            await _send_card(call.from_user.id, bot, restored, session, viewer=viewer)
    else:
        await call.answer("эта анкета больше недоступна.", show_alert=True)
        await _advance_card(call.from_user.id, bot, session, call.message.message_id, viewer=viewer)


# ── Лайк с сообщением ─────────────────────────────────────────────

async def _likemsg_limit(user_id: int, session) -> tuple[bool, str]:
    """(exceeded, alert). Считает отправленные записки за час."""
    repo  = LikeMessageRepository(session)
    count = await repo.count_recent(user_id, hours=1)
    if count < LIKE_MSG_LIMIT_PER_HOUR:
        return False, ""
    oldest = await repo.oldest_in_window(user_id, hours=1)
    timer  = ""
    if oldest:
        delta = (oldest + timedelta(hours=1)) - datetime.now(tz=timezone.utc)
        if delta.total_seconds() > 0:
            timer = f"\nслот через {fmt_delta(delta)}."
    return True, f"⏳ лимит записок: {LIKE_MSG_LIMIT_PER_HOUR}/час.{timer}"


@router.callback_query(F.data.startswith("likemsg:"))
async def likemsg_start(call: CallbackQuery, state: FSMContext, session):
    target_id = int(call.data.split(":")[1])
    if target_id == call.from_user.id:
        await call.answer("это твоя анкета.", show_alert=True)
        return

    exceeded, alert = await _likemsg_limit(call.from_user.id, session)
    if exceeded:
        await call.answer(alert, show_alert=True)
        return

    await call.answer()
    await state.set_state(LikeMsgState.waiting_text)
    await state.update_data(lm_target=target_id, lm_card=call.message.message_id)
    b = InlineKeyboardBuilder()
    b.button(text="✖️ отмена", callback_data="likemsg_cancel")
    await call.message.answer(
        f"💬  напиши записку к лайку  <i>(до {LIKE_MSG_MAX_LEN} симв.)</i>",
        parse_mode="HTML", reply_markup=b.as_markup(),
    )


@router.callback_query(F.data == "likemsg_cancel")
async def likemsg_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer("отменено")
    try:
        await call.message.delete()
    except Exception:
        pass


@router.message(LikeMsgState.waiting_text, F.text)
async def likemsg_send(message: Message, state: FSMContext, bot: Bot, session, db_user=None):
    text = (message.text or "").strip()

    # выход из сценария, если нажали меню/команду
    if text.startswith("/") or text in MENU_BUTTON_TEXTS:
        await state.clear()
        await message.answer("💬 отменено. нажми «💬 лайк+» ещё раз, если что.")
        return

    data      = await state.get_data()
    target_id = data.get("lm_target")
    card_id   = data.get("lm_card")
    await state.clear()

    if not target_id:
        return
    if not text:
        await message.answer("↑ записка пустая.")
        return
    if len(text) > LIKE_MSG_MAX_LEN:
        await message.answer(f"↑ слишком длинно ({len(text)}/{LIKE_MSG_MAX_LEN}).")
        return

    exceeded, alert = await _likemsg_limit(message.from_user.id, session)
    if exceeded:
        await message.answer(alert)
        return

    svc    = BrowseService(session)
    result = await svc.react(message.from_user.id, target_id, liked=True)
    await LikeMessageRepository(session).add(message.from_user.id, target_id, text)
    await session.commit()
    _log.user("likemsg: from=%s to=%s len=%d", message.from_user.id, target_id, len(text))

    if result.is_new_match and result.partner:
        # сразу мэтч — оповещаем обоих и доносим записку партнёру
        await _send_match_notification(message.from_user.id, result.partner, bot, session)
        viewer = await svc.users.get(message.from_user.id)  # полный (с фото!)
        if viewer:
            await _send_match_notification(result.partner.id, viewer, bot, session)
            try:
                await bot.send_message(
                    result.partner.id,
                    f"💬  и записка от <b>{viewer.name}</b>:\n\n«{text}»",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    else:
        viewer = await svc.users.get(message.from_user.id)  # полный (с фото!)
        await _deliver_like_message(target_id, viewer, text, bot, session)

    await message.answer("💬  отправлено.", reply_markup=kb_main_menu())

    if card_id:
        try:
            await bot.delete_message(message.from_user.id, card_id)
        except Exception:
            pass
    await show_next(message.from_user.id, bot, session, viewer=db_user)


@router.message(LikeMsgState.waiting_text)
async def likemsg_invalid(message: Message):
    await message.answer("↑ пришли текст записки или нажми «✖️ отмена».")


async def _deliver_like_message(target_id, liker, text, bot, session):
    """Доставляет получателю лайк с запиской + кнопки ответа."""
    if liker is None or target_id < 0:   # фейку не доставляем
        return
    caption = (
        f"💬  <b>{liker.name}</b> лайкнул(а) тебя с запиской:\n\n"
        f"«{text}»\n\n"
        + await profile_caption(liker, session)
    )
    b = InlineKeyboardBuilder()
    b.button(text="🩸 в ответ", callback_data=f"likeback:{liker.id}")
    b.button(text="✖️ пропустить", callback_data=f"likemsg_pass:{liker.id}")
    b.adjust(2)
    try:
        if liker.photos:
            await bot.send_photo(target_id, photo=liker.photos[0].file_id,
                                 caption=caption, reply_markup=b.as_markup(), parse_mode="HTML")
        else:
            await bot.send_message(target_id, caption, reply_markup=b.as_markup(), parse_mode="HTML")
    except Exception as e:
        _log.warning("deliver likemsg failed to=%s: %s", target_id, e)


@router.callback_query(F.data.startswith("likeback:"))
async def like_back(call: CallbackQuery, bot: Bot, session, db_user=None):
    liker_id = int(call.data.split(":")[1])
    svc    = BrowseService(session)
    result = await svc.react(call.from_user.id, liker_id, liked=True)
    await call.answer("🩸")
    if result.is_new_match and result.partner:
        await _send_match_notification(call.from_user.id, result.partner, bot, session)
        me = await svc.users.get(call.from_user.id)  # полный (с фото!)
        if me:
            await _send_match_notification(result.partner.id, me, bot, session)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


@router.callback_query(F.data.startswith("likemsg_pass:"))
async def likemsg_pass(call: CallbackQuery, session):
    liker_id = int(call.data.split(":")[1])
    await BrowseService(session).react(call.from_user.id, liker_id, liked=False)
    await call.answer("пропущено")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


# ── Кто смотрел анкету ────────────────────────────────────────────

@router.message(Command("views"))
async def cmd_views(message: Message, bot: Bot, session, state: FSMContext):
    await state.clear()
    await _show_views_page(message.from_user.id, bot, session, page=0)


@router.callback_query(F.data == "views")
async def views_open(call: CallbackQuery, bot: Bot, session):
    await call.answer()
    await _show_views_page(call.from_user.id, bot, session, page=0)


@router.callback_query(F.data.startswith("views_page:"))
async def views_page(call: CallbackQuery, bot: Bot, session):
    await call.answer()
    await _show_views_page(
        call.from_user.id, bot, session,
        page=int(call.data.split(":")[1]),
        delete_msg_id=call.message.message_id,
    )


async def _show_views_page(user_id, bot, session, page, delete_msg_id=None):
    if delete_msg_id:
        try:
            await bot.delete_message(user_id, delete_msg_id)
        except Exception:
            pass

    vrepo = ProfileViewRepository(session)
    total = await vrepo.count_viewers(user_id)
    if total == 0:
        await bot.send_message(user_id, "👀 твою анкету ещё никто не смотрел.")
        return

    urepo = UserRepository(session)
    me    = await urepo.get_light(user_id)

    # Кто именно — только для SHROOM+
    if not (me and me.is_premium):
        await bot.send_message(
            user_id,
            f"👀  твою анкету смотрели:  <b>{total}</b>\n\n"
            "узнать <b>кто</b> — в SHROOM+  (/premium).",
            parse_mode="HTML",
        )
        return

    page = max(0, min(page, total - 1))
    row  = await vrepo.get_page(user_id, page)
    if row is None:
        await bot.send_message(user_id, "анкета удалена.")
        return
    viewer_id, viewed_at = row

    viewer = await urepo.get(viewer_id)
    if not viewer:
        await bot.send_message(user_id, "анкета удалена.")
        return

    me_full = await urepo.get(user_id)
    when    = fmt_ago(viewed_at)
    caption = f"👀  {page + 1} / {total}  ·  {when}\n\n" + await profile_caption(viewer, session, me_full)

    b = InlineKeyboardBuilder()
    if page > 0:
        b.button(text="←", callback_data=f"views_page:{page - 1}")
    b.button(text=f"{page + 1}/{total}", callback_data="noop")
    if page < total - 1:
        b.button(text="→", callback_data=f"views_page:{page + 1}")
    b.button(text="🩸", callback_data=f"likeback:{viewer.id}")
    b.button(text="🤮", callback_data=f"likemsg_pass:{viewer.id}")
    b.button(text="🚩", callback_data=f"report:start:{viewer.id}")
    b.adjust(3, 2, 1)

    if viewer.photos:
        await bot.send_photo(user_id, photo=viewer.photos[0].file_id,
                             caption=caption, reply_markup=b.as_markup(), parse_mode="HTML")
    else:
        await bot.send_message(user_id, caption, reply_markup=b.as_markup(), parse_mode="HTML")


# ── Служебные callback ────────────────────────────────────────────


@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data.startswith("try_write:"))
async def try_write(call: CallbackQuery):
    await call.answer("закрытый профиль.", show_alert=True)
