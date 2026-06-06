from typing import Optional
import math
import random

from sqlalchemy import select, update, delete, func, and_, or_, not_, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import User, Photo, Like, Match, GenderEnum, LookingForEnum


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние в км между двумя точками (Haversine)."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def get(self, user_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.id == user_id).options(selectinload(User.photos))
        )
        return result.scalar_one_or_none()

    async def exists(self, user_id: int) -> bool:
        result = await self.session.execute(
            select(exists().where(User.id == user_id))
        )
        return result.scalar()

    async def create(
        self,
        user_id: int,
        username: Optional[str],
        name: str,
        age: int,
        gender: GenderEnum,
        looking_for: LookingForEnum,
        bio: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> User:
        user = User(
            id=user_id,
            username=username,
            name=name,
            age=age,
            gender=gender,
            looking_for=looking_for,
            bio=bio,
            latitude=latitude,
            longitude=longitude,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def update_location(
        self, user_id: int, latitude: float, longitude: float
    ) -> None:
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(latitude=latitude, longitude=longitude)
        )

    async def update_last_seen(self, user_id: int) -> None:
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_seen_at=func.now())
        )

    async def set_active(self, user_id: int, active: bool) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(is_active=active)
        )

    async def set_banned(self, user_id: int, banned: bool) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(is_banned=banned)
        )

    async def delete(self, user_id: int) -> None:
        await self.session.execute(delete(User).where(User.id == user_id))

    # ------------------------------------------------------------------
    # Фото
    # ------------------------------------------------------------------

    async def get_photos(self, user_id: int) -> list[Photo]:
        result = await self.session.execute(
            select(Photo)
            .where(Photo.user_id == user_id)
            .order_by(Photo.position)
        )
        return list(result.scalars().all())

    async def count_photos(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count()).where(Photo.user_id == user_id)
        )
        return result.scalar()

    async def add_photo(self, user_id: int, file_id: str) -> Photo:
        position = await self.count_photos(user_id)
        photo = Photo(user_id=user_id, file_id=file_id, position=position)
        self.session.add(photo)
        await self.session.flush()
        return photo

    async def delete_photos(self, user_id: int) -> None:
        await self.session.execute(delete(Photo).where(Photo.user_id == user_id))

    # ------------------------------------------------------------------
    # Подбор анкет
    # ------------------------------------------------------------------

    async def get_next_candidate(
        self,
        current_user: User,
        nearby_radius_km: int = 50,
    ) -> Optional[User]:
        """
        Возвращает следующую анкету для просмотра.
        Алгоритм:
          1. Исключить себя, забаненных, неактивных, уже просмотренных.
          2. Фильтр по полу (looking_for).
          3. Если у current_user есть координаты — сначала ближайшие,
             потом остальные. Иначе — все подряд в случайном порядке.
        """
        # Подзапрос: уже оценённые пользователи
        seen_subq = select(Like.to_user).where(Like.from_user == current_user.id)

        # Базовый фильтр
        base_filter = and_(
            User.id != current_user.id,
            User.is_active.is_(True),
            User.is_banned.is_(False),
            not_(User.id.in_(seen_subq)),
        )

        # Фильтр по полу
        if current_user.looking_for == LookingForEnum.male:
            base_filter = and_(base_filter, User.gender == GenderEnum.male)
        elif current_user.looking_for == LookingForEnum.female:
            base_filter = and_(base_filter, User.gender == GenderEnum.female)
        # any — не фильтруем по полу

        # Если есть координаты — пытаемся найти рядом
        if current_user.latitude is not None and current_user.longitude is not None:
            candidates_result = await self.session.execute(
                select(User)
                .options(selectinload(User.photos))
                .where(base_filter)
            )
            candidates = list(candidates_result.scalars().all())

            if not candidates:
                return None

            # Разбиваем на «рядом» и «остальные», сортируем по дистанции
            nearby = []
            far = []
            for u in candidates:
                if u.latitude is not None and u.longitude is not None:
                    dist = _haversine_km(
                        current_user.latitude, current_user.longitude,
                        u.latitude, u.longitude
                    )
                    if dist <= nearby_radius_km:
                        nearby.append((dist, u))
                    else:
                        far.append((dist, u))
                else:
                    far.append((float("inf"), u))

            nearby.sort(key=lambda x: x[0])
            random.shuffle(far)

            ordered = [u for _, u in nearby] + [u for _, u in far]
            return ordered[0] if ordered else None

        # Нет координат — случайный порядок
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.photos))
            .where(base_filter)
            .order_by(func.random())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Статистика (для админки)
    # ------------------------------------------------------------------

    async def count_total(self) -> int:
        r = await self.session.execute(select(func.count()).select_from(User))
        return r.scalar()

    async def count_active(self) -> int:
        r = await self.session.execute(
            select(func.count()).where(User.is_active.is_(True), User.is_banned.is_(False))
        )
        return r.scalar()

    async def count_banned(self) -> int:
        r = await self.session.execute(
            select(func.count()).where(User.is_banned.is_(True))
        )
        return r.scalar()

    async def list_users(
        self,
        offset: int = 0,
        limit: int = 50,
        search: Optional[str] = None,
        banned: Optional[bool] = None,
    ) -> list[User]:
        q = select(User).options(selectinload(User.photos))
        if search:
            q = q.where(
                or_(User.name.ilike(f"%{search}%"), User.username.ilike(f"%{search}%"))
            )
        if banned is not None:
            q = q.where(User.is_banned == banned)
        q = q.order_by(User.registered_at.desc()).offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())
