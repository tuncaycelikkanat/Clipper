"""
backend/main.py — Clipper FastAPI application entry point.
"""
from __future__ import annotations

import os
import sys

# Ensure project root is on sys.path for core/ imports
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from backend.db.database import DatabaseManager
from backend.db.migrations import run_migrations
from backend.api.routes.pipeline import router as pipeline_router
from backend.api.routes.clips import router as clips_router
from backend.api.routes.videos import router as videos_router
from backend.api.routes.channels import router as channels_router
from backend.api.routes.queue import router as queue_router
from backend.api.routes.scheduler import router as scheduler_router
from backend.api.routes.upload import router as upload_router
from backend.api.routes.auth import router as auth_router
from backend.api.routes.settings import router as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Clipper API v2.0 başlatılıyor...")
    db = DatabaseManager()
    db.init_db()
    run_migrations(db)
    logger.info("✅ Database hazır.")

    # AutoPilot background scheduler daemon
    try:
        from core.autopilot import AutoPilotManager
        AutoPilotManager.start_background_worker(interval_hours=2.0)
        logger.info("⏰ AutoPilot zamanlayıcı arka planda başlatıldı (1 dk yayın kontrolü aktif).")
    except Exception as e:
        logger.warning("AutoPilot worker başlatılamadı: {}", e)

    yield

    try:
        from core.autopilot import AutoPilotManager
        AutoPilotManager.stop_background_worker()
    except Exception:
        pass
    logger.info("👋 Clipper API kapatılıyor.")


app = FastAPI(
    title="Clipper API",
    version="2.0.0",
    description="Autonomous YouTube gaming clip extraction & publishing system",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routers under /api
app.include_router(pipeline_router, prefix="/api")
app.include_router(clips_router, prefix="/api")
app.include_router(videos_router, prefix="/api")
app.include_router(channels_router, prefix="/api")
app.include_router(queue_router, prefix="/api")
app.include_router(scheduler_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(settings_router, prefix="/api")


@app.get("/")
async def root():
    return {"name": "Clipper API", "version": "2.0.0", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}
