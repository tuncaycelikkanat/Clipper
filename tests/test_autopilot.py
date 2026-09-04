"""
tests/test_autopilot.py — Unit & Integration tests for AutoPilotManager
"""

import datetime
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from core.autopilot import AutoPilotManager
from core.database import DatabaseManager


@pytest.fixture
def auto_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    db.init_db()
    yield db
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def manager(auto_db):
    return AutoPilotManager(
        db=auto_db,
        daily_slots=["13:00", "18:00", "22:00"],
        timezone_offset_hours=3,  # Turkey UTC+3
    )


# ===========================================================================
# 1. SMART SLOT ALLOCATOR TESTS
# ===========================================================================


def test_compute_next_available_slot_morning(manager):
    """Sabah 10:00 UTC (13:00 TR) öncesinde (örn: 06:00 UTC = 09:00 TR) sıradaki slot 13:00 TR (10:00 UTC) olmalıdır."""
    # 2026-08-23 06:00 UTC -> 09:00 TR
    base_utc = datetime.datetime(2026, 8, 23, 6, 0, tzinfo=datetime.timezone.utc)
    cand_utc, iso_str = manager.compute_next_available_slot(reference_time_utc=base_utc)

    # 13:00 TR = 10:00 UTC
    assert cand_utc == datetime.datetime(2026, 8, 23, 10, 0, tzinfo=datetime.timezone.utc)
    assert iso_str == "2026-08-23T10:00:00Z"


def test_compute_next_available_slot_afternoon(manager):
    """Öğleden sonra 14:00 TR (11:00 UTC) durumunda sıradaki slot 18:00 TR (15:00 UTC) olmalıdır."""
    base_utc = datetime.datetime(2026, 8, 23, 11, 0, tzinfo=datetime.timezone.utc)
    cand_utc, iso_str = manager.compute_next_available_slot(reference_time_utc=base_utc)

    # 18:00 TR = 15:00 UTC
    assert cand_utc == datetime.datetime(2026, 8, 23, 15, 0, tzinfo=datetime.timezone.utc)
    assert iso_str == "2026-08-23T15:00:00Z"


def test_compute_next_available_slot_late_night(manager):
    """Gece 23:30 TR (20:30 UTC) durumunda sıradaki slot ertesi gün 13:00 TR (10:00 UTC) olmalıdır."""
    base_utc = datetime.datetime(2026, 8, 23, 20, 30, tzinfo=datetime.timezone.utc)
    cand_utc, iso_str = manager.compute_next_available_slot(reference_time_utc=base_utc)

    # Ertesi gün 13:00 TR = 10:00 UTC
    assert cand_utc == datetime.datetime(2026, 8, 24, 10, 0, tzinfo=datetime.timezone.utc)
    assert iso_str == "2026-08-24T10:00:00Z"


def test_compute_next_available_slot_chains_after_latest(manager):
    """Kuyrukta en son 24 Ağustos 18:00 TR (15:00 UTC) varsa, yeni video 24 Ağustos 22:00 TR (19:00 UTC) slota atanmalıdır."""
    base_utc = datetime.datetime(2026, 8, 23, 8, 0, tzinfo=datetime.timezone.utc)
    latest_iso = "2026-08-24T15:00:00Z"  # 18:00 TR

    cand_utc, iso_str = manager.compute_next_available_slot(
        reference_time_utc=base_utc,
        latest_scheduled_iso=latest_iso,
    )

    assert cand_utc == datetime.datetime(2026, 8, 24, 19, 0, tzinfo=datetime.timezone.utc)
    assert iso_str == "2026-08-24T19:00:00Z"


# ===========================================================================
# 2. CHANNEL MANAGEMENT TESTS
# ===========================================================================


def test_add_and_get_tracked_channels(manager, auto_db):
    ch_id = manager.add_channel(
        url="https://youtube.com/@StreamerTest",
        name="Streamer Test",
        min_score=92,
        target_playlist="PL_TEST_123",
        auto_upload=True,
    )
    assert ch_id is not None

    channels = manager.get_tracked_channels()
    assert len(channels) == 1
    assert channels[0]["name"] == "Streamer Test"
    assert channels[0]["min_score"] == 92
    assert channels[0]["target_playlist"] == "PL_TEST_123"

    # Remove channel
    manager.remove_channel(ch_id)
    assert len(manager.get_tracked_channels()) == 0


# ===========================================================================
# 3. AUTOPILOT QUEUE DATABASE OPERATIONS
# ===========================================================================


