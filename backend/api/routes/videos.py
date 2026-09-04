"""backend/api/routes/videos.py — Video listing."""
from __future__ import annotations
import os, sys
_R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _R not in sys.path: sys.path.insert(0, _R)

from fastapi import APIRouter, HTTPException, UploadFile, File
from core.database import DatabaseManager

router = APIRouter(prefix="/videos", tags=["videos"])

def _db():
    db = DatabaseManager(); db.init_db(); return db


@router.get("")
async def list_videos(limit: int = 50):
    db = _db()
    with db._connect() as conn:
        rows = conn.execute("""
            SELECT v.*, COUNT(c.id) as clip_count
            FROM videos v
            LEFT JOIN clips c ON c.video_id = v.id
            GROUP BY v.id
            ORDER BY v.processed_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]


@router.get("/{video_id}")
async def get_video(video_id: str):
    db = _db()
    video = db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    clips = db.get_clips_for_video(video_id)
    return {**video, "clips": clips}


@router.post("/{video_id}/thumbnail")
async def upload_video_thumbnail(video_id: str, file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Sadece resim dosyaları (.jpg, .png, .webp) yüklenebilir.")

    thumb_dir = os.path.join("outputs", "thumbnails")
    os.makedirs(thumb_dir, exist_ok=True)
    target_path = os.path.join(thumb_dir, f"thumb_{video_id}.jpg")

    # Read and save file using PIL for normalization to JPEG
    from PIL import Image
    import io
    content = await file.read()
    try:
        img = Image.open(io.BytesIO(content)).convert("RGB")
        img.save(target_path, "JPEG", quality=95)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Geçersiz görsel dosyası: {e}")

    db = _db()
    with db._connect() as conn:
        conn.execute(
            "UPDATE clips SET thumbnail_path = ? WHERE video_id = ? OR id LIKE ?",
            (target_path, video_id, f"{video_id}%")
        )
        conn.execute(
            "UPDATE autopilot_queue SET thumbnail_path = ? WHERE video_id = ? OR clip_id LIKE ?",
            (target_path, video_id, f"{video_id}%")
        )
        conn.commit()

        updated_count = conn.execute(
            "SELECT COUNT(*) FROM clips WHERE video_id = ? OR id LIKE ?",
            (video_id, f"{video_id}%")
        ).fetchone()[0]

    return {
        "success": True,
        "video_id": video_id,
        "thumbnail_path": target_path,
        "updated_clips_count": updated_count,
    }
