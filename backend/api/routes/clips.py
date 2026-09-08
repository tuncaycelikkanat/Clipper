"""backend/api/routes/clips.py — Clip CRUD + file serving."""

from __future__ import annotations

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


import contextlib

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.deps import get_db

router = APIRouter(prefix="/clips", tags=["clips"])


def _get_db():
    return get_db()


class ClipUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: str | None = None
    hook_caption: str | None = None


@router.get("")
async def list_clips(
    video_id: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    db = _get_db()
    with db._connect() as conn:
        if video_id:
            rows = conn.execute(
                "SELECT * FROM clips WHERE video_id = ? ORDER BY rank LIMIT ? OFFSET ?", (video_id, limit, offset)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM clips ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{clip_id}")
async def get_clip(clip_id: str):
    db = _get_db()
    with db._connect() as conn:
        row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Clip not found")
    return dict(row)


@router.patch("/{clip_id}")
async def update_clip(clip_id: str, body: ClipUpdateRequest):
    db = _get_db()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [clip_id]
    with db._connect() as conn:
        cur = conn.execute(f"UPDATE clips SET {set_clause} WHERE id = ?", values)
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Clip not found")
        row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    return dict(row)


@router.delete("/{clip_id}")
async def delete_clip(clip_id: str):
    db = _get_db()
    with db._connect() as conn:
        row = conn.execute("SELECT render_path FROM clips WHERE id = ?", (clip_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Clip not found")
        # Delete file if exists
        render_path = row["render_path"]
        if render_path and os.path.exists(render_path):
            with contextlib.suppress(Exception):
                os.remove(render_path)
        conn.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
        conn.execute("DELETE FROM autopilot_queue WHERE clip_id = ?", (clip_id,))
        conn.commit()
    return {"deleted": True}


class BatchDeleteRequest(BaseModel):
    clip_ids: list[str]


@router.post("/batch-delete")
async def batch_delete_clips(body: BatchDeleteRequest):
    if not body.clip_ids:
        return {"deleted_count": 0}
    db = _get_db()
    placeholders = ",".join("?" for _ in body.clip_ids)
    with db._connect() as conn:
        rows = conn.execute(
            f"SELECT render_path FROM clips WHERE id IN ({placeholders})",
            body.clip_ids,
        ).fetchall()
        for row in rows:
            rpath = row["render_path"]
            if rpath and os.path.exists(rpath):
                with contextlib.suppress(Exception):
                    os.remove(rpath)
        conn.execute(
            f"DELETE FROM autopilot_queue WHERE clip_id IN ({placeholders})",
            body.clip_ids,
        )
        cursor = conn.execute(
            f"DELETE FROM clips WHERE id IN ({placeholders})",
            body.clip_ids,
        )
        deleted = cursor.rowcount
        conn.commit()
    return {"deleted_count": deleted}


@router.get("/{clip_id}/file")
async def get_clip_file(clip_id: str):
    db = _get_db()
    with db._connect() as conn:
        row = conn.execute("SELECT render_path, title FROM clips WHERE id = ?", (clip_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Clip not found")
    path = row["render_path"]
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Render file not found")
    filename = os.path.basename(path)
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=filename,
        headers={"Accept-Ranges": "bytes"},
    )


@router.get("/{clip_id}/thumbnail")
async def get_clip_thumbnail(clip_id: str):
    db = _get_db()
    with db._connect() as conn:
        row = conn.execute(
            "SELECT thumbnail_path, render_path, video_id, start_time FROM clips WHERE id = ?", (clip_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Clip not found")

    path = row["thumbnail_path"] if row else None
    if path and os.path.exists(path) and os.path.getsize(path) > 0:
        return FileResponse(
            path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    # Render dosyası mevcutsa anında thumbnail üret ve kaydet
    render_path = row["render_path"] if row else None
    if render_path and os.path.exists(render_path):
        try:
            from core.thumbnail import ThumbnailGenerator

            out_dir = "outputs/thumbnails"
            os.makedirs(out_dir, exist_ok=True)
            out_path = f"{out_dir}/thumb_{clip_id}.jpg"
            ThumbnailGenerator.extract_best_frame(
                video_path=render_path,
                peak_time=1.0,
                output_path=out_path,
                width=720,
                height=1280,
            )
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                with db._connect() as conn:
                    conn.execute("UPDATE clips SET thumbnail_path = ? WHERE id = ?", (out_path, clip_id))
                    conn.commit()
                return FileResponse(
                    out_path,
                    media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=3600"},
                )
        except Exception as e:
            logger.debug("Auto-thumbnail extraction failed for {}: {}", clip_id, e)

    raise HTTPException(status_code=404, detail="Thumbnail not found")


@router.post("/{clip_id}/upload-video-thumbnail")
async def upload_clip_video_thumbnail(clip_id: str, file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Sadece resim dosyaları (.jpg, .png, .webp) yüklenebilir.")

    db = _get_db()
    with db._connect() as conn:
        row = conn.execute("SELECT video_id FROM clips WHERE id = ?", (clip_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Clip not found")

    video_id = row["video_id"]
    thumb_dir = os.path.join("outputs", "thumbnails")
    os.makedirs(thumb_dir, exist_ok=True)
    target_path = os.path.join(thumb_dir, f"thumb_{video_id}.jpg")

    import io

    from PIL import Image

    content = await file.read()
    try:
        img = Image.open(io.BytesIO(content)).convert("RGB")
        img.save(target_path, "JPEG", quality=95)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Geçersiz görsel dosyası: {e}")

    with db._connect() as conn:
        conn.execute(
            "UPDATE clips SET thumbnail_path = ? WHERE video_id = ? OR id = ?",
            (target_path, video_id, video_id),
        )
        conn.execute(
            "UPDATE autopilot_queue SET thumbnail_path = ? WHERE video_id = ? OR clip_id = ?",
            (target_path, video_id, video_id),
        )
        conn.commit()

        updated_count = conn.execute(
            "SELECT COUNT(*) FROM clips WHERE video_id = ? OR id = ?", (video_id, video_id)
        ).fetchone()[0]

    return {
        "success": True,
        "video_id": video_id,
        "thumbnail_path": target_path,
        "updated_clips_count": updated_count,
    }
