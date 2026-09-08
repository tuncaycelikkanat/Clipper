"""tests/test_phase3_code_quality.py — Tests for Phase 3 code quality and type safety."""

import os
import threading
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.deps import get_db
from backend.main import app
from backend.workers.job_store import JobStore
from core.cutter import VideoCutter
from core.database import DatabaseManager
from core.instagram_uploader import InstagramUploader


def test_ffmpeg_cmd_builder_variations():
    """Verify VideoCutter._build_ffmpeg_cmd correctly builds commands for various configurations."""
    cutter = VideoCutter()

    # 1. Complex filter with facecam (dual input stream)
    cmd_cam = cutter._build_ffmpeg_cmd(
        input_path="input.mp4",
        output_path="output_cam.mp4",
        filter_str="[0:v][1:v]overlay=10:10[outv]",
        is_complex=True,
        has_cam=True,
        audio_bitrate="192k",
    )
    # Check dual input flags: "-i", "input.mp4", "-i", "input.mp4"
    assert cmd_cam.count("-i") == 2
    assert "-filter_complex" in cmd_cam
    assert cmd_cam[cmd_cam.index("-filter_complex") + 1] == "[0:v][1:v]overlay=10:10[outv]"
    assert "-map" in cmd_cam
    assert "[outv]" in cmd_cam
    assert "0:a" in cmd_cam
    assert cmd_cam[-1] == "output_cam.mp4"

    # 2. Complex filter without facecam (single input stream)
    cmd_complex_nocam = cutter._build_ffmpeg_cmd(
        input_path="input.mp4",
        output_path="output_nocam.mp4",
        filter_str="[0:v]boxblur=20:20[v];[v]null[outv]",
        is_complex=True,
        has_cam=False,
    )
    assert cmd_complex_nocam.count("-i") == 1
    assert "-filter_complex" in cmd_complex_nocam
    assert "-map" in cmd_complex_nocam

    # 3. Simple filter (uses -vf instead of -filter_complex)
    cmd_simple = cutter._build_ffmpeg_cmd(
        input_path="input.mp4",
        output_path="output_simple.mp4",
        filter_str="scale=1920:1080",
        is_complex=False,
        preset="veryfast",
        crf="22",
        audio_bitrate="128k",
    )
    assert cmd_simple.count("-i") == 1
    assert "-vf" in cmd_simple
    assert cmd_simple[cmd_simple.index("-vf") + 1] == "scale=1920:1080"
    assert "-filter_complex" not in cmd_simple
    assert cmd_simple[cmd_simple.index("-preset") + 1] == "veryfast"
    assert cmd_simple[cmd_simple.index("-crf") + 1] == "22"
    assert cmd_simple[cmd_simple.index("-b:a") + 1] == "128k"


def test_job_store_thread_safe_concurrency(tmp_path):
    """Verify JobStore uses a thread lock and safely handles concurrent creation and updates."""
    # Use isolated test DB to avoid interference
    db_path = str(tmp_path / "test_jobs.db")
    db = DatabaseManager(db_path=db_path)
    db.init_db()

    store = JobStore()
    assert hasattr(store, "_lock")
    assert isinstance(store._lock, type(threading.Lock()))

    num_threads = 20
    created_ids = []
    errors = []

    def worker(idx: int):
        try:
            with patch("backend.deps.get_db", return_value=db):
                job = store.create(f"https://youtube.com/watch?v=thread_{idx}")
                created_ids.append(job.id)
                # Concurrent update
                store.update(job.id, status="running", progress=50, current_step=f"step_{idx}")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Encountered thread errors: {errors}"
    assert len(created_ids) == num_threads

    # Verify all jobs are recorded in store and updated properly
    for jid in created_ids:
        job = store.get(jid)
        assert job is not None
        assert job.status == "running"
        assert job.progress == 50


def test_scoring_config_db_persistence(tmp_path):
    """Verify scoring config is persisted in the database rather than just mutating memory."""
    db_path = str(tmp_path / "test_scoring.db")
    db = DatabaseManager(db_path=db_path)
    db.init_db()

    # 1. Default scoring config
    cfg = db.get_scoring_config()
    assert "hook_strength_weight" in cfg
    assert "ensemble_runs" in cfg
    original_hook = cfg["hook_strength_weight"]

    # 2. Update config in database
    new_hook_weight = 42
    updated = db.set_scoring_config({"hook_strength_weight": new_hook_weight, "ensemble_runs": 5})
    assert updated["hook_strength_weight"] == new_hook_weight
    assert updated["ensemble_runs"] == 5

    # 3. New DatabaseManager instance (simulating app restart) reads from DB
    db_reopened = DatabaseManager(db_path=db_path)
    cfg_persisted = db_reopened.get_scoring_config()
    assert cfg_persisted["hook_strength_weight"] == new_hook_weight
    assert cfg_persisted["ensemble_runs"] == 5


def test_scoring_settings_api_endpoint(tmp_path):
    """Verify /api/settings/scoring GET and POST endpoints interact with DatabaseManager."""
    db_path = str(tmp_path / "test_api_scoring.db")
    db = DatabaseManager(db_path=db_path)
    db.init_db()

    client = TestClient(app)
    app.dependency_overrides[get_db] = lambda: db

    try:
        # GET scoring settings
        res_get = client.get("/api/settings/scoring")
        assert res_get.status_code == 200
        data = res_get.json()
        assert "hook_strength_weight" in data

        # POST scoring settings update
        payload = {"hook_strength_weight": 33, "ensemble_runs": 2}
        res_post = client.post("/api/settings/scoring", json=payload)
        assert res_post.status_code == 200
        assert res_post.json() == {"updated": True}

        # Verify via GET that DB received update
        res_get_after = client.get("/api/settings/scoring")
        assert res_get_after.status_code == 200
        assert res_get_after.json()["hook_strength_weight"] == 33
        assert res_get_after.json()["ensemble_runs"] == 2
    finally:
        app.dependency_overrides.clear()


def test_instagram_uploader_public_base_url(tmp_path):
    """Verify upload_temp_cover_image uses PUBLIC_BASE_URL to serve local thumbnails."""
    dummy_thumb = tmp_path / "thumb.jpg"
    dummy_thumb.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # mock jpeg

    uploader = InstagramUploader(access_token="test_tok", instagram_account_id="test_acc")

    # With PUBLIC_BASE_URL set and clip_id provided
    with patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://clipper.mydomain.com"}):
        url = uploader.upload_temp_cover_image(str(dummy_thumb), clip_id="clip_123")
        assert url == "https://clipper.mydomain.com/api/clips/clip_123/thumbnail"

    # With trailing slash in PUBLIC_BASE_URL
    with patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://clipper.mydomain.com/"}):
        url = uploader.upload_temp_cover_image(str(dummy_thumb), clip_id="clip_abc")
        assert url == "https://clipper.mydomain.com/api/clips/clip_abc/thumbnail"

    # Missing thumbnail returns None
    url_none = uploader.upload_temp_cover_image("/non/existent/path.jpg", clip_id="clip_123")
    assert url_none is None
