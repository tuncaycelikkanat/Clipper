"""backend/api/routes/videos.py — Video listing."""

from __future__ import annotations

import os
import sys

_R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _R not in sys.path:
    sys.path.insert(0, _R)

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from backend.deps import get_db

router = APIRouter(prefix="/videos", tags=["videos"])


def _db():
    return get_db()


class VideoPreviewRequest(BaseModel):
    url: str


@router.post("/preview")
async def preview_video(req: VideoPreviewRequest):
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="Geçerli bir video URL'si belirtilmelidir.")
    try:
        from core.extractor import YouTubeExtractor

        data = YouTubeExtractor.get_video_data(req.url.strip())
        duration = data.get("duration", 0)
        rec = YouTubeExtractor.calculate_recommended_clips(duration)
        return {
            "id": data.get("id"),
            "url": data.get("url"),
            "title": data.get("title"),
            "uploader": data.get("uploader"),
            "duration": duration,
            "duration_formatted": data.get("duration_formatted"),
            "thumbnail": data.get("thumbnail"),
            "view_count": data.get("view_count", 0),
            **rec,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("")
async def list_videos(limit: int = 50):
    db = _db()
    with db._connect() as conn:
        rows = conn.execute(
            """
            SELECT v.*, COUNT(c.id) as clip_count
            FROM videos v
            LEFT JOIN clips c ON c.video_id = v.id
            GROUP BY v.id
            ORDER BY v.processed_at DESC
            LIMIT ?
        """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/pending")
async def list_pending_videos():
    """List all videos with status 'pending'."""
    db = _db()
    with db._connect() as conn:
        rows = conn.execute("SELECT * FROM videos WHERE status = 'pending' ORDER BY rowid DESC").fetchall()
    return [dict(r) for r in rows]


@router.get("/{video_id}")
async def get_video(video_id: str):
    db = _db()
    video = db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    clips = db.get_clips_for_video(video_id)
    return {**video, "clips": clips}


class VideoDelayRequest(BaseModel):
    delay_hours: int = 24  # 0 to remove delay, 24 for 1 day delay


class BatchVideoDelayRequest(BaseModel):
    video_ids: list[str]
    delay_hours: int = 24


@router.post("/batch-delay")
async def batch_toggle_video_delay(body: BatchVideoDelayRequest):
    """Set or remove processing delay (e.g. 24 hours for comment accumulation) for multiple videos."""
    db = _db()
    for vid in body.video_ids:
        db.update_video_delay(vid, delay_hours=body.delay_hours)
    return {"success": True, "count": len(body.video_ids), "delay_hours": body.delay_hours}


@router.post("/{video_id}/delay")
async def toggle_video_delay(video_id: str, body: VideoDelayRequest):
    """Set or remove processing delay (e.g. 24 hours for comment accumulation) for a video."""
    db = _db()
    db.update_video_delay(video_id, delay_hours=body.delay_hours)
    video = db.get_video(video_id)
    return {"success": True, "video": video}


@router.delete("/{video_id}")
async def delete_video(video_id: str):
    db = _db()
    with db._connect() as conn:
        conn.execute("DELETE FROM clips WHERE video_id = ?", (video_id,))
        conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
        conn.commit()
    return {"deleted": True}


class BatchVideoDeleteRequest(BaseModel):
    video_ids: list[str] = []
    all_pending: bool = False


@router.post("/batch-delete")
async def batch_delete_videos(body: BatchVideoDeleteRequest):
    db = _db()
    with db._connect() as conn:
        if body.all_pending:
            conn.execute("DELETE FROM clips WHERE video_id IN (SELECT id FROM videos WHERE status = 'pending')")
            cur = conn.execute("DELETE FROM videos WHERE status = 'pending'")
            deleted = cur.rowcount
        elif body.video_ids:
            placeholders = ",".join("?" for _ in body.video_ids)
            conn.execute(f"DELETE FROM clips WHERE video_id IN ({placeholders})", body.video_ids)
            cur = conn.execute(f"DELETE FROM videos WHERE id IN ({placeholders})", body.video_ids)
            deleted = cur.rowcount
        else:
            deleted = 0
        conn.commit()
    return {"deleted_count": deleted}


@router.post("/{video_id}/thumbnail")
async def upload_video_thumbnail(video_id: str, file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Sadece resim dosyaları (.jpg, .png, .webp) yüklenebilir.")

    thumb_dir = os.path.join("outputs", "thumbnails")
    os.makedirs(thumb_dir, exist_ok=True)
    target_path = os.path.join(thumb_dir, f"thumb_{video_id}.jpg")

    # Read and save file using PIL for normalization to JPEG
    import io

    from PIL import Image

    content = await file.read()
    try:
        img = Image.open(io.BytesIO(content)).convert("RGB")
        img.save(target_path, "JPEG", quality=95)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Geçersiz görsel dosyası: {e}") from e

    db = _db()
    with db._connect() as conn:
        conn.execute(
            "UPDATE clips SET thumbnail_path = ? WHERE video_id = ? OR id LIKE ?",
            (target_path, video_id, f"{video_id}%"),
        )
        conn.execute(
            "UPDATE autopilot_queue SET thumbnail_path = ? WHERE video_id = ? OR clip_id LIKE ?",
            (target_path, video_id, f"{video_id}%"),
        )
        conn.commit()

        updated_count = conn.execute(
            "SELECT COUNT(*) FROM clips WHERE video_id = ? OR id LIKE ?", (video_id, f"{video_id}%")
        ).fetchone()[0]

    return {
        "success": True,
        "video_id": video_id,
        "thumbnail_path": target_path,
        "updated_clips_count": updated_count,
    }
