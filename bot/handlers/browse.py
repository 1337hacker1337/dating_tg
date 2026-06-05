import math

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import kb_main_menu, kb_match
from bot.services import BrowseService
from db.models import User, Like

router = Router()

# ── Ранги (дублируем локально, чтобы не создавать циклических импортов) ──
_TIERS = [
    (3.0,  "sub3",     "🚫"),
    (5.0,  "sub5",     "📉"),
    (6.0,  "ltn",      "👤"),
    (7.0,  "mtn",      "📊"),
    (7.10, "htn",      "🌟"),
    (8.5,  "chadlite", "⚡"),
]
_CHAD = ("chad", "👑")


def _get_tier(avg: float) -> tuple[str, str]:
    for threshold, slug, emoji in _TIERS:
        if avg < threshold:
            return slug, emoji
    return _CHAD


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _profile_caption(candidate: User, viewer: User | None = None) -> str:
    """
    HTML-карточка анкеты:
    👤 <b>Имя</b>, <code>Возраст</code>
    ├─ 🗺️ <i>X км от тебя</i>
    ├─ 🏆 Ранг: <b>emoji slug</b>  (avg/10 · N голосов)
    └─ 📝 <code>«bio»</code>
    """
    lines = [f"👤 <b>{candidate.name}</b>, <code>{candidate.age}</code>"]

    # Дистанция
    if (
        viewer and viewer.latitude is not None and viewer.longitude is not None
        and candidate.latitude is not None and candidate.longitude is not None
    ):
        dist = round(_haversine_km(
            viewer.latitude, viewer.longitude,
            candidate.latitude, candidate.longitude,
        ), 1)
        lines.append(f"├─ 🗺️ <i>{dist} км от тебя</i>")

    # Ранг
    if candidate.rating_count > 0:
        slug, emoji = _get_tier(candidate.avg_rating)
        lines.append(
            f"├─ 🏆 Ранг: <b>{emoji} {slug}</b>  "
            f"<code>({candidate.avg_rating:.1f}/10 · {candidate.rating_count} голосов)</code>"
        )
    else:
        lines.append("├─ 🏷 <i>Ранг пока не определён</i>")

    # Bio
    if candidate.bio:
        lines.append(f"└─ 📝 <code>«{candidate.bio}»</code>")

    return "\n".join(lines)


def kb_browse_for(candidate_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="👍 Лайк",       callback_data=f"like:{candidate_id}")
    builder.button(text="👎 Пропустить", callback_data=f"dislike:{candidate_id}")
    builder.adjust(2)
    return builder.as_markup()


def kb_likes_for(liker_id: int, page: int, total: int):
    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(text="◀️", callback_data=f"likes_page:{page - 1}")
    builder.button(text=f"{page + 1}/{total}", callback_data="noop")
    if page < total - 1:
        builder.button(text="▶️", callback_data=f"likes_page:{page + 1}")
    builder.button(text="👍 Лайкнуть",   callback_data=f"likes_react:like:{liker_id}:{page}")
    builder.button(text="👎 Пропустить", callback_data=f"likes_react:dislike:{liker_id}:{page}")
    builder.button(text="◀️ В меню",     callback_data="menu")
    builder.adjust(3, 2, 1)
    return builder.as_markup()


async def send_profile(
    user_id: int, bot: Bot, candidate: User,
    extra_text: str = "", viewer: User | None = None,
) -> None:
    photos  = candidate.photos
    caption = (extra_text + "\n\n" if extra_text else "") + _profile_caption(candidate, viewer)
    kb      = kb_browse_for(candidate.id)

    if not photos:
        await bot.send_message(user_id, f"{caption}\n\n<i>(нет фото)</i>",
                               parse_mode="HTML", reply_markup=kb)
        return

    if len(photos) == 1:
        await bot.send_photo(user_id, photo=photos[0].file_id,
                             caption=caption, reply_markup=kb, parse_mode="HTML")
    else:
        media = [InputMediaPhoto(media=p.file_id) for p in photos]
        media[-1].caption    = caption
        media[-1].parse_mode = "HTML"
        await bot.send_media_group(user_id, media=media)
        await bot.send_message(user_id, "👍 или 👎?", reply_markup=kb)


