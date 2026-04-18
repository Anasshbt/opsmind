"""
Enterprise module endpoints.

Covers:
  - Enterprise CRUD
  - Challenge builder
  - Candidate invite flow
  - Attempt tracking
  - Leaderboard
  - Analytics
"""
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, require_enterprise
from app.core.config import settings
from app.db.models.enterprise import (
    AttemptStatus,
    Challenge,
    ChallengeAttempt,
    ChallengeInvite,
    ChallengeStatus,
    Enterprise,
)
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter(prefix="/enterprise", tags=["enterprise"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class EnterpriseCreate(BaseModel):
    name: str
    slug: str


class EnterpriseRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    model_config = {"from_attributes": True}


class ChallengeCreate(BaseModel):
    title: str
    description: str | None = None
    instructions_md: str | None = None
    duration_minutes: int = 60
    lab_ids: list[uuid.UUID] = []
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class ChallengeRead(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    status: ChallengeStatus
    duration_minutes: int
    lab_ids: list
    model_config = {"from_attributes": True}


class InviteRequest(BaseModel):
    emails: list[EmailStr]


class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    total_score: int
    submitted_at: datetime | None


# ── Enterprise CRUD ───────────────────────────────────────────────────────────

@router.post("/", response_model=EnterpriseRead, status_code=201)
async def create_enterprise(
    body: EnterpriseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Enterprise:
    existing = (await db.execute(
        select(Enterprise).where(Enterprise.slug == body.slug)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Slug already taken")

    ent = Enterprise(name=body.name, slug=body.slug, owner_id=current_user.id)
    db.add(ent)
    await db.flush()
    return ent


@router.get("/{enterprise_id}", response_model=EnterpriseRead)
async def get_enterprise(
    enterprise_id: uuid.UUID,
    _: User = Depends(require_enterprise),
    db: AsyncSession = Depends(get_db),
) -> Enterprise:
    ent = await db.get(Enterprise, enterprise_id)
    if not ent:
        raise HTTPException(status_code=404)
    return ent


# ── Challenges ────────────────────────────────────────────────────────────────

@router.post("/{enterprise_id}/challenges", response_model=ChallengeRead, status_code=201)
async def create_challenge(
    enterprise_id: uuid.UUID,
    body: ChallengeCreate,
    current_user: User = Depends(require_enterprise),
    db: AsyncSession = Depends(get_db),
) -> Challenge:
    ent = await db.get(Enterprise, enterprise_id)
    if not ent or ent.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your enterprise")

    challenge = Challenge(
        enterprise_id=enterprise_id,
        title=body.title,
        description=body.description,
        instructions_md=body.instructions_md,
        duration_minutes=body.duration_minutes,
        lab_ids=[str(lid) for lid in body.lab_ids],
        starts_at=body.starts_at,
        ends_at=body.ends_at,
    )
    db.add(challenge)
    await db.flush()
    return challenge


@router.get("/{enterprise_id}/challenges", response_model=list[ChallengeRead])
async def list_challenges(
    enterprise_id: uuid.UUID,
    current_user: User = Depends(require_enterprise),
    db: AsyncSession = Depends(get_db),
) -> list[Challenge]:
    result = await db.execute(
        select(Challenge).where(Challenge.enterprise_id == enterprise_id)
    )
    return result.scalars().all()


@router.patch("/{enterprise_id}/challenges/{challenge_id}/publish", response_model=ChallengeRead)
async def publish_challenge(
    enterprise_id: uuid.UUID,
    challenge_id: uuid.UUID,
    current_user: User = Depends(require_enterprise),
    db: AsyncSession = Depends(get_db),
) -> Challenge:
    challenge = await db.get(Challenge, challenge_id)
    if not challenge or challenge.enterprise_id != enterprise_id:
        raise HTTPException(status_code=404)
    challenge.status = ChallengeStatus.ACTIVE
    return challenge


# ── Invites ───────────────────────────────────────────────────────────────────

@router.post("/{enterprise_id}/challenges/{challenge_id}/invite", status_code=201)
async def invite_candidates(
    enterprise_id: uuid.UUID,
    challenge_id: uuid.UUID,
    body: InviteRequest,
    current_user: User = Depends(require_enterprise),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    challenge = await db.get(Challenge, challenge_id)
    if not challenge or challenge.enterprise_id != enterprise_id:
        raise HTTPException(status_code=404)

    expires_at = datetime.now(UTC) + timedelta(hours=settings.ENTERPRISE_INVITE_EXPIRE_HOURS)
    links = []
    for email in body.emails:
        token = secrets.token_urlsafe(32)
        invite = ChallengeInvite(
            challenge_id=challenge_id,
            email=email,
            token=token,
            expires_at=expires_at,
        )
        db.add(invite)
        links.append(f"/challenges/join/{token}")

    return {"invite_links": links}


@router.post("/join/{invite_token}", status_code=201)
async def accept_invite(
    invite_token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    invite = (await db.execute(
        select(ChallengeInvite).where(
            ChallengeInvite.token == invite_token,
            ChallengeInvite.accepted == False,  # noqa: E712
        )
    )).scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found or already used")
    if invite.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Invite expired")

    invite.accepted = True

    attempt = ChallengeAttempt(
        challenge_id=invite.challenge_id,
        user_id=current_user.id,
        status=AttemptStatus.IN_PROGRESS,
        started_at=datetime.now(UTC),
    )
    db.add(attempt)
    await db.flush()

    return {"attempt_id": str(attempt.id), "challenge_id": str(invite.challenge_id)}


# ── Leaderboard ───────────────────────────────────────────────────────────────

@router.get("/{enterprise_id}/challenges/{challenge_id}/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(
    enterprise_id: uuid.UUID,
    challenge_id: uuid.UUID,
    _: User = Depends(require_enterprise),
    db: AsyncSession = Depends(get_db),
) -> list[LeaderboardEntry]:
    stmt = (
        select(ChallengeAttempt, User)
        .join(User, User.id == ChallengeAttempt.user_id)
        .where(ChallengeAttempt.challenge_id == challenge_id)
        .order_by(ChallengeAttempt.total_score.desc(), ChallengeAttempt.submitted_at.asc())
    )
    rows = (await db.execute(stmt)).all()

    return [
        LeaderboardEntry(
            rank=idx + 1,
            username=user.username,
            total_score=attempt.total_score,
            submitted_at=attempt.submitted_at,
        )
        for idx, (attempt, user) in enumerate(rows)
    ]


# ── Analytics ─────────────────────────────────────────────────────────────────

@router.get("/{enterprise_id}/challenges/{challenge_id}/analytics")
async def challenge_analytics(
    enterprise_id: uuid.UUID,
    challenge_id: uuid.UUID,
    _: User = Depends(require_enterprise),
    db: AsyncSession = Depends(get_db),
) -> dict:
    total = (await db.execute(
        select(func.count()).where(ChallengeAttempt.challenge_id == challenge_id)
    )).scalar()
    completed = (await db.execute(
        select(func.count()).where(
            ChallengeAttempt.challenge_id == challenge_id,
            ChallengeAttempt.status == AttemptStatus.SUBMITTED,
        )
    )).scalar()
    avg_score = (await db.execute(
        select(func.avg(ChallengeAttempt.total_score)).where(
            ChallengeAttempt.challenge_id == challenge_id,
            ChallengeAttempt.status == AttemptStatus.SUBMITTED,
        )
    )).scalar()

    return {
        "total_candidates": total,
        "completed": completed,
        "completion_rate": round((completed / total * 100) if total else 0, 1),
        "average_score": round(avg_score or 0, 1),
    }
