from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import update, select, func
from db.models import User, GenderEnum, LookingForEnum, Like, Match
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import kb_main_menu, kb_profile_actions, kb_match, kb_location, remove_kb
from bot.services import ProfileService, BrowseService
from bot.states import EditProfile
from db.repositories.user_repo import UserRepository

router = Router()

GENDER_MAP = {"male": "Мужской", "female": "Женский", "other": "Другой"}
LF_MAP     = {"male": "Парней",  "female": "Девушек", "any": "Всех"}


async def _profile_text(user: User, session) -> str:
    # Статистика
    likes_in = await session.execute(
        select(func.count()).where(Like.to_user == user.id, Like.value.is_(True))
    )
    matches_count = await session.execute(
        select(func.count()).select_from(Match).where(
            (Match.user1_id == user.id) | (Match.user2_id == user.id)
        )
    )
    dislikes_in = await session.execute(
        select(func.count()).where(Like.to_user == user.id, Like.value.is_(False))
    )

    lines = [
        f"<b>👤 {user.name}</b>, {user.age}",
        f"Пол: {GENDER_MAP.get(user.gender.value, user.gender.value)}",
        f"Ищу: {LF_MAP.get(user.looking_for.value, user.looking_for.value)}",
    ]
    if user.bio:
        lines.append(f"\n{user.bio}")
    lines.append("\n📍 Геолокация указана" if user.latitude is not None else "\n📍 Геолокация не указана")
    lines.append(f"Анкета: {'✅ Активна' if user.is_active else '🙈 Скрыта'}")
    lines.append(
        f"\n📊 Статистика:"
        f"\n  ❤️ Лайков получено: {likes_in.scalar()}"
        f"\n  💔 Дизлайков: {dislikes_in.scalar()}"
        f"\n  💌 Мэтчей: {matches_count.scalar()}"
    )
    return "\n".join(lines)


async def _safe_answer(call: CallbackQuery, text: str, **kwargs):
    try:
        await call.message.edit_text(text, **kwargs)
    except Exception:
        await call.message.answer(text, **kwargs)


def _kb_done_photos():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Готово", callback_data="edit_photos_done")
    return builder.as_markup()


# ───────────────────────────────────────────────────────────────
# Главное меню
# ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu")
async def show_menu(call: CallbackQuery):
    await call.answer()
    await _safe_answer(call, "Главное меню:", reply_markup=kb_main_menu())


# ───────────────────────────────────────────────────────────────
# Мой профиль
# ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "my_profile")
async def show_my_profile(call: CallbackQuery, session: AsyncSession):
    repo = UserRepository(session)
    user = await repo.get(call.from_user.id)
    if user is None:
        await call.answer("Сначала зарегистрируйся — /start", show_alert=True)
        return
    await call.answer()
    text = await _profile_text(user, session)
    if user.photos:
        await call.message.answer_photo(photo=user.photos[0].file_id, caption=text,
                                        reply_markup=kb_profile_actions(), parse_mode="HTML")
    else:
        await call.message.answer(text, reply_markup=kb_profile_actions(), parse_mode="HTML")


