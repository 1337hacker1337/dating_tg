from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, Enum,
    Float, ForeignKey, Index, Integer, SmallInteger, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class Base(DeclarativeBase):
    pass


class GenderEnum(str, enum.Enum):
    male   = "male"
    female = "female"
    other  = "other"


class LookingForEnum(str, enum.Enum):
    male   = "male"
    female = "female"
    any    = "any"


class User(Base):
    __tablename__ = "users"

    id:           Mapped[int]            = mapped_column(BigInteger, primary_key=True)
    username:     Mapped[Optional[str]]  = mapped_column(String(64),  nullable=True)
    name:         Mapped[str]            = mapped_column(String(64),  nullable=False)
    age:          Mapped[int]            = mapped_column(SmallInteger, nullable=False)
    gender:       Mapped[GenderEnum]     = mapped_column(Enum(GenderEnum),     nullable=False)
    looking_for:  Mapped[LookingForEnum] = mapped_column(Enum(LookingForEnum), nullable=False)
    bio:          Mapped[Optional[str]]  = mapped_column(Text, nullable=True)

    latitude:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    avg_rating:   Mapped[float] = mapped_column(Float,   default=0.0, nullable=False, server_default="0")
    rating_count: Mapped[int]   = mapped_column(Integer, default=0,   nullable=False, server_default="0")

    is_active:  Mapped[bool] = mapped_column(Boolean, default=True,  nullable=False)
    is_banned:  Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    photos:  Mapped[list["Photo"]]  = relationship(
        "Photo", back_populates="user", order_by="Photo.position"
    )
    ratings: Mapped[list["Rating"]] = relationship(
        "Rating", back_populates="target", foreign_keys="Rating.target_id"
    )

    __table_args__ = (
        CheckConstraint("age >= 14 AND age <= 99", name="ck_users_age"),
        Index("ix_users_active_banned", "is_active", "is_banned"),
        Index("ix_users_gender", "gender"),
        Index("ix_users_looking_for", "looking_for"),
        Index("ix_users_coords", "latitude", "longitude"),
    )


class Photo(Base):
    __tablename__ = "photos"

    id:         Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:    Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    file_id:    Mapped[str] = mapped_column(String(256), nullable=False)
    position:   Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="photos")


class Like(Base):
    __tablename__ = "likes"

    id:        Mapped[int]  = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_user: Mapped[int]  = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    to_user:   Mapped[int]  = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    value:     Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("from_user", "to_user", name="uq_likes_pair"),
        Index("ix_likes_from_user", "from_user"),
        Index("ix_likes_to_user", "to_user"),
    )


class Match(Base):
    __tablename__ = "matches"

    id:       Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user1_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    user2_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user1_id", "user2_id", name="uq_matches_pair"),
        CheckConstraint("user1_id < user2_id", name="ck_matches_order"),
    )


class Rating(Base):
    __tablename__ = "ratings"

    id:        Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    voter_id:  Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    target_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    score:     Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    target: Mapped["User"] = relationship(
        "User", back_populates="ratings", foreign_keys=[target_id]
    )

    __table_args__ = (
        UniqueConstraint("voter_id", "target_id", name="uq_ratings_pair"),
        CheckConstraint("score >= 1 AND score <= 10", name="ck_rating_score"),
    )


class Admin(Base):
    __tablename__ = "admins"

    id:          Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int]           = mapped_column(BigInteger, unique=True, nullable=False)
    username:    Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    added_at:    Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())
    added_by:    Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("admins.id"), nullable=True)
