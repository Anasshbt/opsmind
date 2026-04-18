from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "OpsMind"
    ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: list[AnyHttpUrl] = []

    # ── Security ─────────────────────────────────────────────────────────────
    SECRET_KEY: str  # openssl rand -hex 32
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: PostgresDsn
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: RedisDsn = "redis://localhost:6379/0"  # type: ignore[assignment]
    REDIS_SESSION_DB: int = 1
    REDIS_CACHE_DB: int = 2

    # ── AI ───────────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"
    AI_MAX_TOKENS: int = 2048
    AI_TEMPERATURE: float = 0.3

    # ── Lab Orchestration ────────────────────────────────────────────────────
    ORCHESTRATOR: Literal["docker", "kubernetes"] = "docker"
    LAB_DEFAULT_CPU_LIMIT: str = "500m"      # Kubernetes CPU units
    LAB_DEFAULT_MEM_LIMIT: str = "512Mi"
    LAB_SESSION_TTL_SECONDS: int = 3600      # 1 hour
    LAB_MAX_SESSIONS_PER_USER: int = 2
    K8S_NAMESPACE: str = "opsmind-labs"
    K8S_IN_CLUSTER: bool = False
    K8S_KUBECONFIG_PATH: str | None = None

    # ── Docker (local dev) ───────────────────────────────────────────────────
    DOCKER_NETWORK: str = "opsmind_lab_net"
    DOCKER_IMAGE_PREFIX: str = "opsmind/lab"

    # ── Scoring ──────────────────────────────────────────────────────────────
    SCORING_TIMEOUT_SECONDS: int = 30

    # ── Enterprise ───────────────────────────────────────────────────────────
    ENTERPRISE_INVITE_EXPIRE_HOURS: int = 72

    # ── Rate Limiting ────────────────────────────────────────────────────────
    RATE_LIMIT_DEFAULT: str = "100/minute"
    RATE_LIMIT_AUTH: str = "10/minute"

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
