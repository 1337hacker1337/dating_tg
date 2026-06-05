from aiogram.types import (
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


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
    builder.button(text="Пропустить", callback_data="skip")
    return builder.as_markup()


def kb_location() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Поделиться геолокацией", request_location=True)],
            [KeyboardButton(text="Пропустить")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def kb_done_photos() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Готово", callback_data="photos_done")
    return builder.as_markup()


def kb_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❤️ Смотреть анкеты",    callback_data="browse")
    builder.button(text="💘 Мои лайки",           callback_data="my_likes")
    builder.button(text="💌 Мои мэтчи",           callback_data="my_matches")
    builder.button(text="👤 Мой профиль",          callback_data="my_profile")
    builder.button(text="📍 Геолокация",           callback_data="update_location")
    builder.adjust(1, 2, 2)  # 1 большая + 2 пары
    return builder.as_markup()


def kb_match(partner_tg_id: int, username: str = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if username:
        builder.button(text="✍️ Написать", url=f"https://t.me/{username}")
    else:
        builder.button(text="✍️ Написать", callback_data=f"try_write:{partner_tg_id}")
    builder.button(text="❤️ Продолжить смотреть", callback_data="browse")
    builder.adjust(1)
    return builder.as_markup()


def kb_profile_actions() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Редактировать", callback_data="edit_profile")
    builder.button(text="🙈 Скрыть",        callback_data="hide_profile")
    builder.button(text="👁 Показать",      callback_data="show_profile")
    builder.button(text="🗑 Удалить",       callback_data="delete_profile")
    builder.button(text="◀️ В меню",        callback_data="menu")
    builder.adjust(1, 2, 2)  # редактировать отдельно, скрыть/показать, удалить/меню
    return builder.as_markup()


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
