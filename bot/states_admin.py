from aiogram.fsm.state import State, StatesGroup


class AdminBan(StatesGroup):
    waiting_id = State()

class AdminUnban(StatesGroup):
    waiting_id = State()

class AdminLookup(StatesGroup):
    waiting_id = State()

class AdminBroadcast(StatesGroup):
    waiting_text = State()
    confirm = State()

class AdminCalibration(StatesGroup):
    waiting_id    = State()
    waiting_votes = State()

class AdminAdChannel(StatesGroup):
    waiting_channel = State()
