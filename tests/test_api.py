"""Tests for FastAPI backend routes and API behavior."""
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from core.database import DatabaseManager

client = TestClient(app)


@pytest.fixture(autouse=True)
def seed_database():
    """Seed test data in database before testing API endpoints."""
    db = DatabaseManager()
    db.init_db()
    db.save_video({
        "id": "api_test_vid",
        "url": "https://youtube.com/watch?v=api_test_vid",
        "title": "API Test Video",
        "uploader": "Test Channel",
        "duration": 120,
        "view_count": 500,
        "has_heatmap": True
    })
    clip_ids = db.save_clips("api_test_vid", [
        {
            "rank": 1,
            "title": "Awesome Highlight",
            "category": "CLUTCH",
            "start_time": 10.0,
            "end_time": 25.0,
            "duration": 15.0,
            "score": 95,
            "hook_caption": "Unbelievable moment!"
        }
    ])
    yield
    with db._connect() as conn:
        conn.execute("DELETE FROM clips WHERE video_id = 'api_test_vid'")
        conn.execute("DELETE FROM videos WHERE id = 'api_test_vid'")
        conn.commit()


def test_root_and_health():
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["name"] == "Clipper API"

    res_h = client.get("/health")
    assert res_h.status_code == 200
    assert res_h.json()["status"] == "ok"


def test_get_settings():
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert "GEMINI_API_KEY" in data


def test_list_videos():
    res = client.get("/api/videos")
    assert res.status_code == 200
    videos = res.json()
    assert len(videos) >= 1
    assert any(v["id"] == "api_test_vid" for v in videos)


def test_list_and_get_clips():
    res = client.get("/api/clips")
    assert res.status_code == 200
    clips = res.json()
    assert len(clips) >= 1
    clip_id = clips[0]["id"]

    res_detail = client.get(f"/api/clips/{clip_id}")
    assert res_detail.status_code == 200
    assert res_detail.json()["id"] == clip_id


def test_update_clip():
    res = client.get("/api/clips")
    clip_id = res.json()[0]["id"]

    patch_res = client.patch(f"/api/clips/{clip_id}", json={"title": "Updated Clip Title"})
    assert patch_res.status_code == 200
    assert patch_res.json()["title"] == "Updated Clip Title"


def test_channels_crud():
    create_res = client.post("/api/channels", json={
        "url": "https://youtube.com/@testchannel_fastapi",
        "name": "FastAPI Test Channel",
        "min_score": 85,
        "auto_upload": True
    })
    assert create_res.status_code == 201
    channel = create_res.json()
    channel_id = channel.get("id") or "https://youtube.com/@testchannel_fastapi"

    list_res = client.get("/api/channels")
    assert list_res.status_code == 200

    del_res = client.delete(f"/api/channels/{channel_id}")
    assert del_res.status_code == 200


def test_queue_and_calendar():
    cal_res = client.get("/api/calendar")
    assert cal_res.status_code == 200
    assert isinstance(cal_res.json(), list)

    queue_res = client.get("/api/queue")
    assert queue_res.status_code == 200


def test_scheduler_status():
    status_res = client.get("/api/scheduler/status")
    assert status_res.status_code == 200
    assert "running" in status_res.json()
