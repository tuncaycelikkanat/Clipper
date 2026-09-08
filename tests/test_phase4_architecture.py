"""tests/test_phase4_architecture.py — Tests for Phase 4 Architecture & Scalability."""

import json
import threading
from unittest.mock import patch

import pytest

from backend.deps import get_db
from backend.workers.job_store import JobState, JobStore
from core.autopilot import AutoPilotManager
from core.database import DatabaseManager


def test_job_state_db_persistence_and_recovery(tmp_path):
    """Verify JobStore persists state into pipeline_jobs table and recovers it after server restart."""
    db_path = str(tmp_path / "test_jobs_persist.db")
    db = DatabaseManager(db_path=db_path)
    db.init_db()

    # 1. Create and update a job using JobStore
    store = JobStore()
    with patch("backend.deps.get_db", return_value=db):
        job = store.create("https://youtube.com/watch?v=persisted_vid_01")
        assert job.status == "queued"

        # Update job progress and results
        dummy_result = [{"clip_id": "clip_p1", "score": 95, "title": "Viral Moment"}]
        store.update(
            job.id,
            status="done",
            progress=100,
            current_step="İşlem tamamlandı",
            result=dummy_result,
        )

    # 2. Inspect raw database content
    row = db.get_pipeline_job(job.id)
    assert row is not None
    assert row["status"] == "done"
    assert row["progress"] == 100
    assert row["current_step"] == "İşlem tamamlandı"
    assert json.loads(row["result_json"]) == dummy_result

    # 3. Simulate server restart: Brand new JobStore with completely empty memory
    fresh_store = JobStore()
    assert len(fresh_store._jobs) == 0

    with patch("backend.deps.get_db", return_value=db):
        # 3a. Single get recovery
        recovered = fresh_store.get(job.id)
        assert recovered is not None
        assert recovered.id == job.id
        assert recovered.status == "done"
        assert recovered.progress == 100
        assert recovered.result == dummy_result

        # 3b. Recent list recovery
        another_fresh_store = JobStore()
        recent = another_fresh_store.list_recent(limit=10)
        assert len(recent) >= 1
        assert any(j.id == job.id for j in recent)


def test_deps_connection_pooling_thread_local():
    """Verify backend.deps.get_db uses thread-local instances for safe concurrent access."""
    instances_per_thread = {}

    def worker(t_id: int):
        # Multiple calls in same thread return identical instance
        db1 = get_db()
        db2 = get_db()
        assert db1 is db2
        instances_per_thread[t_id] = id(db1)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Each thread should have had its own independent DatabaseManager instance
    unique_instances = set(instances_per_thread.values())
    assert len(unique_instances) == len(instances_per_thread)


def test_autopilot_worker_info_thread_safety():
    """Verify AutoPilotManager._set_status and get_status are thread-safe."""
    # Reset status
    AutoPilotManager._set_status(running=False, interval_hours=2.0)
    status_init = AutoPilotManager.get_status()
    assert status_init["running"] is False

    num_threads = 20
    errors = []

    def updater(idx: int):
        try:
            AutoPilotManager._set_status(last_run=f"2026-09-08T15:00:{idx:02d}Z", thread_idx=idx)
            current = AutoPilotManager.get_status()
            assert "last_run" in current
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=updater, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    final_status = AutoPilotManager.get_status()
    assert "last_run" in final_status
    assert "thread_idx" in final_status


def test_database_manager_pipeline_jobs_crud(tmp_path):
    """Verify DatabaseManager pipeline_jobs operations (create, update, get, list)."""
    db = DatabaseManager(db_path=str(tmp_path / "crud.db"))
    db.init_db()

    # Create job using alias create_job
    job_id = "job_test_crud_01"
    db.create_job(job_id, "https://youtube.com/watch?v=crud_test")

    job = db.get_job(job_id)
    assert job is not None
    assert job["status"] == "queued"
    assert job["video_url"] == "https://youtube.com/watch?v=crud_test"

    # Update job using alias update_job_status
    db.update_job_status(
        job_id,
        status="running",
        progress=45,
        current_step="Extracting frames",
    )
    job_up = db.get_job(job_id)
    assert job_up["status"] == "running"
    assert job_up["progress"] == 45
    assert job_up["current_step"] == "Extracting frames"

    # List jobs
    jobs_list = db.list_pipeline_jobs(limit=5)
    assert len(jobs_list) == 1
    assert jobs_list[0]["id"] == job_id
