"""FastAPI application factory for Video DNA Analyzer."""

from __future__ import annotations

import hmac

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.router import api_router
from .container import settings
from .core.config import APP_NAME, APP_SLUG, APP_VERSION


def create_app() -> FastAPI:
    application = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        description="Video editing structure analysis and interchange API.",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost",
            "http://127.0.0.1",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "file://",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
    application.include_router(api_router)

    @application.get("/health", tags=["system"])
    def health() -> dict:
        return {
            "status": "ok",
            "service": APP_SLUG,
            "version": APP_VERSION,
            "auth_required": bool(settings.api_token),
        }

    @application.get("/", include_in_schema=False)
    def index(request: Request, token: str | None = None):
        response = FileResponse(settings.static_dir / "index.html")
        if settings.api_token and token and hmac.compare_digest(token, settings.api_token):
            response.set_cookie(
                "videodna_token",
                token,
                httponly=True,
                samesite="strict",
                secure=False,
            )
        return response

    return application


app = create_app()
