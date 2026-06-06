from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def kb_admin_main() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📊 Статистика",     callback_data="adm:stats")
    b.button(text="👤 Найти юзера",    callback_data="adm:lookup")
    b.button(text="🚷 Забанить",       callback_data="adm:ban")
    b.button(text="✅ Разбанить",      callback_data="adm:unban")
    b.button(text="📣 Рассылка",       callback_data="adm:broadcast")
    b.button(text="🧬 Калибровка",     callback_data="adm:calibration")
    b.button(text="👑 Администраторы", callback_data="adm:admins")
    b.adjust(2, 2, 2, 1)
    return b.as_markup()


def kb_admin_back() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="◀️ Меню", callback_data="adm:menu")
    return b.as_markup()


def kb_admin_confirm(action: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data=f"adm:confirm:{action}")
    b.button(text="❌ Отмена",      callback_data="adm:menu")
    b.adjust(2)
    return b.as_markup()


def kb_admin_user_actions(target_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if is_banned:
        b.button(text="✅ Разбанить", callback_data=f"adm:do_unban:{target_id}")
    else:
        b.button(text="🚷 Забанить",  callback_data=f"adm:do_ban:{target_id}")
    b.button(text="🧬 Сбросить калибровку", callback_data=f"adm:do_reset_cal:{target_id}")
    b.button(text="◀️ Меню",                callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def kb_admins_list(admins: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for a in admins:
        label = f"@{a.username}" if a.username else str(a.telegram_id)
        b.button(text=f"❌ {label}", callback_data=f"adm:rm_admin:{a.telegram_id}")
    b.button(text="➕ Добавить", callback_data="adm:add_admin")
    b.button(text="◀️ Меню",    callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()
