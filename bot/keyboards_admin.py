from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def kb_admin_main() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика",       callback_data="adm:stats")
    builder.button(text="👤 Найти юзера",      callback_data="adm:lookup")
    builder.button(text="🚷 Забанить",         callback_data="adm:ban")
    builder.button(text="✅ Разбанить",        callback_data="adm:unban")
    builder.button(text="📣 Рассылка",         callback_data="adm:broadcast")
    builder.button(text="🧬 Калибровка",       callback_data="adm:calibration")
    builder.button(text="👑 Администраторы",   callback_data="adm:admins")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def kb_admin_back() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Меню", callback_data="adm:menu")
    return builder.as_markup()


def kb_admin_confirm(action: str) -> InlineKeyboardMarkup:
    """Универсальная кнопка подтверждения опасного действия."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=f"adm:confirm:{action}")
    builder.button(text="❌ Отмена",      callback_data="adm:menu")
    builder.adjust(2)
    return builder.as_markup()


def kb_admin_user_actions(target_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_banned:
        builder.button(text="✅ Разбанить", callback_data=f"adm:do_unban:{target_id}")
    else:
        builder.button(text="🚷 Забанить",  callback_data=f"adm:do_ban:{target_id}")
    builder.button(text="🧬 Сбросить калибровку", callback_data=f"adm:do_reset_cal:{target_id}")
    builder.button(text="◀️ Меню",                callback_data="adm:menu")
    builder.adjust(1)
    return builder.as_markup()


def kb_admins_list(admins: list) -> InlineKeyboardMarkup:
    """Список администраторов с кнопкой удаления каждого."""
    builder = InlineKeyboardBuilder()
    for a in admins:
        label = f"@{a.username}" if a.username else str(a.telegram_id)
        builder.button(text=f"❌ {label}", callback_data=f"adm:rm_admin:{a.telegram_id}")
    builder.button(text="➕ Добавить", callback_data="adm:add_admin")
    builder.button(text="◀️ Меню",    callback_data="adm:menu")
    builder.adjust(1)
    return builder.as_markup()
