"""bot/utils/formatting.py — форматирование дат, таймеров и карточек анкет."""
from datetime import datetime, timezone, timedelta
from typing import Optional

from bot.utils.geo import haversine_km
from bot.utils.rating import format_rating_line


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
        header += f"  ·  {dist} км"

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

    stats = await UserRepository(session).get_profile_stats(user.id)
    lines = [f"<b>{user.name}</b>, {user.age}"]
    if user.bio:
        lines += ["", f"<i>{user.bio}</i>"]
    lines += [
        "",
        format_rating_line(user.avg_rating, user.rating_count),
        "",
        f"🩸 <code>{stats['likes']}</code>  ·  🤮 <code>{stats['dislikes']}</code>  ·  ⚔️ <code>{stats['matches']}</code>",
    ]
    warnings = []
    if not user.is_active:
        warnings.append("скрыта")
    if user.latitude is None:
        warnings.append("гео не указана")
    if warnings:
        lines += ["", "  ·  ".join(warnings)]
    return "\n".join(lines)
