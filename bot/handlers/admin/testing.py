"""
bot/handlers/admin/testing.py — тест-режим (без живых тестеров).

Генерит синтетические анкеты (id < 0 — не пересекаются с реальными
Telegram id) и умеет симулировать взаимодействия с ними:
лайки/записки/просмотры/мэтчи/репорты в сторону админа.

Очистка — DELETE по id < 0, остальное (лайки, мэтчи, просмотры,
записки, репорты) уносится каскадом по FK ondelete=CASCADE.
"""
import random
from datetime import datetime, timezone, timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select, func, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from bot import logger as log
from bot.keyboards import kb_admin_testing
from db.models import User, Photo, Like, GenderEnum, LookingForEnum
from db.repositories.user_repo import UserRepository
from db.repositories.like_repo import LikeRepository, MatchRepository, LikeMessageRepository
from db.repositories.view_repo import ProfileViewRepository
from db.repositories.report_repo import ReportRepository

_log = log.get(__name__)
router = Router(name="admin_testing")

_NAMES = ["Мара", "Лилит", "Ника", "Рада", "Вера", "Глеб", "Юра", "Артём",
          "Соня", "Кира", "Лена", "Макс", "Ева", "Лео", "Тая", "Рик", "Оля", "Влад"]
_CITIES = ["Москва", "Питер", "Казань", "Самара", "Тверь", "Сочи", "Пермь", "Уфа"]
_BIOS = [
    "тёмный эмбиент и кофе", "ищу того, кто не боится темноты",
    "грибы, книги, тишина", "сарказм прилагается", "ночные прогулки по кладбищам",
    "меньше слов", "кошатник со стажем", "рейв и мерч", "",
]
_NOTES = ["ты что-то особенное", "напиши, если не призрак", "027", "🕯️", "давай поговорим"]


# ── helpers ───────────────────────────────────────────────────────

async def _fake_count(session: AsyncSession) -> int:
    r = await session.execute(select(func.count()).select_from(User).where(User.id < 0))
    return r.scalar() or 0


async def _next_base(session: AsyncSession) -> int:
    r = await session.execute(select(func.min(User.id)))
    m = r.scalar()
    return (m - 1) if (m is not None and m < 0) else -1


async def _seed(session: AsyncSession, admin: User, n: int) -> list[int]:
    base = await _next_base(session)
    photo_fid = admin.photos[0].file_id if (admin and admin.photos) else None
    created: list[int] = []
    for i in range(n):
        uid = base - i
        lat = lon = None
        if admin and admin.latitude is not None and admin.longitude is not None:
            lat = admin.latitude + random.uniform(-0.25, 0.25)
            lon = admin.longitude + random.uniform(-0.25, 0.25)
        rc = random.choice([0, 8, 20, 55, 90, 130])
        u = User(
            id=uid, username=None, name=random.choice(_NAMES),
            age=random.randint(18, 42),
            gender=random.choice(list(GenderEnum)),
            looking_for=random.choice(list(LookingForEnum)),
            bio=random.choice(_BIOS),
            latitude=lat, longitude=lon, city=random.choice(_CITIES),
            avg_rating=round(random.uniform(0.2, 0.95), 2), rating_count=rc,
            is_active=True, is_banned=False,
            premium_until=(datetime.now(timezone.utc) + timedelta(days=30)) if random.random() < 0.25 else None,
            last_seen_at=datetime.now(timezone.utc),
        )
        session.add(u)
        await session.flush()
        if photo_fid:
            session.add(Photo(user_id=uid, file_id=photo_fid, position=0))
        created.append(uid)
    await session.commit()
    return created


async def _ensure(session: AsyncSession, admin, need: int) -> list[int]:
    """
    Фейки, которых админ ещё НЕ свайпал (иначе результат «лайкнут меня /
    записка / просмотры» спрячется фильтром «уже отреагировал»). Если таких
    не хватает — досоздаёт новые (они по определению «свежие»).
    """
    if admin is not None:
        reacted = (
            select(Like.id)
            .where(Like.from_user == admin.id, Like.to_user == User.id)
            .exists()
        )
        cond = and_(User.id < 0, ~reacted)
    else:
        cond = User.id < 0

    r = await session.execute(
        select(User.id).where(cond).order_by(User.id.desc()).limit(need)
    )
    ids = [row[0] for row in r.fetchall()]
    if len(ids) < need:
        ids += await _seed(session, admin, need - len(ids))
    return ids[:need]


async def _show_testing(call: CallbackQuery, session: AsyncSession) -> None:
    cnt = await _fake_count(session)
    text = (
        "🧪  <b>тест-режим</b>\n\n"
        f"фейковых анкет в базе: <b>{cnt}</b>\n\n"
        "генерируй анкеты и симулируй взаимодействия — потом «🧹 удалить тестовые».\n"
        "<i>чтобы видеть кто смотрел/лайкнул, выдай себе SHROOM+.</i>"
    )
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_admin_testing(cnt))
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=kb_admin_testing(cnt))


async def _admin_user(session: AsyncSession, admin_id: int) -> User | None:
    return await UserRepository(session).get(admin_id)


# ── вход ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:test")
async def adm_test(call: CallbackQuery, session: AsyncSession):
    await call.answer()
    await _show_testing(call, session)


# ── генерация анкет ───────────────────────────────────────────────

@router.callback_query(F.data == "adm:test_seed")
async def adm_test_seed(call: CallbackQuery, session: AsyncSession):
    admin = await _admin_user(session, call.from_user.id)
    created = await _seed(session, admin, 10)
    _log.user("test seed: admin=%s n=%d", call.from_user.id, len(created))
    await call.answer(f"🧪 +{len(created)} анкет в ленту", show_alert=True)
    await _show_testing(call, session)


