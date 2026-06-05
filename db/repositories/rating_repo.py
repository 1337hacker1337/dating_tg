# ───────────────────────────────────────────────────────────────
# db/repositories/rating_repo.py
# ───────────────────────────────────────────────────────────────
from sqlalchemy import select, func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Rating, User


class RatingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(self, voter_id: int, target_id: int, score: int) -> None:
        """
        Сохраняет оценку (INSERT или UPDATE при повторном голосе).
        После — пересчитывает avg_rating и rating_count в таблице users на лету.
        """
        stmt = (
            insert(Rating)
            .values(voter_id=voter_id, target_id=target_id, score=score)
            .on_conflict_do_update(
                constraint="uq_ratings_pair",
                set_={"score": score},
            )
        )
        await self.session.execute(stmt)

        # Пересчёт avg и count прямо в БД — один запрос, никакой Python-математики
        avg_q = (
            select(
                func.round(func.avg(Rating.score).cast(
                    # numeric для round() в PostgreSQL
                    __import__("sqlalchemy").Numeric(6, 2)
                ), 2).label("avg"),
                func.count().label("cnt"),
            )
            .where(Rating.target_id == target_id)
        )
        row = (await self.session.execute(avg_q)).one()

        await self.session.execute(
            update(User)
            .where(User.id == target_id)
            .values(avg_rating=float(row.avg or 0), rating_count=row.cnt)
        )

    async def get_avg(self, target_id: int) -> float:
        """Быстрое чтение из денормализованного поля users.avg_rating."""
        result = await self.session.execute(
            select(User.avg_rating).where(User.id == target_id)
        )
        return float(result.scalar_one_or_none() or 0.0)
