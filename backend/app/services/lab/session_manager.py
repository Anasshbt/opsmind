"""
Session manager — high-level CRUD on top of the orchestrator.
Persists session state to PostgreSQL and caches active sessions in Redis.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.lab import Lab, LabSession, LabSessionStatus
from app.services.lab.orchestrator import OrchestratorBase, get_orchestrator

logger = structlog.get_logger(__name__)

SESSION_KEY = "lab_session:{session_id}"
USER_SESSIONS_KEY = "user_sessions:{user_id}"


class SessionManager:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self._db = db
        self._redis = redis
        self._orch: OrchestratorBase = get_orchestrator()

    async def start_session(self, user_id: uuid.UUID, lab_id: uuid.UUID) -> LabSession:
        # Enforce per-user session cap
        active = await self._count_active_sessions(user_id)
        if active >= settings.LAB_MAX_SESSIONS_PER_USER:
            raise ValueError(
                f"Maximum concurrent sessions ({settings.LAB_MAX_SESSIONS_PER_USER}) reached"
            )

        lab = await self._db.get(Lab, lab_id)
        if not lab:
            raise ValueError(f"Lab {lab_id} not found")

        # Create DB record (PENDING)
        session = LabSession(
            user_id=user_id,
            lab_id=lab_id,
            status=LabSessionStatus.PENDING,
        )
        self._db.add(session)
        await self._db.flush()  # get the PK

        try:
            info = await self._orch.create_session(
                session_id=session.id,
                image=lab.image,
                cpu_limit=lab.cpu_limit,
                memory_limit=lab.memory_limit,
                timeout_seconds=lab.timeout_seconds,
                env_vars=dict(lab.env_vars),
            )
        except Exception as exc:
            session.status = LabSessionStatus.FAILED
            await self._db.flush()
            logger.error("session_start_failed", session_id=str(session.id), error=str(exc))
            raise

        session.container_id = info.container_id
        session.container_ip = info.container_ip
        session.status = LabSessionStatus.RUNNING
        session.started_at = datetime.now(UTC)
        session.expires_at = info.expires_at

        # Cache in Redis for fast lookup
        await self._cache_session(session)
        await self._redis.sadd(USER_SESSIONS_KEY.format(user_id=str(user_id)), str(session.id))

        logger.info("session_started", session_id=str(session.id), user=str(user_id))
        return session

    async def stop_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> None:
        session = await self._get_owned_session(session_id, user_id)
        if session.status not in (LabSessionStatus.RUNNING, LabSessionStatus.PENDING):
            return

        session.status = LabSessionStatus.STOPPING
        await self._db.flush()

        if session.container_id:
            await self._orch.destroy_session(session.container_id)

        session.status = LabSessionStatus.STOPPED
        session.stopped_at = datetime.now(UTC)

        await self._redis.delete(SESSION_KEY.format(session_id=str(session_id)))
        await self._redis.srem(USER_SESSIONS_KEY.format(user_id=str(user_id)), str(session_id))
        logger.info("session_stopped", session_id=str(session_id))

    async def get_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> LabSession:
        return await self._get_owned_session(session_id, user_id)

    async def expire_stale_sessions(self) -> int:
        """Called by the background worker. Returns number of sessions expired."""
        now = datetime.now(UTC)
        stmt = select(LabSession).where(
            LabSession.status == LabSessionStatus.RUNNING,
            LabSession.expires_at <= now,
        )
        result = await self._db.execute(stmt)
        sessions = result.scalars().all()
        count = 0
        for s in sessions:
            try:
                if s.container_id:
                    await self._orch.destroy_session(s.container_id)
                s.status = LabSessionStatus.EXPIRED
                s.stopped_at = now
                count += 1
            except Exception as exc:
                logger.error("expire_session_error", session_id=str(s.id), error=str(exc))
        if count:
            logger.info("sessions_expired", count=count)
        return count

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _count_active_sessions(self, user_id: uuid.UUID) -> int:
        key = USER_SESSIONS_KEY.format(user_id=str(user_id))
        return await self._redis.scard(key)

    async def _get_owned_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> LabSession:
        result = await self._db.execute(
            select(LabSession).where(
                LabSession.id == session_id,
                LabSession.user_id == user_id,
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise ValueError("Session not found or access denied")
        return session

    async def _cache_session(self, session: LabSession) -> None:
        key = SESSION_KEY.format(session_id=str(session.id))
        await self._redis.hset(key, mapping={
            "container_id": session.container_id or "",
            "user_id": str(session.user_id),
            "status": session.status.value,
        })
        if session.expires_at:
            ttl = int((session.expires_at - datetime.now(UTC)).total_seconds())
            await self._redis.expire(key, ttl)
