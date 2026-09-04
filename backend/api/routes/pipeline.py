"""
backend/api/routes/pipeline.py — Pipeline run + SSE streaming endpoints.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.workers.job_store import job_store
from backend.workers.pipeline_worker import run_pipeline_async

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class PipelineRunRequest(BaseModel):
    url: str
    target_clips: int = 3
    render_mode: str = "shorts_9x16_blur"
    add_subtitles: bool = False
    add_hook_card: bool = False
    enhance_colors: bool = True
    api_key: str | None = None


class BatchProcessVideosRequest(BaseModel):
    video_ids: list[str]
    target_clips: int = 3
    render_mode: str = "shorts_9x16_blur"
    add_subtitles: bool = False
    add_hook_card: bool = False
    enhance_colors: bool = True
    api_key: str | None = None


@router.post("/run")
async def run_pipeline(body: PipelineRunRequest, background_tasks: BackgroundTasks):
    """Start a pipeline job. Returns job_id immediately."""
    job = job_store.create(body.url)
    background_tasks.add_task(
        run_pipeline_async,
        job_id=job.id,
        url=body.url,
        target_clips=body.target_clips,
        render_mode=body.render_mode,
        add_subtitles=body.add_subtitles,
        add_hook_card=body.add_hook_card,
        enhance_colors=body.enhance_colors,
        api_key=body.api_key,
    )
    return {"job_id": job.id, "status": job.status}


@router.post("/batch-process-videos")
async def batch_process_videos(body: BatchProcessVideosRequest, background_tasks: BackgroundTasks):
    """Start pipeline jobs for selected pending videos."""
    from core.database import DatabaseManager

    db = DatabaseManager()
    db.init_db()
    created_jobs = []

    with db._connect() as conn:
        for vid in body.video_ids:
            row = conn.execute("SELECT * FROM videos WHERE id = ?", (vid,)).fetchone()
            if row:
                row_dict = dict(row)
                url = row_dict.get("url")
                if not url:
                    continue
                job = job_store.create(url)
                background_tasks.add_task(
                    run_pipeline_async,
                    job_id=job.id,
                    url=url,
                    target_clips=body.target_clips,
                    render_mode=body.render_mode,
                    add_subtitles=body.add_subtitles,
                    add_hook_card=body.add_hook_card,
                    enhance_colors=body.enhance_colors,
                    api_key=body.api_key,
                )
                created_jobs.append({"job_id": job.id, "video_id": vid, "title": row_dict.get("title")})

    return {"jobs": created_jobs, "count": len(created_jobs)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get current status/result of a pipeline job."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    """SSE stream — yields progress events until job completes."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    q = job_store.subscribe(job_id)
    if not q:
        raise HTTPException(status_code=404, detail="Job not found")

    # Transfer any pre-buffered events from _sse_queue into the subscriber queue
    while not job._sse_queue.empty():
        try:
            ev = job._sse_queue.get_nowait()
            q.put_nowait(ev)
        except Exception:
            break

    async def event_generator():
        try:
            # Emit current state & past logs immediately
            init_data = json.dumps(
                {
                    "status": job.status,
                    "progress": job.progress,
                    "current_step": job.current_step,
                    "logs": job.logs,
                    "clips": job.result or [],
                }
            )
            yield f"event: init\ndata: {init_data}\n\n"

            if job.status in ("done", "failed", "cancelled"):
                if job.status == "done":
                    data = json.dumps({"clips": job.result or [], "count": len(job.result or [])})
                    yield f"event: done\ndata: {data}\n\n"
                else:
                    data = json.dumps({"message": job.error_msg or "Cancelled"})
                    yield f"event: error\ndata: {data}\n\n"
                return

            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=20.0)
                    event_type = event["event"]
                    data = json.dumps(event["data"])
                    yield f"event: {event_type}\ndata: {data}\n\n"
                    if event_type in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            job_store.unsubscribe(job_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a running or queued job."""
    cancelled = job_store.cancel(job_id)
    if not cancelled:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled")
    return {"cancelled": True}


@router.get("/jobs")
async def list_jobs(limit: int = 20):
    """List recent pipeline jobs."""
    jobs = job_store.list_recent(limit=limit)
    return [j.to_dict() for j in jobs]
