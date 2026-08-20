import os
import sqlite3
import tempfile
import pytest
from core.database import DatabaseManager

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    yield db
    if os.path.exists(path):
        os.remove(path)

def test_init_db_creates_tables(temp_db):
    temp_db.init_db()
    conn = sqlite3.connect(temp_db.db_path)
    cursor = conn.cursor()
    
    tables = ["videos", "clips", "channels", "renders"]
    for table in tables:
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
        assert cursor.fetchone() is not None
        
    conn.close()

def test_save_and_get_video(temp_db):
    temp_db.init_db()
    assert temp_db.get_video("vid123") is None

    video_data = {
        "id": "vid123",
        "url": "http://youtube.com/watch?v=vid123",
        "title": "Test Video",
        "uploader": "Tester",
        "duration": 600,
        "view_count": 100,
        "has_heatmap": 0,
        "status": "pending"
    }
    temp_db.save_video(video_data)
    
    v = temp_db.get_video("vid123")
    assert v is not None
    assert v["title"] == "Test Video"

    pending = temp_db.get_unprocessed_videos()
    assert len(pending) == 1
    assert pending[0]["id"] == "vid123"
    assert pending[0]["title"] == "Test Video"
    
    temp_db.mark_video_done("vid123")
    assert len(temp_db.get_unprocessed_videos()) == 0

def test_video_exists(temp_db):
    temp_db.init_db()
    assert not temp_db.video_exists("vid456")
    
    temp_db.save_video({"id": "vid456"})
    assert temp_db.video_exists("vid456")

def test_save_clips(temp_db):
    temp_db.init_db()
    temp_db.save_video({"id": "vid123"})
    
    clips = [
        {"rank": 1, "title": "Clip 1", "start_time": 10.0, "end_time": 20.0, "score": 90},
        {"rank": 2, "title": "Clip 2", "start_time": 30.0, "end_time": 40.0, "score": 80}
    ]
    
    clip_ids = temp_db.save_clips("vid123", clips)
    assert len(clip_ids) == 2
    
    saved_clips = temp_db.get_clips_for_video("vid123")
    assert len(saved_clips) == 2
    assert saved_clips[0]["title"] == "Clip 1"
    assert saved_clips[1]["title"] == "Clip 2"

def test_save_render_with_real_file(temp_db):
    temp_db.init_db()
    temp_db.save_video({"id": "vid123"})
    clip_ids = temp_db.save_clips("vid123", [{"rank": 1}])
    clip_id = clip_ids[0]
    
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"fake content" * 100)
        file_path = f.name
        
    try:
        render_id = temp_db.save_render(clip_id, "square_1x1_black", file_path)
        
        conn = sqlite3.connect(temp_db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM renders WHERE id = ?", (render_id,))
        row = cursor.fetchone()
        assert row["clip_id"] == clip_id
        assert row["render_mode"] == "square_1x1_black"
        assert row["file_path"] == file_path
        assert row["file_size"] > 0
        conn.close()
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

def test_save_channel(temp_db):
    temp_db.init_db()
    chan_id = temp_db.save_channel({
        "url": "https://youtube.com/@test",
        "name": "Test Channel",
        "dna_json": {"style": "energetic"}
    })
    assert chan_id is not None
