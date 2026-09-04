"""backend/api/routes/auth.py — YouTube OAuth2 flow."""

from __future__ import annotations

import os
import sys

_R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _R not in sys.path:
    sys.path.insert(0, _R)

from fastapi import APIRouter, HTTPException

from core.uploader import YouTubeUploader

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/youtube/status")
async def youtube_auth_status():
    try:
        uploader = YouTubeUploader()
        authenticated = uploader.is_authenticated()
        return {"authenticated": authenticated}
    except Exception as e:
        return {"authenticated": False, "error": str(e)}


@router.get("/youtube/url")
async def youtube_auth_url():
    """Returns instructions for OAuth2 — desktop app flow opens browser."""
    return {
        "message": "Desktop OAuth2 flow. Run authenticate() from the server.",
        "action": "call POST /api/auth/youtube/authenticate",
    }


@router.post("/youtube/authenticate")
async def youtube_authenticate():
    """Trigger the OAuth2 browser flow on the server side."""
    try:
        uploader = YouTubeUploader()
        uploader.authenticate()
        return {"success": True, "authenticated": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
