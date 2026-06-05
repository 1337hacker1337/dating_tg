from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states import Registration
from bot.keyboards import (
    kb_gender, kb_looking_for, kb_skip, kb_location,
    kb_done_photos, kb_main_menu, remove_kb,
)
from bot.services import ProfileService
from db.repositories.user_repo import UserRepository

router = Router()


# ───────────────────────────────────────────────────────────────
# /start
# ───────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession, db_user=None):
    repo = UserRepository(session)
    if await repo.exists(message.from_user.id):
        await state.clear()
        await message.answer(
            "👋 С возвращением! Выбери действие:",
            reply_markup=kb_main_menu(),
        )
        return

    await message.answer(
        "👋 Привет! Давай создадим твой профиль.\n\n"
        "Как тебя зовут? (только имя, до 64 символов)"
    )
    await state.set_state(Registration.name)


# ───────────────────────────────────────────────────────────────
# Шаг 1 — Имя
# ───────────────────────────────────────────────────────────────

@router.message(Registration.name)
async def reg_name(message: Message, state: FSMContext):
    name = message.text.strip() if message.text else ""
    if not name or len(name) > 64:
        await message.answer("Имя должно быть от 1 до 64 символов. Попробуй ещё раз:")
        return
    await state.update_data(name=name)
    await message.answer("Сколько тебе лет?")
    await state.set_state(Registration.age)


# ───────────────────────────────────────────────────────────────
# Шаг 2 — Возраст
# ───────────────────────────────────────────────────────────────

@router.message(Registration.age)
async def reg_age(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.isdigit() or not (18 <= int(text) <= 99):
        await message.answer("Введи возраст числом от 18 до 99:")
        return
    await state.update_data(age=int(text))
    await message.answer("Выбери свой пол:", reply_markup=kb_gender())
    await state.set_state(Registration.gender)


# ───────────────────────────────────────────────────────────────
# Шаг 3 — Пол
# ───────────────────────────────────────────────────────────────

@router.callback_query(Registration.gender, F.data.startswith("gender:"))
async def reg_gender(call: CallbackQuery, state: FSMContext):
    gender = call.data.split(":")[1]
    await state.update_data(gender=gender)
    await call.message.edit_text(
        "Кого ты ищешь?", reply_markup=kb_looking_for()
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
        "Напиши немного о себе (до 500 символов) или пропусти:",
        reply_markup=kb_skip(),
    )
    await state.set_state(Registration.bio)


# ───────────────────────────────────────────────────────────────
# Шаг 5 — Bio
# ───────────────────────────────────────────────────────────────

@router.message(Registration.bio)
async def reg_bio_text(message: Message, state: FSMContext):
    bio = message.text.strip() if message.text else ""
    if len(bio) > 500:
        await message.answer("Слишком длинно — не более 500 символов:")
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
        "📍 Поделись геолокацией — так мы покажем тебе людей рядом.\n"
        "Это необязательно, можно пропустить:",
        reply_markup=kb_location(),
    )
    await state.set_state(Registration.location)


# ───────────────────────────────────────────────────────────────
# Шаг 6 — Геолокация
# ───────────────────────────────────────────────────────────────

@router.message(Registration.location, F.location)
async def reg_location(message: Message, state: FSMContext):
    await state.update_data(
        latitude=message.location.latitude,
        longitude=message.location.longitude,
    )
    await message.answer("Геолокация сохранена ✅", reply_markup=remove_kb())
    await _ask_photos(message, state)


@router.message(Registration.location, F.text == "Пропустить")
async def reg_location_skip(message: Message, state: FSMContext):
    await state.update_data(latitude=None, longitude=None)
    await message.answer(
        "Без проблем, геолокация не указана.", reply_markup=remove_kb()
    )
    await _ask_photos(message, state)


async def _ask_photos(message: Message, state: FSMContext):
    await message.answer(
        "Загрузи до 5 фотографий для профиля.\n"
        "Отправляй по одной, когда закончишь — нажми «Готово»:",
        reply_markup=kb_done_photos(),
    )
    await state.update_data(photo_file_ids=[])
    await state.set_state(Registration.photos)


# ───────────────────────────────────────────────────────────────
# Шаг 7 — Фото
# ───────────────────────────────────────────────────────────────

@router.message(Registration.photos, F.photo)
async def reg_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos: list = data.get("photo_file_ids", [])

    if len(photos) >= 5:
        await message.answer("Максимум 5 фото. Нажми «Готово» чтобы завершить:")
        return

    # Берём наибольшее разрешение
    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photo_file_ids=photos)

    remaining = 5 - len(photos)
    if remaining > 0:
        await message.answer(
            f"Фото принято ({len(photos)}/5). Можешь загрузить ещё {remaining} или нажми «Готово»:",
            reply_markup=kb_done_photos(),
        )
    else:
        await message.answer(
            "Загружено 5 фото — это максимум. Нажми «Готово»:",
            reply_markup=kb_done_photos(),
        )


@router.callback_query(Registration.photos, F.data == "photos_done")
async def reg_photos_done(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    photo_file_ids: list = data.get("photo_file_ids", [])

    svc = ProfileService(session)
    user = await svc.register(
        user_id=call.from_user.id,
        username=call.from_user.username,
        name=data["name"],
        age=data["age"],
        gender=data["gender"],
        looking_for=data["looking_for"],
        bio=data.get("bio"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
    )

    for file_id in photo_file_ids:
        await svc.add_photo(user.id, file_id)

    await state.clear()
    await call.message.edit_text(
        f"🎉 Профиль создан, {data['name']}!\n\n"
        "Теперь ты можешь смотреть анкеты и находить людей:",
        reply_markup=kb_main_menu(),
    )
