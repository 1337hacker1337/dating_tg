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

    async def update_location(self, user_id, latitude, longitude, city=None):
        await self.session.execute(
            update(User).where(User.id == user_id)
            .values(latitude=latitude, longitude=longitude, city=city)
        )

    async def set_city(self, user_id: int, city) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(city=city)
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

        # ── Фильтр по возрасту (доступен всем) ────────────────────
        if current_user.age_min is not None:
            base_filter = and_(base_filter, User.age >= current_user.age_min)
        if current_user.age_max is not None:
            base_filter = and_(base_filter, User.age <= current_user.age_max)

        # ── Жёсткий фильтр по дистанции (доступен всем) ──────────
        if (
            current_user.max_distance_km
            and current_user.latitude is not None
            and current_user.longitude is not None
        ):
            d = current_user.max_distance_km / 111.0
            base_filter = and_(
                base_filter,
                User.latitude.isnot(None), User.longitude.isnot(None),
                User.latitude.between(current_user.latitude - d, current_user.latitude + d),
                User.longitude.between(current_user.longitude - d, current_user.longitude + d),
            )

        # SHROOM+ показывается выше в ленте (но не ломает гео-приоритет)
        now = datetime.now(tz=timezone.utc)
        prem_priority = case(
            (and_(User.premium_until.isnot(None), User.premium_until > now), 0),
            else_=1,
        )

        # ── Умный подбор ──────────────────────────────────────────
        # 1) кто меня уже лайкнул — выше всех (максимальный шанс мэтча)
        liked_me = (
            select(Like.id).where(
                Like.from_user == User.id,
                Like.to_user == current_user.id,
                Like.value.is_(True),
            ).exists()
        )
        like_boost = case((liked_me, 0), else_=1)

        # 2) взаимный интерес: кандидат ищет мой пол (или «всех») — выше
        if current_user.gender == GenderEnum.male:
            wants_me = or_(User.looking_for == LookingForEnum.any,
                           User.looking_for == LookingForEnum.male)
        elif current_user.gender == GenderEnum.female:
            wants_me = or_(User.looking_for == LookingForEnum.any,
                           User.looking_for == LookingForEnum.female)
        else:
            wants_me = (User.looking_for == LookingForEnum.any)
        mutual = case((wants_me, 0), else_=1)

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
            # лайкнувшие → ближние → взаимный интерес → премиум → ближе по дистанции → рандом
            q = (
                select(User).options(selectinload(User.photos))
                .where(base_filter)
                .order_by(like_boost, priority, mutual, prem_priority, dist_sq, func.random())
                .limit(1)
            )
        else:
            q = (
                select(User).options(selectinload(User.photos))
                .where(base_filter)
                .order_by(like_boost, mutual, prem_priority, func.random())
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

    # ── Рефералы ──────────────────────────────────────────────────

    async def apply_referral(
        self,
        new_user_id: int,
        referrer_id: int,
        welcome_bonus: int,
        referrer_bonus: int,
    ) -> bool:
        """
        Привязывает реферера к новичку и начисляет бонусные свайпы обоим.
        Возвращает True, если начисление выполнено.

        Защита от накруток:
          • нельзя пригласить самого себя;
          • реферер должен существовать;
          • привязка ставится один раз (referred_by уже задан → отказ).
        """
        if referrer_id == new_user_id:
            return False

        referrer = await self.get_light(referrer_id)
        if referrer is None:
            return False

        new_user = await self.get_light(new_user_id)
        if new_user is None or new_user.referred_by is not None:
            return False

        await self.session.execute(
            update(User)
            .where(User.id == new_user_id)
            .values(
                referred_by=referrer_id,
                bonus_swipes=User.bonus_swipes + welcome_bonus,
            )
        )
        await self.session.execute(
            update(User)
            .where(User.id == referrer_id)
            .values(bonus_swipes=User.bonus_swipes + referrer_bonus)
        )
        return True

    async def count_referrals(self, user_id: int) -> int:
        r = await self.session.execute(
            select(func.count()).select_from(User).where(User.referred_by == user_id)
        )
        return r.scalar() or 0

    # ── SHROOM+ ───────────────────────────────────────────────────

    async def grant_premium(self, user_id: int, days: int) -> datetime:
        """
        Выдаёт или продлевает премиум. Если уже активен — продлевает от
        текущей даты окончания (стопкой), иначе от текущего момента.
        Возвращает новую дату окончания.
        """
        now  = datetime.now(tz=timezone.utc)
        user = await self.get_light(user_id)
        base = (
            user.premium_until
            if (user and user.premium_until and user.premium_until > now)
            else now
        )
        new_until = base + timedelta(days=days)
        await self.session.execute(
            update(User).where(User.id == user_id).values(premium_until=new_until)
        )
        return new_until

    async def is_premium(self, user_id: int) -> bool:
        user = await self.get_light(user_id)
        return bool(user and user.is_premium)

    async def count_premium(self) -> int:
        now = datetime.now(tz=timezone.utc)
        r = await self.session.execute(
            select(func.count()).select_from(User).where(User.premium_until > now)
        )
        return r.scalar() or 0

    # ── Фильтры поиска ────────────────────────────────────────────

    async def set_age_filter(self, user_id: int, age_min, age_max) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(age_min=age_min, age_max=age_max)
        )

    async def set_max_distance(self, user_id: int, km) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(max_distance_km=km)
        )

    async def reset_filters(self, user_id: int) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(
                age_min=None, age_max=None, max_distance_km=None
            )
        )

