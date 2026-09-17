"""backend/api/routes/channels.py — Channel CRUD."""

from __future__ import annotations

import os
import sys

_R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _R not in sys.path:
    sys.path.insert(0, _R)


from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.deps import get_db

router = APIRouter(prefix="/channels", tags=["channels"])


def _db():
    return get_db()


class ChannelCreateRequest(BaseModel):
    url: str
    name: str
    min_score: int = 90
    auto_upload: bool = True
    check_interval_h: float = 2.0
    target_playlist: str | None = None
    youtube_username: str | None = None
    instagram_username: str | None = None


class ChannelUpdateRequest(BaseModel):
    name: str | None = None
    min_score: int | None = None
    auto_upload: bool | None = None
    active: bool | None = None
    check_interval_h: float | None = None
    youtube_username: str | None = None
    instagram_username: str | None = None


@router.get("")
async def list_channels(is_tracked: bool | None = None, active_only: bool = False):
    db = _db()
    with db._connect() as conn:
        sql = "SELECT * FROM tracked_channels"
        conds = []
        if is_tracked is not None:
            conds.append("active = 1" if is_tracked else "active = 0")
        if active_only:
            conds.append("active = 1")
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def create_channel(body: ChannelCreateRequest):
    db = _db()
    channel_id = db.add_tracked_channel(
        url=body.url,
        name=body.name,
        min_score=body.min_score,
        target_playlist=body.target_playlist,
        auto_upload=1 if body.auto_upload else 0,
        youtube_username=body.youtube_username,
        instagram_username=body.instagram_username,
    )
    with db._connect() as conn:
        row = conn.execute("SELECT * FROM tracked_channels WHERE id = ?", (channel_id,)).fetchone()
    return dict(row) if row else {"id": channel_id}


@router.get("/{channel_id}")
async def get_channel(channel_id: str):
    db = _db()
    with db._connect() as conn:
        row = conn.execute(
            "SELECT * FROM tracked_channels WHERE id = ? OR url = ?", (channel_id, channel_id)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Channel not found")
    return dict(row)


@router.patch("/{channel_id}")
async def update_channel(channel_id: str, body: ChannelUpdateRequest):
    db = _db()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    # Map bool fields
    if "auto_upload" in updates:
        updates["auto_upload"] = 1 if updates["auto_upload"] else 0
    if "active" in updates:
        updates["active"] = 1 if updates["active"] else 0
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [channel_id]
    with db._connect() as conn:
        cur = conn.execute(f"UPDATE tracked_channels SET {set_clause} WHERE id = ?", values)
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Channel not found")
        row = conn.execute("SELECT * FROM tracked_channels WHERE id = ?", (channel_id,)).fetchone()
    return dict(row)


@router.delete("/{channel_id}")
async def delete_channel(channel_id: str):
    db = _db()
    db.remove_tracked_channel(channel_id)
    return {"deleted": True}


class ChannelBatchDeleteRequest(BaseModel):
    channel_ids: list[str] = []
    all: bool = False


@router.post("/batch-delete")
async def batch_delete_channels(body: ChannelBatchDeleteRequest):
    db = _db()
    with db._connect() as conn:
        if body.all:
            cur = conn.execute("DELETE FROM tracked_channels")
            deleted = cur.rowcount
        elif body.channel_ids:
            placeholders = ",".join("?" for _ in body.channel_ids)
            cur = conn.execute(
                f"DELETE FROM tracked_channels WHERE id IN ({placeholders}) OR url IN ({placeholders})",
                body.channel_ids + body.channel_ids,
            )
            deleted = cur.rowcount
        else:
            deleted = 0
        conn.commit()
    return {"deleted_count": deleted}


class ChannelScanRequest(BaseModel):
    exclude: str | None = None
    max_per_channel: int = 1
    max_age_days: int = 7


@router.post("/scan-latest")
async def scan_latest_channel_videos(body: ChannelScanRequest | None = None):
    """Takip edilen kanalları tarar ve son videoları işleme sırasına ekler."""
    from core.autopilot import AutoPilotManager

    db = _db()
    ap = AutoPilotManager(db=db)
    exclude_str = body.exclude if body and body.exclude else None
    max_count = body.max_per_channel if body else 1
    max_age = body.max_age_days if body and body.max_age_days is not None else 7
    excludes = [k.strip() for k in exclude_str.split(",") if k.strip()] if exclude_str else []
    result = ap.scan_and_queue_latest_channels(
        exclude_keywords=excludes,
        max_videos_per_channel=max_count,
        max_age_days=max_age,
    )
    return result
