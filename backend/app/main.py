"""
OpsMind FastAPI application entry point.
"""
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, logger
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    logger.info("opsmind_starting", env=settings.ENV, version="0.1.0")

    # Verify DB connection
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: c.execute(__import__("sqlalchemy").text("SELECT 1")))
    logger.info("db_connected")

    yield

    # Cleanup
    await engine.dispose()
    logger.info("opsmind_shutdown")


limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_DEFAULT])

app = FastAPI(
    title="OpsMind API",
    version="0.1.0",
    description="AI-powered DevOps learning platform",
    docs_url="/api/docs" if settings.ENV != "production" else None,
    redoc_url="/api/redoc" if settings.ENV != "production" else None,
    openapi_url="/api/openapi.json" if settings.ENV != "production" else None,
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# Prometheus metrics (internal — protect with network policy in prod)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/health", tags=["observability"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


# ── Global error handlers ─────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )
