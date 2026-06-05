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

_ERR_PHOTO = (
    "🔮 <b>Ошибка авторизации в грибнице</b>\n"
    "└ <code>Для калибровки профиля необходим визуальный слепок анкеты.</code>\n\n"
    "📸 <i>Пожалуйста, отправь ОДНО качественное фото своего лица...</i>"
)


# ───────────────────────────────────────────────────────────────
# /start
# ───────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession, db_user=None):
    repo = UserRepository(session)
    if await repo.exists(message.from_user.id):
        await state.clear()
        await message.answer(
            "🌌 <b>С возвращением в грибницу!</b>\n"
            "└─ <i>Выбери действие:</i>",
            parse_mode="HTML",
            reply_markup=kb_main_menu(),
        )
        return

    await message.answer(
        "🌌 <b>Добро пожаловать в shroom</b>\n"
        "├─ Найди свою половинку в грибнице\n"
        "└─ Начнём создание профиля!\n\n"
        "📝 <i>Как тебя зовут?</i> — до <code>16</code> символов",
        parse_mode="HTML",
    )
    await state.set_state(Registration.name)


# ───────────────────────────────────────────────────────────────
# Шаг 1 — Имя (лимит 16 символов)
# ───────────────────────────────────────────────────────────────

@router.message(Registration.name)
async def reg_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer(
            "🔮 <b>Ошибка</b>\n"
            "└ <code>Имя не может быть пустым. Попробуй ещё раз:</code>",
            parse_mode="HTML",
        )
        return
    if len(name) > 16:
        await message.answer(
            f"🔮 <b>Слишком длинно</b> — <code>{len(name)}/16</code> символов\n"
            "└ <i>Укороти имя и попробуй снова:</i>",
            parse_mode="HTML",
        )
        return
    await state.update_data(name=name)
    await message.answer(
        f"✅ <b>{name}</b> — принято.\n\n"
        "🎂 <i>Сколько тебе лет?</i> <code>(18–99)</code>",
        parse_mode="HTML",
    )
    await state.set_state(Registration.age)


# ───────────────────────────────────────────────────────────────
# Шаг 2 — Возраст
# ───────────────────────────────────────────────────────────────

@router.message(Registration.age)
async def reg_age(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.isdigit() or not (18 <= int(text) <= 99):
        await message.answer(
            "🔮 <b>Ошибка</b>\n"
            "└ <code>Введи возраст числом от 18 до 99:</code>",
            parse_mode="HTML",
        )
        return
    await state.update_data(age=int(text))
    await message.answer(
        "⚧ <b>Выбери свой пол:</b>",
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
        "🔍 <b>Кого ты ищешь?</b>",
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
        "💬 <b>Расскажи о себе</b>\n"
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
            "🔮 <b>Слишком длинно</b>\n"
            "└ <code>Не более 500 символов. Попробуй ещё раз:</code>",
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
        "📍 <b>Геолокация</b>\n"
        "├─ <i>Поделись — покажем людей рядом.</i>\n"
        "└─ <i>Необязательно, можно пропустить.</i>",
        parse_mode="HTML",
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
    await message.answer(
        "✅ <b>Геолокация сохранена</b>",
        parse_mode="HTML",
        reply_markup=remove_kb(),
    )
    await _ask_photos(message, state)


@router.message(Registration.location, F.text == "Пропустить")
async def reg_location_skip(message: Message, state: FSMContext):
    await state.update_data(latitude=None, longitude=None)
    await message.answer(
        "📍 <b>Без геолокации</b> — окей.\n"
        "└ <i>Можно добавить позже в профиле.</i>",
        parse_mode="HTML",
        reply_markup=remove_kb(),
    )
    await _ask_photos(message, state)


async def _ask_photos(message: Message, state: FSMContext):
    await message.answer(
        "📸 <b>Фотографии профиля</b>\n"
        "├─ <i>Загрузи до</i> <code>5</code> <i>фото — отправляй по одной.</i>\n"
        "└─ <i>Когда закончишь — нажми «Готово»:</i>",
        parse_mode="HTML",
        reply_markup=kb_done_photos(),
    )
    await state.update_data(photo_file_ids=[])
    await state.set_state(Registration.photos)


# ───────────────────────────────────────────────────────────────
# Шаг 7 — Фото (валидный ввод)
# ───────────────────────────────────────────────────────────────

@router.message(Registration.photos, F.photo)
async def reg_photo(message: Message, state: FSMContext):
    data   = await state.get_data()
    photos: list = data.get("photo_file_ids", [])

    if len(photos) >= 5:
        await message.answer(
            "🔮 <b>Максимум 5 фото</b>\n"
            "└ <code>Нажми «Готово» для завершения:</code>",
            parse_mode="HTML",
            reply_markup=kb_done_photos(),
        )
        return

    photos.append(message.photo[-1].file_id)
    await state.update_data(photo_file_ids=photos)
    remaining = 5 - len(photos)

    await message.answer(
        f"✅ <b>Фото принято</b> — <code>{len(photos)}/5</code>\n"
        + (f"└ <i>Можешь загрузить ещё {remaining} или нажми «Готово»</i>"
           if remaining else "└ <i>Это максимум. Нажми «Готово»</i>"),
        parse_mode="HTML",
        reply_markup=kb_done_photos(),
    )


# ───────────────────────────────────────────────────────────────
# Шаг 7 — БЛОКИРОВКА невалидного ввода на этапе фото
# Регистрируется ПОСЛЕ F.photo — работает как catch-all
# ───────────────────────────────────────────────────────────────

@router.message(Registration.photos)
async def reg_photo_invalid(message: Message):
    await message.answer(_ERR_PHOTO, parse_mode="HTML")


# ───────────────────────────────────────────────────────────────
# Завершение регистрации
# ───────────────────────────────────────────────────────────────

@router.callback_query(Registration.photos, F.data == "photos_done")
async def reg_photos_done(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    data           = await state.get_data()
    photo_file_ids: list = data.get("photo_file_ids", [])

    svc  = ProfileService(session)
    user = await svc.register(
        user_id    =call.from_user.id,
        username   =call.from_user.username,
        name       =data["name"],
        age        =data["age"],
        gender     =data["gender"],
        looking_for=data["looking_for"],
        bio        =data.get("bio"),
        latitude   =data.get("latitude"),
        longitude  =data.get("longitude"),
    )

    for file_id in photo_file_ids:
        await svc.add_photo(user.id, file_id)

    await state.clear()
    await call.message.edit_text(
        f"🌌 <b>Профиль создан, {data['name']}!</b>\n\n"
        "🍄 <b>Грибница ждёт — начинай искать!</b>",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )