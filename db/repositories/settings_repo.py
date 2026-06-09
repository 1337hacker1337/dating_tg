from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BotSettings


class SettingsRepository:
    AD_CHANNEL_KEY = "ad_channel_id"
    AD_EXPIRES_KEY = "ad_channel_expires_at"

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, key: str) -> Optional[str]:
        r = await self.session.execute(
            select(BotSettings.value).where(BotSettings.key == key)
        )
        return r.scalar_one_or_none()

    async def set(self, key: str, value: Optional[str]) -> None:
        if value is None:
            await self.session.execute(
                delete(BotSettings).where(BotSettings.key == key)
            )
        else:
            stmt = (
                insert(BotSettings)
                .values(key=key, value=value)
                .on_conflict_do_update(index_elements=["key"], set_={"value": value})
            )
            await self.session.execute(stmt)

    # ── Рекламный канал ───────────────────────────────────────────

    async def get_ad_channel(self) -> Optional[str]:
        return await self.get(self.AD_CHANNEL_KEY)

    async def set_ad_channel(self, channel_id: Optional[str]) -> None:
        await self.set(self.AD_CHANNEL_KEY, channel_id)

    # ── Таймер рекламы ────────────────────────────────────────────

    async def get_ad_expires(self) -> Optional[datetime]:
        """None = постоянно (без таймера)."""
        val = await self.get(self.AD_EXPIRES_KEY)
        if val is None:
            return None
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return None

    async def set_ad_expires(self, dt: Optional[datetime]) -> None:
        """dt=None — постоянно. dt в прошлом — уже истёк."""
        await self.set(
            self.AD_EXPIRES_KEY,
            dt.isoformat() if dt is not None else None
        )

    async def set_ad_expires_hours(self, hours: int) -> Optional[datetime]:
        """
        hours=0 → постоянно (убирает таймер).
        Возвращает datetime истечения или None если постоянно.
        """
        if hours == 0:
            await self.set_ad_expires(None)
            return None
        expires = datetime.now(tz=timezone.utc) + timedelta(hours=hours)
        await self.set_ad_expires(expires)
        return expires

    async def is_ad_active(self) -> bool:
        """True если рекламный канал активен (установлен и таймер не истёк)."""
        channel = await self.get_ad_channel()
        if not channel:
            return False
        expires = await self.get_ad_expires()
        if expires is None:
            return True  # постоянно
        return datetime.now(tz=timezone.utc) < expires
