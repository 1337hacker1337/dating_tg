from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import update, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User, GenderEnum, LookingForEnum, Like, Match
from bot.keyboards import kb_main_menu, kb_profile_actions, kb_match, kb_location, remove_kb
from bot.services import ProfileService, BrowseService
from bot.rating import format_rating_line
from bot.states import EditProfile
from db.repositories.user_repo import UserRepository

router = Router()

GENDER_MAP = {"male": "Мужской", "female": "Женский", "other": "Другой"}
LF_MAP     = {"male": "Парней",  "female": "Девушек", "any": "Всех"}

# ── Текст профиля ────────────────────────────────────────────────
async def _profile_text(user: User, session) -> str:
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

    status = "✅ активна" if user.is_active else "🙈 скрыта"
    geo    = "🗺️ указана" if user.latitude is not None else "🗺️ не указана"

    lines = [
        f"🕯️ <b>{user.name}</b>, <code>{user.age}</code>",
        f"├ {GENDER_MAP.get(user.gender.value, '—')} · ищу: {LF_MAP.get(user.looking_for.value, '—')}",
        f"├ Анкета: <i>{status}</i> · {geo}",
    ]
    if user.bio:
        lines.append(f"├ 📜 <i>{user.bio}</i>")

    lines.append(format_rating_line(user.avg_rating, user.rating_count))
    lines.append(
        f"\n📊 <b>Стата</b>\n"
        f"├ 🩸 Лайков: <code>{likes_in.scalar()}</code>\n"
        f"├ ⚰️ Дизлайков: <code>{dislikes_in.scalar()}</code>\n"
        f"└ ⚔️ Мэтчей: <code>{matches_count.scalar()}</code>"
    )
    return "\n".join(lines)


async def _safe_answer(call: CallbackQuery, text: str, **kwargs):
    try:
        await call.message.edit_text(text, **kwargs)
    except Exception:
        await call.message.answer(text, **kwargs)




# ───────────────────────────────────────────────────────────────
# Главное меню
# ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu")
async def show_menu(call: CallbackQuery):
    await call.answer()
    await call.message.answer(
        "🌌 <b>Грибница.</b>\n└ <i>Выбери действие в меню ниже.</i>",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )


# ───────────────────────────────────────────────────────────────
# Мой профиль
# ───────────────────────────────────────────────────────────────

@router.message(F.text == "👁️ Профиль")
async def show_my_profile_msg(message: Message, session: AsyncSession):
    await _send_profile(message.from_user.id, message, session)


@router.callback_query(F.data == "my_profile")
async def show_my_profile(call: CallbackQuery, session: AsyncSession):
    await call.answer()
    await _send_profile(call.from_user.id, call.message, session)


