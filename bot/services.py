from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import GenderEnum, LookingForEnum, User
from db.repositories.user_repo import UserRepository
from db.repositories.like_repo import LikeRepository, MatchRepository
from db.repositories.rating_repo import RatingRepository

MAX_PHOTOS = 5


@dataclass
class MatchResult:
    matched:      bool
    is_new_match: bool = False
    notify_like:  bool = False
    partner:      Optional[User] = None


class ProfileService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users   = UserRepository(session)

    async def register(
        self,
        user_id:     int,
        username:    Optional[str],
        name:        str,
        age:         int,
        gender:      str,
        looking_for: str,
        bio:         Optional[str],
        latitude:    Optional[float] = None,
        longitude:   Optional[float] = None,
    ) -> User:
        user = await self.users.create(
            user_id=user_id,
            username=username,
            name=name,
            age=age,
            gender=GenderEnum(gender),
            looking_for=LookingForEnum(looking_for),
            bio=bio,
            latitude=latitude,
            longitude=longitude,
        )
        await self.session.commit()
        return user

    async def add_photo(self, user_id: int, file_id: str) -> bool:
        count = await self.users.count_photos(user_id)
        if count >= MAX_PHOTOS:
            return False
        await self.users.add_photo(user_id, file_id)
        await self.session.commit()
        return True

    async def get_profile(self, user_id: int) -> Optional[User]:
        return await self.users.get(user_id)

    async def update_location(self, user_id: int, lat: float, lon: float) -> None:
        await self.users.update_location(user_id, lat, lon)
        await self.session.commit()

    async def touch(self, user_id: int) -> None:
        await self.users.update_last_seen(user_id)
        await self.session.commit()


class BrowseService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users   = UserRepository(session)
        self.likes   = LikeRepository(session)
        self.matches = MatchRepository(session)

    async def next_candidate(self, viewer_id: int) -> Optional[User]:
        viewer = await self.users.get(viewer_id)
        if viewer is None:
            return None
        return await self.users.get_next_candidate(
            viewer, nearby_radius_km=settings.nearby_radius_km
        )

    async def react(self, from_user_id: int, to_user_id: int, liked: bool) -> MatchResult:
        was_already_liked = await self.likes.already_liked(from_user_id, to_user_id)
        await self.likes.add(from_user_id, to_user_id, liked)

        if liked:
            mutual = await self.likes.has_mutual_like(from_user_id, to_user_id)
            if mutual:
                already_matched = await self.matches.exists(from_user_id, to_user_id)
                if not already_matched:
                    await self.matches.create(from_user_id, to_user_id)
                    partner = await self.users.get(to_user_id)
                    await self.session.commit()
                    return MatchResult(matched=True, is_new_match=True,
                                       notify_like=False, partner=partner)
                await self.session.commit()
                return MatchResult(matched=True, is_new_match=False)

            await self.session.commit()
            return MatchResult(matched=False, notify_like=not was_already_liked)

        await self.session.commit()
        return MatchResult(matched=False, notify_like=False)

    async def get_matches(self, user_id: int) -> list[User]:
        return await self.matches.list_for_user(user_id)


class RatingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo    = RatingRepository(session)

    async def vote(self, voter_id: int, target_id: int, score: int) -> float:
        await self.repo.upsert(voter_id, target_id, score)
        await self.session.commit()
        return await self.repo.get_avg(target_id)
