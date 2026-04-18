import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class ChallengeStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


class AttemptStatus(str, enum.Enum):
    INVITED = "invited"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    EVALUATED = "evaluated"
    EXPIRED = "expired"


class Enterprise(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "enterprises"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(512))
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    owner: Mapped["User"] = relationship("User")  # noqa: F821
    members: Mapped[list["EnterpriseMember"]] = relationship(
        "EnterpriseMember", back_populates="enterprise", cascade="all, delete-orphan"
    )
    challenges: Mapped[list["Challenge"]] = relationship(
        "Challenge", back_populates="enterprise", cascade="all, delete-orphan"
    )


class EnterpriseMember(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "enterprise_members"

    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("enterprises.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    enterprise: Mapped[Enterprise] = relationship("Enterprise", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="enterprise_membership")  # noqa: F821


class Challenge(Base, UUIDMixin, TimestampMixin):
    """
    An enterprise-created challenge composed of one or more labs.
    Candidates are invited via a unique link.
    """
    __tablename__ = "challenges"

    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("enterprises.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    instructions_md: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ChallengeStatus] = mapped_column(
        Enum(ChallengeStatus, name="challenge_status"), default=ChallengeStatus.DRAFT
    )

    # Time limits
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Labs included in this challenge
    lab_ids: Mapped[list] = mapped_column(JSONB, default=list)  # [uuid, ...]

    enterprise: Mapped[Enterprise] = relationship("Enterprise", back_populates="challenges")
    invites: Mapped[list["ChallengeInvite"]] = relationship(
        "ChallengeInvite", back_populates="challenge", cascade="all, delete-orphan"
    )
    attempts: Mapped[list["ChallengeAttempt"]] = relationship(
        "ChallengeAttempt", back_populates="challenge", cascade="all, delete-orphan"
    )


class ChallengeInvite(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "challenge_invites"

    challenge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)

    challenge: Mapped[Challenge] = relationship("Challenge", back_populates="invites")


class ChallengeAttempt(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "challenge_attempts"

    challenge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[AttemptStatus] = mapped_column(
        Enum(AttemptStatus, name="attempt_status"), default=AttemptStatus.INVITED
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_score: Mapped[int] = mapped_column(Integer, default=0)
    rank: Mapped[int | None] = mapped_column(Integer)

    challenge: Mapped[Challenge] = relationship("Challenge", back_populates="attempts")
    user: Mapped["User"] = relationship("User")  # noqa: F821


class Score(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "scores"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    lab_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lab_sessions.id", ondelete="CASCADE"), nullable=False
    )
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    max_points: Mapped[int] = mapped_column(Integer, default=0)
    time_bonus: Mapped[int] = mapped_column(Integer, default=0)
    attempts_penalty: Mapped[int] = mapped_column(Integer, default=0)
    final_score: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped["User"] = relationship("User", back_populates="scores")  # noqa: F821
