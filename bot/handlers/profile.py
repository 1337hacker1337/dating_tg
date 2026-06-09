from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User, GenderEnum, LookingForEnum
from bot.keyboards import kb_main_menu, kb_profile_actions, kb_location, remove_kb
from bot.services import ProfileService
from bot import logger as log
from bot.rating import format_rating_line
from bot.states import EditProfile
from db.repositories.user_repo import UserRepository

_log = log.get(__name__)
router = Router()

async def _profile_text(user, session) -> str:
    repo = UserRepository(session)
    stats = await repo.get_profile_stats(user.id)
    lines = [f"<b>{user.name}</b>, {user.age}"]
    if user.bio: lines += ["", f"<i>{user.bio}</i>"]
    lines += ["", format_rating_line(user.avg_rating, user.rating_count), "",
              f"🩸 <code>{stats['likes']}</code>  ·  🤮 <code>{stats['dislikes']}</code>  ·  ⚔️ <code>{stats['matches']}</code>"]
    warnings = []
    if not user.is_active: warnings.append("скрыта")
    if user.latitude is None: warnings.append("гео не указана")
    if warnings: lines += ["", "  ·  ".join(warnings)]
    return "\n".join(lines)

@router.callback_query(F.data == "menu")
async def show_menu(call: CallbackQuery):
    await call.answer(); await call.message.answer("·", reply_markup=kb_main_menu())

@router.message(F.text.in_({"👁️ профиль", "👁️ Профиль"}))
async def show_my_profile_msg(message: Message, session):
    await _send_profile(message.from_user.id, message, session)

@router.callback_query(F.data == "my_profile")
async def show_my_profile(call: CallbackQuery, session):
    await call.answer(); await _send_profile(call.from_user.id, call.message, session)

async def _send_profile(user_id, msg, session):
    repo = UserRepository(session)
    user = await repo.get(user_id)
    if user is None: await msg.answer("анкеты нет.\n\n/start"); return
    text = await _profile_text(user, session)
    if user.photos:
        await msg.answer_photo(photo=user.photos[0].file_id, caption=text, reply_markup=kb_profile_actions(), parse_mode="HTML")
    else:
        await msg.answer(text, reply_markup=kb_profile_actions(), parse_mode="HTML")

@router.callback_query(F.data == "edit_profile")
async def edit_profile_menu(call: CallbackQuery):
    b = InlineKeyboardBuilder()
    for text, cd in [("имя","edit:name"),("возраст","edit:age"),("пол","edit:gender"),
                     ("ищу","edit:looking_for"),("о себе","edit:bio"),("геолокация","update_location"),
                     ("фото","edit:photos"),("◀️ назад","my_profile")]:
        b.button(text=text, callback_data=cd)
    b.adjust(2)
    await call.answer(); await call.message.answer("что менять —", reply_markup=b.as_markup())

@router.callback_query(F.data.startswith("edit:"))
async def edit_field_start(call: CallbackQuery, state: FSMContext):
    field = call.data.split(":")[1]; await call.answer()
    if field == "name":
        await call.message.answer("имя —", parse_mode="HTML")
        await state.set_state(EditProfile.new_value); await state.update_data(edit_field="name")
    elif field == "age":
        await call.message.answer("возраст.  <code>14–99</code>", parse_mode="HTML")
        await state.set_state(EditProfile.new_value); await state.update_data(edit_field="age")
    elif field == "bio":
        await call.message.answer("о себе.  <i>до 500</i>", parse_mode="HTML")
        await state.set_state(EditProfile.new_value); await state.update_data(edit_field="bio")
    elif field == "gender":
        b = InlineKeyboardBuilder()
        b.button(text="парень", callback_data="set_gender:male")
        b.button(text="девушка", callback_data="set_gender:female")
        b.button(text="что-то другое", callback_data="set_gender:other")
        b.adjust(2, 1); await call.message.answer("пол —", parse_mode="HTML", reply_markup=b.as_markup())
    elif field == "looking_for":
        b = InlineKeyboardBuilder()
        b.button(text="парней", callback_data="set_lf:male")
        b.button(text="девушек", callback_data="set_lf:female")
        b.button(text="всех", callback_data="set_lf:any")
        b.adjust(2, 1); await call.message.answer("ищешь —", parse_mode="HTML", reply_markup=b.as_markup())
    elif field == "photos":
        await call.message.answer("фото.  <i>заменит текущее</i>", parse_mode="HTML")
        await state.set_state(EditProfile.new_photo)

@router.callback_query(F.data.startswith("set_gender:"))
async def set_gender(call: CallbackQuery, session):
    val = call.data.split(":")[1]
    await session.execute(update(User).where(User.id == call.from_user.id).values(gender=GenderEnum(val)))
    await session.commit(); await call.answer("сохранено.", show_alert=True)
    await call.message.answer("·", reply_markup=kb_main_menu())

