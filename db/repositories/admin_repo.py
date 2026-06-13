from typing import Optional

from sqlalchemy import select, delete, exists
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Admin


class AdminRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def is_admin(self, telegram_id: int) -> bool:
        result = await self.session.execute(
            select(exists().where(Admin.telegram_id == telegram_id))
        )
        return result.scalar()

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[Admin]:
        result = await self.session.execute(
            select(Admin).where(Admin.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def add(self, telegram_id: int, username: Optional[str] = None,
                  added_by: Optional[int] = None) -> Admin:
        admin = Admin(telegram_id=telegram_id, username=username, added_by=added_by)
        self.session.add(admin)
        await self.session.flush()
        return admin

    async def remove(self, telegram_id: int) -> None:
        await self.session.execute(delete(Admin).where(Admin.telegram_id == telegram_id))

    async def list_all(self) -> list[Admin]:
        result = await self.session.execute(select(Admin).order_by(Admin.added_at))
        return list(result.scalars().all())
