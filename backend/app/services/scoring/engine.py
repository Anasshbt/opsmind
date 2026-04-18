"""
Scoring Engine

Validates lab tasks by executing check scripts inside the user's container.
Calculates final score with time bonus and attempt penalty.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.lab import LabSession, LabSessionStatus, LabTask, TaskResult
from app.db.models.enterprise import Score
from app.services.lab.orchestrator import get_orchestrator

logger = structlog.get_logger(__name__)

TIME_BONUS_MAX_PERCENT = 20     # up to 20% bonus for speed
ATTEMPT_PENALTY_PERCENT = 5     # 5% penalty per extra attempt after first


class ScoringEngine:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._orch = get_orchestrator()

    async def check_task(
        self,
        session_id: uuid.UUID,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> TaskResult:
        """
        Run the check script for a single task inside the user's container.
        Returns a TaskResult (persisted to DB).
        """
        session = await self._load_session(session_id, user_id)
        task = await self._db.get(LabTask, task_id)
        if not task or str(task.lab_id) != str(session.lab_id):
            raise ValueError("Task not found in this lab")

        if not session.container_id:
            raise ValueError("Session has no running container")

        exit_code, output = await self._orch.exec_command(
            container_id=session.container_id,
            command=task.check_script,
        )

        passed = exit_code == 0
        points = task.points if passed else 0

        # Upsert TaskResult
        result = await self._get_or_create_task_result(session_id, task_id)
        result.passed = passed
        result.points_earned = points
        result.output = output[:4096]  # cap stored output

        logger.info(
            "task_checked",
            session=str(session_id),
            task=str(task_id),
            passed=passed,
            exit_code=exit_code,
        )
        return result

    async def finalize_score(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Score:
        """
        Aggregate all TaskResults for a session and compute the final Score.
        Called when a user submits or when the session expires.
        """
        session = await self._load_session(session_id, user_id)

        # Fetch all tasks and results
        stmt = select(LabTask).where(LabTask.lab_id == session.lab_id)
        tasks = (await self._db.execute(stmt)).scalars().all()

        stmt2 = select(TaskResult).where(TaskResult.session_id == session_id)
        results = {r.task_id: r for r in (await self._db.execute(stmt2)).scalars().all()}

        max_points = sum(t.points for t in tasks)
        total_earned = sum(r.points_earned for r in results.values() if r.passed)
        tasks_passed = sum(1 for r in results.values() if r.passed)

        # Time bonus: reward finishing early
        time_bonus = 0
        if session.started_at and session.lab:
            elapsed = (datetime.now(UTC) - session.started_at).total_seconds()
            allotted = session.lab.timeout_seconds
            ratio = max(0.0, 1.0 - elapsed / allotted)
            time_bonus = int(max_points * (TIME_BONUS_MAX_PERCENT / 100) * ratio)

        final = min(total_earned + time_bonus, max_points)

        score = Score(
            user_id=user_id,
            lab_session_id=session_id,
            total_points=total_earned,
            max_points=max_points,
            time_bonus=time_bonus,
            attempts_penalty=0,
            final_score=final,
        )
        self._db.add(score)
        logger.info(
            "score_finalized",
            session=str(session_id),
            final=final,
            max=max_points,
            passed=tasks_passed,
        )
        return score

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _load_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> LabSession:
        stmt = (
            select(LabSession)
            .where(LabSession.id == session_id, LabSession.user_id == user_id)
        )
        session = (await self._db.execute(stmt)).scalar_one_or_none()
        if not session:
            raise ValueError("Session not found or access denied")
        if session.status != LabSessionStatus.RUNNING:
            raise ValueError(f"Session is not running (status={session.status})")
        return session

    async def _get_or_create_task_result(
        self, session_id: uuid.UUID, task_id: uuid.UUID
    ) -> TaskResult:
        stmt = select(TaskResult).where(
            TaskResult.session_id == session_id,
            TaskResult.task_id == task_id,
        )
        existing = (await self._db.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing
        new_result = TaskResult(session_id=session_id, task_id=task_id)
        self._db.add(new_result)
        await self._db.flush()
        return new_result
