"""backend/api/routes/upload.py — Platform upload endpoints."""
from __future__ import annotations
import os, sys
_R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _R not in sys.path: sys.path.insert(0, _R)

from fastapi import APIRouter, HTTPException
from core.database import DatabaseManager
from core.uploader import YouTubeUploader
from core.instagram_uploader import InstagramUploader

router = APIRouter(prefix="/upload", tags=["upload"])

def _db():
    db = DatabaseManager(); db.init_db(); return db


def _get_clip(clip_id: str):
    db = _db()
    with db._connect() as conn:
        row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Clip not found")
    return dict(row)


@router.post("/youtube/{clip_id}")
async def upload_youtube(clip_id: str):
    clip = _get_clip(clip_id)
    render_path = clip.get("render_path", "")
    if not render_path or not os.path.exists(render_path):
        raise HTTPException(status_code=400, detail="Render file not found")
    try:
        uploader = YouTubeUploader()
        if not uploader.is_authenticated():
            raise HTTPException(status_code=401, detail="YouTube not authenticated. Visit /api/auth/youtube/url")
        result = uploader.upload_short(
            video_path=render_path,
            title=clip.get("title", "Gaming Clip"),
            description=clip.get("description", ""),
            tags=(clip.get("tags", "") or "").split(","),
            thumbnail_path=clip.get("thumbnail_path"),
        )
        return {"success": True, "youtube_url": result.get("url"), "video_id": result.get("id")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/instagram/{clip_id}")
async def upload_instagram(clip_id: str):
    clip = _get_clip(clip_id)
    render_path = clip.get("render_path", "")
    if not render_path or not os.path.exists(render_path):
        raise HTTPException(status_code=400, detail="Render file not found")
    try:
        ig = InstagramUploader()
        result = ig.upload_reel(
            video_path=render_path,
            caption=clip.get("title", "") + "\n\n" + (clip.get("description", "") or ""),
            thumbnail_path=clip.get("thumbnail_path"),
        )
        return {"success": True, "instagram_url": result.get("url")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tiktok/{clip_id}")
async def upload_tiktok(clip_id: str):
    clip = _get_clip(clip_id)
    return {"success": False, "detail": "TikTok upload not yet implemented"}
