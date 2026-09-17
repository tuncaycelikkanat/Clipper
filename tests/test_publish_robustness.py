"""tests/test_publish_robustness.py — Unit tests for Instagram Reels transient retry, concurrency lock, and exponential backoff."""

import datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.autopilot import AutoPilotManager, _PUBLISH_LOCK
from core.database import DatabaseManager
from core.instagram_uploader import InstagramUploader


@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_publish.db")
    db = DatabaseManager(db_path=db_path)
    db.init_db()
    return db


def test_instagram_publish_container_retry_on_transient_error():
    uploader = InstagramUploader(access_token="test_token", instagram_account_id="act_123")

    # First attempt: Meta transient error (code 2), second attempt: success
    resp_fail = MagicMock()
    resp_fail.status_code = 500
    resp_fail.json.return_value = {"error": {"code": 2, "message": "Please retry your request later"}}
    resp_fail.text = "Error"

    resp_success = MagicMock()
    resp_success.status_code = 200
    resp_success.json.return_value = {"id": "media_999"}

    with patch("requests.post", side_effect=[resp_fail, resp_success]) as mock_post, \
         patch("time.sleep") as mock_sleep:
        res = uploader.publish_container(container_id="c_123", max_retries=2)
        assert res["media_id"] == "media_999"
        assert res["status"] == "published"
        assert mock_post.call_count == 2
        # Verify sleep was called for initial CDN wait (3s) and retry backoff (6s)
        mock_sleep.assert_any_call(3)
        mock_sleep.assert_any_call(6)


def test_database_update_autopilot_queue_status_with_retry_and_schedule(test_db):
    test_db.save_video({"id": "v_test", "title": "Test Video"})
    test_db.add_to_autopilot_queue(
        video_id="v_test",
        clip_id="c_test",
        channel_url="http://yt.com",
        title="Test Clip",
        render_path="/path/test.mp4",
        thumbnail_path="",
        viral_score=90,
        scheduled_at="2026-01-01T10:00:00Z",
        status="QUEUED",
    )

    items = test_db.get_autopilot_queue()
    assert len(items) == 1
    q_id = items[0]["id"]

    new_sched = "2026-01-01T10:15:00Z"
    test_db.update_autopilot_queue_status(
        queue_id=q_id,
        status="PARTIAL_FAILED",
        youtube_url="https://youtube.com/shorts/test12345",
        retry_count=1,
        scheduled_at=new_sched,
        error_msg="Instagram failed",
    )

    with test_db._connect() as conn:
        row = conn.execute("SELECT status, youtube_url, retry_count, scheduled_at, error_msg FROM autopilot_queue WHERE id=?", (q_id,)).fetchone()
        assert row["status"] == "PARTIAL_FAILED"
        assert row["youtube_url"] == "https://youtube.com/shorts/test12345"
        assert row["retry_count"] == 1
        assert row["scheduled_at"] == new_sched
        assert row["error_msg"] == "Instagram failed"


def test_publish_due_socials_concurrency_lock(test_db):
    manager = AutoPilotManager(db=test_db)
    # Simulate another thread holding the lock
    _PUBLISH_LOCK.acquire()
    try:
        # Should skip immediately and return 0
        res = manager.publish_due_socials()
        assert res == 0
    finally:
        _PUBLISH_LOCK.release()


def test_publish_due_socials_youtube_success_instagram_fail_backoff(test_db, tmp_path):
    manager = AutoPilotManager(db=test_db)

    fake_video = tmp_path / "vid_partial.mp4"
    fake_video.write_bytes(b"data")

    test_db.save_video({"id": "v_part", "title": "Partial Video"})
    test_db.add_to_autopilot_queue(
        video_id="v_part",
        clip_id="c_part",
        channel_url="http://yt.com",
        title="Partial Clip",
        render_path=str(fake_video),
        thumbnail_path="",
        viral_score=95,
        scheduled_at="2020-01-01T10:00:00Z",
        status="QUEUED",
    )

    # Mock multi_pub to succeed for YouTube and fail for Instagram
    mock_multi = MagicMock()
    mock_multi.publish_clip.return_value = {
        "youtube": {"status": "success", "url": "https://youtube.com/shorts/yt_ok_123"},
        "instagram": {"status": "failed", "error": "Instagram network error"},
    }

    with patch("core.multi_publisher.MultiPublisher", return_value=mock_multi):
        published = manager.publish_due_socials()
        assert published == 0

    with test_db._connect() as conn:
        row = conn.execute("SELECT status, youtube_url, instagram_url, retry_count, scheduled_at, error_msg FROM autopilot_queue WHERE title='Partial Clip'").fetchone()
        assert row["status"] == "PARTIAL_FAILED"
        assert row["youtube_url"] == "https://youtube.com/shorts/yt_ok_123"
        assert row["instagram_url"] is None
        assert row["retry_count"] == 1
        # scheduled_at must be moved to future (10 min later)
        assert row["scheduled_at"] > "2020-01-01T10:00:00Z"
        assert "Instagram: Instagram network error" in row["error_msg"]


def test_publish_due_socials_max_retries_exceeded(test_db, tmp_path):
    manager = AutoPilotManager(db=test_db)

    fake_video = tmp_path / "vid_fail.mp4"
    fake_video.write_bytes(b"data")

    test_db.save_video({"id": "v_max", "title": "Max Retries Video"})
    test_db.add_to_autopilot_queue(
        video_id="v_max",
        clip_id="c_max",
        channel_url="http://yt.com",
        title="Max Retries Clip",
        render_path=str(fake_video),
        thumbnail_path="",
        viral_score=95,
        scheduled_at="2020-01-01T10:00:00Z",
        status="PARTIAL_FAILED",
    )

    # Set retry_count to 2
    with test_db._connect() as conn:
        conn.execute("UPDATE autopilot_queue SET retry_count = 2 WHERE title = 'Max Retries Clip'")
        conn.commit()

    mock_multi = MagicMock()
    mock_multi.publish_clip.return_value = {
        "youtube": {"status": "success", "url": "https://youtube.com/shorts/yt_saved"},
        "instagram": {"status": "failed", "error": "Permanent error"},
    }

    with patch("core.multi_publisher.MultiPublisher", return_value=mock_multi):
        published = manager.publish_due_socials()
        assert published == 0

    with test_db._connect() as conn:
        row = conn.execute("SELECT status, youtube_url, retry_count, error_msg FROM autopilot_queue WHERE title='Max Retries Clip'").fetchone()
        # Since youtube succeeded, final_status is PARTIAL_PUBLISHED
        assert row["status"] == "PARTIAL_PUBLISHED"
        assert row["youtube_url"] == "https://youtube.com/shorts/yt_saved"
        assert row["retry_count"] == 3
        assert "Maksimum deneme (3) aşıldı" in row["error_msg"]
