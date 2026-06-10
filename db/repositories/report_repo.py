from typing import Optional

from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Report, ReportReasonEnum


class ReportRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, reporter_id: int, target_id: int, reason: str) -> bool:
        """
        Создаёт репорт. Возвращает True если новый, False если уже был.
        Один репортёр → одна жалоба на конкретного юзера (uq_reports_pair).
        """
        stmt = (
            insert(Report)
            .values(
                reporter_id=reporter_id,
                target_id=target_id,
                reason=ReportReasonEnum(reason),
            )
            .on_conflict_do_nothing(constraint="uq_reports_pair")
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def count_pending(self) -> int:
        r = await self.session.execute(
            select(func.count()).select_from(Report)
            .where(Report.is_reviewed.is_(False))
        )
        return r.scalar() or 0

    async def get_pending_at(self, offset: int) -> Optional[Report]:
        r = await self.session.execute(
            select(Report)
            .where(Report.is_reviewed.is_(False))
            .order_by(Report.created_at.asc())
            .offset(offset)
            .limit(1)
        )
        return r.scalar_one_or_none()

    async def mark_reviewed(self, report_id: int) -> None:
        await self.session.execute(
            update(Report)
            .where(Report.id == report_id)
            .values(is_reviewed=True)
        )

    async def count_recent_by_reporter(self, reporter_id: int, hours: int = 1) -> int:
        """Сколько репортов отправил пользователь за последние N часов."""
        from datetime import datetime, timezone, timedelta
        since = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
        r = await self.session.execute(
            select(func.count()).select_from(Report).where(
                Report.reporter_id == reporter_id,
                Report.created_at  >= since,
            )
        )
        return r.scalar() or 0