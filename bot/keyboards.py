from aiogram.types import (
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


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


def kb_skip() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="→ пропустить", callback_data="skip")
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
    b.button(text="🤮", callback_data=f"dislike:{candidate_id}")
    b.button(text="🩸", callback_data=f"like:{candidate_id}")
    b.adjust(2)
    return b.as_markup()


def kb_match(partner_tg_id: int, username: str = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if username:
        b.button(text="💬 написать", url=f"https://t.me/{username}")
    else:
        b.button(text="💬 написать", callback_data=f"try_write:{partner_tg_id}")
    b.adjust(1)
    return b.as_markup()


def kb_profile_actions() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✏️ редактировать", callback_data="edit_profile")
    b.button(text="🙈 скрыть",        callback_data="hide_profile")
    b.button(text="👁 показать",      callback_data="show_profile")
    b.button(text="⚰️ удалить анкету", callback_data="delete_profile")
    b.adjust(1, 2, 1)
    return b.as_markup()
