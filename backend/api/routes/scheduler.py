"""backend/api/routes/scheduler.py — Autopilot daemon control."""

from __future__ import annotations

import os
import sys

_R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _R not in sys.path:
    sys.path.insert(0, _R)

from fastapi import APIRouter
from pydantic import BaseModel

from core.autopilot import AutoPilotManager

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


class SchedulerStartRequest(BaseModel):
    interval_hours: float = 2.0


@router.post("/start")
async def start_scheduler(body: SchedulerStartRequest):
    ok = AutoPilotManager.start_background_worker(interval_hours=body.interval_hours)
    return {"started": ok, **AutoPilotManager.get_background_worker_info()}


@router.post("/stop")
async def stop_scheduler():
    ok = AutoPilotManager.stop_background_worker()
    return {"stopped": ok}


@router.get("/status")
async def scheduler_status():
    return AutoPilotManager.get_background_worker_info()
