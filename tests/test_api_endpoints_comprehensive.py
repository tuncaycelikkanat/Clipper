import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.workers.job_store import job_store
from core.database import DatabaseManager

client = TestClient(app)


@pytest.fixture
def test_data(tmp_path):
    db = DatabaseManager()
    db.init_db()

    # Create fake files
    fake_video_file = tmp_path / "clip.mp4"
    fake_video_file.write_bytes(b"dummy video bytes" * 100)

    fake_thumb_file = tmp_path / "thumb.jpg"
    fake_thumb_file.write_bytes(b"dummy thumb bytes")

    vid_id = "comp_test_video"
    db.save_video(
        {
            "id": vid_id,
            "url": f"https://youtube.com/watch?v={vid_id}",
            "title": "Comprehensive Test Video",
            "uploader": "https://youtube.com/@channel1",
            "duration": 300,
            "view_count": 1000,
            "has_heatmap": True,
        }
    )

    clip_ids = db.save_clips(
        vid_id,
        [
            {
                "rank": 1,
                "title": "Epic Clip 1",
                "category": "ACTION",
                "start_time": 0.0,
                "end_time": 20.0,
                "duration": 20.0,
                "score": 88,
                "hook_caption": "Wait for it",
            }
        ],
    )
    clip_id = clip_ids[0]

    # Update clip with paths
    with db._connect() as conn:
        conn.execute(
            "UPDATE clips SET render_path = ?, thumbnail_path = ?, description = ?, tags = ? WHERE id = ?",
            (str(fake_video_file), str(fake_thumb_file), "Clip desc", "tag1,tag2", clip_id),
        )
    yield {
        "video_id": vid_id,
        "clip_id": clip_id,
        "video_file": str(fake_video_file),
        "thumb_file": str(fake_thumb_file),
    }

    with db._connect() as conn:
        conn.execute("DELETE FROM clips WHERE video_id = ?", (vid_id,))
        conn.execute("DELETE FROM videos WHERE id = ?", (vid_id,))
        conn.commit()


# ─────────────────────────────────────────────────────────────
# 1. AUTH
# ─────────────────────────────────────────────────────────────


def test_auth_youtube_status_cases():
    with patch("core.uploader.YouTubeUploader.is_authenticated", return_value=True):
        res = client.get("/api/auth/youtube/status")
        assert res.status_code == 200
        assert res.json() == {"authenticated": True}

    with patch("core.uploader.YouTubeUploader.is_authenticated", return_value=False):
        res = client.get("/api/auth/youtube/status")
        assert res.status_code == 200
        assert res.json() == {"authenticated": False}

    with patch("core.uploader.YouTubeUploader.__init__", side_effect=Exception("OAuth fail")):
        res = client.get("/api/auth/youtube/status")
        assert res.status_code == 200
        assert res.json()["authenticated"] is False
        assert "OAuth fail" in res.json()["error"]


def test_auth_youtube_url():
    res = client.get("/api/auth/youtube/url")
    assert res.status_code == 200
    assert "action" in res.json()


def test_auth_youtube_authenticate():
    with patch("core.uploader.YouTubeUploader.authenticate", return_value=None):
        res = client.post("/api/auth/youtube/authenticate")
        assert res.status_code == 200
        assert res.json()["success"] is True

    with patch("core.uploader.YouTubeUploader.authenticate", side_effect=RuntimeError("Auth error")):
        res = client.post("/api/auth/youtube/authenticate")
        assert res.status_code == 500
        assert "Auth error" in res.json()["detail"]


# ─────────────────────────────────────────────────────────────
# 2. CHANNELS
# ─────────────────────────────────────────────────────────────


