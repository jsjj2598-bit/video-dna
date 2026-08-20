"""Top-level API router composition."""

from fastapi import APIRouter

from .routes import analysis, components, exports, media, studio

api_router = APIRouter()
api_router.include_router(analysis.router)
api_router.include_router(media.router)
api_router.include_router(exports.router)
api_router.include_router(studio.router)
api_router.include_router(components.router)

