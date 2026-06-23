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
    city:         Mapped[Optional[str]]   = mapped_column(String(64), nullable=True)

    avg_rating:   Mapped[float] = mapped_column(Float,   default=0.0, nullable=False, server_default="0")
    rating_count: Mapped[int]   = mapped_column(Integer, default=0,   nullable=False, server_default="0")

    is_active:  Mapped[bool] = mapped_column(Boolean, default=True,  nullable=False)
    is_banned:  Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Пользователь может отключить все push-уведомления от бота
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="true"
    )

    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Рефералы ──────────────────────────────────────────────────
    # telegram_id того, кто пригласил (заполняется один раз при регистрации).
    # FK намеренно не ставим: реферер может удалить анкету, ссылка остаётся.
    referred_by:  Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    # бонусные свайпы (за рефералов), плюсуются к базовому SWIPE_LIMIT
    bonus_swipes: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )

    # ── SHROOM+ ───────────────────────────────────────────────────
    # дата окончания премиума (NULL = никогда не было)
    premium_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Фильтры поиска ────────────────────────────────────────────
    # возрастной диапазон (NULL = без ограничения) — доступно всем
    age_min: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    age_max: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    # максимальная дистанция в км (NULL = без ограничения) — фильтр SHROOM+
    max_distance_km: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)

    @property
    def is_premium(self) -> bool:
        from datetime import datetime, timezone
        return self.premium_until is not None and self.premium_until > datetime.now(tz=timezone.utc)

    photos: Mapped[list["Photo"]] = relationship(
        "Photo", back_populates="user", order_by="Photo.position"
    )

    __table_args__ = (
        CheckConstraint("age >= 14 AND age <= 99", name="ck_users_age"),
        Index("ix_users_active_banned", "is_active", "is_banned"),
        Index("ix_users_gender", "gender"),
        Index("ix_users_looking_for", "looking_for"),
        Index("ix_users_coords", "latitude", "longitude"),
        Index("ix_users_referred_by", "referred_by"),
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


class LikeMessage(Base):
    """Лайк с сообщением — короткая записка, отправляемая вместе с лайком."""
    __tablename__ = "like_messages"

    id:         Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_user:  Mapped[int]      = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    to_user:    Mapped[int]      = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    text:       Mapped[str]      = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_like_messages_from_created", "from_user", "created_at"),
        Index("ix_like_messages_to", "to_user"),
    )


class ProfileView(Base):
    """Кто смотрел анкету. Одна строка на пару (viewer, target), время обновляется."""
    __tablename__ = "profile_views"

    id:        Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    viewer_id: Mapped[int]      = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    target_id: Mapped[int]      = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("viewer_id", "target_id", name="uq_profile_views_pair"),
        Index("ix_profile_views_target_time", "target_id", "viewed_at"),
    )


class Admin(Base):
    __tablename__ = "admins"

    id:          Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int]           = mapped_column(BigInteger, unique=True, nullable=False)
    username:    Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    added_at:    Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())
    added_by:    Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("admins.id"), nullable=True)


class BotSettings(Base):
    """Хранилище настроек бота (key-value)."""
    __tablename__ = "bot_settings"

    key:   Mapped[str]           = mapped_column(String(64), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ReportReasonEnum(str, enum.Enum):
    spam   = "spam"
    nudity = "nudity"
    other  = "other"


class Report(Base):
    __tablename__ = "reports"

    id:          Mapped[int]              = mapped_column(Integer, primary_key=True, autoincrement=True)
    reporter_id: Mapped[int]              = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    target_id:   Mapped[int]              = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    reason:      Mapped[ReportReasonEnum] = mapped_column(Enum(ReportReasonEnum), nullable=False)
    is_reviewed: Mapped[bool]             = mapped_column(Boolean, default=False, nullable=False)
    created_at:  Mapped[datetime]         = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("reporter_id", "target_id", name="uq_reports_pair"),
        Index("ix_reports_target",   "target_id"),
        Index("ix_reports_reviewed", "is_reviewed"),
    )
