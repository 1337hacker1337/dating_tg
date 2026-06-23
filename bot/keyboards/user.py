"""bot/keyboards/user.py — клавиатуры пользовательской части."""
from typing import Optional

from aiogram.types import (
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.constants import PREMIUM_BADGE


def kb_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🕯️ лента"),  KeyboardButton(text="💬 мэтчи")],
            [KeyboardButton(text="🩸 лайки"),   KeyboardButton(text="👁️ профиль")],
        ],
        resize_keyboard=True,
        persistent=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def kb_gender() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="парень",         callback_data="gender:male")
    b.button(text="девушка",        callback_data="gender:female")
    b.button(text="что-то другое",  callback_data="gender:other")
    b.adjust(2, 1)
    return b.as_markup()


def kb_looking_for() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="парней",  callback_data="lf:male")
    b.button(text="девушек", callback_data="lf:female")
    b.button(text="всех",    callback_data="lf:any")
    b.adjust(2, 1)
    return b.as_markup()


def kb_location() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 поделиться геолокацией", request_location=True)],
            [KeyboardButton(text="→ пропустить")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def kb_swipe(candidate_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🩸", callback_data=f"like:{candidate_id}")
    b.button(text="🤮", callback_data=f"dislike:{candidate_id}")
    b.button(text="↩️", callback_data="rewind")
    b.button(text="💬 лайк+", callback_data=f"likemsg:{candidate_id}")
    b.button(text="🚩", callback_data=f"report:start:{candidate_id}")
    b.adjust(3, 2)
    return b.as_markup()


def kb_match(partner_tg_id: int, username: Optional[str] = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if username:
        b.button(text="💬 написать", url=f"https://t.me/{username}")
    else:
        b.button(text="💬 написать", callback_data=f"try_write:{partner_tg_id}")
    b.adjust(1)
    return b.as_markup()


def kb_profile_actions(notifications_on: bool = True, is_active: bool = True) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    # ряд 1: редактирование + фильтры
    b.button(text="✏️ редактировать", callback_data="edit_profile")
    b.button(text="🔍 фильтры", callback_data="filters")
    # ряд 2: кто смотрел + видимость
    b.button(text="👀 кто смотрел", callback_data="views")
    vis = "🙈 скрыть" if is_active else "👁 показать"
    b.button(text=vis, callback_data="toggle_visibility")
    # ряд 3: уведомления + премиум
    notif = "🔔 уведы" if notifications_on else "🔕 уведы"
    b.button(text=notif, callback_data="toggle_notifications")
    b.button(text=f"{PREMIUM_BADGE} shroom+", callback_data="premium")
    # ряд 4: приглашения + удаление
    b.button(text="🔗 пригласить", callback_data="invite")
    b.button(text="⚰️ удалить", callback_data="delete_profile")
    b.adjust(2, 2, 2, 2)
    return b.as_markup()


def kb_filters() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎂 возраст", callback_data="filters:age")
    b.button(text="📍 расстояние", callback_data="filters:dist")
    b.button(text="♻️ сбросить", callback_data="filters:reset")
    b.button(text="◀️ назад", callback_data="filters:back")
    b.adjust(2, 1, 1)
    return b.as_markup()


def kb_filter_distance() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for km in (5, 10, 25, 50, 100, 200):
        b.button(text=f"{km} км", callback_data=f"filters:dist_set:{km}")
    b.button(text="без ограничения", callback_data="filters:dist_set:0")
    b.button(text="◀️ назад", callback_data="filters:open")
    b.adjust(3, 3, 1, 1)
    return b.as_markup()


def kb_report_reasons(target_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📢 спам / реклама",      callback_data=f"report:do:{target_id}:spam")
    b.button(text="🔞 откровенный контент", callback_data=f"report:do:{target_id}:nudity")
    b.button(text="⚙️ другое",              callback_data=f"report:do:{target_id}:other")
    b.button(text="❌ отмена",              callback_data="report:cancel")
    b.adjust(1)
    return b.as_markup()