def test_channels_full_flow():
    # List with various filter options
    assert client.get("/api/channels?is_tracked=true").status_code == 200
    assert client.get("/api/channels?is_tracked=false").status_code == 200
    assert client.get("/api/channels?active_only=true").status_code == 200

    # Create channel
    create_res = client.post(
        "/api/channels",
        json={
            "url": "https://youtube.com/@comprehensive_chan",
            "name": "Comp Channel",
            "min_score": 90,
            "auto_upload": True,
            "check_interval_h": 3.0,
            "target_playlist": "PL123",
        },
    )
    assert create_res.status_code == 201
    ch_id = create_res.json()["id"]

    # Get single channel
    get_res = client.get(f"/api/channels/{ch_id}")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Comp Channel"

    # Get non-existent
    assert client.get("/api/channels/nonexistent_channel_id").status_code == 404

    # Patch with no fields -> 400
    assert client.patch(f"/api/channels/{ch_id}", json={}).status_code == 400

    # Patch fields
    patch_res = client.patch(
        f"/api/channels/{ch_id}",
        json={
            "name": "Updated Comp Channel",
            "min_score": 75,
            "auto_upload": False,
            "active": True,
            "check_interval_h": 1.5,
        },
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Updated Comp Channel"
    assert patch_res.json()["auto_upload"] == 0

    # Patch non-existent -> 404
    assert client.patch("/api/channels/nonexistent", json={"name": "X"}).status_code == 404

    # Delete channel
    del_res = client.delete(f"/api/channels/{ch_id}")
    assert del_res.status_code == 200
    assert del_res.json() == {"deleted": True}


# ─────────────────────────────────────────────────────────────
# 3. CLIPS
# ─────────────────────────────────────────────────────────────


def test_clips_endpoints(test_data):
    cid = test_data["clip_id"]
    vid = test_data["video_id"]

    # List clips with filter
    res_filt = client.get(f"/api/clips?video_id={vid}&limit=10&offset=0")
    assert res_filt.status_code == 200
    assert len(res_filt.json()) >= 1

    # List clips without filter
    assert client.get("/api/clips?limit=5&offset=0").status_code == 200

    # Get single clip
    res_clip = client.get(f"/api/clips/{cid}")
    assert res_clip.status_code == 200
    assert res_clip.json()["id"] == cid

    # Get non-existent
    assert client.get("/api/clips/nonexistent").status_code == 404

    # Patch clip with empty body -> 400
    assert client.patch(f"/api/clips/{cid}", json={}).status_code == 400

    # Patch clip
    res_patch = client.patch(
        f"/api/clips/{cid}",
        json={"title": "Patched Title", "description": "Patched Desc", "tags": "t1,t2", "hook_caption": "Patched Hook"},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["title"] == "Patched Title"

    # Patch non-existent -> 404
    assert client.patch("/api/clips/nonexistent", json={"title": "N"}).status_code == 404

    # Stream video file
    res_file = client.get(f"/api/clips/{cid}/file")
    assert res_file.status_code == 200
    assert res_file.headers["content-type"] == "video/mp4"

    # Get thumbnail
    res_thumb = client.get(f"/api/clips/{cid}/thumbnail")
    assert res_thumb.status_code == 200

    # File and thumbnail 404s
    assert client.get("/api/clips/nonexistent/file").status_code == 404
    assert client.get("/api/clips/nonexistent/thumbnail").status_code == 404

    # Batch delete clips
    batch_del_res = client.post("/api/clips/batch-delete", json={"clip_ids": [cid, "nonexistent_clip"]})
    assert batch_del_res.status_code == 200

    # Delete clip with file on disk
    del_res = client.delete(f"/api/clips/{cid}")
    assert del_res.status_code == 404 or del_res.status_code == 200

    # Delete non-existent -> 404
    assert client.delete("/api/clips/definitely_not_here").status_code == 404


def test_clips_file_missing_on_disk(tmp_path):
    db = DatabaseManager()
    try:
        with db._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO videos (id, url) VALUES ('v_missing', 'http://yt')")
            conn.execute(
                "INSERT OR REPLACE INTO clips (id, video_id, render_path, thumbnail_path, created_at) VALUES ('c_missing', 'v_missing', '/nonexistent/file.mp4', '/nonexistent/thumb.jpg', '2026-01-01')"
            )
            conn.commit()

        assert client.get("/api/clips/c_missing/file").status_code == 404
        assert client.get("/api/clips/c_missing/thumbnail").status_code == 404
    finally:
        with db._connect() as conn:
            conn.execute("DELETE FROM clips WHERE id = 'c_missing'")
            conn.execute("DELETE FROM videos WHERE id = 'v_missing'")
            conn.commit()


# ─────────────────────────────────────────────────────────────
# 4. PIPELINE & SSE
# ─────────────────────────────────────────────────────────────


def test_pipeline_run_and_jobs():
    with patch("backend.api.routes.pipeline.run_pipeline_async", return_value=None):
        res = client.post(
            "/api/pipeline/run",
            json={
                "url": "https://youtube.com/watch?v=run_test",
                "target_clips": 2,
                "render_mode": "shorts_9x16_blur",
                "add_subtitles": True,
                "add_hook_card": True,
                "enhance_colors": True,
            },
        )
        assert res.status_code == 200
        job_id = res.json()["job_id"]
        assert job_id is not None

    # Get job status
    get_res = client.get(f"/api/pipeline/jobs/{job_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == job_id

    # Get non-existent job -> 404
    assert client.get("/api/pipeline/jobs/nonexistent_id").status_code == 404

    # List jobs
    list_res = client.get("/api/pipeline/jobs?limit=10")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # Cancel job
    cancel_res = client.delete(f"/api/pipeline/jobs/{job_id}")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["cancelled"] is True

    # Cancel already cancelled -> 400
    assert client.delete(f"/api/pipeline/jobs/{job_id}").status_code == 400


def test_pipeline_stream_states():
    # 1. Nonexistent -> 404
    assert client.get("/api/pipeline/jobs/missing/stream").status_code == 404

    # 2. Already done job
    done_job = job_store.create("http://yt/done")
    job_store.update(done_job.id, status="done", result=[{"clip": 1}])
    res_done = client.get(f"/api/pipeline/jobs/{done_job.id}/stream")
    assert res_done.status_code == 200
    assert "event: done" in res_done.text

    # 3. Already failed job
    fail_job = job_store.create("http://yt/fail")
    job_store.update(fail_job.id, status="failed", error_msg="Crash error")
    res_fail = client.get(f"/api/pipeline/jobs/{fail_job.id}/stream")
    assert res_fail.status_code == 200
    assert "event: error" in res_fail.text
    assert "Crash error" in res_fail.text

    # 4. Running job with active queue events
    running_job = job_store.create("http://yt/running")
    job_store.update(running_job.id, status="running")
    running_job._sse_queue.put_nowait({"event": "progress", "data": {"step": "extract", "progress": 10}})
    running_job._sse_queue.put_nowait({"event": "done", "data": {"clips": []}})
    res_run = client.get(f"/api/pipeline/jobs/{running_job.id}/stream")
    assert res_run.status_code == 200
    assert "event: progress" in res_run.text
    assert "event: done" in res_run.text

    # 5. Running job with timeout keepalive
    timeout_job = job_store.create("http://yt/timeout")
    job_store.update(timeout_job.id, status="running")

    call_count = [0]
    import asyncio

    async def mock_wait_for(fut, timeout):
        call_count[0] += 1
        if call_count[0] == 1:
            raise asyncio.TimeoutError()
        return {"event": "done", "data": {}}

    with patch("asyncio.wait_for", side_effect=mock_wait_for):
        res_timeout = client.get(f"/api/pipeline/jobs/{timeout_job.id}/stream")
        assert res_timeout.status_code == 200
        assert ": keepalive" in res_timeout.text


# ─────────────────────────────────────────────────────────────
# 5. QUEUE & CALENDAR
# ─────────────────────────────────────────────────────────────


def test_queue_endpoints(test_data):
    cid = test_data["clip_id"]

    # Add to queue without scheduled_at (auto slot)
    with patch(
        "core.autopilot.AutoPilotManager.compute_next_available_slot", return_value=(None, "2026-09-04T15:30:00Z")
    ):
        add_res = client.post("/api/queue", json={"clip_id": cid})
        assert add_res.status_code == 201
        qid = add_res.json()["id"]

    # Add to queue with non-existent clip -> 404
    assert client.post("/api/queue", json={"clip_id": "nonexistent"}).status_code == 404

    # List queue with status filter
    assert client.get("/api/queue?status=QUEUED").status_code == 200

    # Update queue item
    patch_res = client.patch(f"/api/queue/{qid}", json={"scheduled_at": "2026-09-05T19:00:00Z", "status": "SCHEDULED"})
    assert patch_res.status_code == 200

    # Calendar
    cal_res = client.get("/api/calendar?days=7")
    assert cal_res.status_code == 200
    assert len(cal_res.json()) >= 1

    # Shuffle
    with patch("core.autopilot.AutoPilotManager.diversified_shuffle", return_value={"shuffled": True}):
        shuf_res = client.post("/api/queue/shuffle")
        assert shuf_res.status_code == 200
        assert shuf_res.json()["shuffled"] is True

    # Delete from queue
    del_res = client.delete(f"/api/queue/{qid}")
    assert del_res.status_code == 200


# ─────────────────────────────────────────────────────────────
# 6. SCHEDULER
# ─────────────────────────────────────────────────────────────


def test_scheduler_endpoints():
    with (
        patch("core.autopilot.AutoPilotManager.start_background_worker", return_value=True),
        patch("core.autopilot.AutoPilotManager.get_background_worker_info", return_value={"running": True}),
    ):
        start_res = client.post("/api/scheduler/start", json={"interval_hours": 2.5})
        assert start_res.status_code == 200
        assert start_res.json()["started"] is True

    with patch("core.autopilot.AutoPilotManager.stop_background_worker", return_value=True):
        stop_res = client.post("/api/scheduler/stop")
        assert stop_res.status_code == 200
        assert stop_res.json()["stopped"] is True


# ─────────────────────────────────────────────────────────────
# 7. SETTINGS
# ─────────────────────────────────────────────────────────────


def test_settings_endpoints(tmp_path):
    # Masking helper in GET /api/settings
    with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaSyTestKey123456789", "OPENROUTER_API_KEY": "sk-or-v1-short"}):
        res = client.get("/api/settings")
        assert res.status_code == 200
        data = res.json()
        assert data["GEMINI_API_KEY"]["set"] is True
        assert "..." in data["GEMINI_API_KEY"]["masked"]

    # POST /api/settings/env with disallowed key -> 400
    assert client.post("/api/settings/env", json={"key": "DISALLOWED_KEY", "value": "x"}).status_code == 400

    # POST /api/settings/env with allowed key
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=old_key\n")
    with patch("backend.api.routes.settings._ENV_PATH", str(env_file)):
        res_env = client.post("/api/settings/env", json={"key": "GEMINI_API_KEY", "value": "new_key_value"})
        assert res_env.status_code == 200
        assert "new_key_value" in env_file.read_text()

        # Append new key that wasn't there
        res_append = client.post("/api/settings/env", json={"key": "DEEPSEEK_API_KEY", "value": "ds_key"})
        assert res_append.status_code == 200
        assert "DEEPSEEK_API_KEY=ds_key" in env_file.read_text()

    # Cache clear
    with patch("core.cache_manager.CacheManager.clear_temp_files", return_value=None):
        assert client.post("/api/settings/cache/clear").status_code == 200

    # DB clear
    with patch("core.database.DatabaseManager.clear_database", return_value=None):
        assert client.post("/api/settings/db/clear").status_code == 200

    # Disk usage
    with patch("core.cache_manager.CacheManager.get_disk_usage", return_value={"total_mb": 100}):
        res_disk = client.get("/api/settings/disk")
        assert res_disk.status_code == 200
        assert res_disk.json() == {"total_mb": 100}

    # Scoring config GET
    res_sc = client.get("/api/settings/scoring")
    assert res_sc.status_code == 200
    assert "hook_strength_weight" in res_sc.json()
    assert "categories" in res_sc.json()

    # Scoring config POST
    res_sc_post = client.post(
        "/api/settings/scoring",
        json={
            "hook_strength_weight": 40,
            "emotion_weight": 25,
            "story_completeness_weight": 20,
            "signal_validation_weight": 15,
            "band_labels_enabled": True,
            "ensemble_runs": 3,
            "mundane_score_cap": 25,
        },
    )
    assert res_sc_post.status_code == 200
    assert res_sc_post.json()["updated"] is True


# ─────────────────────────────────────────────────────────────
# 8. UPLOAD
# ─────────────────────────────────────────────────────────────


def test_upload_endpoints(test_data):
    cid = test_data["clip_id"]

    # YouTube 404 clip not found
    assert client.post("/api/upload/youtube/nonexistent").status_code == 404

    # YouTube upload - not authenticated -> 401
    with patch("core.uploader.YouTubeUploader.is_authenticated", return_value=False):
        assert client.post(f"/api/upload/youtube/{cid}").status_code == 401

    # YouTube upload - authenticated success
    with (
        patch("core.uploader.YouTubeUploader.is_authenticated", return_value=True),
        patch("core.uploader.YouTubeUploader.upload_short", return_value={"url": "http://yt.com/s", "id": "s1"}),
    ):
        yt_res = client.post(f"/api/upload/youtube/{cid}")
        assert yt_res.status_code == 200
        assert yt_res.json()["success"] is True

    # YouTube upload - exception -> 500
    with (
        patch("core.uploader.YouTubeUploader.is_authenticated", return_value=True),
        patch("core.uploader.YouTubeUploader.upload_short", side_effect=Exception("Upload quota exceeded")),
    ):
        assert client.post(f"/api/upload/youtube/{cid}").status_code == 500

    # Instagram upload - success
    with patch("core.instagram_uploader.InstagramUploader.upload_reel", return_value={"url": "http://ig.com/r"}):
        ig_res = client.post(f"/api/upload/instagram/{cid}")
        assert ig_res.status_code == 200
        assert ig_res.json()["success"] is True

    # Instagram upload - exception -> 500
    with patch("core.instagram_uploader.InstagramUploader.upload_reel", side_effect=Exception("IG token expired")):
        assert client.post(f"/api/upload/instagram/{cid}").status_code == 500

    # TikTok upload
    tt_res = client.post(f"/api/upload/tiktok/{cid}")
    assert tt_res.status_code == 200
    assert tt_res.json()["success"] is False


def test_upload_missing_file_400():
    db = DatabaseManager()
    try:
        with db._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO videos (id, url) VALUES ('v_nofile', 'http://yt')")
            conn.execute(
                "INSERT OR REPLACE INTO clips (id, video_id, render_path, created_at) VALUES ('c_nofile', 'v_nofile', '', '2026-01-01')"
            )
            conn.commit()

        assert client.post("/api/upload/youtube/c_nofile").status_code == 400
        assert client.post("/api/upload/instagram/c_nofile").status_code == 400
    finally:
        with db._connect() as conn:
            conn.execute("DELETE FROM clips WHERE id = 'c_nofile'")
            conn.execute("DELETE FROM videos WHERE id = 'v_nofile'")
            conn.commit()


# ─────────────────────────────────────────────────────────────
# 9. VIDEOS
# ─────────────────────────────────────────────────────────────


def test_videos_endpoints(test_data):
    vid = test_data["video_id"]

    # List videos
    client.get("/api/videos?limit=10")
    # Get single video
    get_res = client.get(f"/api/videos/{vid}")
    assert get_res.status_code == 200

    # Non-existent video
    assert client.get("/api/videos/nonexistent_vid").status_code == 404

    # Upload video thumbnail - non image
    res_non_img = client.post(
        f"/api/videos/{vid}/thumbnail", files={"file": ("test.txt", b"not an image", "text/plain")}
    )
    assert res_non_img.status_code == 400

    # Upload video thumbnail - invalid image bytes
    res_inv_img = client.post(
        f"/api/videos/{vid}/thumbnail", files={"file": ("test.jpg", b"corrupted image bytes", "image/jpeg")}
    )
    assert res_inv_img.status_code == 400

    # Upload video thumbnail - valid image
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (300, 450), color=(100, 200, 50)).save(buf, "JPEG")
    valid_bytes = buf.getvalue()

    res_up_vid = client.post(f"/api/videos/{vid}/thumbnail", files={"file": ("thumb.jpg", valid_bytes, "image/jpeg")})
    assert res_up_vid.status_code == 200
    assert res_up_vid.json()["success"] is True

    # Upload clip video thumbnail - valid image
    cid = test_data["clip_id"]
    res_up_clip = client.post(
        f"/api/clips/{cid}/upload-video-thumbnail", files={"file": ("thumb.jpg", valid_bytes, "image/jpeg")}
    )
    assert res_up_clip.status_code == 200
    assert res_up_clip.json()["success"] is True

    # Upload clip video thumbnail - non image
    assert (
        client.post(
            f"/api/clips/{cid}/upload-video-thumbnail", files={"file": ("test.txt", b"txt", "text/plain")}
        ).status_code
        == 400
    )

    # Upload clip video thumbnail - invalid clip_id
    assert (
        client.post(
            "/api/clips/nonexistent_clip_123/upload-video-thumbnail",
            files={"file": ("thumb.jpg", valid_bytes, "image/jpeg")},
        ).status_code
        == 404
    )

    # Upload clip video thumbnail - corrupted bytes
    assert (
        client.post(
            f"/api/clips/{cid}/upload-video-thumbnail", files={"file": ("thumb.jpg", b"bad image data", "image/jpeg")}
        ).status_code
        == 400
    )
    assert get_res.json()["id"] == vid
    assert "clips" in get_res.json()

    # Get non-existent video -> 404
    assert client.get("/api/videos/nonexistent_vid").status_code == 404
