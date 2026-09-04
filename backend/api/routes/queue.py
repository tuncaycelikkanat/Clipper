"""backend/api/routes/queue.py — Publish queue + calendar."""

from __future__ import annotations

import datetime
import os
import sys

_R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _R not in sys.path:
    sys.path.insert(0, _R)


from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.autopilot import AutoPilotManager
from core.database import DatabaseManager

router = APIRouter(tags=["queue"])
_TZ_OFFSET = 3  # UTC+3


def _db():
    db = DatabaseManager()
    db.init_db()
    return db


def _ap():
    db = _db()
    return AutoPilotManager(db=db), db


class QueueAddRequest(BaseModel):
    clip_id: str
    scheduled_at: str | None = None  # ISO UTC, None = pool


class QueueUpdateRequest(BaseModel):
    scheduled_at: str | None = None
    status: str | None = None


@router.get("/queue")
async def list_queue(status: str | None = None, limit: int = 100):
    db = _db()
    items = db.get_autopilot_queue(limit=limit)
    if status:
        items = [i for i in items if i.get("status", "").upper() == status.upper()]
    return items


@router.post("/queue", status_code=201)
async def add_to_queue(body: QueueAddRequest):
    db = _db()
    with db._connect() as conn:
        clip = conn.execute("SELECT * FROM clips WHERE id = ?", (body.clip_id,)).fetchone()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    clip = dict(clip)
    # Get channel_url from video
    with db._connect() as conn:
        video = conn.execute("SELECT uploader FROM videos WHERE id = ?", (clip["video_id"],)).fetchone()
    channel_url = dict(video)["uploader"] if video else ""

    # Find next slot if none provided
    ap = AutoPilotManager(db=db)
    scheduled_at = body.scheduled_at
    if not scheduled_at:
        latest = db.get_latest_scheduled_time()
        slot_dt, slot_iso = ap.compute_next_available_slot(latest_scheduled_iso=latest)
        scheduled_at = slot_iso

    queue_id = db.add_to_autopilot_queue(
        video_id=clip["video_id"],
        clip_id=clip["id"],
        channel_url=channel_url,
        title=clip.get("title", ""),
        render_path=clip.get("render_path", ""),
        thumbnail_path=clip.get("thumbnail_path"),
        viral_score=clip.get("score", 0),
        scheduled_at=scheduled_at,
        description=clip.get("description", ""),
    )
    return {"id": queue_id, "scheduled_at": scheduled_at}


@router.patch("/queue/{queue_id}")
async def update_queue_item(queue_id: str, body: QueueUpdateRequest):
    db = _db()
    if body.scheduled_at is not None:
        db.update_autopilot_queue_scheduled_time(queue_id, body.scheduled_at or "")
    if body.status is not None:
        db.update_autopilot_queue_status(queue_id, body.status)
    return {"updated": True}


@router.delete("/queue/{queue_id}")
async def remove_from_queue(queue_id: str):
    db = _db()
    db.delete_from_autopilot_queue(queue_id)
    return {"deleted": True}


@router.get("/calendar")
async def get_calendar(days: int = 14):
    ap, db = _ap()
    days_data = ap.get_calendar_days_data(days_ahead=days)
    SLOTS = ["11:30", "15:30", "19:00", "22:30"]
    result = []
    for day in days_data:
        slot_map = {s: None for s in SLOTS}
        for item in day["items"]:
            t = item.get("local_time", "")
            if t in slot_map:
                slot_map[t] = item
        result.append(
            {
                "date": day["date_str"],
                "label": day["label"],
                "slots": [{"time": s, "item": slot_map[s]} for s in SLOTS],
            }
        )
    return result


class ShuffleRequest(BaseModel):
    selected_dates: list[str] | None = None


@router.post("/queue/shuffle")
async def shuffle_queue(body: ShuffleRequest | None = None):
    ap, db = _ap()
    dates = body.selected_dates if body and body.selected_dates else None
    if not dates:
        now_local = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=_TZ_OFFSET)
        dates = [(now_local + datetime.timedelta(days=i)).date().isoformat() for i in range(14)]
    result = ap.diversified_shuffle(selected_dates=dates)
    return result
