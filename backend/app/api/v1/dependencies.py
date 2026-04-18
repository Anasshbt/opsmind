"""FastAPI dependency injection."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis, from_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import JWTError, decode_token
from app.db.models.user import User, UserRole
from app.db.session import get_db

logger = structlog.get_logger(__name__)
bearer = HTTPBearer()

# ── Redis pool (singleton) ────────────────────────────────────────────────────
_redis_pool: Redis | None = None


async def get_redis() -> AsyncGenerator[Redis, None]:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = from_url(str(settings.REDIS_URL), decode_responses=True)
    yield _redis_pool


# ── Auth ──────────────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise JWTError("not an access token")
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


def require_role(*roles: UserRole):
    """Factory that returns a dependency enforcing one of the given roles."""
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user
    return _check


require_admin = require_role(UserRole.ADMIN)
require_enterprise = require_role(UserRole.ENTERPRISE, UserRole.ADMIN)
