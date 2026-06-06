from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states import Registration
from bot.keyboards import (
    kb_gender, kb_looking_for, kb_skip, kb_location,
    kb_main_menu, remove_kb,
)
from bot.services import ProfileService
from db.repositories.user_repo import UserRepository

router = Router()

# Всего шагов регистрации
_STEPS = 6

_ERR_PHOTO = (
    "⚠️ <b>Нарушение ритуала</b>\n"
    "└ <i>Система ожидает фотографию — не текст, не файл.</i>\n\n"
    "📜 Отправь своё фото, чтобы продолжить."
)


def _progress(step: int) -> str:
    """[●●●○○○] Шаг 3 из 6"""
    filled = "●" * step
    empty  = "○" * (_STEPS - step)
    return f"<code>[{filled}{empty}]</code> · <i>шаг {step} из {_STEPS}</i>"


# ───────────────────────────────────────────────────────────────
# /start
# ───────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession):
    repo = UserRepository(session)
    if await repo.exists(message.from_user.id):
        await state.clear()
        await message.answer(
            "🌌 <b>Грибница приветствует тебя.</b>\n"
            "└ <i>Лента ждёт — выбери действие:</i>",
            parse_mode="HTML",
            reply_markup=kb_main_menu(),
        )
        return

    await message.answer(
        "🌌 <b>Добро пожаловать в Shroom</b>\n"
        "├ Здесь работает своя система отбора\n"
        "└ Начнём создание анкеты\n\n"
        f"{_progress(1)}\n\n"
        "🕯️ <b>Как тебя зовут?</b>\n"
        "└ <i>До 16 символов</i>",
        parse_mode="HTML",
        reply_markup=remove_kb(),
    )
    await state.set_state(Registration.name)


# ───────────────────────────────────────────────────────────────
# Шаг 1 — Имя
# ───────────────────────────────────────────────────────────────

@router.message(Registration.name)
async def reg_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer(
            "⚠️ <b>Нарушение ритуала</b>\n"
            "└ <i>Имя не может быть пустым. Попробуй снова:</i>",
            parse_mode="HTML",
        )
        return
    if len(name) > 16:
        await message.answer(
            f"⚠️ <b>Слишком длинно</b> — <code>{len(name)}/16</code>\n"
            "└ <i>Укороти имя:</i>",
            parse_mode="HTML",
        )
        return

    await state.update_data(name=name)
    await message.answer(
        f"{_progress(2)}\n\n"
        f"🕯️ <b>{name}</b> — принято.\n\n"
        "📜 <b>Сколько тебе лет?</b>\n"
        "└ <i>От 1 до 99</i>",
        parse_mode="HTML",
    )
    await state.set_state(Registration.age)


# ───────────────────────────────────────────────────────────────
# Шаг 2 — Возраст
# ───────────────────────────────────────────────────────────────

