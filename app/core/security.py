"""Optional token authentication for deployments beyond localhost."""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status

from .config import get_settings


def require_api_token(request: Request) -> None:
    """Require ``X-VideoDNA-Token`` when VIDEODNA_API_TOKEN is configured."""
    expected = get_settings().api_token
    if not expected:
        return
    supplied = request.headers.get("X-VideoDNA-Token") or request.cookies.get("videodna_token", "")
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少或无效的 API Token")
