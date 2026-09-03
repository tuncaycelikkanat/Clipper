import pytest
import datetime
from core.database import DatabaseManager
from core.autopilot import AutoPilotManager

@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "test_planner.db")
    db = DatabaseManager(db_path=db_path)
    db.init_db()
    return db

def _create_dummy_clip(db, video_id="vid1", clip_id="c1", ch_url="https://youtube.com/@test"):
    db.save_video({
        "id": video_id,
        "url": f"https://youtube.com/watch?v={video_id}",
        "title": "Video " + video_id,
        "uploader": "Tester"
    })
    db.save_clips(video_id, [{
        "id": clip_id,
        "rank": 1,
        "title": "Clip " + clip_id,
        "category": "ACTION",
        "score": 90,
        "hook_caption": "Hook",
        "start_time": 10.0,
        "end_time": 25.0,
        "duration": 15.0
    }])

def test_assign_and_unassign_slot(temp_db):
    db = temp_db
    _create_dummy_clip(db, "vid1", "c1")
    
    # Klip ekle
    db.add_to_autopilot_queue(
        video_id="vid1",
        clip_id="c1",
        channel_url="https://youtube.com/@test",
        title="Test Clip 1",
        render_path="/path/to/clip1.mp4",
        thumbnail_path=None,
        viral_score=95,
        scheduled_at="2026-08-28T08:30:00Z",
        status="QUEUED"
    )
    
    # 1. Day items kontrolü
    items = db.get_day_slot_items("2026-08-28", tz_offset_hours=3)
    assert len(items) == 1
    assert items[0]["title"] == "Test Clip 1"
    
    queue_id = items[0]["id"]
    
    # 2. Havuza çek (unassign)
    ok = db.unassign_clip_to_pool(queue_id)
    assert ok is True
    
    # Gün slotu boşalmalı
    items_after = db.get_day_slot_items("2026-08-28", tz_offset_hours=3)
    assert len(items_after) == 0
    
    # Havuzda görünmeli
    pool = db.get_pool_clips()
    assert len(pool) == 1
    assert pool[0]["id"] == queue_id
    assert pool[0]["status"] == "UNASSIGNED"
    
    # 3. Yeniden slota ata
    ok2 = db.assign_clip_to_slot(queue_id, "2026-08-29T12:30:00Z")
    assert ok2 is True
    
    items_29 = db.get_day_slot_items("2026-08-29", tz_offset_hours=3)
    assert len(items_29) == 1
    assert items_29[0]["status"] == "QUEUED"

def test_swap_clip_slots(temp_db):
    db = temp_db
    _create_dummy_clip(db, "vid1", "c1")
    _create_dummy_clip(db, "vid2", "c2")
    
    db.add_to_autopilot_queue(
        video_id="vid1", clip_id="c1", channel_url="https://youtube.com/@ch1",
        title="Clip 1", render_path="", thumbnail_path=None, viral_score=90,
        scheduled_at="2026-08-28T08:30:00Z", status="QUEUED"
    )
    db.add_to_autopilot_queue(
        video_id="vid2", clip_id="c2", channel_url="https://youtube.com/@ch2",
        title="Clip 2", render_path="", thumbnail_path=None, viral_score=92,
        scheduled_at="2026-08-28T16:00:00Z", status="QUEUED"
    )
    
    with db._connect() as conn:
        q_ids = [r["id"] for r in conn.execute("SELECT id FROM autopilot_queue ORDER BY created_at ASC;").fetchall()]
    
    id1, id2 = q_ids[0], q_ids[1]
    
    # Swap yap
    swapped = db.swap_clip_slots(id1, id2)
    assert swapped is True
    
    with db._connect() as conn:
        row1 = conn.execute("SELECT scheduled_at FROM autopilot_queue WHERE id=?", (id1,)).fetchone()
        row2 = conn.execute("SELECT scheduled_at FROM autopilot_queue WHERE id=?", (id2,)).fetchone()
        
    assert row1["scheduled_at"] == "2026-08-28T16:00:00Z"
    assert row2["scheduled_at"] == "2026-08-28T08:30:00Z"

def test_autopilot_grid_and_shuffle(temp_db):
    db = temp_db
    autopilot = AutoPilotManager(db=db)
    
    for i in range(1, 5):
        _create_dummy_clip(db, f"v{i}", f"c{i}")
        
    # 4 klip ekle (2'si Kanal A, 2'si Kanal B)
    db.add_to_autopilot_queue(
        video_id="v1", clip_id="c1", channel_url="https://youtube.com/@KanalA",
        title="Kanal A - Klip 1", render_path="", thumbnail_path=None, viral_score=90,
        scheduled_at="2026-08-28T08:30:00Z", status="QUEUED"
    )
    db.add_to_autopilot_queue(
        video_id="v2", clip_id="c2", channel_url="https://youtube.com/@KanalA",
        title="Kanal A - Klip 2", render_path="", thumbnail_path=None, viral_score=91,
        scheduled_at="2026-08-28T12:30:00Z", status="QUEUED"
    )
    db.add_to_autopilot_queue(
        video_id="v3", clip_id="c3", channel_url="https://youtube.com/@KanalB",
        title="Kanal B - Klip 1", render_path="", thumbnail_path=None, viral_score=92,
        scheduled_at="2026-08-28T16:00:00Z", status="QUEUED"
    )
    db.add_to_autopilot_queue(
        video_id="v4", clip_id="c4", channel_url="https://youtube.com/@KanalB",
        title="Kanal B - Klip 2", render_path="", thumbnail_path=None, viral_score=93,
        scheduled_at="2026-08-28T19:30:00Z", status="QUEUED"
    )
    
    # Grid kontrolü
    grid = autopilot.get_day_slots_grid("2026-08-28")
    assert len(grid) == 4
    assert grid["11:30"] is not None
    assert grid["15:30"] is not None
    assert grid["19:00"] is not None
    assert grid["22:30"] is not None
    
    # Shuffle testi
    res = autopilot.diversified_shuffle(["2026-08-28"])
    assert res["shuffled_count"] == 4
    
    # Tekrar grid çek
    new_grid = autopilot.get_day_slots_grid("2026-08-28")
    assert all(v is not None for v in new_grid.values())
