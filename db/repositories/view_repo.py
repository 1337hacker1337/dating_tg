"""db/repositories/view_repo.py — «кто смотрел анкету».

Просмотр фиксируется при показе карточки в ленте. В выдаче «кто смотрел меня»
исключаются только те, кого Я УЖЕ ОТРЕАГИРОВАЛ (лайк/диз) — чтобы после моей
реакции человек уходил из списка и счётчика. Все остальные смотревшие
(включая тех, кто меня дизлайкнул) остаются.
"""
from typing import Optional, Tuple

from sqlalchemy import select, func, and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ProfileView, Like


def _pending_cond(target_id: int):
    """Просмотры target_id, кроме тех, кого он уже отреагировал."""
    reacted_by_me = (
        select(Like.id)
        .where(Like.from_user == target_id, Like.to_user == ProfileView.viewer_id)
        .exists()
    )
    return and_(ProfileView.target_id == target_id, ~reacted_by_me)


class ProfileViewRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, viewer_id: int, target_id: int) -> None:
        """Фиксирует просмотр (upsert: одна строка на пару, время обновляется)."""
        if viewer_id == target_id:
            return
        stmt = (
            insert(ProfileView)
            .values(viewer_id=viewer_id, target_id=target_id)
            .on_conflict_do_update(
                constraint="uq_profile_views_pair",
                set_={"viewed_at": func.now()},
            )
        )
        await self.session.execute(stmt)

    async def count_viewers(self, target_id: int) -> int:
        r = await self.session.execute(
            select(func.count()).select_from(ProfileView).where(_pending_cond(target_id))
        )
        return r.scalar() or 0

    async def get_page(self, target_id: int, offset: int) -> Optional[Tuple[int, object]]:
        """(viewer_id, viewed_at) для N-го по свежести неразрешённого просмотра."""
        r = await self.session.execute(
            select(ProfileView.viewer_id, ProfileView.viewed_at)
            .where(_pending_cond(target_id))
            .order_by(ProfileView.viewed_at.desc())
            .offset(offset).limit(1)
        )
        row = r.first()
        return (row[0], row[1]) if row else None
