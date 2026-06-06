from aiogram.types import (
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ── Reply: главное меню (всегда внизу) ──────────────────────────

def kb_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🕯️ Лента"),      KeyboardButton(text="💬 Мэтчи")],
            [KeyboardButton(text="🩸 Лайки"),       KeyboardButton(text="👁️ Профиль")],
        ],
        resize_keyboard=True,
        persistent=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


# ── Inline: регистрация ──────────────────────────────────────────

def kb_gender() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Мужской", callback_data="gender:male")
    builder.button(text="Женский", callback_data="gender:female")
    builder.button(text="Другой",  callback_data="gender:other")
    builder.adjust(2, 1)
    return builder.as_markup()


def kb_looking_for() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Парней",  callback_data="lf:male")
    builder.button(text="Девушек", callback_data="lf:female")
    builder.button(text="Всех",    callback_data="lf:any")
    builder.adjust(2, 1)
    return builder.as_markup()


def kb_skip() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Пропустить →", callback_data="skip")
    return builder.as_markup()


def kb_location() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Поделиться геолокацией", request_location=True)],
            [KeyboardButton(text="Пропустить →")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ── Inline: свайп ────────────────────────────────────────────────

def kb_swipe(candidate_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⚰️",  callback_data=f"dislike:{candidate_id}")
    builder.button(text="🩸",  callback_data=f"like:{candidate_id}")
    builder.adjust(2)
    return builder.as_markup()


# ── Inline: мэтч ────────────────────────────────────────────────

def kb_match(partner_tg_id: int, username: str = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if username:
        builder.button(text="💬 Написать", url=f"https://t.me/{username}")
    else:
        builder.button(text="💬 Написать", callback_data=f"try_write:{partner_tg_id}")
    builder.adjust(1)
    return builder.as_markup()


# ── Inline: профиль ──────────────────────────────────────────────

def kb_profile_actions() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Редактировать", callback_data="edit_profile")
    builder.button(text="🙈 Скрыть",        callback_data="hide_profile")
    builder.button(text="👁 Показать",      callback_data="show_profile")
    builder.button(text="⚰️ Удалить анкету", callback_data="delete_profile")
    builder.adjust(1, 2, 1)
    return builder.as_markup()
