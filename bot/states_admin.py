from aiogram.fsm.state import State, StatesGroup


class AdminBan(StatesGroup):
    waiting_id = State()        # ждём telegram_id для бана


class AdminUnban(StatesGroup):
    waiting_id = State()        # ждём telegram_id для разбана


class AdminLookup(StatesGroup):
    waiting_id = State()        # ждём telegram_id для просмотра анкеты


class AdminBroadcast(StatesGroup):
    waiting_text = State()      # ждём текст рассылки
    confirm = State()           # ждём подтверждения


class AdminCalibration(StatesGroup):
    waiting_id = State()        # ждём telegram_id
    waiting_votes = State()     # ждём новое значение rating_count


class AdminAddAdmin(StatesGroup):
    waiting_id = State()        # ждём telegram_id нового администратора
