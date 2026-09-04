"""
tests/test_database_advanced.py — Advanced coverage tests for DatabaseManager
"""

import pytest

from core.database import DatabaseManager


@pytest.fixture
def db(tmp_path):
    db_file = tmp_path / "test_adv.db"
    manager = DatabaseManager(db_path=str(db_file))
    manager.init_db()
    return manager


def test_database_channels_and_clips(db):
    db.save_video({"id": "v1", "title": "Game 1", "uploader": "ProGamer"})
    db.save_clips("v1", [{"title": "Clip 1", "score": 90, "start_time": 0, "end_time": 10}])
    clips = db.get_clips_for_video("v1")
    assert len(clips) == 1
    cid = clips[0]["id"]

    db.save_render(clip_id=cid, render_mode="shorts", file_path="/fake/render.mp4")
    channel_clips = db.get_channel_clips("ProGamer")
    assert len(channel_clips) == 1

    db.save_channel({"id": "ch1", "url": "https://yt.com/@progamer", "name": "ProGamer"})
    ch = db.get_channel("ProGamer")
    assert ch is not None
    assert ch["id"] == "ch1"


def test_database_tracked_channels(db):
    db.add_tracked_channel("https://yt.com/@pro", "Pro Gamer", min_score=85, target_playlist="PL1", auto_upload=1)
    channels = db.get_tracked_channels(active_only=True)
    assert len(channels) == 1
    assert channels[0]["name"] == "Pro Gamer"

    db.update_tracked_channel_checked("https://yt.com/@pro")
    db.remove_tracked_channel("https://yt.com/@pro")
    assert len(db.get_tracked_channels(active_only=True)) == 0


def test_database_autopilot_queue_operations(db):
    db.save_video({"id": "v2", "title": "Game 2"})
    qid = db.add_to_autopilot_queue(
        video_id="v2",
        clip_id="c2",
        channel_url="https://yt.com/@ch",
        title="Epic Move",
        render_path="/fake/path.mp4",
        thumbnail_path="/fake/thumb.jpg",
        viral_score=95,
        scheduled_at="2026-09-01T12:00:00Z",
        status="QUEUED",
    )

    queue = db.get_autopilot_queue()
    assert len(queue) >= 1
    assert db.get_latest_scheduled_time() == "2026-09-01T12:00:00Z"

    db.update_autopilot_queue_status(qid, "PUBLISHED", youtube_url="https://yt.com/short1")
    queue_all = db.get_all_active_scheduled_queue()
    assert isinstance(queue_all, list)

    db.update_autopilot_queue_scheduled_time(qid, "2026-09-02T15:00:00Z")
    db.delete_from_autopilot_queue(qid)
    assert len(db.get_autopilot_queue()) == 0


def test_database_heatmap_pattern_and_slots(db):
    db.save_video({"id": "v3", "title": "Game 3"})
    db.save_heatmap_pattern(
        video_id="v3",
        channel_id="ch3",
        spike_heatmap_corr=0.85,
        silence_heatmap_corr=0.45,
        peak_ratio=0.15,
        heatmap_meta={"source": "test"},
    )
    patterns = db.get_videos_with_heatmap_patterns()
    assert len(patterns) >= 1

    # Pool & Slot assignments
    qid1 = db.add_to_autopilot_queue("v3", "c3_1", "https://yt.com/@ch", "P1", "", "", 90, "2026-09-05T12:00:00Z")
    qid2 = db.add_to_autopilot_queue("v3", "c3_2", "https://yt.com/@ch", "P2", "", "", 90, "2026-09-05T15:00:00Z")

    db.unassign_clip_to_pool(qid1)
    pool = db.get_pool_clips()
    assert len(pool) >= 1

    db.assign_clip_to_slot(qid1, "2026-09-05T18:00:00Z")
    db.swap_clip_slots(qid1, qid2)

    day_items = db.get_day_slot_items("2026-09-05")
    assert len(day_items) >= 1

    db.cleanup_keep_planned()
    db.clear_database(keep_tracked_channels=True)
