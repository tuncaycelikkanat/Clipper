"""Tests for Streamlit UI navigation and page rendering with full database branches."""

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from core.database import DatabaseManager

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def seed_database():
    """Seed test data in database before testing UI pages."""
    db = DatabaseManager()
    db.init_db()
    db.save_video({
        "id": "ui_test_vid",
        "url": "https://youtube.com/watch?v=ui_test_vid",
        "title": "UI Test Video",
        "uploader": "Test Channel",
        "duration": 120,
        "view_count": 500,
        "has_heatmap": True
    })
    clip_ids = db.save_clips("ui_test_vid", [
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
    if clip_ids:
        db.save_render(clip_ids[0], "square_1x1_black", "/tmp/fake_clip.mp4")
    yield


def test_main_app_navigation():
    """Test that ui/app.py loads and configures navigation without error."""
    at = AppTest.from_file(str(ROOT / "ui" / "app.py"), default_timeout=10)
    at.run()
    assert not at.exception, f"UI threw exception: {at.exception}"


def test_analyze_page():
    """Test that ui/app_pages/analyze.py renders properly without crash."""
    at = AppTest.from_file(str(ROOT / "ui" / "app_pages" / "analyze.py"), default_timeout=10)
    at.run()
    assert not at.exception, f"Analyze page error: {at.exception}"


def test_clips_page_with_data():
    """Test that ui/app_pages/clips.py renders filters and clip cards properly."""
    at = AppTest.from_file(str(ROOT / "ui" / "app_pages" / "clips.py"), default_timeout=10)
    at.run()
    assert not at.exception, f"Clips page error: {at.exception}"


def test_export_page(monkeypatch):
    """Test that ui/app_pages/export.py renders properly."""
    from unittest.mock import MagicMock
    from core.uploader import YouTubeUploader
    monkeypatch.setattr(YouTubeUploader, "is_authenticated", lambda self: False)
    at = AppTest.from_file(str(ROOT / "ui" / "app_pages" / "export.py"), default_timeout=15)
    at.run()
    assert not at.exception, f"Export page error: {at.exception}"



def test_autopilot_page(monkeypatch):
    """Test that ui/app_pages/autopilot.py renders tabs and metrics properly."""
    from core.uploader import YouTubeUploader
    monkeypatch.setattr(YouTubeUploader, "is_authenticated", lambda self: False)
    at = AppTest.from_file(str(ROOT / "ui" / "app_pages" / "autopilot.py"), default_timeout=15)
    at.run()
    assert not at.exception, f"AutoPilot page error: {at.exception}"


def test_planner_page():
    """Test that ui/app_pages/planner.py renders day picker and slot cards properly."""
    at = AppTest.from_file(str(ROOT / "ui" / "app_pages" / "planner.py"), default_timeout=15)
    at.run()
    assert not at.exception, f"Planner page error: {at.exception}"


def test_settings_page():
    """Test that ui/app_pages/settings.py renders properly."""
    at = AppTest.from_file(str(ROOT / "ui" / "app_pages" / "settings.py"), default_timeout=10)
    at.run()
    assert not at.exception, f"Settings page error: {at.exception}"


