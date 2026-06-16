"""bot/keyboards/admin.py — клавиатуры админ-панели."""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.constants import PREMIUM_DAYS_PRESETS


def kb_admin_grant_periods(target_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for days in PREMIUM_DAYS_PRESETS:
        b.button(text=f"{days} дней", callback_data=f"adm:grant_do:{target_id}:{days}")
    b.button(text="◀️ меню", callback_data="adm:menu")
    b.adjust(2, 2, 1)
    return b.as_markup()


def kb_admin_main() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📊 статистика",     callback_data="adm:stats")
    b.button(text="👤 найти юзера",    callback_data="adm:lookup")
    b.button(text="🚷 забанить",       callback_data="adm:ban")
    b.button(text="✅ разбанить",      callback_data="adm:unban")
    b.button(text="📣 рассылка",       callback_data="adm:broadcast")
    b.button(text="🧬 калибровка",     callback_data="adm:calibration")
    b.button(text="👑 администраторы", callback_data="adm:admins")
    b.button(text="📢 реклама",        callback_data="adm:ad_channel")
    b.button(text="🚩 репорты",        callback_data="adm:reports")
    b.button(text="🔱 выдать shroom+", callback_data="adm:grant_prem")
    b.button(text="🧪 тест-режим",     callback_data="adm:test")
    b.adjust(2, 2, 2, 2, 2, 1)
    return b.as_markup()


def kb_admin_testing(fake_count: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🧪 +10 анкет",        callback_data="adm:test_seed")
    b.button(text="🩸 5 лайкнут меня",   callback_data="adm:test_likes")
    b.button(text="💬 записка мне",      callback_data="adm:test_note")
    b.button(text="👀 7 просмотров",     callback_data="adm:test_views")
    b.button(text="⚔️ мэтч с фейком",    callback_data="adm:test_match")
    b.button(text="🩸 ответит на лайк",  callback_data="adm:test_reply")
    b.button(text="🚩 создать репорт",   callback_data="adm:test_report")
    b.button(text=f"🧹 удалить тестовые ({fake_count})", callback_data="adm:test_clear")
    b.button(text="◀️ меню",             callback_data="adm:menu")
    b.adjust(2, 2, 2, 2, 1)
    return b.as_markup()


def kb_admin_back() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="◀️ меню", callback_data="adm:menu")
    return b.as_markup()


def kb_admin_confirm(action: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ подтвердить", callback_data=f"adm:confirm:{action}")
    b.button(text="❌ отмена",      callback_data="adm:menu")
    b.adjust(2)
    return b.as_markup()


def kb_admin_user_actions(target_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if is_banned:
        b.button(text="✅ разбанить", callback_data=f"adm:do_unban:{target_id}")
    else:
        b.button(text="🚷 забанить",  callback_data=f"adm:do_ban:{target_id}")
    b.button(text="🧬 сбросить калибровку", callback_data=f"adm:do_reset_cal:{target_id}")
    b.button(text="🔱 +30д shroom+",        callback_data=f"adm:do_grant_prem:{target_id}")
    b.button(text="◀️ меню",                callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def kb_admins_list(admins: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for a in admins:
        label = f"@{a.username}" if a.username else str(a.telegram_id)
        b.button(text=f"❌ {label}", callback_data=f"adm:rm_admin:{a.telegram_id}")
    b.button(text="➕ добавить", callback_data="adm:add_admin")
    b.button(text="◀️ меню",    callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def kb_ad_channel(has_channel: bool, has_timer: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✏️ сменить канал", callback_data="adm:ad_set")
    if has_channel:
        b.button(text="⏱ таймер",    callback_data="adm:ad_timer")
        b.button(text="🗑 отключить", callback_data="adm:ad_clear")
    b.button(text="◀️ меню", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def kb_ad_timer() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    presets = [
        ("1 час",     "adm:ad_timer_set:1"),
        ("3 часа",    "adm:ad_timer_set:3"),
        ("6 часов",   "adm:ad_timer_set:6"),
        ("12 часов",  "adm:ad_timer_set:12"),
        ("24 часа",   "adm:ad_timer_set:24"),
        ("3 дня",     "adm:ad_timer_set:72"),
        ("7 дней",    "adm:ad_timer_set:168"),
        ("постоянно", "adm:ad_timer_set:0"),
    ]
    for label, cd in presets:
        b.button(text=label, callback_data=cd)
    b.button(text="◀️ назад", callback_data="adm:ad_channel")
    b.adjust(2, 2, 2, 2, 1)
    return b.as_markup()


def kb_report_actions(
    report_id: int,
    target_id: int,
    is_banned: bool,
    page: int,
    total: int,
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()

    # Действия
    if not is_banned:
        b.button(text="🚷 забанить",  callback_data=f"adm:rep_ban:{report_id}:{page}")
    b.button(text="✅ отклонить", callback_data=f"adm:rep_dismiss:{report_id}:{page}")

    # Навигация — считаем фактическое число кнопок
    # (БАГФИКС: раньше nav_cols = min(3, total) ломал раскладку
    #  на первой/последней странице, где кнопок 2, а не 3)
    nav_buttons = 0
    if total > 1:
        if page > 0:
            b.button(text="←", callback_data=f"adm:rep_page:{page - 1}")
            nav_buttons += 1
        b.button(text=f"{page + 1}/{total}", callback_data="noop")
        nav_buttons += 1
        if page < total - 1:
            b.button(text="→", callback_data=f"adm:rep_page:{page + 1}")
            nav_buttons += 1

    b.button(text="◀️ меню", callback_data="adm:menu")

    action_cols = 1 if is_banned else 2
    if nav_buttons:
        b.adjust(action_cols, nav_buttons, 1)
    else:
        b.adjust(action_cols, 1)

    return b.as_markup()
