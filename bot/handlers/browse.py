import math
import logging

logger = logging.getLogger(__name__)

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import kb_main_menu, kb_match, kb_swipe
from bot.rating import format_rating_line
from bot.services import BrowseService
from db.models import User, Like
from db.repositories.user_repo import UserRepository

router = Router()


# ── Утилиты ─────────────────────────────────────────────────────

def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _profile_caption(candidate: User, viewer: User | None = None) -> str:
    """
    🕯️ Имя, возраст · 📍 X км
    📊 [████░░░░] 72% 🔮 htn
    📜 bio
    """
    # Строка 1
    line1 = f"🕯️ <b>{candidate.name}</b>, <code>{candidate.age}</code>"
    if (
        viewer
        and viewer.latitude is not None and viewer.longitude is not None
        and candidate.latitude is not None and candidate.longitude is not None
    ):
        dist = round(_haversine_km(
            viewer.latitude, viewer.longitude,
            candidate.latitude, candidate.longitude,
        ), 1)
        line1 += f" · 📍 {dist} км"

    # Строка 2: ранг
    line2 = format_rating_line(candidate.avg_rating, candidate.rating_count)

    lines = [line1, line2]

    # Bio
    if candidate.bio:
        lines.append(f"📜 <i>{candidate.bio}</i>")

    return "\n".join(lines)


async def _send_card(
    user_id: int,
    bot: Bot,
    candidate: User,
    viewer: User | None = None,
) -> int | None:
    """Отправляет карточку. Возвращает message_id для последующего удаления."""
    caption = _profile_caption(candidate, viewer)
    kb      = kb_swipe(candidate.id)
    photos  = candidate.photos

    if not photos:
        msg = await bot.send_message(
            user_id, caption + "\n\n<i>(нет фото)</i>",
            parse_mode="HTML", reply_markup=kb,
        )
        return msg.message_id

    msg = await bot.send_photo(
        user_id, photo=photos[0].file_id,
        caption=caption, reply_markup=kb, parse_mode="HTML",
    )
    return msg.message_id


async def show_next(
    user_id: int,
    bot: Bot,
    session: AsyncSession,
    delete_msg_id: int | None = None,
) -> None:
    if delete_msg_id:
        try:
            await bot.delete_message(user_id, delete_msg_id)
        except Exception:
            pass

    repo      = UserRepository(session)
    viewer    = await repo.get(user_id)
    if viewer is None:
        await bot.send_message(user_id, "⚠️ Сначала создай анкету — /start")
        return

    candidate = await repo.get_next_candidate(viewer, nearby_radius_km=50)
    if candidate is None:
        await bot.send_message(
            user_id,
            "🌐 <b>Мёртвая сеть.</b>\n"
            "└ <i>Поток душ иссяк — загляни позже.</i>",
            parse_mode="HTML",
            reply_markup=kb_main_menu(),
        )
        return

    await _send_card(user_id, bot, candidate, viewer=viewer)


# ───────────────────────────────────────────────────────────────
# Лента — reply-кнопка
# ───────────────────────────────────────────────────────────────

@router.message(F.text == "🕯️ Лента")
async def handle_browse_msg(message: Message, bot: Bot, session: AsyncSession):
    await show_next(message.from_user.id, bot, session)


# ───────────────────────────────────────────────────────────────
# 🩸 Лайк
# ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("like:"))
async def handle_like(call: CallbackQuery, bot: Bot, session: AsyncSession):
    candidate_id = int(call.data.split(":")[1])
    svc          = BrowseService(session)
    result       = await svc.react(call.from_user.id, candidate_id, liked=True)
    await call.answer("🩸")

    if result.is_new_match and result.partner:
        await _send_match_notification(call.from_user.id, result.partner, bot)
        viewer = await svc.users.get(call.from_user.id)
        if viewer:
            await _send_match_notification(
                result.partner.id, viewer, bot, write_to=call.from_user.id
            )
    elif result.notify_like:
        await _notify_liked(candidate_id, bot)

    await show_next(call.from_user.id, bot, session, delete_msg_id=call.message.message_id)


# ───────────────────────────────────────────────────────────────
# ⚰️ Дизлайк
# ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("dislike:"))
async def handle_dislike(call: CallbackQuery, bot: Bot, session: AsyncSession):
    candidate_id = int(call.data.split(":")[1])
    svc          = BrowseService(session)
    await svc.react(call.from_user.id, candidate_id, liked=False)
    await call.answer("⚰️")
    await show_next(call.from_user.id, bot, session, delete_msg_id=call.message.message_id)


# ───────────────────────────────────────────────────────────────
# Лайки — reply-кнопка
# ───────────────────────────────────────────────────────────────

@router.message(F.text == "🩸 Лайки")
async def show_likes_msg(message: Message, bot: Bot, session: AsyncSession):
    await _show_likes_page(message.from_user.id, bot, session, page=0)


async def _get_unanswered_likers(user_id: int, session: AsyncSession) -> list[int]:
    liked_me  = select(Like.from_user).where(Like.to_user == user_id, Like.value.is_(True))
    i_reacted = select(Like.to_user).where(Like.from_user == user_id)
    result    = await session.execute(liked_me.where(Like.from_user.not_in(i_reacted)))
    return [row[0] for row in result.fetchall()]