def test_autopilot_queue_persistence_and_status(auto_db):
    auto_db.save_video({"id": "v_queue_01", "title": "Test Video"})

    q_id = auto_db.add_to_autopilot_queue(
        video_id="v_queue_01",
        clip_id="c_01",
        channel_url="https://youtube.com/@test",
        title="Epic Clutch #Shorts",
        render_path="/tmp/fake_render.mp4",
        thumbnail_path="/tmp/fake_thumb.jpg",
        viral_score=95,
        scheduled_at="2026-08-25T10:00:00Z",
        status="QUEUED",
    )
    assert q_id is not None

    items = auto_db.get_autopilot_queue()
    assert len(items) == 1
    assert items[0]["status"] == "QUEUED"
    assert items[0]["viral_score"] == 95

    # Update to SCHEDULED with youtube URL
    auto_db.update_autopilot_queue_status(
        queue_id=q_id,
        status="SCHEDULED",
        youtube_url="https://youtube.com/shorts/fake_id",
    )

    updated_items = auto_db.get_autopilot_queue()
    assert updated_items[0]["status"] == "SCHEDULED"
    assert updated_items[0]["youtube_url"] == "https://youtube.com/shorts/fake_id"

    # Latest scheduled time
    latest = auto_db.get_latest_scheduled_time()
    assert latest == "2026-08-25T10:00:00Z"


# ===========================================================================
# 4. AUTOPILOT CYCLE RUNNER & >=90 FILTERING
# ===========================================================================


def test_run_cycle_no_channels(manager):
    res = manager.run_cycle()
    assert res["channels_checked"] == 0
    assert res["clips_stockpiled"] == 0


@patch("core.notifier.Notifier.notify_clip_ready")
@patch("core.uploader.YouTubeUploader.upload_short")
@patch("core.uploader.YouTubeUploader.is_authenticated")
@patch("core.thumbnail.ThumbnailGenerator.batch_generate_thumbnails")
@patch("core.deepseek_engine.DeepSeekEngine.generate_shorts_copy")
@patch("core.pipeline.ClipperPipeline.execute")
@patch("core.feed.ChannelFeed.get_channel_videos")
def test_run_cycle_processes_and_filters_90_score(
    mock_feed,
    mock_pipeline,
    mock_deepseek,
    mock_thumbs,
    mock_is_auth,
    mock_upload,
    mock_notify,
    manager,
    tmp_path,
):
    # 1. Kanal ekle
    manager.add_channel(
        url="https://youtube.com/@TopGamer",
        name="Top Gamer",
        min_score=90,
        target_playlist="PL_GAMES",
        auto_upload=True,
    )

    # 2. Feed 2 video dönsün (1 yeni, 1 eski)
    mock_feed.return_value = [
        {"id": "new_vid_101", "url": "https://youtube.com/watch?v=new_vid_101", "title": "New Stream 101"},
    ]

    # 3. Pipeline render sonuçları: 1 klip 94 skor (geçer), 1 klip 82 skor (elenir)
    fake_render = str(tmp_path / "top_clip.mp4")
    with open(fake_render, "w") as f:
        f.write("video_bytes")

    mock_pipeline.return_value = [
        {
            "clip_id": "clip_high_score",
            "title": "İnanılmaz Vuruş",
            "category": "CLUTCH",
            "score": 94,
            "viral_confidence": 94,
            "render_path": fake_render,
            "hook_caption": "Bunu kimse beklemiyordu!",
            "duration": 25.0,
        },
        {
            "clip_id": "clip_low_score",
            "title": "Sıradan An",
            "category": "GAMING",
            "score": 82,
            "viral_confidence": 82,
            "render_path": fake_render,
            "duration": 20.0,
        },
    ]

    # 4. Copywriting & Thumbnail
    mock_deepseek.return_value = {
        "title": "Burada ölürsem oyunu silerim dedi ve... 😂 #Shorts",
        "description": "Son saniye 1v4 clutch anı! Sizce ne yapmalıydı?\n\n🎬 Orijinal: Top Gamer\n\n#Shorts #Gaming",
        "tags": ["gaming", "shorts", "clutch"],
    }
    mock_thumbs.return_value = [str(tmp_path / "thumb.jpg")]

    # 5. YouTube Auth & Upload
    mock_is_auth.return_value = True
    mock_upload.return_value = {
        "video_id": "yt_sched_101",
        "url": "https://youtube.com/shorts/yt_sched_101",
        "status": "uploaded",
    }

    # Döngüyü çalıştır (1. Tarama, 2. İşleme)
    res_scan = manager.run_cycle()
    assert res_scan["channels_checked"] == 1
    assert res_scan["new_videos_found"] == 1

    res_proc = manager.process_pending_videos(max_videos=5)
    assert res_proc["processed"] == 1

    # DB Kuyruğu kontrolü
    queue = manager.db.get_autopilot_queue()
    assert len(queue) == 1
    assert queue[0]["viral_score"] == 94
    assert queue[0]["status"] == "QUEUED"
    assert queue[0]["youtube_url"] is None