async def show_next(user_id: int, bot: Bot, session: AsyncSession) -> None:
    from db.repositories.user_repo import UserRepository
    svc       = BrowseService(session)
    viewer    = await UserRepository(session).get(user_id)
    candidate = await svc.next_candidate(user_id)
    if candidate is None:
        await bot.send_message(
            user_id,
            "😔 <b>Пока анкеты закончились.</b>\n└─ <i>Загляни позже!</i>",
            parse_mode="HTML",
            reply_markup=kb_main_menu(),
        )
        return
    await send_profile(user_id, bot, candidate, viewer=viewer)


# ───────────────────────────────────────────────────────────────
# Смотреть анкеты
# ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "browse")
async def handle_browse(call: CallbackQuery, bot: Bot, session: AsyncSession):
    await call.answer()
    await show_next(call.from_user.id, bot, session)


# ───────────────────────────────────────────────────────────────
# Лайк / дизлайк
# ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("like:"))
async def handle_like(call: CallbackQuery, bot: Bot, session: AsyncSession):
    candidate_id = int(call.data.split(":")[1])
    svc          = BrowseService(session)
    result       = await svc.react(call.from_user.id, candidate_id, liked=True)
    await call.answer("❤️")

    if result.is_new_match and result.partner:
        await _send_match_notification(call.from_user.id, result.partner, bot)
        viewer = await svc.users.get(call.from_user.id)
        if viewer:
            await _send_match_notification(result.partner.id, viewer, bot,
                                           write_to=call.from_user.id)
        return

    if result.notify_like:
        await _notify_liked(candidate_id, bot)

    await show_next(call.from_user.id, bot, session)


@router.callback_query(F.data.startswith("dislike:"))
async def handle_dislike(call: CallbackQuery, bot: Bot, session: AsyncSession):
    candidate_id = int(call.data.split(":")[1])
    svc          = BrowseService(session)
    await svc.react(call.from_user.id, candidate_id, liked=False)
    await call.answer("👎")
    await show_next(call.from_user.id, bot, session)


# ───────────────────────────────────────────────────────────────
# Мои лайки
# ───────────────────────────────────────────────────────────────

async def _get_unanswered_likers(user_id: int, session: AsyncSession) -> list[int]:
    liked_me  = select(Like.from_user).where(Like.to_user == user_id, Like.value.is_(True))
    i_reacted = select(Like.to_user).where(Like.from_user == user_id)
    result = await session.execute(liked_me.where(Like.from_user.not_in(i_reacted)))
    return [row[0] for row in result.fetchall()]


@router.callback_query(F.data == "my_likes")
async def show_likes(call: CallbackQuery, bot: Bot, session: AsyncSession):
    await call.answer()
    await _show_likes_page(call.from_user.id, bot, session, page=0)


@router.callback_query(F.data.startswith("likes_page:"))
async def likes_page(call: CallbackQuery, bot: Bot, session: AsyncSession):
    page = int(call.data.split(":")[1])
    await call.answer()
    await _show_likes_page(call.from_user.id, bot, session, page=page)


async def _show_likes_page(user_id: int, bot: Bot, session: AsyncSession, page: int) -> None:
    from db.repositories.user_repo import UserRepository
    liker_ids = await _get_unanswered_likers(user_id, session)

    if not liker_ids:
        await bot.send_message(
            user_id,
            "😔 <b>Новых лайков нет.</b>",
            parse_mode="HTML",
            reply_markup=kb_main_menu(),
        )
        return

    page  = max(0, min(page, len(liker_ids) - 1))
    liker = await UserRepository(session).get(liker_ids[page])
    if not liker:
        await bot.send_message(user_id, "Анкета удалена.", reply_markup=kb_main_menu())
        return

    caption = (
        f"💘 <b>Лайк {page + 1} из {len(liker_ids)}</b>\n\n"
        + _profile_caption(liker)
    )
    kb = kb_likes_for(liker.id, page, len(liker_ids))

    if liker.photos:
        await bot.send_photo(user_id, photo=liker.photos[0].file_id,
                             caption=caption, reply_markup=kb, parse_mode="HTML")
    else:
        await bot.send_message(user_id, caption, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("likes_react:"))