@router.callback_query(F.data.startswith("likes_page:"))
async def likes_page(call: CallbackQuery, bot: Bot, session: AsyncSession):
    page = int(call.data.split(":")[1])
    await call.answer()
    await _show_likes_page(
        call.from_user.id, bot, session, page=page,
        delete_msg_id=call.message.message_id,
    )


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

    liker_ids = await _get_unanswered_likers(user_id, session)
    if not liker_ids:
        await bot.send_message(
            user_id,
            "🩸 <b>Новых лайков нет.</b>\n"
            "└ <i>Лента пустая — иди в ленту.</i>",
            parse_mode="HTML",
        )
        return

    page  = max(0, min(page, len(liker_ids) - 1))
    liker = await UserRepository(session).get(liker_ids[page])
    if not liker:
        await bot.send_message(user_id, "⚠️ Анкета удалена.")
        return

    caption = (
        f"🩸 <b>Лайк {page + 1} / {len(liker_ids)}</b>\n\n"
        + _profile_caption(liker)
    )

    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(text="◀️", callback_data=f"likes_page:{page - 1}")
    builder.button(text=f"{page + 1}/{len(liker_ids)}", callback_data="noop")
    if page < len(liker_ids) - 1:
        builder.button(text="▶️", callback_data=f"likes_page:{page + 1}")
    builder.button(text="⚰️", callback_data=f"likes_react:dislike:{liker.id}:{page}")
    builder.button(text="🩸", callback_data=f"likes_react:like:{liker.id}:{page}")
    builder.adjust(3, 2)

    if liker.photos:
        await bot.send_photo(
            user_id, photo=liker.photos[0].file_id,
            caption=caption, reply_markup=builder.as_markup(), parse_mode="HTML",
        )
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
    await call.answer("🩸" if liked else "⚰️")

    if result.is_new_match and result.partner:
        await _send_match_notification(call.from_user.id, result.partner, bot)
        viewer = await svc.users.get(call.from_user.id)
        if viewer:
            await _send_match_notification(
                result.partner.id, viewer, bot, write_to=call.from_user.id
            )

    liker_ids = await _get_unanswered_likers(call.from_user.id, session)
    if not liker_ids:
        try:
            await bot.delete_message(call.from_user.id, call.message.message_id)
        except Exception:
            pass
        await bot.send_message(
            call.from_user.id,
            "✅ <b>Все лайки обработаны.</b>",
            parse_mode="HTML",
        )
        return

    await _show_likes_page(
        call.from_user.id, bot, session,
        page=min(page, len(liker_ids) - 1),
        delete_msg_id=call.message.message_id,
    )


# ───────────────────────────────────────────────────────────────
# Мэтчи — reply-кнопка
# ───────────────────────────────────────────────────────────────

@router.message(F.text == "💬 Мэтчи")
async def show_matches_msg(message: Message, bot: Bot, session: AsyncSession):
    await _show_matches_page(message.from_user.id, bot, session, page=0)


@router.callback_query(F.data.startswith("matches_page:"))
async def matches_page(call: CallbackQuery, bot: Bot, session: AsyncSession):
    page = int(call.data.split(":")[1])
    await call.answer()
    await _show_matches_page(
        call.from_user.id, bot, session, page=page,
        delete_msg_id=call.message.message_id,
    )


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
        await bot.send_message(
            user_id,
            "⚔️ <b>Мэтчей пока нет.</b>\n"
            "└ <i>Иди в ленту — столкновение импульсов ждёт.</i>",
            parse_mode="HTML",
        )
        return

    page    = max(0, min(page, len(matches) - 1))
    partner = matches[page]
    caption = (
        f"⚔️ <b>Мэтч {page + 1} / {len(matches)}</b>\n\n"
        + _profile_caption(partner)
    )

    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(text="◀️", callback_data=f"matches_page:{page - 1}")
    builder.button(text=f"{page + 1}/{len(matches)}", callback_data="noop")
    if page < len(matches) - 1:
        builder.button(text="▶️", callback_data=f"matches_page:{page + 1}")
    if partner.username:
        builder.button(text="💬 Написать", url=f"https://t.me/{partner.username}")
    else:
        builder.button(text="💬 Написать", callback_data=f"try_write:{partner.id}")
    builder.adjust(3, 1)

    if partner.photos:
        await bot.send_photo(
            user_id, photo=partner.photos[0].file_id,
            caption=caption, reply_markup=builder.as_markup(), parse_mode="HTML",
        )
    else:
        await bot.send_message(
            user_id, caption, reply_markup=builder.as_markup(), parse_mode="HTML",
        )


# ───────────────────────────────────────────────────────────────
# Вспомогательные
# ───────────────────────────────────────────────────────────────

async def _send_match_notification(
    user_id: int, partner: User, bot: Bot, write_to: int | None = None,
) -> None:
    target   = write_to or partner.id
    username = partner.username if not write_to else None
    caption  = f"⚔️ <b>Мэтч — скрещенные клинки.</b>\n\n{_profile_caption(partner)}"
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
        logger.warning("Не удалось отправить уведомление о мэтче user_id=%s: %s", user_id, e)


async def _notify_liked(user_id: int, bot: Bot) -> None:
    try:
        await bot.send_message(
            user_id,
            "🩸 <b>Кто-то пролил за тебя кровь.</b>\n"
            "└ <i>Загляни во вкладку Лайки.</i>",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("Не удалось отправить уведомление о лайке user_id=%s: %s", user_id, e)


@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data.startswith("try_write:"))
async def try_write(call: CallbackQuery):
    await call.answer(
        "⛓️ Закрытые настройки приватности — попроси написать первым.",
        show_alert=True,
    )