# ───────────────────────────────────────────────────────────────
# Редактировать профиль
# ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "edit_profile")
async def edit_profile_menu(call: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Имя",        callback_data="edit:name")
    builder.button(text="🎂 Возраст",    callback_data="edit:age")
    builder.button(text="⚧ Пол",        callback_data="edit:gender")
    builder.button(text="🔍 Кого ищу",  callback_data="edit:looking_for")
    builder.button(text="💬 О себе",     callback_data="edit:bio")
    builder.button(text="📍 Геолокация", callback_data="update_location")
    builder.button(text="🖼 Фото",       callback_data="edit:photos")
    builder.button(text="◀️ Назад",      callback_data="my_profile")
    builder.adjust(2)
    await call.answer()
    await call.message.answer("Что хочешь изменить?", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("edit:"))
async def edit_field_start(call: CallbackQuery, state: FSMContext):
    field = call.data.split(":")[1]
    await call.answer()

    if field == "name":
        await call.message.answer("Введи новое имя:")
        await state.set_state(EditProfile.new_value)
        await state.update_data(edit_field="name")

    elif field == "age":
        await call.message.answer("Введи новый возраст (18–99):")
        await state.set_state(EditProfile.new_value)
        await state.update_data(edit_field="age")

    elif field == "bio":
        await call.message.answer("Напиши новый текст о себе (до 500 символов):")
        await state.set_state(EditProfile.new_value)
        await state.update_data(edit_field="bio")

    elif field == "gender":
        builder = InlineKeyboardBuilder()
        builder.button(text="Мужской", callback_data="set_gender:male")
        builder.button(text="Женский", callback_data="set_gender:female")
        builder.button(text="Другой",  callback_data="set_gender:other")
        builder.adjust(2, 1)
        await call.message.answer("Выбери новый пол:", reply_markup=builder.as_markup())

    elif field == "looking_for":
        builder = InlineKeyboardBuilder()
        builder.button(text="Парней",  callback_data="set_lf:male")
        builder.button(text="Девушек", callback_data="set_lf:female")
        builder.button(text="Всех",    callback_data="set_lf:any")
        builder.adjust(2, 1)
        await call.message.answer("Кого ищешь?", reply_markup=builder.as_markup())

    elif field == "photos":
        await call.message.answer(
            "Отправь новые фото (старые будут заменены, до 5 шт.).\nКогда закончишь — нажми «Готово»:",
            reply_markup=_kb_done_photos(),
        )
        await state.set_state(EditProfile.new_photo)
        await state.update_data(new_photo_ids=[])


# Смена пола
@router.callback_query(F.data.startswith("set_gender:"))
async def set_gender(call: CallbackQuery, session: AsyncSession):
    val = call.data.split(":")[1]
    await session.execute(update(User).where(User.id == call.from_user.id).values(gender=GenderEnum(val)))
    await session.commit()
    await call.answer(f"Пол изменён на «{GENDER_MAP[val]}» ✅", show_alert=True)
    await call.message.answer("Главное меню:", reply_markup=kb_main_menu())


# Смена «кого ищу»
@router.callback_query(F.data.startswith("set_lf:"))
async def set_looking_for(call: CallbackQuery, session: AsyncSession):
    val = call.data.split(":")[1]
    await session.execute(update(User).where(User.id == call.from_user.id).values(looking_for=LookingForEnum(val)))
    await session.commit()
    await call.answer(f"Теперь ищешь: {LF_MAP[val]} ✅", show_alert=True)
    await call.message.answer("Главное меню:", reply_markup=kb_main_menu())


# Применение текстовых правок
@router.message(EditProfile.new_value)
async def apply_edit_value(message: Message, state: FSMContext, session: AsyncSession):
    data  = await state.get_data()
    field = data.get("edit_field")

    if field == "name":
        val = (message.text or "").strip()
        if not val or len(val) > 64:
            await message.answer("Имя от 1 до 64 символов:")
            return
        await session.execute(update(User).where(User.id == message.from_user.id).values(name=val))
        await session.commit()
        await message.answer(f"✅ Имя изменено на «{val}»", reply_markup=kb_main_menu())

    elif field == "age":
        txt = (message.text or "").strip()
        if not txt.isdigit() or not (18 <= int(txt) <= 99):
            await message.answer("Возраст числом от 18 до 99:")
            return
        await session.execute(update(User).where(User.id == message.from_user.id).values(age=int(txt)))
        await session.commit()
        await message.answer(f"✅ Возраст изменён на {txt}", reply_markup=kb_main_menu())

    elif field == "bio":
        val = (message.text or "").strip()
        if len(val) > 500:
            await message.answer("Не более 500 символов:")
            return
        await session.execute(update(User).where(User.id == message.from_user.id).values(bio=val or None))
        await session.commit()
        await message.answer("✅ Описание обновлено", reply_markup=kb_main_menu())

    elif field == "location":
        # обрабатывается отдельным хэндлером F.location
        return

    await state.clear()


# ───────────────────────────────────────────────────────────────
# Редактирование фото
# ───────────────────────────────────────────────────────────────

@router.message(EditProfile.new_photo, F.photo)
async def collect_edit_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    ids: list = data.get("new_photo_ids", [])
    if len(ids) >= 5:
        await message.answer("Максимум 5 фото. Нажми «Готово»:", reply_markup=_kb_done_photos())
        return
    ids.append(message.photo[-1].file_id)
    await state.update_data(new_photo_ids=ids)
    await message.answer(f"Фото {len(ids)}/5 принято.", reply_markup=_kb_done_photos())


@router.callback_query(EditProfile.new_photo, F.data == "edit_photos_done")
async def save_edit_photos(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    ids: list = data.get("new_photo_ids", [])
    repo = UserRepository(session)
    await repo.delete_photos(call.from_user.id)
    for file_id in ids:
        await repo.add_photo(call.from_user.id, file_id)
    await session.commit()
    await state.clear()
    await call.message.answer(
        f"✅ Фото обновлены ({len(ids)} шт.)" if ids else "✅ Фото удалены",
        reply_markup=kb_main_menu(),
    )
    await call.answer()


# ───────────────────────────────────────────────────────────────
# Скрыть / показать анкету
# ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "hide_profile")
async def hide_profile(call: CallbackQuery, session: AsyncSession):
    repo = UserRepository(session)
    user = await repo.get(call.from_user.id)
    if user and user.is_active:
        await repo.set_active(call.from_user.id, False)
        await session.commit()
        await call.answer("Анкета скрыта 🙈", show_alert=True)
    else:
        await call.answer("Анкета уже скрыта.")


@router.callback_query(F.data == "show_profile")
async def show_profile_handler(call: CallbackQuery, session: AsyncSession):
    repo = UserRepository(session)
    user = await repo.get(call.from_user.id)
    if user and not user.is_active:
        await repo.set_active(call.from_user.id, True)
        await session.commit()
        await call.answer("Анкета снова видна ✅", show_alert=True)
    else:
        await call.answer("Анкета уже активна.")


# ───────────────────────────────────────────────────────────────
# Удалить анкету
# ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "delete_profile")
async def confirm_delete(call: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Да, удалить",  callback_data="delete_confirmed")
    builder.button(text="◀️ Отмена",       callback_data="my_profile")
    builder.adjust(1)
    await call.answer()
    await call.message.answer(
        "⚠️ <b>Удалить анкету?</b>\n\nВсе данные, фото, лайки и мэтчи будут удалены безвозвратно.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "delete_confirmed")
async def delete_profile(call: CallbackQuery, session: AsyncSession, state: FSMContext):
    repo = UserRepository(session)
    await repo.delete(call.from_user.id)
    await session.commit()
    await state.clear()
    await call.answer()
    await call.message.answer(
        "🗑 Анкета удалена. Если захочешь вернуться — просто напиши /start."
    )


# ───────────────────────────────────────────────────────────────
# Обновить геолокацию
# ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "update_location")
async def ask_update_location(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("📍 Поделись новой геолокацией или пропусти:", reply_markup=kb_location())
    await state.set_state(EditProfile.new_value)
    await state.update_data(edit_field="location")


@router.message(F.location)
async def receive_location_update(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    if data.get("edit_field") == "location":
        svc = ProfileService(session)
        await svc.update_location(message.from_user.id, message.location.latitude, message.location.longitude)
        await state.clear()
        await message.answer("📍 Геолокация обновлена!", reply_markup=remove_kb())
        await message.answer("Главное меню:", reply_markup=kb_main_menu())


@router.message(F.text == "Пропустить")
async def skip_location_update(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("edit_field") == "location":
        await state.clear()
        await message.answer("Без изменений.", reply_markup=remove_kb())
        await message.answer("Главное меню:", reply_markup=kb_main_menu())
