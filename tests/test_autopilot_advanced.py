"""
tests/test_autopilot_advanced.py — Advanced coverage tests for AutoPilotManager and SlotAllocator
"""

import datetime
from unittest.mock import MagicMock, patch
import pytest
from core.autopilot import AutoPilotManager
from core.database import DatabaseManager


@pytest.fixture
def auto_mgr(tmp_path):
    db_file = tmp_path / "auto_adv.db"
    db = DatabaseManager(db_path=str(db_file))
    db.init_db()
    mgr = AutoPilotManager(db=db)
    return mgr


def test_autopilot_channel_tracking_and_backfill(auto_mgr):
    auto_mgr.add_channel("https://yt.com/@gamer1", "Gamer 1", min_score=90)
    channels = auto_mgr.get_tracked_channels()
    assert len(channels) == 1

    auto_mgr.feed.get_channel_videos = MagicMock(return_value=[
        {"id": "vid1", "url": "https://yt.com/watch?v=vid1", "title": "Old Stream"}
    ])

    summary = auto_mgr.backfill_processed_videos()
    assert summary["recorded"] == 1
    assert auto_mgr.db.is_channel_video_processed("https://yt.com/@gamer1", "vid1")

    auto_mgr.remove_channel("https://yt.com/@gamer1")
    assert len(auto_mgr.get_tracked_channels()) == 0


def test_autopilot_calendar_days_and_slots(auto_mgr):
    # Add dummy item to queue
    auto_mgr.db.save_video({"id": "v10", "title": "V10"})
    qid = auto_mgr.db.add_to_autopilot_queue(
        video_id="v10",
        clip_id="c10",
        channel_url="https://yt.com/@ch",
        title="Slot Test",
        render_path="",
        thumbnail_path="",
        viral_score=92,
        scheduled_at="2026-09-02T12:00:00Z",
        status="QUEUED"
    )

    days = auto_mgr.get_calendar_days_data(days_ahead=3)
    assert len(days) == 3

    grid = auto_mgr.get_day_slots_grid("2026-09-02")
    assert isinstance(grid, dict)


def test_autopilot_assign_clip_to_date_slot(auto_mgr):
    auto_mgr.db.save_video({"id": "v11", "title": "V11"})
    qid = auto_mgr.db.add_to_autopilot_queue(
        video_id="v11",
        clip_id="c11",
        channel_url="https://yt.com/@ch",
        title="Assign Test",
        render_path="",
        thumbnail_path="",
        viral_score=92,
        scheduled_at="2026-09-02T12:00:00Z",
        status="QUEUED"
    )

    res = auto_mgr.assign_clip_to_date_slot(qid, "2026-09-03", "15:30")
    assert res is True
