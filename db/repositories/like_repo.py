from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, exists, and_, update, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Like, Match, User, LikeMessage


class LikeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, from_user: int, to_user: int, value: bool) -> None:
        stmt = (
            insert(Like)
            .values(from_user=from_user, to_user=to_user, value=value)
            .on_conflict_do_update(
                constraint="uq_likes_pair",
                set_={"value": value},
            )
        )
        await self.session.execute(stmt)
        await self._recalc_rating(to_user)

    async def _recalc_rating(self, user_id: int) -> None:
        q = select(
            func.count().filter(Like.value.is_(True)).label("likes"),
            func.count().label("total"),
        ).where(Like.to_user == user_id)
        row = (await self.session.execute(q)).one()
        likes: int = row.likes or 0
        total: int = row.total or 0
        ratio = (likes / total) if total > 0 else 0.0
        await self.session.execute(
            update(User).where(User.id == user_id).values(avg_rating=ratio, rating_count=total)
        )

    async def already_liked(self, from_user: int, to_user: int) -> bool:
        result = await self.session.execute(
            select(exists().where(
                and_(Like.from_user == from_user, Like.to_user == to_user, Like.value.is_(True))
            ))
        )
        return result.scalar()

    async def reaction_exists(self, from_user: int, to_user: int) -> bool:
        result = await self.session.execute(
            select(exists().where(
                and_(Like.from_user == from_user, Like.to_user == to_user)
            ))
        )
        return result.scalar()

    async def has_mutual_like(self, user_a: int, user_b: int) -> bool:
        result = await self.session.execute(
            select(exists().where(
                and_(Like.from_user == user_b, Like.to_user == user_a, Like.value.is_(True))
            ))
        )
        return result.scalar()

    async def count_unanswered_likers(self, user_id: int) -> int:
        liked_me  = select(Like.from_user).where(Like.to_user == user_id, Like.value.is_(True))
        i_reacted = select(Like.to_user).where(Like.from_user == user_id)
        r = await self.session.execute(
            select(func.count()).select_from(
                liked_me.where(Like.from_user.not_in(i_reacted)).subquery()
            )
        )
        return r.scalar() or 0

    async def get_unanswered_liker_at(self, user_id: int, offset: int) -> Optional[int]:
        liked_me  = select(Like.from_user).where(Like.to_user == user_id, Like.value.is_(True))
        i_reacted = select(Like.to_user).where(Like.from_user == user_id)
        q = (
            liked_me
            .where(Like.from_user.not_in(i_reacted))
            .order_by(Like.created_at)
            .offset(offset)
            .limit(1)
        )
        r = await self.session.execute(q)
        row = r.fetchone()
        return row[0] if row else None

    async def count_total(self) -> int:
        r = await self.session.execute(
            select(func.count()).select_from(Like).where(Like.value.is_(True))
        )
        return r.scalar()

    # ── Лимиты свайпов ────────────────────────────────────────────

    async def count_recent_swipes(self, user_id: int, hours: int = 6) -> int:
        """Количество свайпов (лайки + дизы) за последние N часов."""
        since = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
        r = await self.session.execute(
            select(func.count()).select_from(Like).where(
                Like.from_user == user_id,
                Like.created_at >= since,
            )
        )
        return r.scalar() or 0

    async def get_oldest_swipe_in_window(
        self, user_id: int, hours: int = 6
    ) -> Optional[datetime]:
        """Самый ранний свайп в текущем окне (нужен для расчёта таймера)."""
        since = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
        r = await self.session.execute(
            select(Like.created_at).where(
                Like.from_user == user_id,
                Like.created_at >= since,
            ).order_by(Like.created_at.asc()).limit(1)
        )
        return r.scalar_one_or_none()

    # ── Откат свайпа (SHROOM+) ────────────────────────────────────

    async def get_last_swipe(self, user_id: int) -> Optional[Like]:
        r = await self.session.execute(
            select(Like).where(Like.from_user == user_id)
            .order_by(Like.created_at.desc()).limit(1)
        )
        return r.scalar_one_or_none()

    async def get_last_swipe_to(self, from_user: int, to_user: int) -> Optional[Like]:
        """Реакция from_user → to_user (для возврата конкретной анкеты)."""
        r = await self.session.execute(
            select(Like).where(Like.from_user == from_user, Like.to_user == to_user).limit(1)
        )
        return r.scalar_one_or_none()

    async def delete_swipe(self, like_id: int) -> None:
        await self.session.execute(delete(Like).where(Like.id == like_id))

    async def recalc_rating(self, user_id: int) -> None:
        """Публичная обёртка пересчёта рейтинга (после отката свайпа)."""
        await self._recalc_rating(user_id)


class MatchRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_a: int, user_b: int) -> Match:
        u1, u2 = sorted([user_a, user_b])
        match = Match(user1_id=u1, user2_id=u2)
        self.session.add(match)
        await self.session.flush()
        return match

    async def exists(self, user_a: int, user_b: int) -> bool:
        u1, u2 = sorted([user_a, user_b])
        result = await self.session.execute(
            select(exists().where(and_(Match.user1_id == u1, Match.user2_id == u2)))
        )
        return result.scalar()

    async def delete_pair(self, user_a: int, user_b: int) -> None:
        u1, u2 = sorted([user_a, user_b])
        await self.session.execute(
            delete(Match).where(and_(Match.user1_id == u1, Match.user2_id == u2))
        )

    async def list_for_user(self, user_id: int) -> list[User]:
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.photos))
            .where(
                User.id.in_(
                    select(Match.user2_id).where(Match.user1_id == user_id)
                    .union(select(Match.user1_id).where(Match.user2_id == user_id))
                )
            )
            .order_by(User.name)
        )
        return list(result.scalars().all())

    async def count_total(self) -> int:
        r = await self.session.execute(select(func.count()).select_from(Match))
        return r.scalar()


class LikeMessageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def count_recent(self, from_user: int, hours: int = 1) -> int:
        since = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
        r = await self.session.execute(
            select(func.count()).select_from(LikeMessage).where(
                LikeMessage.from_user == from_user,
                LikeMessage.created_at >= since,
            )
        )
        return r.scalar() or 0

    async def add(self, from_user: int, to_user: int, text: str) -> None:
        self.session.add(LikeMessage(from_user=from_user, to_user=to_user, text=text))
        await self.session.flush()

    async def oldest_in_window(self, from_user: int, hours: int = 1):
        since = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
        r = await self.session.execute(
            select(LikeMessage.created_at).where(
                LikeMessage.from_user == from_user,
                LikeMessage.created_at >= since,
            ).order_by(LikeMessage.created_at.asc()).limit(1)
        )
        return r.scalar_one_or_none()

    async def latest_from(self, from_user: int, to_user: int) -> Optional[str]:
        """Последняя записка от from_user к to_user (для показа в «лайках»)."""
        r = await self.session.execute(
            select(LikeMessage.text).where(
                LikeMessage.from_user == from_user,
                LikeMessage.to_user == to_user,
            ).order_by(LikeMessage.created_at.desc()).limit(1)
        )
        return r.scalar_one_or_none()