# ── фейки лайкают меня ────────────────────────────────────────────

@router.callback_query(F.data == "adm:test_likes")
async def adm_test_likes(call: CallbackQuery, session: AsyncSession):
    admin = await _admin_user(session, call.from_user.id)
    if admin is None:
        await call.answer("сначала зарегистрируй свою анкету (/start).", show_alert=True)
        return
    ids   = await _ensure(session, admin, 5)
    likes = LikeRepository(session)
    for fid in ids:
        await likes.add(fid, admin.id, True)
    await session.commit()
    _log.user("test likes: admin=%s n=%d", call.from_user.id, len(ids))
    await call.answer("🩸 5 фейков лайкнули тебя — проверь «🩸 лайки»", show_alert=True)
    await _show_testing(call, session)


# ── записка мне ───────────────────────────────────────────────────

@router.callback_query(F.data == "adm:test_note")
async def adm_test_note(call: CallbackQuery, session: AsyncSession):
    admin = await _admin_user(session, call.from_user.id)
    if admin is None:
        await call.answer("сначала зарегистрируй свою анкету (/start).", show_alert=True)
        return
    fid = (await _ensure(session, admin, 1))[0]
    await LikeRepository(session).add(fid, admin.id, True)
    await LikeMessageRepository(session).add(fid, admin.id, random.choice(_NOTES))
    await session.commit()
    _log.user("test note: admin=%s from=%s", call.from_user.id, fid)
    await call.answer("💬 записка пришла — она в «🩸 лайки»", show_alert=True)
    await _show_testing(call, session)


# ── просмотры моей анкеты ─────────────────────────────────────────

@router.callback_query(F.data == "adm:test_views")
async def adm_test_views(call: CallbackQuery, session: AsyncSession):
    admin = await _admin_user(session, call.from_user.id)
    if admin is None:
        await call.answer("сначала зарегистрируй свою анкету (/start).", show_alert=True)
        return
    ids   = await _ensure(session, admin, 7)
    vrepo = ProfileViewRepository(session)
    for fid in ids:
        await vrepo.add(fid, admin.id)
    await session.commit()
    _log.user("test views: admin=%s n=%d", call.from_user.id, len(ids))
    await call.answer("👀 7 просмотров — проверь «👀 кто смотрел» (нужен SHROOM+)", show_alert=True)
    await _show_testing(call, session)


# ── мэтч с фейком ─────────────────────────────────────────────────

@router.callback_query(F.data == "adm:test_match")
async def adm_test_match(call: CallbackQuery, session: AsyncSession):
    admin = await _admin_user(session, call.from_user.id)
    if admin is None:
        await call.answer("сначала зарегистрируй свою анкету (/start).", show_alert=True)
        return
    fid     = (await _ensure(session, admin, 1))[0]
    likes   = LikeRepository(session)
    matches = MatchRepository(session)
    await likes.add(admin.id, fid, True)
    await likes.add(fid, admin.id, True)
    if not await matches.exists(admin.id, fid):
        await matches.create(admin.id, fid)
    await session.commit()
    _log.user("test match: admin=%s with=%s", call.from_user.id, fid)
    await call.answer("⚔️ мэтч создан — проверь «💬 мэтчи»", show_alert=True)
    await _show_testing(call, session)


# ── репорт (для модерации в «🚩 репорты») ─────────────────────────

@router.callback_query(F.data == "adm:test_report")
async def adm_test_report(call: CallbackQuery, session: AsyncSession):
    admin = await _admin_user(session, call.from_user.id)
    ids = await _ensure(session, admin, 2)
    reporter, target = ids[0], ids[1]
    await ReportRepository(session).add(reporter, target, random.choice(["spam", "other"]))
    await session.commit()
    _log.user("test report: admin=%s reporter=%s target=%s", call.from_user.id, reporter, target)
    await call.answer("🚩 репорт создан — проверь «🚩 репорты»", show_alert=True)
    await _show_testing(call, session)


# ── фейк отвечает на мой лайк (мэтч с тем, кого лайкнул в ленте) ───

@router.callback_query(F.data == "adm:test_reply")
async def adm_test_reply(call: CallbackQuery, session: AsyncSession):
    admin_id = call.from_user.id
    # последние лайки админа на фейков, ещё без мэтча
    r = await session.execute(
        select(Like.to_user).where(
            Like.from_user == admin_id, Like.value.is_(True), Like.to_user < 0
        ).order_by(Like.created_at.desc())
    )
    matches = MatchRepository(session)
    target  = None
    for (fid,) in r.fetchall():
        if not await matches.exists(admin_id, fid):
            target = fid
            break
    if target is None:
        await call.answer("сначала лайкни фейка в ленте 🩸", show_alert=True)
        return

    await LikeRepository(session).add(target, admin_id, True)  # фейк лайкает в ответ
    if not await matches.exists(admin_id, target):
        await matches.create(admin_id, target)
    await session.commit()
    _log.user("test reply: admin=%s fake=%s", admin_id, target)
    await call.answer("⚔️ фейк ответил — мэтч! проверь «💬 мэтчи»", show_alert=True)
    await _show_testing(call, session)


# ── очистка ───────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:test_clear")
async def adm_test_clear(call: CallbackQuery, session: AsyncSession):
    cnt = await _fake_count(session)
    await session.execute(delete(User).where(User.id < 0))
    await session.commit()
    _log.user("test clear: admin=%s removed=%d", call.from_user.id, cnt)
    await call.answer(f"🧹 удалено тестовых: {cnt}", show_alert=True)
    await _show_testing(call, session)
