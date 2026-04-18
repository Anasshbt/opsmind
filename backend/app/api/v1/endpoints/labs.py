"""
Lab endpoints — start/stop/status for lab sessions + WebSocket terminal.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, get_redis
from app.core.security import decode_token, JWTError
from app.db.models.lab import Lab, LabSession, LabSessionStatus
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.lab import (
    LabRead,
    LabScoreRead,
    LabSessionCreate,
    LabSessionRead,
    LabTaskRead,
    TaskCheckRequest,
    TaskCheckResult,
)
from app.services.lab.session_manager import SessionManager
from app.services.lab.terminal import get_terminal_handler
from app.services.scoring.engine import ScoringEngine

router = APIRouter(prefix="/labs", tags=["labs"])


@router.get("/", response_model=list[LabRead])
async def list_labs(db: AsyncSession = Depends(get_db)) -> list[Lab]:
    result = await db.execute(select(Lab))
    return result.scalars().all()


@router.get("/{lab_id}", response_model=LabRead)
async def get_lab(lab_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Lab:
    lab = await db.get(Lab, lab_id)
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    return lab


@router.get("/{lab_id}/tasks", response_model=list[LabTaskRead])
async def get_lab_tasks(lab_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list:
    from app.db.models.lab import LabTask
    result = await db.execute(
        select(LabTask).where(LabTask.lab_id == lab_id).order_by(LabTask.order)
    )
    return result.scalars().all()


# ── Sessions ──────────────────────────────────────────────────────────────────

@router.post("/sessions", response_model=LabSessionRead, status_code=status.HTTP_201_CREATED)
async def start_session(
    body: LabSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> LabSession:
    mgr = SessionManager(db=db, redis=redis)
    try:
        session = await mgr.start_session(user_id=current_user.id, lab_id=body.lab_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return session


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def stop_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> None:
    mgr = SessionManager(db=db, redis=redis)
    try:
        await mgr.stop_session(session_id=session_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/sessions/{session_id}", response_model=LabSessionRead)
async def get_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> LabSession:
    mgr = SessionManager(db=db, redis=redis)
    try:
        return await mgr.get_session(session_id=session_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ── Scoring ───────────────────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/check-task", response_model=TaskCheckResult)
async def check_task(
    session_id: uuid.UUID,
    body: TaskCheckRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskCheckResult:
    engine = ScoringEngine(db=db)
    try:
        result = await engine.check_task(
            session_id=session_id,
            task_id=body.task_id,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return TaskCheckResult(
        task_id=result.task_id,
        passed=result.passed,
        points_earned=result.points_earned,
        output=result.output or "",
    )


@router.post("/sessions/{session_id}/submit", response_model=LabScoreRead)
async def submit_lab(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> LabScoreRead:
    engine = ScoringEngine(db=db)
    mgr = SessionManager(db=db, redis=redis)
    try:
        score = await engine.finalize_score(session_id=session_id, user_id=current_user.id)
        await mgr.stop_session(session_id=session_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return LabScoreRead(
        total_points=score.total_points,
        max_points=score.max_points,
        final_score=score.final_score,
        time_bonus=score.time_bonus,
        attempts_penalty=score.attempts_penalty,
        tasks_passed=0,  # compute in real impl
        tasks_total=0,
    )


# ── WebSocket Terminal ────────────────────────────────────────────────────────

@router.websocket("/sessions/{session_id}/terminal")
async def terminal_ws(
    websocket: WebSocket,
    session_id: uuid.UUID,
    token: str,  # passed as query param: ?token=<jwt>
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    WebSocket endpoint for xterm.js browser terminal.
    Authentication via JWT query parameter (can't set headers on WS).
    """
    # Authenticate
    try:
        payload = decode_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, ValueError):
        await websocket.close(code=4401, reason="Unauthorized")
        return

    # Validate session ownership
    result = await db.execute(
        select(LabSession).where(
            LabSession.id == session_id,
            LabSession.user_id == user_id,
            LabSession.status == LabSessionStatus.RUNNING,
        )
    )
    session = result.scalar_one_or_none()
    if not session or not session.container_id:
        await websocket.close(code=4404, reason="Session not found or not running")
        return

    await websocket.accept()

    try:
        await get_terminal_handler(websocket, session.container_id)
    except WebSocketDisconnect:
        pass
