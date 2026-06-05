from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import update, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User, GenderEnum, LookingForEnum, Like, Match
from bot.keyboards import kb_main_menu, kb_profile_actions, kb_match, kb_location, remove_kb
from bot.services import ProfileService, BrowseService
from bot.states import EditProfile
from db.repositories.user_repo import UserRepository

router = Router()

GENDER_MAP = {"male": "Мужской", "female": "Женский", "other": "Другой"}
LF_MAP     = {"male": "Парней",  "female": "Девушек", "any": "Всех"}

# ── Ранги ────────────────────────────────────────────────────────
_TIERS = [
    (3.0,  "sub3",     "🚫"),
    (5.0,  "sub5",     "📉"),
    (6.0,  "ltn",      "👤"),
    (7.0,  "mtn",      "📊"),
    (7.10, "htn",      "🌟"),
    (8.5,  "chadlite", "⚡"),
]
_CHAD = ("chad", "👑")


def get_tier(avg: float) -> tuple[str, str]:
    for threshold, slug, emoji in _TIERS:
        if avg < threshold:
            return slug, emoji
    return _CHAD


def tier_line(avg: float, count: int) -> str:
    if count == 0:
        return "🏷 <i>Ранг ещё не определён</i>"
    slug, emoji = get_tier(avg)
    return f"🏆 Ранг: <b>{emoji} {slug}</b>  <code>({avg:.1f}/10 · {count} голосов)</code>"


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

    lines = [
        f"👤 <b>{user.name}</b>, <code>{user.age}</code>",
        f"├─ Пол: <i>{GENDER_MAP.get(user.gender.value, user.gender.value)}</i>",
        f"├─ Ищу: <i>{LF_MAP.get(user.looking_for.value, user.looking_for.value)}</i>",
    ]
    if user.bio:
        lines.append(f"├─ 📝 <code>«{user.bio}»</code>")

    lines.append(
        "├─ 📍 <i>Геолокация указана</i>" if user.latitude is not None
        else "├─ 📍 <i>Геолокация не указана</i>"
    )
    lines.append(
        f"├─ Анкета: {'✅ <i>Активна</i>' if user.is_active else '🙈 <i>Скрыта</i>'}"
    )
    lines.append(tier_line(user.avg_rating, user.rating_count))
    lines.append(
        f"\n📊 <b>Статистика</b>\n"
        f"├─ ❤️ Лайков: <code>{likes_in.scalar()}</code>\n"
        f"├─ 💔 Дизлайков: <code>{dislikes_in.scalar()}</code>\n"
        f"└─ 💌 Мэтчей: <code>{matches_count.scalar()}</code>"
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
    await _safe_answer(
        call,
        "🌌 <b>Главное меню</b>\n└─ <i>Выбери действие:</i>",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )


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
        await call.message.answer_photo(
            photo=user.photos[0].file_id,
            caption=text,
            reply_markup=kb_profile_actions(),
            parse_mode="HTML",
        )
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
            "🎂 <b>Введи новый возраст</b> <code>(18–99)</code>:",
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
            "📸 <b>Отправь новые фото</b> <i>(старые будут заменены, до 5 шт.)</i>\n"
            "└─ Когда закончишь — нажми «Готово»:",
            parse_mode="HTML",
            reply_markup=_kb_done_photos(),
        )
        await state.set_state(EditProfile.new_photo)
        await state.update_data(new_photo_ids=[])


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
                "🔮 <b>Ошибка</b>\n└ <code>Имя от 1 до 64 символов:</code>",
                parse_mode="HTML",
            )
            return
        await session.execute(update(User).where(User.id == message.from_user.id).values(name=val))
        await session.commit()
        await message.answer(
            f"✅ <b>Имя изменено на «{val}»</b>",
            parse_mode="HTML",
            reply_markup=kb_main_menu(),
        )

    elif field == "age":
        txt = (message.text or "").strip()
        if not txt.isdigit() or not (18 <= int(txt) <= 99):
            await message.answer(
                "🔮 <b>Ошибка</b>\n└ <code>Возраст от 18 до 99:</code>",
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
                "🔮 <b>Слишком длинно</b>\n└ <code>Не более 500 символов:</code>",
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
async def collect_edit_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    ids: list = data.get("new_photo_ids", [])
    if len(ids) >= 5:
        await message.answer(
            "🔮 <b>Максимум 5 фото</b>\n└ <code>Нажми «Готово»:</code>",
            parse_mode="HTML",
            reply_markup=_kb_done_photos(),
        )
        return
    ids.append(message.photo[-1].file_id)
    await state.update_data(new_photo_ids=ids)
    await message.answer(
        f"✅ <b>Фото {len(ids)}/5 принято</b>",
        parse_mode="HTML",
        reply_markup=_kb_done_photos(),
    )


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
        f"✅ <b>Фото обновлены</b> <code>({len(ids)} шт.)</code>" if ids else "✅ <b>Фото удалены</b>",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )
    await call.answer()


# ── Скрыть / Показать / Удалить ──────────────────────────────────

@router.callback_query(F.data == "hide_profile")
async def hide_profile(call: CallbackQuery, session: AsyncSession):
    repo = UserRepository(session)
    user = await repo.get(call.from_user.id)
    if user and user.is_active:
        await repo.set_active(call.from_user.id, False)
        await session.commit()
        await call.answer("🙈 Анкета скрыта", show_alert=True)
    else:
        await call.answer("Анкета уже скрыта.")


@router.callback_query(F.data == "show_profile")
async def show_profile_handler(call: CallbackQuery, session: AsyncSession):
    repo = UserRepository(session)
    user = await repo.get(call.from_user.id)
    if user and not user.is_active:
        await repo.set_active(call.from_user.id, True)
        await session.commit()
        await call.answer("✅ Анкета снова видна", show_alert=True)
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
        "⚠️ <b>Удалить анкету?</b>\n\n"
        "<i>Все данные, фото, лайки и мэтчи будут удалены безвозвратно.</i>",
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
        "🗑 <b>Анкета удалена.</b>\n"
        "└ <i>Если захочешь вернуться — напиши /start.</i>",
        parse_mode="HTML",
    )


# ── Геолокация ───────────────────────────────────────────────────

@router.callback_query(F.data == "update_location")
async def ask_update_location(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer(
        "📍 <b>Поделись новой геолокацией</b> или пропусти:",
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
        "✅ <b>Геолокация обновлена</b>",
        parse_mode="HTML",
        reply_markup=remove_kb(),
    )
    await message.answer(
        "🌌 <b>Главное меню</b>",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )
