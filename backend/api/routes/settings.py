"""backend/api/routes/settings.py — API keys, cache, disk."""

from __future__ import annotations

import os
import sys

_R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _R not in sys.path:
    sys.path.insert(0, _R)


from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.deps import get_db
from core.database import DatabaseManager

router = APIRouter(prefix="/settings", tags=["settings"])
_ENV_PATH = os.path.join(_R, ".env")


def _mask(val: str, show: int = 6) -> str:
    if not val:
        return ""
    return val[:show] + "..." + val[-4:] if len(val) > show + 4 else "***"


@router.get("")
async def get_settings():
    load_dotenv(_ENV_PATH, override=True)
    keys = {
        "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", ""),
        "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", ""),
        "INSTAGRAM_ACCESS_TOKEN": os.environ.get("INSTAGRAM_ACCESS_TOKEN", ""),
        "INSTAGRAM_ACCOUNT_ID": os.environ.get("INSTAGRAM_ACCOUNT_ID", ""),
        "TIKTOK_SESSION_ID": os.environ.get("TIKTOK_SESSION_ID", ""),
    }
    return {k: {"masked": _mask(v), "set": bool(v)} for k, v in keys.items()}


class EnvUpdateRequest(BaseModel):
    key: str
    value: str


@router.post("/env")
async def update_env(body: EnvUpdateRequest):
    allowed = {
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "INSTAGRAM_ACCESS_TOKEN",
        "INSTAGRAM_ACCOUNT_ID",
        "TIKTOK_SESSION_ID",
        "DEEPSEEK_API_KEY",
    }
    if body.key not in allowed:
        raise HTTPException(status_code=400, detail=f"Key '{body.key}' not allowed")
    # Read current .env
    lines = []
    if os.path.exists(_ENV_PATH):
        with open(_ENV_PATH) as f:
            lines = f.readlines()
    # Replace or append
    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{body.key}="):
            new_lines.append(f"{body.key}={body.value}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{body.key}={body.value}\n")
    with open(_ENV_PATH, "w") as f:
        f.writelines(new_lines)
    os.environ[body.key] = body.value
    return {"updated": True, "key": body.key}


@router.post("/cache/clear")
async def clear_cache():
    from core.cache_manager import CacheManager

    cache = CacheManager(output_dir="outputs/clips")
    cache.clear_temp_files()
    return {"cleared": True}


@router.post("/db/clear")
async def clear_database(keep_channels: bool = True):
    from core.database import DatabaseManager

    db = DatabaseManager()
    db.init_db()
    db.clear_database(keep_tracked_channels=keep_channels)
    return {"cleared": True}


@router.get("/disk")
async def disk_usage():
    from core.cache_manager import CacheManager

    cache = CacheManager(output_dir="outputs/clips")
    info = cache.get_disk_usage()
    return info


class ScoringConfigUpdate(BaseModel):
    hook_strength_weight: int | None = None
    emotion_weight: int | None = None
    story_completeness_weight: int | None = None
    signal_validation_weight: int | None = None
    band_labels_enabled: bool | None = None
    ensemble_runs: int | None = None
    mundane_score_cap: int | None = None


@router.get("/scoring")
async def get_scoring_config(db: DatabaseManager = Depends(get_db)):
    return db.get_scoring_config()


@router.post("/scoring")
async def update_scoring_config(body: ScoringConfigUpdate, db: DatabaseManager = Depends(get_db)):
    import core.scoring_config as SC

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if "ensemble_runs" in update_data:
        update_data["ensemble_runs"] = max(1, update_data["ensemble_runs"])

    db.set_scoring_config(update_data)

    if body.hook_strength_weight is not None:
        SC.HOOK_STRENGTH_WEIGHT = body.hook_strength_weight
    if body.emotion_weight is not None:
        SC.EMOTION_WEIGHT = body.emotion_weight
    if body.story_completeness_weight is not None:
        SC.STORY_COMPLETENESS_WEIGHT = body.story_completeness_weight
    if body.signal_validation_weight is not None:
        SC.SIGNAL_VALIDATION_WEIGHT = body.signal_validation_weight
    if body.band_labels_enabled is not None:
        SC.BAND_LABELS_ENABLED = body.band_labels_enabled
    if body.ensemble_runs is not None:
        SC.ENSEMBLE_RUNS = max(1, body.ensemble_runs)
    if body.mundane_score_cap is not None:
        SC.MUNDANE_SCORE_CAP = body.mundane_score_cap
    return {"updated": True}
