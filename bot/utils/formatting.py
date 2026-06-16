"""bot/utils/formatting.py — форматирование дат, таймеров и карточек анкет."""
from datetime import datetime, timezone, timedelta
from typing import Optional

from bot.utils.geo import haversine_km
from bot.utils.rating import format_rating_line
from bot.constants import PREMIUM_BADGE


def fmt_delta(delta: timedelta) -> str:
    """'2ч 15м' / '45м' для оставшегося времени."""
    secs = max(0, int(delta.total_seconds()))
    h, rem = divmod(secs, 3600)
    m = rem // 60
    if h and m:
        return f"{h}ч {m}м"
    if h:
        return f"{h}ч"
    return f"{m}м"


def fmt_ago(dt: Optional[datetime]) -> str:
    """'5 мин назад' / '3 ч назад' / '2 д назад'."""
    if dt is None:
        return ""
    now = datetime.now(tz=timezone.utc)
    secs = max(0, int((now - dt).total_seconds()))
    if secs < 60:
        return "только что"
    mins = secs // 60
    if mins < 60:
        return f"{mins} мин назад"
    hours = mins // 60
    if hours < 24:
        return f"{hours} ч назад"
    days = hours // 24
    return f"{days} д назад"


def fmt_expires(expires: Optional[datetime]) -> str:
    """Время истечения таймера в читаемом виде с остатком."""
    if expires is None:
        return "постоянно ♾"
    now = datetime.now(tz=timezone.utc)
    if now >= expires:
        return "истёк ❌"
    delta = expires - now
    total_minutes = int(delta.total_seconds() // 60)
    days    = total_minutes // 1440
    hours   = (total_minutes % 1440) // 60
    minutes = total_minutes % 60
    parts = []
    if days:
        parts.append(f"{days}д")
    if hours:
        parts.append(f"{hours}ч")
    if minutes:
        parts.append(f"{minutes}м")
    remaining = " ".join(parts) or "< 1м"
    ts = expires.strftime("%d.%m.%Y %H:%M UTC")
    return f"{ts}  (осталось {remaining})"


async def profile_caption(candidate, session, viewer=None) -> str:
    """Карточка анкеты для ленты / лайков / мэтчей."""
    from db.repositories.user_repo import UserRepository  # локально — против циклов импорта

    header = f"<b>{candidate.name}</b>, {candidate.age}"
    if getattr(candidate, "is_premium", False):
        header = f"{PREMIUM_BADGE} " + header

    loc = []
    if getattr(candidate, "city", None):
        loc.append(f"🏙 {candidate.city}")
    if (
        viewer is not None
        and viewer.latitude is not None and viewer.longitude is not None
        and candidate.latitude is not None and candidate.longitude is not None
    ):
        dist = round(
            haversine_km(
                viewer.latitude, viewer.longitude,
                candidate.latitude, candidate.longitude,
            ),
            1,
        )
        loc.append(f"{dist} км")
    if loc:
        header += "  ·  " + "  ·  ".join(loc)

    lines = [header]
    if candidate.bio:
        lines += ["", f"<i>{candidate.bio}</i>"]

    likes    = round(candidate.avg_rating * candidate.rating_count)
    dislikes = candidate.rating_count - likes
    stats    = await UserRepository(session).get_profile_stats(candidate.id)
    lines += [
        "",
        format_rating_line(candidate.avg_rating, candidate.rating_count),
        "",
        f"🩸 <code>{likes}</code>  ·  🤮 <code>{dislikes}</code>  ·  ⚔️ <code>{stats['matches']}</code>",
    ]
    return "\n".join(lines)


async def own_profile_text(user, session) -> str:
    """Текст собственного профиля (раздел «👁️ профиль»)."""
    from db.repositories.user_repo import UserRepository
    from db.repositories.view_repo import ProfileViewRepository

    stats = await UserRepository(session).get_profile_stats(user.id)
    views = await ProfileViewRepository(session).count_viewers(user.id)
    head = f"<b>{user.name}</b>, {user.age}"
    if getattr(user, "is_premium", False):
        head = f"{PREMIUM_BADGE} " + head
    lines = [head]
    if user.bio:
        lines += ["", f"<i>{user.bio}</i>"]
    lines += [
        "",
        format_rating_line(user.avg_rating, user.rating_count),
        "",
        f"🩸 <code>{stats['likes']}</code>  ·  🤮 <code>{stats['dislikes']}</code>  ·  "
        f"⚔️ <code>{stats['matches']}</code>  ·  👀 <code>{views}</code>",
    ]
    warnings = []
    if not user.is_active:
        warnings.append("скрыта")
    if user.latitude is None:
        warnings.append("гео не указана")
    elif getattr(user, "city", None):
        warnings.append(f"🏙 {user.city}")
    if warnings:
        lines += ["", "  ·  ".join(warnings)]
    return "\n".join(lines)


# ── Экран покупки SHROOM+ (чистый рендер) ─────────────────────────

from bot.constants import SWIPE_LIMIT, PREMIUM_SWIPE_LIMIT  # noqa: E402

_PLUS_MULT  = max(2, PREMIUM_SWIPE_LIMIT // SWIPE_LIMIT)
_PLUS_PERKS = (
    f"🩸  свайпов в {_PLUS_MULT}× больше  ·  до {PREMIUM_SWIPE_LIMIT}\n"
    "🔝  приоритет в ленте\n"
    "↩️  возврат к анкете (кнопка в ленте)\n"
    "👀  кто смотрел анкету\n"
    f"{PREMIUM_BADGE}  бейдж в анкете"
)


def render_premium_offer(expires: Optional[datetime] = None) -> str:
    """
    Экран SHROOM+. Если expires задан и в будущем — статус «активен»,
    иначе — витрина. Цены показаны на кнопках тарифов (см. premium.py).
    """
    now = datetime.now(tz=timezone.utc)
    active = expires is not None and expires > now

    if active:
        head = (
            "✦  <b>SHROOM+</b>  —  активен\n\n"
            f"до:  {fmt_expires(expires)}"
        )
        footer = "<i>продлить — срок добавится к текущему. выбери тариф:</i>"
    else:
        head = (
            "✦  <b>SHROOM+</b>\n\n"
            "<i>больше свайпов, выше в ленте, меньше границ.</i>"
        )
        footer = "выбери тариф:"

    return f"{head}\n\n{_PLUS_PERKS}\n\n┄┄┄┄┄┄┄┄┄┄┄\n{footer}"
