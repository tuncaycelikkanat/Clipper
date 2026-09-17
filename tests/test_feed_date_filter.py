"""tests/test_feed_date_filter.py — Tests for date filtering and new video detection."""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from core.autopilot import AutoPilotManager
from core.database import DatabaseManager
from core.feed import ChannelFeed


def test_is_video_too_old_iso_date():
    now = datetime.datetime.now(datetime.timezone.utc)
    recent_iso = (now - datetime.timedelta(days=1)).isoformat()
    assert ChannelFeed.is_video_too_old({"published_at": recent_iso}, max_age_days=7) is False

    old_iso = (now - datetime.timedelta(days=20)).isoformat()
    assert ChannelFeed.is_video_too_old({"published_at": old_iso}, max_age_days=7) is True
    assert ChannelFeed.is_video_too_old({"published_at": old_iso}, max_age_days=None) is False


def test_is_video_too_old_upload_date_string():
    now = datetime.datetime.now(datetime.timezone.utc)
    recent_ymd = (now - datetime.timedelta(days=1)).strftime("%Y%m%d")
    assert ChannelFeed.is_video_too_old({"upload_date": recent_ymd}, max_age_days=7) is False

    old_ymd = (now - datetime.timedelta(days=30)).strftime("%Y%m%d")
    assert ChannelFeed.is_video_too_old({"upload_date": old_ymd}, max_age_days=7) is True


def test_get_new_videos_filters_by_max_age():
    now = datetime.datetime.now(datetime.timezone.utc)
    recent_iso = (now - datetime.timedelta(days=2)).isoformat()
    old_iso = (now - datetime.timedelta(days=45)).isoformat()

    mock_videos = [
        {"id": "vid_recent", "title": "Yeni Video", "published_at": recent_iso},
        {"id": "vid_old", "title": "2 Ay Önceki Video", "published_at": old_iso},
    ]

    with patch.object(ChannelFeed, "get_channel_videos", return_value=mock_videos):
        new_vids = ChannelFeed.get_new_videos(
            channel_url="https://youtube.com/@Test",
            processed_ids=[],
            max_count=10,
            max_age_days=7,
        )
        assert len(new_vids) == 1
        assert new_vids[0]["id"] == "vid_recent"


def test_scan_and_queue_skips_old_videos_and_no_fallback(tmp_path):
    db_file = str(tmp_path / "test_filter.db")
    db = DatabaseManager(db_path=db_file)
    db.init_db()

    manager = AutoPilotManager(db=db)
    manager.add_channel(url="https://youtube.com/@OldChannel", name="Old Channel", auto_anchor=False)

    now = datetime.datetime.now(datetime.timezone.utc)
    old_1 = (now - datetime.timedelta(days=60)).isoformat()
    old_2 = (now - datetime.timedelta(days=90)).isoformat()

    mock_videos = [
        {"id": "old_vid_1", "url": "https://youtube.com/watch?v=old1", "title": "60 Gün Önce", "published_at": old_1},
        {"id": "old_vid_2", "url": "https://youtube.com/watch?v=old2", "title": "90 Gün Önce", "published_at": old_2},
    ]

    manager.feed.get_channel_videos = MagicMock(return_value=mock_videos)
    res = manager.scan_and_queue_latest_channels(max_videos_per_channel=1, max_age_days=7)

    assert res["new_videos_found"] == 0
    assert len(res["videos"]) == 0
    assert len(db.get_unprocessed_videos()) == 0


def test_add_channel_auto_anchor(tmp_path):
    db_file = str(tmp_path / "test_anchor.db")
    db = DatabaseManager(db_path=db_file)
    db.init_db()

    mock_feed = MagicMock()
    mock_feed.get_channel_videos.return_value = [
        {"id": "existing_1", "title": "Eski 1"},
        {"id": "existing_2", "title": "Eski 2"},
    ]

    manager = AutoPilotManager(db=db, feed=mock_feed)
    ch_url = "https://youtube.com/@ExistingChannel"
    manager.add_channel(url=ch_url, name="Existing Channel", auto_anchor=True)

    processed_ids = db.get_processed_video_ids(ch_url)
    assert "existing_1" in processed_ids
    assert "existing_2" in processed_ids