@router.message(Registration.age)
async def reg_age(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.isdigit() or not (1 <= int(text) <= 99):
        await message.answer(
            "⚠️ <b>Нарушение ритуала</b>\n"
            "└ <i>Введи возраст числом от 1 до 99:</i>",
            parse_mode="HTML",
        )
        return
    await state.update_data(age=int(text))
    await message.answer(
        f"{_progress(3)}\n\n"
        "📜 <b>Выбери свой пол:</b>",
        parse_mode="HTML",
        reply_markup=kb_gender(),
    )
    await state.set_state(Registration.gender)


# ───────────────────────────────────────────────────────────────
# Шаг 3 — Пол
# ───────────────────────────────────────────────────────────────

@router.callback_query(Registration.gender, F.data.startswith("gender:"))
async def reg_gender(call: CallbackQuery, state: FSMContext):
    gender = call.data.split(":")[1]
    await state.update_data(gender=gender)
    await call.message.edit_text(
        f"{_progress(4)}\n\n"
        "📜 <b>Кого ты ищешь?</b>",
        parse_mode="HTML",
        reply_markup=kb_looking_for(),
    )
    await state.set_state(Registration.looking_for)


# ───────────────────────────────────────────────────────────────
# Шаг 4 — Кого ищешь
# ───────────────────────────────────────────────────────────────

@router.callback_query(Registration.looking_for, F.data.startswith("lf:"))
async def reg_looking_for(call: CallbackQuery, state: FSMContext):
    lf = call.data.split(":")[1]
    await state.update_data(looking_for=lf)
    await call.message.edit_text(
        f"{_progress(5)}\n\n"
        "📜 <b>Расскажи о себе</b>\n"
        "└ <i>До 500 символов — или пропусти:</i>",
        parse_mode="HTML",
        reply_markup=kb_skip(),
    )
    await state.set_state(Registration.bio)


# ───────────────────────────────────────────────────────────────
# Шаг 5 — Bio
# ───────────────────────────────────────────────────────────────

@router.message(Registration.bio)
async def reg_bio_text(message: Message, state: FSMContext):
    bio = (message.text or "").strip()
    if len(bio) > 500:
        await message.answer(
            "⚠️ <b>Слишком длинно</b>\n"
            "└ <i>Не более 500 символов. Попробуй снова:</i>",
            parse_mode="HTML",
        )
        return
    await state.update_data(bio=bio or None)
    await _ask_location(message, state)


@router.callback_query(Registration.bio, F.data == "skip")
async def reg_bio_skip(call: CallbackQuery, state: FSMContext):
    await state.update_data(bio=None)
    await call.message.delete()
    await _ask_location(call.message, state)


async def _ask_location(message: Message, state: FSMContext):
    await message.answer(
        f"{_progress(5)}\n\n"
        "📍 <b>Геолокация</b>\n"
        "├ <i>Поделись — покажем людей рядом.</i>\n"
        "└ <i>Необязательно, можно пропустить.</i>",
        parse_mode="HTML",
        reply_markup=kb_location(),
    )
    await state.set_state(Registration.location)


# ───────────────────────────────────────────────────────────────
# Шаг 5 — Геолокация
# ───────────────────────────────────────────────────────────────

@router.message(Registration.location, F.location)
async def reg_location(message: Message, state: FSMContext):
    await state.update_data(
        latitude=message.location.latitude,
        longitude=message.location.longitude,
    )
    await message.answer(
        "📍 <b>Геолокация сохранена.</b>",
        parse_mode="HTML",
        reply_markup=remove_kb(),
    )
    await _ask_photo(message, state)


@router.message(Registration.location, F.text == "Пропустить →")
async def reg_location_skip(message: Message, state: FSMContext):
    await state.update_data(latitude=None, longitude=None)
    await message.answer(
        "📍 <i>Без геолокации — окей.</i>",
        parse_mode="HTML",
        reply_markup=remove_kb(),
    )
    await _ask_photo(message, state)


async def _ask_photo(message: Message, state: FSMContext):
    await message.answer(
        f"{_progress(6)}\n\n"
        "🕯️ <b>Фото профиля</b>\n"
        "└ <i>Отправь одну фотографию — анкета без неё не создаётся.</i>",
        parse_mode="HTML",
    )
    await state.set_state(Registration.photos)


# ───────────────────────────────────────────────────────────────
# Шаг 6 — Фото → сразу регистрация
# ───────────────────────────────────────────────────────────────

@router.message(Registration.photos, F.photo)
async def reg_photo(message: Message, state: FSMContext, session: AsyncSession):
    file_id = message.photo[-1].file_id
    data    = await state.get_data()

    svc  = ProfileService(session)
    user = await svc.register(
        user_id    =message.from_user.id,
        username   =message.from_user.username,
        name       =data["name"],
        age        =data["age"],
        gender     =data["gender"],
        looking_for=data["looking_for"],
        bio        =data.get("bio"),
        latitude   =data.get("latitude"),
        longitude  =data.get("longitude"),
    )
    await svc.add_photo(user.id, file_id)
    await state.clear()

    await message.answer(
        f"👁️‍🗨️ <b>Анкета активирована, {data['name']}.</b>\n\n"
        "🌌 <i>Грибница открыта — лента ждёт.</i>",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )


# Catch-all — невалидный ввод на шаге фото
@router.message(Registration.photos)
async def reg_photo_invalid(message: Message):
    await message.answer(_ERR_PHOTO, parse_mode="HTML")
