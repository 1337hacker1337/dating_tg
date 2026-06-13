"""bot/services/profile.py — бизнес-логика профиля."""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import MAX_PHOTOS
from db.models import GenderEnum, LookingForEnum, User
from db.repositories.user_repo import UserRepository


class ProfileService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)

    async def register(self, user_id, username, name, age, gender, looking_for,
                       bio=None, latitude=None, longitude=None) -> User:
        user = await self.users.create(
            user_id=user_id, username=username, name=name, age=age,
            gender=GenderEnum(gender), looking_for=LookingForEnum(looking_for),
            bio=bio, latitude=latitude, longitude=longitude,
        )
        await self.session.commit()
        return user

    async def add_photo(self, user_id, file_id) -> bool:
        count = await self.users.count_photos(user_id)
        if count >= MAX_PHOTOS:
            return False
        await self.users.add_photo(user_id, file_id)
        await self.session.commit()
        return True

    async def get_profile(self, user_id) -> Optional[User]:
        return await self.users.get(user_id)

    async def update_location(self, user_id, lat, lon):
        await self.users.update_location(user_id, lat, lon)
        await self.session.commit()

    async def touch(self, user_id):
        await self.users.update_last_seen(user_id)
        await self.session.commit()
