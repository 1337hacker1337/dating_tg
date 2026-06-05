from aiogram.fsm.state import State, StatesGroup


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
