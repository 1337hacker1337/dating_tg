from aiogram.types import (
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


def kb_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🕯️ Лента"),  KeyboardButton(text="💬 Мэтчи")],
            [KeyboardButton(text="🩸 Лайки"),   KeyboardButton(text="👁️ Профиль")],
        ],
        resize_keyboard=True,
        persistent=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def kb_gender() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Мужской", callback_data="gender:male")
    b.button(text="Женский", callback_data="gender:female")
    b.button(text="Другой",  callback_data="gender:other")
    b.adjust(2, 1)
    return b.as_markup()


def kb_looking_for() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Парней",  callback_data="lf:male")
    b.button(text="Девушек", callback_data="lf:female")
    b.button(text="Всех",    callback_data="lf:any")
    b.adjust(2, 1)
    return b.as_markup()


def kb_skip() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Пропустить →", callback_data="skip")
    return b.as_markup()


def kb_location() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Поделиться геолокацией", request_location=True)],
            [KeyboardButton(text="Пропустить →")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def kb_swipe(candidate_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⚰️", callback_data=f"dislike:{candidate_id}")
    b.button(text="🩸", callback_data=f"like:{candidate_id}")
    b.adjust(2)
    return b.as_markup()


def kb_match(partner_tg_id: int, username: str = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if username:
        b.button(text="💬 Написать", url=f"https://t.me/{username}")
    else:
        b.button(text="💬 Написать", callback_data=f"try_write:{partner_tg_id}")
    b.adjust(1)
    return b.as_markup()


def kb_profile_actions() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Редактировать", callback_data="edit_profile")
    b.button(text="🙈 Скрыть",        callback_data="hide_profile")
    b.button(text="👁 Показать",      callback_data="show_profile")
    b.button(text="⚰️ Удалить анкету", callback_data="delete_profile")
    b.adjust(1, 2, 1)
    return b.as_markup()
