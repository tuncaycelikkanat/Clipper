"""tests/test_schema_consistency.py — Schema and DatabaseManager consistency tests."""

import pytest
from backend.deps import get_db
from core.database import DatabaseManager


def test_backend_routes_use_core_db():
    """Verify that backend.deps.get_db returns core.database.DatabaseManager."""
    db = get_db()
    assert isinstance(db, DatabaseManager)
    assert hasattr(db, "get_connection")
    assert hasattr(db, "_connect")


def test_schema_tables_exist(temp_db):
    """Verify all required tables exist in DatabaseManager schema."""
    result = temp_db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    tables = {r["name"] for r in result}

    expected_tables = {
        "videos",
        "clips",
        "channels",
        "renders",
        "heatmap_patterns",
        "tracked_channels",
        "channel_processed_videos",
        "autopilot_queue",
        "app_config",
        "pipeline_jobs",
    }
    for expected in expected_tables:
        assert expected in tables, f"Expected table '{expected}' not found in DB schema"


def test_scoring_config_persistence(temp_db):
    """Verify get_scoring_config and set_scoring_config correctly persist and retrieve values."""
    config = temp_db.get_scoring_config()
    assert "hook_strength_weight" in config

    temp_db.set_scoring_config({"hook_strength_weight": 42, "ensemble_runs": 3})
    updated = temp_db.get_scoring_config()
    assert updated["hook_strength_weight"] == 42
    assert updated["ensemble_runs"] == 3


def test_pipeline_job_persistence(temp_db):
    """Verify create_pipeline_job, update_pipeline_job, and get_pipeline_job."""
    job_id = "test-job-uuid-1234"
    temp_db.create_pipeline_job(job_id, "https://youtube.com/watch?v=sample123")

    job = temp_db.get_pipeline_job(job_id)
    assert job is not None
    assert job["id"] == job_id
    assert job["status"] == "queued"
    assert job["progress"] == 0

    temp_db.update_pipeline_job(job_id, status="running", progress=50, current_step="audio")
    updated = temp_db.get_pipeline_job(job_id)
    assert updated["status"] == "running"
    assert updated["progress"] == 50
    assert updated["current_step"] == "audio"
