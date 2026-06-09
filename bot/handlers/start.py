from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from bot.states import Registration
from bot.keyboards import kb_gender, kb_looking_for, kb_location, kb_main_menu, remove_kb
from bot.services import ProfileService
from bot import logger as log
from db.repositories.user_repo import UserRepository

_log = log.get(__name__)
router = Router()
_STEPS = 7

def _progress(step: int) -> str:
    return f"<code>{'●' * step}{'○' * (_STEPS - step)}</code>  {step}/{_STEPS}"

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession):
    repo = UserRepository(session)
    if await repo.exists(message.from_user.id):
        await state.clear()
        await message.answer("снова здесь.", reply_markup=kb_main_menu())
        return
    await message.answer(f"SHROOM\n\n{_progress(1)}\n\nимя.\n<i>до 16 символов</i>",
                         parse_mode="HTML", reply_markup=remove_kb())
    await state.set_state(Registration.name)

@router.message(Registration.name)
async def reg_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("↑ имя не может быть пустым.")
        return
    if len(name) > 16:
        await message.answer(f"↑ {len(name)}/16 — слишком длинно.")
        return
    await state.update_data(name=name)
    await message.answer(f"{_progress(2)}\n\n<b>{name}</b>\n\nвозраст.  <i>14–99</i>", parse_mode="HTML")
    await state.set_state(Registration.age)

@router.message(Registration.age)
async def reg_age(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.isdecimal() or not (14 <= int(text) <= 99):
        await message.answer("↑ 14–99.")
        return
    await state.update_data(age=int(text))
    await message.answer(f"{_progress(3)}\n\nты —", parse_mode="HTML", reply_markup=kb_gender())
    await state.set_state(Registration.gender)

@router.callback_query(Registration.gender, F.data.startswith("gender:"))
async def reg_gender(call: CallbackQuery, state: FSMContext):
    await state.update_data(gender=call.data.split(":")[1])
    await call.message.edit_text(f"{_progress(4)}\n\nищешь —", parse_mode="HTML", reply_markup=kb_looking_for())
    await state.set_state(Registration.looking_for)

@router.callback_query(Registration.looking_for, F.data.startswith("lf:"))
async def reg_looking_for(call: CallbackQuery, state: FSMContext):
    await state.update_data(looking_for=call.data.split(":")[1])
    await call.message.edit_text(f"{_progress(5)}\n\nо себе.\n<i>до 500 символов</i>", parse_mode="HTML")
    await state.set_state(Registration.bio)

@router.message(Registration.bio)
async def reg_bio_text(message: Message, state: FSMContext):
    bio = (message.text or "").strip()
    if not bio:
        await message.answer("↑ расскажи о себе.")
        return
    if len(bio) > 500:
        await message.answer("↑ не более 500.")
        return
    await state.update_data(bio=bio)
    await _ask_location(message, state)

async def _ask_location(message, state):
    await message.answer(f"{_progress(6)}\n\n📡  геолокация.\n<i>необязательно  ·  для расстояния</i>",
                         parse_mode="HTML", reply_markup=kb_location())
    await state.set_state(Registration.location)

@router.message(Registration.location, F.location)
async def reg_location(message: Message, state: FSMContext):
    await state.update_data(latitude=message.location.latitude, longitude=message.location.longitude)
    await message.answer("📡  сохранена.", reply_markup=remove_kb())
    await _ask_photo(message, state)

@router.message(Registration.location, F.text == "→ пропустить")
async def reg_location_skip(message: Message, state: FSMContext):
    await state.update_data(latitude=None, longitude=None)
    await message.answer("без геолокации.", reply_markup=remove_kb())
    await _ask_photo(message, state)

async def _ask_photo(message, state):
    await message.answer(f"{_progress(7)}\n\nфото.\n<i>одно — обязательно</i>", parse_mode="HTML")
    await state.set_state(Registration.photos)

@router.message(Registration.photos, F.photo)
async def reg_photo(message: Message, state: FSMContext, session: AsyncSession):
    file_id = message.photo[-1].file_id
    data = await state.get_data()
    svc = ProfileService(session)
    user = await svc.register(
        user_id=message.from_user.id, username=message.from_user.username,
        name=data["name"], age=data["age"], gender=data["gender"],
        looking_for=data["looking_for"], bio=data.get("bio"),
        latitude=data.get("latitude"), longitude=data.get("longitude"),
    )
    await svc.add_photo(user.id, file_id)
    await state.clear()
    _log.user("register: user=%s name=%s", message.from_user.id, data["name"])
    await message.answer(f"готово, <b>{data['name']}</b>.\n\n<i>добро пожаловать в темноту.</i>",
                         parse_mode="HTML", reply_markup=kb_main_menu())

@router.message(Registration.photos)
async def reg_photo_invalid(message: Message):
    await message.answer("↑ ожидается фото.")