@patch("core.feed.ChannelFeed.get_channel_videos")
def test_run_cycle_skips_when_no_new_videos(mock_feed, manager, auto_db):
    manager.add_channel(
        url="https://youtube.com/@Streamer",
        name="Streamer",
    )
    auto_db.save_video({"id": "already_processed_v1", "title": "Old Video"})
    # Kanalın işlenmiş videoları listesine ekle (anchor tabanlı yeni video tespiti)
    auto_db.record_processed_video("https://youtube.com/@Streamer", "already_processed_v1", "Old Video")
    mock_feed.return_value = [{"id": "already_processed_v1", "url": "http://yt.com/1"}]

    res = manager.run_cycle()
    assert res["channels_checked"] == 1
    assert res["new_videos_found"] == 0
    assert res["clips_stockpiled"] == 0


@patch("core.notifier.Notifier.notify_clip_ready")
@patch("core.uploader.YouTubeUploader.upload_short")
@patch("core.uploader.YouTubeUploader.is_authenticated")
@patch("core.deepseek_engine.DeepSeekEngine.generate_shorts_copy")
@patch("core.pipeline.ClipperPipeline.execute")
@patch("core.feed.ChannelFeed.get_channel_videos")
def test_run_cycle_upload_error_fallbacks_to_queued(
    mock_feed,
    mock_pipeline,
    mock_deepseek,
    mock_is_auth,
    mock_upload,
    mock_notify,
    manager,
    tmp_path,
):
    manager.add_channel(
        url="https://youtube.com/@ErrorStreamer",
        name="Error Streamer",
        min_score=90,
        auto_upload=True,
    )
    mock_feed.return_value = [{"id": "vid_err_1", "url": "http://yt.com/err", "title": "Err Vid"}]

    fake_render = str(tmp_path / "clip_err.mp4")
    with open(fake_render, "w") as f:
        f.write("data")

    mock_pipeline.return_value = [
        {
            "clip_id": "c_err",
            "title": "High score clip",
            "score": 95,
            "render_path": fake_render,
        }
    ]
    mock_deepseek.side_effect = Exception("DeepSeek API down")
    mock_is_auth.return_value = True

    res_scan = manager.run_cycle()
    assert res_scan["new_videos_found"] == 1

    res_proc = manager.process_pending_videos(max_videos=5)
    assert res_proc["processed"] == 1

    queue = manager.db.get_autopilot_queue()
    assert len(queue) == 1
    assert queue[0]["status"] == "QUEUED"  # Stokta kaldı!


def test_remove_and_refill_gap_shifts_subsequent_items(manager, auto_db):
    auto_db.save_video({"id": "v_gap", "title": "Gap Test Video"})

    # 3 video ekle
    q1 = auto_db.add_to_autopilot_queue(
        video_id="v_gap",
        clip_id="c1",
        channel_url="http://yt.com",
        title="Video 1 (13:00)",
        render_path="/tmp/1.mp4",
        thumbnail_path="",
        viral_score=92,
        scheduled_at="2026-08-25T10:00:00Z",
        status="SCHEDULED",
    )
    q2 = auto_db.add_to_autopilot_queue(
        video_id="v_gap",
        clip_id="c2",
        channel_url="http://yt.com",
        title="Video 2 (18:00)",
        render_path="/tmp/2.mp4",
        thumbnail_path="",
        viral_score=94,
        scheduled_at="2026-08-25T15:00:00Z",
        status="SCHEDULED",
    )
    q3 = auto_db.add_to_autopilot_queue(
        video_id="v_gap",
        clip_id="c3",
        channel_url="http://yt.com",
        title="Video 3 (22:00)",
        render_path="/tmp/3.mp4",
        thumbnail_path="",
        viral_score=96,
        scheduled_at="2026-08-25T19:00:00Z",
        status="SCHEDULED",
    )

    # 1. videoyu sil -> 2 ve 3 öne kaymalı!
    res = manager.remove_and_refill_gap(q1)
    assert res["success"] is True
    assert res["deleted_title"] == "Video 1 (13:00)"
    assert res["shifted_count"] == 2

    # Kalan kuyruğu kontrol et
    remaining = auto_db.get_all_active_scheduled_queue()
    assert len(remaining) == 2
    # Video 2 artık 13:00'te (10:00 UTC) olmalı
    assert remaining[0]["id"] == q2
    assert remaining[0]["scheduled_at"] == "2026-08-25T10:00:00Z"
    # Video 3 artık 18:00'de (15:00 UTC) olmalı
    assert remaining[1]["id"] == q3
    assert remaining[1]["scheduled_at"] == "2026-08-25T15:00:00Z"


