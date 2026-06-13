from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, update, delete, func, and_, or_, not_, exists, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import User, Photo, Like, Match, GenderEnum, LookingForEnum


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, user_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.id == user_id).options(selectinload(User.photos))
        )
        return result.scalar_one_or_none()

    async def get_light(self, user_id: int) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def exists(self, user_id: int) -> bool:
        result = await self.session.execute(select(exists().where(User.id == user_id)))
        return result.scalar()

    async def create(self, user_id, username, name, age, gender, looking_for,
                     bio=None, latitude=None, longitude=None) -> User:
        user = User(id=user_id, username=username, name=name, age=age,
                    gender=gender, looking_for=looking_for, bio=bio,
                    latitude=latitude, longitude=longitude)
        self.session.add(user)
        await self.session.flush()
        return user

    async def update_location(self, user_id, latitude, longitude):
        await self.session.execute(
            update(User).where(User.id == user_id).values(latitude=latitude, longitude=longitude)
        )

    async def update_username(self, user_id: int, username: Optional[str]) -> None:
        """Синхронизация username с Telegram (мог измениться после регистрации)."""
        await self.session.execute(
            update(User).where(User.id == user_id).values(username=username)
        )

    async def update_last_seen(self, user_id):
        await self.session.execute(
            update(User).where(User.id == user_id).values(last_seen_at=func.now())
        )

    async def set_active(self, user_id, active):
        await self.session.execute(
            update(User).where(User.id == user_id).values(is_active=active)
        )

    async def set_banned(self, user_id, banned):
        await self.session.execute(
            update(User).where(User.id == user_id).values(is_banned=banned)
        )

    async def set_notifications(self, user_id: int, enabled: bool) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(notifications_enabled=enabled)
        )

    async def delete(self, user_id):
        await self.session.execute(delete(User).where(User.id == user_id))

    async def count_photos(self, user_id):
        result = await self.session.execute(
            select(func.count()).where(Photo.user_id == user_id)
        )
        return result.scalar()

    async def add_photo(self, user_id, file_id):
        position = await self.count_photos(user_id)
        photo = Photo(user_id=user_id, file_id=file_id, position=position)
        self.session.add(photo)
        await self.session.flush()
        return photo

    async def delete_photos(self, user_id):
        await self.session.execute(delete(Photo).where(Photo.user_id == user_id))

    async def get_profile_stats(self, user_id) -> dict:
        likes_q = select(
            func.count().filter(Like.value.is_(True)).label("likes"),
            func.count().filter(Like.value.is_(False)).label("dislikes"),
        ).where(Like.to_user == user_id)
        matches_q = (
            select(func.count().label("matches")).select_from(Match)
            .where((Match.user1_id == user_id) | (Match.user2_id == user_id))
        )
        row_l = (await self.session.execute(likes_q)).one()
        row_m = (await self.session.execute(matches_q)).one()
        return {
            "likes":    row_l.likes    or 0,
            "dislikes": row_l.dislikes or 0,
            "matches":  row_m.matches  or 0,
        }

    async def get_next_candidate(self, current_user: User, nearby_radius_km: int = 50) -> Optional[User]:
        seen_subq = select(Like.to_user).where(Like.from_user == current_user.id)
        base_filter = and_(
            User.id != current_user.id,
            User.is_active.is_(True),
            User.is_banned.is_(False),
            not_(User.id.in_(seen_subq)),
        )
        if current_user.looking_for == LookingForEnum.male:
            base_filter = and_(base_filter, User.gender == GenderEnum.male)
        elif current_user.looking_for == LookingForEnum.female:
            base_filter = and_(base_filter, User.gender == GenderEnum.female)

        if current_user.latitude is not None and current_user.longitude is not None:
            lat, lon = current_user.latitude, current_user.longitude
            deg = nearby_radius_km / 111.0
            in_bbox = and_(
                User.latitude.isnot(None), User.longitude.isnot(None),
                User.latitude.between(lat - deg, lat + deg),
                User.longitude.between(lon - deg, lon + deg),
            )
            priority = case((in_bbox, 0), else_=1)
            dist_sq  = (
                (User.latitude - lat) * (User.latitude - lat) +
                (User.longitude - lon) * (User.longitude - lon)
            )
            q = (
                select(User).options(selectinload(User.photos))
                .where(base_filter)
                .order_by(priority, dist_sq, func.random())
                .limit(1)
            )
        else:
            q = (
                select(User).options(selectinload(User.photos))
                .where(base_filter)
                .order_by(func.random())
                .limit(1)
            )

        result = await self.session.execute(q)
        return result.scalar_one_or_none()

    async def count_total(self):
        r = await self.session.execute(select(func.count()).select_from(User))
        return r.scalar()

    async def count_active(self):
        r = await self.session.execute(
            select(func.count()).where(User.is_active.is_(True), User.is_banned.is_(False))
        )
        return r.scalar()

    async def count_banned(self):
        r = await self.session.execute(
            select(func.count()).where(User.is_banned.is_(True))
        )
        return r.scalar()

    async def list_users(self, offset=0, limit=50, search=None, banned=None):
        q = select(User).options(selectinload(User.photos))
        if search:
            q = q.where(or_(User.name.ilike(f"%{search}%"), User.username.ilike(f"%{search}%")))
        if banned is not None:
            q = q.where(User.is_banned == banned)
        q = q.order_by(User.registered_at.desc()).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    async def get_users_for_notify(self, inactive_hours=48, cooldown_hours=48):
        now            = datetime.now(tz=timezone.utc)
        inactive_since = now - timedelta(hours=inactive_hours)
        notified_since = now - timedelta(hours=cooldown_hours)
        q = select(User.id).where(
            User.is_active.is_(True),
            User.is_banned.is_(False),
            User.notifications_enabled.is_(True),
            User.last_seen_at.isnot(None),
            User.last_seen_at < inactive_since,
            or_(User.notified_at.is_(None), User.notified_at < notified_since),
        )
        r = await self.session.execute(q)
        return [row[0] for row in r.fetchall()]

    async def set_notified(self, user_ids: list[int]):
        if not user_ids:
            return
        await self.session.execute(
            update(User).where(User.id.in_(user_ids)).values(notified_at=func.now())
        )
