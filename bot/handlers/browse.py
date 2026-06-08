"""
bot/handlers/browse.py — лента / лайк / дизлайк / лайки / мэтчи.
"""
import math

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import kb_main_menu, kb_match, kb_swipe
from bot.rating import format_rating_line
from bot.services import BrowseService
from bot import logger as log
from config import settings
from db.models import User
from db.repositories.user_repo import UserRepository
from db.repositories.like_repo import LikeRepository

_log   = log.get(__name__)
router = Router()


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _profile_caption(candidate: User, viewer: User | None = None) -> str:
    header = f"<b>{candidate.name}</b>, {candidate.age}"

    if (
        viewer
        and viewer.latitude   is not None and viewer.longitude   is not None
        and candidate.latitude is not None and candidate.longitude is not None
    ):
        dist = round(_haversine_km(
            viewer.latitude, viewer.longitude,
            candidate.latitude, candidate.longitude,
        ), 1)
        header += f"  ·  📡 {dist} км"

    lines = [header, format_rating_line(candidate.avg_rating, candidate.rating_count)]
    if candidate.bio:
        lines.append(f"\n<i>{candidate.bio}</i>")
    return "\n".join(lines)


async def _send_card(user_id: int, bot: Bot, candidate: User, viewer: User | None = None) -> None:
    caption = _profile_caption(candidate, viewer)
    kb      = kb_swipe(candidate.id)
    if candidate.photos:
        await bot.send_photo(user_id, photo=candidate.photos[0].file_id,
                             caption=caption, reply_markup=kb, parse_mode="HTML")
    else:
        await bot.send_message(user_id, caption + "\n\n<i>нет фото</i>",
                               parse_mode="HTML", reply_markup=kb)


async def show_next(
    user_id: int,
    bot: Bot,
    session: AsyncSession,
    delete_msg_id: int | None = None,
    viewer: User | None = None,
) -> None:
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

    candidate = await repo.get_next_candidate(
        viewer, nearby_radius_km=settings.nearby_radius_km
    )
    if candidate is None:
        await bot.send_message(
            user_id,
            "пусто.\n\n<i>загляни позже.</i>",
            parse_mode="HTML",
            reply_markup=kb_main_menu(),
        )
        return

    await _send_card(user_id, bot, candidate, viewer=viewer)


# ── лента ────────────────────────────────────────────────────────

@router.message(F.text.in_({"🕯️ лента", "🕯️ Лента"}))
async def handle_browse_msg(message: Message, bot: Bot, session: AsyncSession,
                            db_user: User | None = None):
    await show_next(message.from_user.id, bot, session, viewer=db_user)


# ── лайк / дизлайк ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("like:"))
async def handle_like(call: CallbackQuery, bot: Bot, session: AsyncSession,
                      db_user: User | None = None):
    candidate_id = int(call.data.split(":")[1])
    svc          = BrowseService(session)
    result       = await svc.react(call.from_user.id, candidate_id, liked=True)
    await call.answer("🩸")
    _log.user("like: user=%s → %s", call.from_user.id, candidate_id)

    if result.is_new_match and result.partner:
        _log.user("match: user=%s ↔ %s", call.from_user.id, candidate_id)
        await _send_match_notification(call.from_user.id, result.partner, bot)
        viewer = db_user or await svc.users.get(call.from_user.id)
        if viewer:
            await _send_match_notification(result.partner.id, viewer, bot,
                                           write_to=call.from_user.id)
    elif result.notify_like:
        await _notify_liked(candidate_id, bot)

    await show_next(call.from_user.id, bot, session,
                    delete_msg_id=call.message.message_id, viewer=db_user)


@router.callback_query(F.data.startswith("dislike:"))
async def handle_dislike(call: CallbackQuery, bot: Bot, session: AsyncSession,
                         db_user: User | None = None):
    candidate_id = int(call.data.split(":")[1])
    svc = BrowseService(session)
    await svc.react(call.from_user.id, candidate_id, liked=False)
    await call.answer("🤮")
    _log.user("dislike: user=%s → %s", call.from_user.id, candidate_id)
    await show_next(call.from_user.id, bot, session,
                    delete_msg_id=call.message.message_id, viewer=db_user)


# ── лайки ────────────────────────────────────────────────────────

@router.message(F.text.in_({"🩸 лайки", "🩸 Лайки"}))
async def show_likes_msg(message: Message, bot: Bot, session: AsyncSession):
    await _show_likes_page(message.from_user.id, bot, session, page=0)


@router.callback_query(F.data.startswith("likes_page:"))
async def likes_page(call: CallbackQuery, bot: Bot, session: AsyncSession):
    page = int(call.data.split(":")[1])
    await call.answer()
    await _show_likes_page(call.from_user.id, bot, session, page=page,
                           delete_msg_id=call.message.message_id)


async def _show_likes_page(
    user_id: int,
    bot: Bot,
    session: AsyncSession,
    page: int,
    delete_msg_id: int | None = None,
) -> None:
    if delete_msg_id:
        try:
            await bot.delete_message(user_id, delete_msg_id)
        except Exception:
            pass

    like_repo = LikeRepository(session)
    total     = await like_repo.count_unanswered_likers(user_id)
    if total == 0:
        await bot.send_message(user_id, "лайков нет.")
        return

    page     = max(0, min(page, total - 1))
    liker_id = await like_repo.get_unanswered_liker_at(user_id, page)
    if liker_id is None:
        await bot.send_message(user_id, "анкета удалена.")
        return

    liker = await UserRepository(session).get(liker_id)
    if not liker:
        await bot.send_message(user_id, "анкета удалена.")
        return

    caption = f"🩸  {page + 1} / {total}\n\n" + _profile_caption(liker)

    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(text="←", callback_data=f"likes_page:{page - 1}")
    builder.button(text=f"{page + 1}/{total}", callback_data="noop")
    if page < total - 1:
        builder.button(text="→", callback_data=f"likes_page:{page + 1}")
    builder.button(text="🤮", callback_data=f"likes_react:dislike:{liker.id}:{page}")
    builder.button(text="🩸", callback_data=f"likes_react:like:{liker.id}:{page}")
    builder.adjust(3, 2)

    if liker.photos:
        await bot.send_photo(user_id, photo=liker.photos[0].file_id,
                             caption=caption, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await bot.send_message(user_id, caption, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("likes_react:"))
async def likes_react(call: CallbackQuery, bot: Bot, session: AsyncSession):
    _, action, liker_id_str, page_str = call.data.split(":")
    liker_id = int(liker_id_str)
    page     = int(page_str)
    liked    = action == "like"

    svc    = BrowseService(session)
    result = await svc.react(call.from_user.id, liker_id, liked=liked)
    await call.answer("🩸" if liked else "🤮")

    if result.is_new_match and result.partner:
        _log.user("match: user=%s ↔ %s (from likes)", call.from_user.id, liker_id)
        await _send_match_notification(call.from_user.id, result.partner, bot)
        viewer = await svc.users.get(call.from_user.id)
        if viewer:
            await _send_match_notification(result.partner.id, viewer, bot,
                                           write_to=call.from_user.id)

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


# ── мэтчи ────────────────────────────────────────────────────────

@router.message(F.text.in_({"💬 мэтчи", "💬 Мэтчи"}))
async def show_matches_msg(message: Message, bot: Bot, session: AsyncSession):
    await _show_matches_page(message.from_user.id, bot, session, page=0)


@router.callback_query(F.data.startswith("matches_page:"))
async def matches_page(call: CallbackQuery, bot: Bot, session: AsyncSession):
    page = int(call.data.split(":")[1])
    await call.answer()
    await _show_matches_page(call.from_user.id, bot, session, page=page,
                             delete_msg_id=call.message.message_id)


async def _show_matches_page(
    user_id: int,
    bot: Bot,
    session: AsyncSession,
    page: int,
    delete_msg_id: int | None = None,
) -> None:
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
    caption = f"⚔️  {page + 1} / {len(matches)}\n\n" + _profile_caption(partner)

    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(text="←", callback_data=f"matches_page:{page - 1}")
    builder.button(text=f"{page + 1}/{len(matches)}", callback_data="noop")
    if page < len(matches) - 1:
        builder.button(text="→", callback_data=f"matches_page:{page + 1}")
    if partner.username:
        builder.button(text="💬 написать", url=f"https://t.me/{partner.username}")
    else:
        builder.button(text="💬 написать", callback_data=f"try_write:{partner.id}")
    builder.adjust(3, 1)

    if partner.photos:
        await bot.send_photo(user_id, photo=partner.photos[0].file_id,
                             caption=caption, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await bot.send_message(user_id, caption, reply_markup=builder.as_markup(), parse_mode="HTML")


# ── уведомления ──────────────────────────────────────────────────

async def _send_match_notification(
    user_id: int, partner: User, bot: Bot, write_to: int | None = None,
) -> None:
    target   = write_to or partner.id
    username = partner.username if not write_to else None
    caption  = f"⚔️  мэтч.\n\n{_profile_caption(partner)}"
    kb       = kb_match(target, username=username)
    try:
        if partner.photos:
            await bot.send_photo(user_id, photo=partner.photos[0].file_id,
                                 caption=caption, reply_markup=kb, parse_mode="HTML")
        else:
            await bot.send_message(user_id, caption, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        _log.warning("match notify failed user_id=%s: %s", user_id, e)


async def _notify_liked(user_id: int, bot: Bot) -> None:
    try:
        await bot.send_message(
            user_id,
            "🩸  тебя лайкнули.\n<i>загляни в лайки.</i>",
            parse_mode="HTML",
        )
    except Exception as e:
        _log.warning("like notify failed user_id=%s: %s", user_id, e)


@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data.startswith("try_write:"))
async def try_write(call: CallbackQuery):
    await call.answer("закрытый профиль.", show_alert=True)
