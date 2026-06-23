"""
bot/handlers/user/filters.py — фильтры поиска.

Возраст — доступен всем. Дистанция — фильтр SHROOM+.
Применяются в UserRepository.get_next_candidate.
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot import logger as log
from bot.constants import AGE_MIN, AGE_MAX
from bot.keyboards import kb_filters, kb_filter_distance, kb_main_menu
from bot.states import FiltersState
from db.repositories.user_repo import UserRepository

_log = log.get(__name__)
router = Router(name="filters")


def _has_geo(user) -> bool:
    return user.latitude is not None and user.longitude is not None


def _filters_text(user) -> str:
    if user.age_min is not None or user.age_max is not None:
        lo = user.age_min if user.age_min is not None else AGE_MIN
        hi = user.age_max if user.age_max is not None else AGE_MAX
        age = f"{lo}–{hi}"
    else:
        age = "любой"

    # Дистанция работает только при указанной геолокации — сообщаем об этом
    # прямо в экране, чтобы юзер не тыкал «📍 расстояние» вслепую.
    if not _has_geo(user):
        dist = "нужна геолокация  <i>(укажи в «✏️ редактировать»)</i>"
    elif user.max_distance_km:
        dist = f"до {user.max_distance_km} км"
    else:
        dist = "без ограничения"

    looking = {"male": "парней", "female": "девушек", "any": "всех"}.get(
        user.looking_for.value if hasattr(user.looking_for, "value") else str(user.looking_for),
        "—",
    )

    return (
        "🔍  <b>фильтры поиска</b>\n\n"
        f"🎂 возраст:      {age}\n"
        f"📍 расстояние:   {dist}\n"
        f"⚧ ищу:          {looking}  <i>(меняется в «редактировать»)</i>"
    )


async def _show(user_id: int, target, session: AsyncSession) -> None:
    user = await UserRepository(session).get_light(user_id)
    if user is None:
        await target.answer("анкеты нет.\n\n/start")
        return
    await target.answer(
        _filters_text(user), parse_mode="HTML",
        reply_markup=kb_filters(),
    )


@router.message(Command("filters"))
async def cmd_filters(message: Message, session: AsyncSession):
    await _show(message.from_user.id, message, session)


@router.callback_query(F.data == "filters")
async def open_filters(call: CallbackQuery, session: AsyncSession):
    await call.answer()
    await _show(call.from_user.id, call.message, session)


@router.callback_query(F.data == "filters:open")
async def reopen_filters(call: CallbackQuery, session: AsyncSession):
    await call.answer()
    await _show(call.from_user.id, call.message, session)


@router.callback_query(F.data == "filters:back")
async def filters_back(call: CallbackQuery):
    await call.answer()
    await call.message.answer("🍄 меню", reply_markup=kb_main_menu())


# ── Возраст ───────────────────────────────────────────────────────

@router.callback_query(F.data == "filters:age")
async def filters_age_prompt(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(FiltersState.age)
    await call.message.answer(
        f"🎂  диапазон возраста через дефис, напр. <code>18-25</code>\n"
        f"<i>допустимо {AGE_MIN}–{AGE_MAX}. «0» — сбросить фильтр.</i>",
        parse_mode="HTML",
    )


@router.message(FiltersState.age, F.text)
async def filters_age_set(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()

    if raw == "0":
        await UserRepository(session).set_age_filter(message.from_user.id, None, None)
        await session.commit()
        await state.clear()
        await message.answer("🎂 фильтр возраста сброшен.")
        await _show(message.from_user.id, message, session)
        return

    parts = raw.replace("—", "-").replace("–", "-").split("-")
    if len(parts) != 2 or not all(p.strip().isdecimal() for p in parts):
        await message.answer("↑ формат: <code>18-25</code> или <code>0</code>.", parse_mode="HTML")
        return

    lo, hi = int(parts[0]), int(parts[1])
    if lo > hi:
        lo, hi = hi, lo
    if lo < AGE_MIN or hi > AGE_MAX:
        await message.answer(f"↑ допустимо {AGE_MIN}–{AGE_MAX}.")
        return

    await UserRepository(session).set_age_filter(message.from_user.id, lo, hi)
    await session.commit()
    await state.clear()
    _log.user("filters age: user=%s %d-%d", message.from_user.id, lo, hi)
    await message.answer(f"🎂 возраст: {lo}–{hi}")
    await _show(message.from_user.id, message, session)


@router.message(FiltersState.age)
async def filters_age_invalid(message: Message):
    await message.answer("↑ пришли диапазон, напр. <code>18-25</code>.", parse_mode="HTML")


# ── Расстояние ────────────────────────────────────────────────────
# Жёсткий гео-фильтр доступен всем, но требует указанной геолокации.

@router.callback_query(F.data == "filters:dist")
async def filters_dist_menu(call: CallbackQuery, session: AsyncSession):
    repo = UserRepository(session)
    user = await repo.get_light(call.from_user.id)
    if user is None:
        await call.answer()
        return
    if not _has_geo(user):
        await call.answer(
            "сначала укажи геолокацию в «✏️ редактировать».", show_alert=True
        )
        return
    await call.answer()
    await call.message.answer(
        "📍  максимальное расстояние до анкеты:",
        reply_markup=kb_filter_distance(),
    )


@router.callback_query(F.data.startswith("filters:dist_set:"))
async def filters_dist_set(call: CallbackQuery, session: AsyncSession):
    repo = UserRepository(session)
    user = await repo.get_light(call.from_user.id)
    # Подстраховка: вдруг гео сбросили, пока меню висело открытым.
    if user is None or not _has_geo(user):
        await call.answer(
            "сначала укажи геолокацию в «✏️ редактировать».", show_alert=True
        )
        return
    km = int(call.data.split(":")[2])
    await repo.set_max_distance(call.from_user.id, km or None)
    await session.commit()
    _log.user("filters dist: user=%s km=%s", call.from_user.id, km)
    await call.answer("📍 сохранено" if km else "📍 без ограничения")
    await _show(call.from_user.id, call.message, session)


# ── Сброс ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "filters:reset")
async def filters_reset(call: CallbackQuery, session: AsyncSession):
    await UserRepository(session).reset_filters(call.from_user.id)
    await session.commit()
    await call.answer("♻️ фильтры сброшены", show_alert=False)
    await _show(call.from_user.id, call.message, session)
