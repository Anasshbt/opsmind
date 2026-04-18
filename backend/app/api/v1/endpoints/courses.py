import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.dependencies import get_current_user
from app.db.models.course import Course, Enrollment, Module, Quiz
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter(prefix="/courses", tags=["courses"])


class CourseRead(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    description: str | None
    domain: str
    difficulty: str
    is_published: bool
    estimated_hours: int
    model_config = {"from_attributes": True}


class ModuleRead(BaseModel):
    id: uuid.UUID
    title: str
    order: int
    content_md: str | None
    is_published: bool
    model_config = {"from_attributes": True}


class EnrollmentRead(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    progress_pct: int
    completed: bool
    model_config = {"from_attributes": True}


@router.get("/", response_model=list[CourseRead])
async def list_courses(
    domain: str | None = None,
    difficulty: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[Course]:
    stmt = select(Course).where(Course.is_published == True)  # noqa: E712
    if domain:
        stmt = stmt.where(Course.domain == domain)
    if difficulty:
        stmt = stmt.where(Course.difficulty == difficulty)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{slug}", response_model=CourseRead)
async def get_course(slug: str, db: AsyncSession = Depends(get_db)) -> Course:
    result = await db.execute(
        select(Course)
        .where(Course.slug == slug, Course.is_published == True)  # noqa: E712
        .options(selectinload(Course.modules))
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.get("/{course_id}/modules", response_model=list[ModuleRead])
async def get_modules(course_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[Module]:
    result = await db.execute(
        select(Module)
        .where(Module.course_id == course_id, Module.is_published == True)  # noqa: E712
        .order_by(Module.order)
    )
    return result.scalars().all()


@router.post("/{course_id}/enroll", response_model=EnrollmentRead, status_code=201)
async def enroll(
    course_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Enrollment:
    # Check already enrolled
    existing = (await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == current_user.id,
            Enrollment.course_id == course_id,
        )
    )).scalar_one_or_none()
    if existing:
        return existing

    course = await db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    enrollment = Enrollment(user_id=current_user.id, course_id=course_id)
    db.add(enrollment)
    await db.flush()
    return enrollment


@router.get("/my/enrollments", response_model=list[EnrollmentRead])
async def my_enrollments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Enrollment]:
    result = await db.execute(
        select(Enrollment).where(Enrollment.user_id == current_user.id)
    )
    return result.scalars().all()