@router.callback_query(F.data.startswith("set_lf:"))
async def set_looking_for(call: CallbackQuery, session):
    val = call.data.split(":")[1]
    await session.execute(update(User).where(User.id == call.from_user.id).values(looking_for=LookingForEnum(val)))
    await session.commit(); await call.answer("сохранено.", show_alert=True)
    await call.message.answer("·", reply_markup=kb_main_menu())

@router.message(EditProfile.new_value)
async def apply_edit_value(message: Message, state: FSMContext, session):
    data = await state.get_data(); field = data.get("edit_field")
    if field == "name":
        val = (message.text or "").strip()
        if not val or len(val) > 64: await message.answer("↑ 1–64 символа."); return
        await session.execute(update(User).where(User.id == message.from_user.id).values(name=val))
        await session.commit(); await message.answer(f"имя → {val}", reply_markup=kb_main_menu())
    elif field == "age":
        txt = (message.text or "").strip()
        if not txt.isdecimal() or not (14 <= int(txt) <= 99): await message.answer("↑ 14–99."); return
        await session.execute(update(User).where(User.id == message.from_user.id).values(age=int(txt)))
        await session.commit(); await message.answer(f"возраст → {txt}", reply_markup=kb_main_menu())
    elif field == "bio":
        val = (message.text or "").strip()
        if not val: await message.answer("↑ не может быть пустым."); return
        if len(val) > 500: await message.answer("↑ не более 500."); return
        await session.execute(update(User).where(User.id == message.from_user.id).values(bio=val))
        await session.commit(); await message.answer("о себе → ok", reply_markup=kb_main_menu())
    elif field == "location":
        if (message.text or "").strip() == "→ пропустить":
            await state.clear(); await message.answer("без изменений.", reply_markup=remove_kb())
            await message.answer("·", reply_markup=kb_main_menu()); return
        await message.answer("📡  нажми «📍 поделиться геолокацией» или «→ пропустить».", reply_markup=kb_location()); return
    await state.clear()

@router.message(EditProfile.new_photo, F.photo)
async def collect_edit_photo(message: Message, state: FSMContext, session):
    file_id = message.photo[-1].file_id; repo = UserRepository(session)
    await repo.delete_photos(message.from_user.id); await repo.add_photo(message.from_user.id, file_id)
    await session.commit(); await state.clear(); await message.answer("фото → ok", reply_markup=kb_main_menu())

@router.callback_query(F.data == "hide_profile")
async def hide_profile(call: CallbackQuery, session):
    repo = UserRepository(session); user = await repo.get_light(call.from_user.id)
    if user and user.is_active:
        await repo.set_active(call.from_user.id, False); await session.commit(); await call.answer("скрыта.", show_alert=True)
    else: await call.answer("уже скрыта.")

@router.callback_query(F.data == "show_profile")
async def show_profile_handler(call: CallbackQuery, session):
    repo = UserRepository(session); user = await repo.get_light(call.from_user.id)
    if user and not user.is_active:
        await repo.set_active(call.from_user.id, True); await session.commit(); await call.answer("активирована.", show_alert=True)
    else: await call.answer("уже активна.")

@router.callback_query(F.data == "delete_profile")
async def confirm_delete(call: CallbackQuery):
    b = InlineKeyboardBuilder()
    b.button(text="удалить", callback_data="delete_confirmed")
    b.button(text="отмена", callback_data="my_profile")
    b.adjust(2); await call.answer()
    await call.message.answer("удалить?\n\n<i>без возврата.</i>", reply_markup=b.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "delete_confirmed")
async def delete_profile(call: CallbackQuery, session, state: FSMContext):
    await UserRepository(session).delete(call.from_user.id); await session.commit(); await state.clear()
    _log.user("delete_profile: user=%s", call.from_user.id); await call.answer()
    await call.message.answer("удалено.\n\n<i>/start — если передумаешь.</i>", parse_mode="HTML")

@router.callback_query(F.data == "update_location")
async def ask_update_location(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("📡  геолокация.", parse_mode="HTML", reply_markup=kb_location())
    await state.set_state(EditProfile.new_value); await state.update_data(edit_field="location")

@router.message(EditProfile.new_value, F.location)
async def save_new_location(message: Message, state: FSMContext, session):
    svc = ProfileService(session)
    await svc.update_location(message.from_user.id, message.location.latitude, message.location.longitude)
    await state.clear()
    _log.user("update_location: user=%s", message.from_user.id)
    await message.answer("📡  обновлена.", reply_markup=remove_kb())
    await message.answer("·", reply_markup=kb_main_menu())
