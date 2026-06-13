"""bot/services/browse.py — реакции, мэтчи, выдача кандидатов."""
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import User
from db.repositories.user_repo import UserRepository
from db.repositories.like_repo import LikeRepository, MatchRepository


@dataclass
class MatchResult:
    matched:      bool
    is_new_match: bool = False
    notify_like:  bool = False
    partner:      Optional[User] = None


class BrowseService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)
        self.likes = LikeRepository(session)
        self.matches = MatchRepository(session)

    async def next_candidate(self, viewer_id) -> Optional[User]:
        viewer = await self.users.get(viewer_id)
        if viewer is None:
            return None
        return await self.users.get_next_candidate(
            viewer, nearby_radius_km=settings.nearby_radius_km
        )

    async def react(self, from_user_id, to_user_id, liked) -> MatchResult:
        had_prev_reaction = await self.likes.reaction_exists(from_user_id, to_user_id)
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
            return MatchResult(matched=False, notify_like=not had_prev_reaction)
        await self.session.commit()
        return MatchResult(matched=False, notify_like=False)

    async def get_matches(self, user_id) -> list[User]:
        return await self.matches.list_for_user(user_id)
