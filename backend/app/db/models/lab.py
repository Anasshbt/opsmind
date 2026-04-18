import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class LabEnvironment(str, enum.Enum):
    DOCKER = "docker"
    KUBERNETES = "kubernetes"


class LabSessionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    EXPIRED = "expired"


class Lab(Base, UUIDMixin, TimestampMixin):
    """
    Lab definition — describes what container/pod to spin up,
    what tasks to validate, what resources to allocate.
    """
    __tablename__ = "labs"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    instructions_md: Mapped[str | None] = mapped_column(Text)

    # Container image to use
    image: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[LabEnvironment] = mapped_column(
        Enum(LabEnvironment, name="lab_environment"), default=LabEnvironment.DOCKER
    )

    # Resource limits
    cpu_limit: Mapped[str] = mapped_column(String(16), default="500m")
    memory_limit: Mapped[str] = mapped_column(String(16), default="512Mi")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=3600)

    # Environment variables injected into the container
    env_vars: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Validation tasks (list of scripts/checks)
    tasks: Mapped[list["LabTask"]] = relationship(
        "LabTask", back_populates="lab", cascade="all, delete-orphan", order_by="LabTask.order"
    )
    sessions: Mapped[list["LabSession"]] = relationship(
        "LabSession", back_populates="lab"
    )


class LabTask(Base, UUIDMixin):
    """
    A single validation step inside a lab.
    The scoring engine runs the check_script inside the user container.
    """
    __tablename__ = "lab_tasks"

    lab_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("labs.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    order: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=10)

    # Shell script that returns 0 on success
    check_script: Mapped[str] = mapped_column(Text, nullable=False)

    lab: Mapped[Lab] = relationship("Lab", back_populates="tasks")


class LabSession(Base, UUIDMixin, TimestampMixin):
    """
    A running instance of a lab for a specific user.
    """
    __tablename__ = "lab_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    lab_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("labs.id", ondelete="CASCADE"), nullable=False
    )

    # Runtime info set by the orchestrator
    container_id: Mapped[str | None] = mapped_column(String(128))  # docker or k8s pod name
    container_ip: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[LabSessionStatus] = mapped_column(
        Enum(LabSessionStatus, name="lab_session_status"),
        default=LabSessionStatus.PENDING,
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Optional: enterprise challenge context
    challenge_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("challenge_attempts.id", ondelete="SET NULL")
    )

    user: Mapped["User"] = relationship("User", back_populates="lab_sessions")  # noqa: F821
    lab: Mapped[Lab] = relationship("Lab", back_populates="sessions")
    task_results: Mapped[list["TaskResult"]] = relationship(
        "TaskResult", back_populates="session", cascade="all, delete-orphan"
    )


class TaskResult(Base, UUIDMixin, TimestampMixin):
    """Records which lab tasks a user has passed."""
    __tablename__ = "task_results"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lab_sessions.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lab_tasks.id", ondelete="CASCADE"), nullable=False
    )
    passed: Mapped[bool] = mapped_column(default=False)
    points_earned: Mapped[int] = mapped_column(Integer, default=0)
    output: Mapped[str | None] = mapped_column(Text)  # stdout/stderr of check script

    session: Mapped[LabSession] = relationship("LabSession", back_populates="task_results")
    task: Mapped[LabTask] = relationship("LabTask")
