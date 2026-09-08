"""
backend/workers/job_store.py — In-memory + DB-backed pipeline job tracker.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from loguru import logger


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobState:
    id: str
    video_url: str
    status: str = "queued"  # queued | running | done | failed | cancelled
    progress: int = 0  # 0-100
    current_step: str | None = None
    result: list[dict] | None = None
    error_msg: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    logs: list[dict[str, Any]] = field(default_factory=list)

    # Legacy SSE queue + multi-subscriber list
    _sse_queue: asyncio.Queue = field(default_factory=asyncio.Queue, repr=False)
    _subscribers: list[asyncio.Queue] = field(default_factory=list, repr=False)

    def add_log(self, message: str, step: str = "processing", progress: int = 0) -> dict[str, Any]:
        log_entry = {
            "time": _utcnow(),
            "step": step,
            "progress": progress,
            "message": message,
        }
        self.logs.append(log_entry)
        self.current_step = message
        self.progress = progress
        self.updated_at = _utcnow()
        return log_entry

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "video_url": self.video_url,
            "status": self.status,
            "progress": self.progress,
            "current_step": self.current_step,
            "result": self.result,
            "error_msg": self.error_msg,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "logs": self.logs,
        }


import json
import threading


class JobStore:
    """Thread-safe in-memory + DB-backed job store with multi-client pub/sub support."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()

    def create(self, video_url: str) -> JobState:
        job = JobState(id=str(uuid.uuid4()), video_url=video_url)
        with self._lock:
            self._jobs[job.id] = job
        try:
            from backend.deps import get_db

            get_db().create_pipeline_job(job.id, video_url)
        except Exception as e:
            logger.debug("DB job create error: {}", e)
        logger.debug("Job created: {}", job.id)
        return job

    def get(self, job_id: str) -> JobState | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                return job
        # Fallback to database if server was restarted
        try:
            from backend.deps import get_db

            db_job = get_db().get_pipeline_job(job_id)
            if db_job:
                result_val = None
                if db_job.get("result_json"):
                    with contextlib.suppress(Exception):
                        result_val = json.loads(db_job["result_json"])
                job = JobState(
                    id=db_job["id"],
                    video_url=db_job["video_url"],
                    status=db_job.get("status", "queued"),
                    progress=db_job.get("progress", 0),
                    current_step=db_job.get("current_step", ""),
                    result=result_val,
                    error_msg=db_job.get("error_msg"),
                    created_at=db_job.get("created_at", _utcnow()),
                    updated_at=db_job.get("updated_at", _utcnow()),
                )
                with self._lock:
                    self._jobs[job.id] = job
                return job
        except Exception as e:
            logger.debug("DB job get fallback error: {}", e)
        return None

    get_job = get

    def list_recent(self, limit: int = 20) -> list[JobState]:
        with self._lock:
            if not self._jobs:
                try:
                    from backend.deps import get_db

                    db_jobs = get_db().list_pipeline_jobs(limit=limit)
                    for dj in db_jobs:
                        if dj["id"] not in self._jobs:
                            result_val = None
                            if dj.get("result_json"):
                                with contextlib.suppress(Exception):
                                    result_val = json.loads(dj["result_json"])
                            self._jobs[dj["id"]] = JobState(
                                id=dj["id"],
                                video_url=dj["video_url"],
                                status=dj.get("status", "queued"),
                                progress=dj.get("progress", 0),
                                current_step=dj.get("current_step", ""),
                                result=result_val,
                                error_msg=dj.get("error_msg"),
                                created_at=dj.get("created_at", _utcnow()),
                                updated_at=dj.get("updated_at", _utcnow()),
                            )
                except Exception as e:
                    logger.debug("DB list_pipeline_jobs fallback error: {}", e)

            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            return jobs[:limit]

    def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        current_step: str | None = None,
        result: list[dict] | None = None,
        error_msg: str | None = None,
    ) -> JobState | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = progress
            if current_step is not None:
                job.current_step = current_step
            if result is not None:
                job.result = result
            if error_msg is not None:
                job.error_msg = error_msg
            job.updated_at = _utcnow()

        try:
            from backend.deps import get_db

            res_json = json.dumps(result, ensure_ascii=False) if result is not None else None
            get_db().update_pipeline_job(
                job_id,
                status=status,
                progress=progress,
                current_step=current_step,
                result_json=res_json,
                error_msg=error_msg,
            )
        except Exception as e:
            logger.debug("DB job update error: {}", e)

        return job

    async def push_sse(self, job_id: str, event_type: str, data: dict) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return

        if event_type == "progress":
            msg = data.get("message", "")
            step = data.get("step", "processing")
            pct = data.get("progress", job.progress)
            job.add_log(msg, step, pct)

        event_payload = {"event": event_type, "data": data}
        await job._sse_queue.put(event_payload)

        for q in list(job._subscribers):
            with contextlib.suppress(Exception):
                await q.put(event_payload)

    async def get_sse_queue(self, job_id: str) -> asyncio.Queue | None:
        job = self._jobs.get(job_id)
        return job._sse_queue if job else None

    def subscribe(self, job_id: str) -> asyncio.Queue | None:
        job = self._jobs.get(job_id)
        if not job:
            return None
        q: asyncio.Queue = asyncio.Queue()
        job._subscribers.append(q)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        job = self._jobs.get(job_id)
        if job and q in job._subscribers:
            job._subscribers.remove(q)

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job and job.status in ("queued", "running"):
            job.status = "cancelled"
            job.updated_at = _utcnow()
            return True
        return False


# Global singleton
job_store = JobStore()
