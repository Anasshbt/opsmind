from fastapi import APIRouter

from app.api.v1.endpoints import ai, auth, courses, enterprise, labs

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(courses.router)
api_router.include_router(labs.router)
api_router.include_router(ai.router)
api_router.include_router(enterprise.router)
