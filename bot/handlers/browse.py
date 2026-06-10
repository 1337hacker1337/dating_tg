import math
from datetime import datetime, timezone, timedelta

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
from db.repositories.admin_repo import AdminRepository
from db.repositories.user_repo import UserRepository
from db.repositories.like_repo import LikeRepository

_log = log.get(__name__)
router = Router()

# ── Лимиты свайпов ────────────────────────────────────────────────
SWIPE_LIMIT        = 50   # свайпов (лайки + дизы вместе)
SWIPE_WINDOW_HOURS = 6    # скользящее окно в часах


def _fmt_delta(delta: timedelta) -> str:
    secs = max(0, int(delta.total_seconds()))
    h, rem = divmod(secs, 3600)
    m = rem // 60
    if h and m:
        return f"{h}ч {m}м"
    if h:
        return f"{h}ч"
    return f"{m}м"


async def _swipe_limit_exceeded(user_id: int, session) -> tuple[bool, str]:
    """
    Возвращает (exceeded, alert_text).
    Admins всегда пропускаются.
    """
    if await AdminRepository(session).is_admin(user_id):
        return False, ""

    repo  = LikeRepository(session)
    count = await repo.count_recent_swipes(user_id, SWIPE_WINDOW_HOURS)
    if count < SWIPE_LIMIT:
        return False, ""

    oldest = await repo.get_oldest_swipe_in_window(user_id, SWIPE_WINDOW_HOURS)
    timer  = ""
    if oldest:
        next_slot = oldest + timedelta(hours=SWIPE_WINDOW_HOURS)
        delta = next_slot - datetime.now(tz=timezone.utc)
        if delta.total_seconds() > 0:
            timer = f"\nследующий слот через {_fmt_delta(delta)}."

    text = (
        f"⏳  лимит.\n"
        f"{SWIPE_LIMIT}/{SWIPE_LIMIT} свайпов за {SWIPE_WINDOW_HOURS}ч.{timer}"
    )
    return True, text


# ── Вспомогательные ───────────────────────────────────────────────

def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


async def _profile_caption(candidate: User, session, viewer=None) -> str:
    header = f"<b>{candidate.name}</b>, {candidate.age}"
    if viewer and viewer.latitude is not None and candidate.latitude is not None:
        dist = round(
            _haversine_km(
                viewer.latitude, viewer.longitude,
                candidate.latitude, candidate.longitude,
            ),
            1,
        )
        header += f"  ·  {dist} км"
    lines = [header]
    if candidate.bio:
        lines += ["", f"<i>{candidate.bio}</i>"]
    likes    = round(candidate.avg_rating * candidate.rating_count)
    dislikes = candidate.rating_count - likes
    stats    = await UserRepository(session).get_profile_stats(candidate.id)
    lines += [
        "",
        format_rating_line(candidate.avg_rating, candidate.rating_count),
        "",
        f"🩸 <code>{likes}</code>  ·  🤮 <code>{dislikes}</code>  ·  ⚔️ <code>{stats['matches']}</code>",
    ]
    return "\n".join(lines)


async def _send_card(user_id, bot, candidate, session, viewer=None):
    caption = await _profile_caption(candidate, session, viewer)
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
async def handle_browse_msg(message: Message, bot: Bot, session, db_user=None):
    await show_next(message.from_user.id, bot, session, viewer=db_user)


# ── Лайк ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("like:"))
async def handle_like(call: CallbackQuery, bot: Bot, session, db_user=None):
    exceeded, limit_text = await _swipe_limit_exceeded(call.from_user.id, session)
    if exceeded:
        await call.answer(limit_text, show_alert=True)
        return

    candidate_id = int(call.data.split(":")[1])
    svc    = BrowseService(session)
    result = await svc.react(call.from_user.id, candidate_id, liked=True)
    await call.answer("🩸")
    _log.user("like: user=%s → %s", call.from_user.id, candidate_id)

    if result.is_new_match and result.partner:
        await _send_match_notification(call.from_user.id, result.partner, bot, session)
        viewer = db_user or await svc.users.get(call.from_user.id)
        if viewer:
            await _send_match_notification(
                result.partner.id, viewer, bot, session, write_to=call.from_user.id
            )
    elif result.notify_like:
        await _notify_liked(candidate_id, bot, session)

    await show_next(
        call.from_user.id, bot, session,
        delete_msg_id=call.message.message_id, viewer=db_user,
    )


# ── Дизлайк ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("dislike:"))
async def handle_dislike(call: CallbackQuery, bot: Bot, session, db_user=None):
    exceeded, limit_text = await _swipe_limit_exceeded(call.from_user.id, session)
    if exceeded:
        await call.answer(limit_text, show_alert=True)
        return

    candidate_id = int(call.data.split(":")[1])
    await BrowseService(session).react(call.from_user.id, candidate_id, liked=False)
    await call.answer("🤮")
    await show_next(
        call.from_user.id, bot, session,
        delete_msg_id=call.message.message_id, viewer=db_user,
    )


# ── Лайки (входящие) ──────────────────────────────────────────────

@router.message(F.text.in_({"🩸 лайки", "🩸 Лайки"}))
async def show_likes_msg(message: Message, bot: Bot, session):
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
    caption = f"🩸  {page + 1} / {total}\n\n" + await _profile_caption(liker, session, viewer)

    b = InlineKeyboardBuilder()
    if page > 0:
        b.button(text="←", callback_data=f"likes_page:{page - 1}")
    b.button(text=f"{page + 1}/{total}", callback_data="noop")
    if page < total - 1:
        b.button(text="→", callback_data=f"likes_page:{page + 1}")
    b.button(text="🤮", callback_data=f"likes_react:dislike:{liker.id}:{page}")
    b.button(text="🩸", callback_data=f"likes_react:like:{liker.id}:{page}")
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
            await _send_match_notification(
                result.partner.id, viewer, bot, session, write_to=call.from_user.id
            )

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
async def show_matches_msg(message: Message, bot: Bot, session):
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
    caption = f"⚔️  {page + 1} / {len(matches)}\n\n" + await _profile_caption(partner, session, viewer)

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

async def _send_match_notification(user_id, partner, bot, session, write_to=None):
    target   = write_to or partner.id
    username = partner.username if not write_to else None
    caption  = "⚔️  мэтч.\n\n" + await _profile_caption(partner, session)
    kb       = kb_match(target, username=username)
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


# ── Служебные callback ────────────────────────────────────────────

@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data.startswith("try_write:"))
async def try_write(call: CallbackQuery):
    await call.answer("закрытый профиль.", show_alert=True)