def test_get_calendar_days_data(manager, auto_db):
    auto_db.save_video({"id": "v_cal", "title": "Cal Test"})
    # Add an item
    auto_db.add_to_autopilot_queue(
        video_id="v_cal",
        clip_id="c_cal",
        channel_url="http://yt.com",
        title="Today's Video",
        render_path="/tmp/cal.mp4",
        thumbnail_path="",
        viral_score=93,
        scheduled_at="2026-08-23T10:00:00Z",
        status="SCHEDULED",
    )

    days = manager.get_calendar_days_data(days_ahead=7)
    assert len(days) == 7
    assert "label" in days[0]
    assert "item_count" in days[0]


def test_background_worker_lifecycle(auto_db):
    AutoPilotManager.stop_background_worker()
    assert AutoPilotManager.is_background_worker_running() is False

    started = AutoPilotManager.start_background_worker(interval_hours=1.0, db=auto_db)
    assert started is True
    assert AutoPilotManager.is_background_worker_running() is True

    # Double start is safe
    assert AutoPilotManager.start_background_worker(interval_hours=1.0, db=auto_db) is True

    info = AutoPilotManager.get_background_worker_info()
    assert info["running"] is True
    assert info["interval_hours"] == 1.0

    stopped = AutoPilotManager.stop_background_worker()
    assert stopped is True
    assert AutoPilotManager.is_background_worker_running() is False


def test_publish_due_socials_empty(manager):
    """publish_due_socials returns 0 when no items are due."""
    count = manager.publish_due_socials()
    assert count == 0


@patch("core.multi_publisher.MultiPublisher")
def test_publish_due_socials(mock_multi_pub_class, manager, auto_db, tmp_path):
    mock_multi = mock_multi_pub_class.return_value
    mock_multi.publish_clip.return_value = {
        "youtube": {"status": "success", "url": "http://yt.com"},
        "instagram": {"status": "success", "url": "http://ig.com"},
    }

    manager.uploader.is_authenticated = MagicMock(return_value=True)
    manager.instagram.is_authenticated = MagicMock(return_value=True)

    # Add dummy queued item with existing render file
    fake_video = tmp_path / "sync_video.mp4"
    fake_video.write_bytes(b"sample_data")

    auto_db.save_video({"id": "v_sync", "title": "Sync Test"})
    auto_db.add_to_autopilot_queue(
        video_id="v_sync",
        clip_id="c_sync",
        channel_url="http://yt.com",
        title="Sync Clip",
        render_path=str(fake_video),
        thumbnail_path="",
        viral_score=95,
        scheduled_at="2020-01-01T10:00:00Z",
        status="QUEUED",
    )

    count = manager.publish_due_socials()
    assert count == 1

    with manager.db._connect() as conn:
        row = conn.execute(
            "SELECT status, youtube_url, instagram_url FROM autopilot_queue WHERE title='Sync Clip'"
        ).fetchone()
        assert row[0] == "PUBLISHED"
        assert row[1] == "http://yt.com"
        assert row[2] == "http://ig.com"


def test_scan_and_queue_latest_channels_excludes_adal(manager, auto_db):
    """Kanalları tararken Adal kanalı hariç tutulmalı, diğer kanalların son videoları sıraya eklenmelidir."""
    # Add two channels: one Adal, one other streamer
    manager.add_channel(url="https://youtube.com/@Adal", name="Adal")
    manager.add_channel(url="https://youtube.com/@TolunayOren", name="Tolunay Ören")

    # Mock feed videos
    manager.feed.get_channel_videos = MagicMock(
        return_value=[
            {"id": "vid_tolunay_1", "url": "https://youtube.com/watch?v=t1", "title": "Tolunay Yeni Video 1"},
        ]
    )

    res = manager.scan_and_queue_latest_channels(exclude_keywords=["adal"], max_videos_per_channel=1)

    assert res["scanned_channels"] == 1
    assert "Adal" in res["skipped_channels"]
    assert res["new_videos_found"] == 1
    assert len(res["videos"]) == 1
    assert res["videos"][0]["id"] == "vid_tolunay_1"

    # Verify stored in DB with status pending
    pending = auto_db.get_unprocessed_videos()
    assert any(v["id"] == "vid_tolunay_1" and v["status"] == "pending" for v in pending)