async def likes_react(call: CallbackQuery, bot: Bot, session: AsyncSession):
    _, action, liker_id_str, page_str = call.data.split(":")
    liker_id = int(liker_id_str)
    page     = int(page_str)
    liked    = action == "like"

    svc    = BrowseService(session)
    result = await svc.react(call.from_user.id, liker_id, liked=liked)
    await call.answer("❤️" if liked else "👎")

    if result.is_new_match and result.partner:
        await _send_match_notification(call.from_user.id, result.partner, bot)
        viewer = await svc.users.get(call.from_user.id)
        if viewer:
            await _send_match_notification(result.partner.id, viewer, bot,
                                           write_to=call.from_user.id)
        liker_ids = await _get_unanswered_likers(call.from_user.id, session)
        if liker_ids:
            await _show_likes_page(call.from_user.id, bot, session, page=0)
        return

    liker_ids = await _get_unanswered_likers(call.from_user.id, session)
    if not liker_ids:
        await bot.send_message(
            call.from_user.id,
            "✅ <b>Все лайки просмотрены!</b>",
            parse_mode="HTML",
            reply_markup=kb_main_menu(),
        )
        return
    await _show_likes_page(call.from_user.id, bot, session, page=min(page, len(liker_ids) - 1))


# ───────────────────────────────────────────────────────────────
# Мои мэтчи
# ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "my_matches")
async def show_matches(call: CallbackQuery, bot: Bot, session: AsyncSession):
    await call.answer()
    await _show_matches_page(call.from_user.id, bot, session, page=0)


@router.callback_query(F.data.startswith("matches_page:"))
async def matches_page(call: CallbackQuery, bot: Bot, session: AsyncSession):
    page = int(call.data.split(":")[1])
    await call.answer()
    await _show_matches_page(call.from_user.id, bot, session, page=page)


async def _show_matches_page(user_id: int, bot: Bot, session: AsyncSession, page: int) -> None:
    svc     = BrowseService(session)
    matches = await svc.get_matches(user_id)

    if not matches:
        await bot.send_message(
            user_id,
            "💔 <b>Пока нет мэтчей.</b>\n└─ <i>Продолжай смотреть анкеты!</i>",
            parse_mode="HTML",
            reply_markup=kb_main_menu(),
        )
        return

    page    = max(0, min(page, len(matches) - 1))
    partner = matches[page]
    caption = (
        f"💌 <b>Мэтч {page + 1} из {len(matches)}</b>\n\n"
        + _profile_caption(partner)
    )

    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(text="◀️", callback_data=f"matches_page:{page - 1}")
    builder.button(text=f"{page + 1}/{len(matches)}", callback_data="noop")
    if page < len(matches) - 1:
        builder.button(text="▶️", callback_data=f"matches_page:{page + 1}")
    if partner.username:
        builder.button(text="✍️ Написать", url=f"https://t.me/{partner.username}")
    else:
        builder.button(text="✍️ Написать", callback_data=f"try_write:{partner.id}")
    builder.button(text="◀️ В меню", callback_data="menu")
    builder.adjust(3, 1, 1)

    if partner.photos:
        await bot.send_photo(user_id, photo=partner.photos[0].file_id,
                             caption=caption, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await bot.send_message(user_id, caption, reply_markup=builder.as_markup(), parse_mode="HTML")


# ───────────────────────────────────────────────────────────────
# Вспомогательные
# ───────────────────────────────────────────────────────────────

async def _send_match_notification(
    user_id: int, partner: User, bot: Bot, write_to: int = None
) -> None:
    target   = write_to or partner.id
    username = partner.username if not write_to else None
    caption  = f"🎉 <b>Мэтч!</b>\n\n{_profile_caption(partner)}"
    kb       = kb_match(target, username=username)
    try:
        if partner.photos:
            await bot.send_photo(user_id, photo=partner.photos[0].file_id,
                                 caption=caption, reply_markup=kb, parse_mode="HTML")
        else:
            await bot.send_message(user_id, caption, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


async def _notify_liked(user_id: int, bot: Bot) -> None:
    builder = InlineKeyboardBuilder()
    builder.button(text="💘 Посмотреть кто лайкнул", callback_data="my_likes")
    try:
        await bot.send_message(
            user_id,
            "💘 <b>Кто-то поставил тебе лайк!</b>",
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
    except Exception:
        pass


@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data.startswith("try_write:"))
async def try_write(call: CallbackQuery):
    await call.answer(
        "У этого пользователя закрытые настройки приватности. "
        "Попроси его написать тебе первым!",
        show_alert=True,
    )
