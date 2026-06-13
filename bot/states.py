"""bot/states.py — все FSM-состояния (пользовательские + админские)."""
from aiogram.fsm.state import State, StatesGroup


# ── Пользователь ──────────────────────────────────────────────────

class Registration(StatesGroup):
    name = State()
    age = State()
    gender = State()
    looking_for = State()
    bio = State()
    location = State()
    photos = State()


class EditProfile(StatesGroup):
    choose_field = State()
    new_value = State()
    new_photo = State()


# ── Админ ─────────────────────────────────────────────────────────

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