async def _send_profile(user_id: int, msg, session: AsyncSession):
    repo = UserRepository(session)
    user = await repo.get(user_id)
    if user is None:
        await msg.answer("⚠️ Сначала создай анкету — /start")
        return
    text = await _profile_text(user, session)
    if user.photos:
        await msg.answer_photo(
            photo=user.photos[0].file_id,
            caption=text,
            reply_markup=kb_profile_actions(),
            parse_mode="HTML",
        )
    else:
        await msg.answer(text, reply_markup=kb_profile_actions(), parse_mode="HTML")


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
    builder.button(text="🗺️ Геолокация", callback_data="update_location")
    builder.button(text="🖼 Фото",       callback_data="edit:photos")
    builder.button(text="◀️ Назад",      callback_data="my_profile")
    builder.adjust(2)
    await call.answer()
    await call.message.answer(
        "✏️ <b>Что хочешь изменить?</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("edit:"))
async def edit_field_start(call: CallbackQuery, state: FSMContext):
    field = call.data.split(":")[1]
    await call.answer()

    if field == "name":
        await call.message.answer(
            "📝 <b>Введи новое имя:</b>",
            parse_mode="HTML",
        )
        await state.set_state(EditProfile.new_value)
        await state.update_data(edit_field="name")

    elif field == "age":
        await call.message.answer(
            "🎂 <b>Введи новый возраст</b> <code>(1–99)</code>:",
            parse_mode="HTML",
        )
        await state.set_state(EditProfile.new_value)
        await state.update_data(edit_field="age")

    elif field == "bio":
        await call.message.answer(
            "💬 <b>Напиши новое «О себе»</b> <i>(до 500 символов)</i>:",
            parse_mode="HTML",
        )
        await state.set_state(EditProfile.new_value)
        await state.update_data(edit_field="bio")

    elif field == "gender":
        builder = InlineKeyboardBuilder()
        builder.button(text="Мужской", callback_data="set_gender:male")
        builder.button(text="Женский", callback_data="set_gender:female")
        builder.button(text="Другой",  callback_data="set_gender:other")
        builder.adjust(2, 1)
        await call.message.answer(
            "⚧ <b>Выбери новый пол:</b>",
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )

    elif field == "looking_for":
        builder = InlineKeyboardBuilder()
        builder.button(text="Парней",  callback_data="set_lf:male")
        builder.button(text="Девушек", callback_data="set_lf:female")
        builder.button(text="Всех",    callback_data="set_lf:any")
        builder.adjust(2, 1)
        await call.message.answer(
            "🔍 <b>Кого ищешь?</b>",
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )

    elif field == "photos":
        await call.message.answer(
            "📸 <b>Отправь новое фото</b> <i>(заменит текущее)</i>:",
            parse_mode="HTML",
        )
        await state.set_state(EditProfile.new_photo)


@router.callback_query(F.data.startswith("set_gender:"))
async def set_gender(call: CallbackQuery, session: AsyncSession):
    val = call.data.split(":")[1]
    await session.execute(
        update(User).where(User.id == call.from_user.id).values(gender=GenderEnum(val))
    )
    await session.commit()
    await call.answer(f"✅ Пол изменён на «{GENDER_MAP[val]}»", show_alert=True)
    await call.message.answer(
        "🌌 <b>Главное меню</b>",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )


@router.callback_query(F.data.startswith("set_lf:"))
async def set_looking_for(call: CallbackQuery, session: AsyncSession):
    val = call.data.split(":")[1]
    await session.execute(
        update(User).where(User.id == call.from_user.id).values(looking_for=LookingForEnum(val))
    )
    await session.commit()
    await call.answer(f"✅ Теперь ищешь: {LF_MAP[val]}", show_alert=True)
    await call.message.answer(
        "🌌 <b>Главное меню</b>",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )


@router.message(EditProfile.new_value)
async def apply_edit_value(message: Message, state: FSMContext, session: AsyncSession):
    data  = await state.get_data()
    field = data.get("edit_field")

    if field == "name":
        val = (message.text or "").strip()
        if not val or len(val) > 64:
            await message.answer(
                "⚠️ <b>Нарушение ритуала</b>\n└ <i>Имя от 1 до 64 символов:</i>",
                parse_mode="HTML",
            )
            return
        await session.execute(update(User).where(User.id == message.from_user.id).values(name=val))
        await session.commit()
        await message.answer(
            f"🕯️ <b>Имя изменено на «{val}»</b>",
            parse_mode="HTML",
            reply_markup=kb_main_menu(),
        )

    elif field == "age":
        txt = (message.text or "").strip()
        if not txt.isdigit() or not (1 <= int(txt) <= 99):
            await message.answer(
                "⚠️ <b>Нарушение ритуала</b>\n└ <i>Возраст от 1 до 99:</i>",
                parse_mode="HTML",
            )
            return
        await session.execute(update(User).where(User.id == message.from_user.id).values(age=int(txt)))
        await session.commit()
        await message.answer(
            f"✅ <b>Возраст изменён на {txt}</b>",
            parse_mode="HTML",
            reply_markup=kb_main_menu(),
        )

    elif field == "bio":
        val = (message.text or "").strip()
        if len(val) > 500:
            await message.answer(
                "⚠️ <b>Слишком длинно</b>\n└ <i>Не более 500 символов:</i>",
                parse_mode="HTML",
            )
            return
        await session.execute(
            update(User).where(User.id == message.from_user.id).values(bio=val or None)
        )
        await session.commit()
        await message.answer(
            "✅ <b>Описание обновлено</b>",
            parse_mode="HTML",
            reply_markup=kb_main_menu(),
        )

    await state.clear()


# ── Редактирование фото ──────────────────────────────────────────

@router.message(EditProfile.new_photo, F.photo)
async def collect_edit_photo(message: Message, state: FSMContext, session: AsyncSession):
    file_id = message.photo[-1].file_id
    repo = UserRepository(session)
    await repo.delete_photos(message.from_user.id)
    await repo.add_photo(message.from_user.id, file_id)
    await session.commit()
    await state.clear()
    await message.answer(
        "🕯️ <b>Фото обновлено.</b>",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )


# ── Скрыть / Показать / Удалить ──────────────────────────────────

@router.callback_query(F.data == "hide_profile")
async def hide_profile(call: CallbackQuery, session: AsyncSession):
    repo = UserRepository(session)
    user = await repo.get(call.from_user.id)
    if user and user.is_active:
        await repo.set_active(call.from_user.id, False)
        await session.commit()
        await call.answer("🙈 Анкета скрыта — ты вне системы.", show_alert=True)
    else:
        await call.answer("Анкета уже скрыта.")


@router.callback_query(F.data == "show_profile")
async def show_profile_handler(call: CallbackQuery, session: AsyncSession):
    repo = UserRepository(session)
    user = await repo.get(call.from_user.id)
    if user and not user.is_active:
        await repo.set_active(call.from_user.id, True)
        await session.commit()
        await call.answer("👁 Анкета активирована — ты в системе.", show_alert=True)
    else:
        await call.answer("Анкета уже активна.")


@router.callback_query(F.data == "delete_profile")
async def confirm_delete(call: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Да, удалить", callback_data="delete_confirmed")
    builder.button(text="◀️ Отмена",      callback_data="my_profile")
    builder.adjust(1)
    await call.answer()
    await call.message.answer(
        "⚰️ <b>Удалить анкету?</b>\n\n"
        "<i>Все данные, фото, лайки и мэтчи будут уничтожены. Это необратимо.</i>",
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
        "⚰️ <b>Анкета уничтожена.</b>\n"
        "└ <i>Если захочешь вернуться — /start.</i>",
        parse_mode="HTML",
    )


# ── Геолокация ───────────────────────────────────────────────────

@router.callback_query(F.data == "update_location")
async def ask_update_location(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await _ask_location_prompt(call.message, state)


async def _ask_location_prompt(message: Message, state: FSMContext):
    await message.answer(
        "🗺️ <b>Обнови геолокацию</b> — или пропусти:",
        parse_mode="HTML",
        reply_markup=kb_location(),
    )
    await state.set_state(EditProfile.new_value)
    await state.update_data(edit_field="location")


@router.message(EditProfile.new_value, F.location)
async def save_new_location(message: Message, state: FSMContext, session: AsyncSession):
    svc = ProfileService(session)
    await svc.update_location(
        message.from_user.id,
        message.location.latitude,
        message.location.longitude,
    )
    await state.clear()
    await message.answer(
        "🗺️ <b>Геолокация обновлена.</b>",
        parse_mode="HTML",
        reply_markup=remove_kb(),
    )
    await message.answer(
        "🌌 <b>Главное меню</b>",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )
