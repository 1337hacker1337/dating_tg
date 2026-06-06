from sqlalchemy import select, func, exists, and_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Like, Match, User


class LikeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, from_user: int, to_user: int, value: bool) -> None:
        """INSERT или UPDATE если запись уже есть."""
        stmt = (
            insert(Like)
            .values(from_user=from_user, to_user=to_user, value=value)
            .on_conflict_do_update(
                constraint="uq_likes_pair",
                set_={"value": value},
            )
        )
        await self.session.execute(stmt)
        # Пересчитываем рейтинг как ratio лайков
        await self._recalc_rating(to_user)

    async def _recalc_rating(self, user_id: int) -> None:
        """
        avg_rating = likes / (likes + dislikes)  [0.0 .. 1.0]
        rating_count = likes + dislikes
        """
        q = select(
            func.count().filter(Like.value.is_(True)).label("likes"),
            func.count().label("total"),
        ).where(Like.to_user == user_id)
        row = (await self.session.execute(q)).one()

        likes: int = row.likes or 0
        total: int = row.total or 0
        ratio = (likes / total) if total > 0 else 0.0

        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(avg_rating=ratio, rating_count=total)
        )

    async def already_liked(self, from_user: int, to_user: int) -> bool:
        result = await self.session.execute(
            select(exists().where(
                and_(
                    Like.from_user == from_user,
                    Like.to_user == to_user,
                    Like.value.is_(True),
                )
            ))
        )
        return result.scalar()

    async def has_mutual_like(self, user_a: int, user_b: int) -> bool:
        result = await self.session.execute(
            select(exists().where(
                and_(
                    Like.from_user == user_b,
                    Like.to_user == user_a,
                    Like.value.is_(True),
                )
            ))
        )
        return result.scalar()

    async def count_total(self) -> int:
        r = await self.session.execute(
            select(func.count()).select_from(Like).where(Like.value.is_(True))
        )
        return r.scalar()


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
            select(exists().where(
                and_(Match.user1_id == u1, Match.user2_id == u2)
            ))
        )
        return result.scalar()

    async def list_for_user(self, user_id: int) -> list[User]:
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.photos))
            .where(
                User.id.in_(
                    select(Match.user2_id).where(Match.user1_id == user_id)
                    .union(
                        select(Match.user1_id).where(Match.user2_id == user_id)
                    )
                )
            )
            .order_by(User.name)
        )
        return list(result.scalars().all())

    async def count_total(self) -> int:
        r = await self.session.execute(select(func.count()).select_from(Match))
        return r.scalar()
