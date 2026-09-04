import sqlite3

from backend.db.database import DatabaseManager
from backend.db.migrations import _safe_alter, run_migrations


def test_safe_alter(tmp_path):
    db_file = tmp_path / "test_alter.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE sample (id TEXT PRIMARY KEY);")

    # Successful alter
    _safe_alter(conn, "ALTER TABLE sample ADD COLUMN age INTEGER;")
    # Duplicate alter should be caught safely
    _safe_alter(conn, "ALTER TABLE sample ADD COLUMN age INTEGER;")
    conn.close()


def test_run_migrations_with_legacy_tables(tmp_path):
    db_file = tmp_path / "test_mig.db"
    db = DatabaseManager(db_path=str(db_file))

    # Setup legacy schema before migration
    with db.get_connection() as conn:
        conn.execute("CREATE TABLE clips (id TEXT PRIMARY KEY, video_id TEXT);")
        conn.execute("CREATE TABLE videos (id TEXT PRIMARY KEY, url TEXT);")
        conn.execute("CREATE TABLE tracked_channels (id TEXT PRIMARY KEY, url TEXT, name TEXT);")
        conn.execute("""
            CREATE TABLE channel_processed_videos (
                channel_url TEXT,
                video_id TEXT,
                title TEXT,
                processed_at TEXT,
                PRIMARY KEY (channel_url, video_id)
            );
        """)
        conn.execute("CREATE TABLE autopilot_queue (id TEXT PRIMARY KEY, clip_id TEXT);")

        # Seed some data to verify migration
        conn.execute("INSERT INTO tracked_channels (id, url, name) VALUES ('ch1', 'http://yt.com/ch1', 'Chan1');")
        conn.execute(
            "INSERT INTO channel_processed_videos (channel_url, video_id, title, processed_at) VALUES ('http://yt.com/ch1', 'v1', 'Video 1', '2026-01-01');"
        )
        conn.commit()

    run_migrations(db)

    # Verify columns and migrated data
    with db.get_connection() as conn:
        # Check clips columns
        cur = conn.execute("PRAGMA table_info(clips);")
        clip_cols = [r[1] for r in cur.fetchall()]
        assert "description" in clip_cols
        assert "tags" in clip_cols
        assert "thumbnail_path" in clip_cols
        assert "render_mode" in clip_cols
        assert "has_facecam" in clip_cols

        # Check videos columns
        cur = conn.execute("PRAGMA table_info(videos);")
        vid_cols = [r[1] for r in cur.fetchall()]
        assert "upload_date" in vid_cols
        assert "error_msg" in vid_cols
        assert "channel_id" in vid_cols

        # Check tracked_channels columns
        cur = conn.execute("PRAGMA table_info(tracked_channels);")
        ch_cols = [r[1] for r in cur.fetchall()]
        assert "check_interval_h" in ch_cols
        assert "last_video_id" in ch_cols
        assert "last_video_date" in ch_cols

        # Check channel_seen_videos migration
        rows = conn.execute("SELECT * FROM channel_seen_videos;").fetchall()
        assert len(rows) == 1
        assert rows[0]["channel_id"] == "ch1"
        assert rows[0]["video_id"] == "v1"

        # Check autopilot_queue columns
        cur = conn.execute("PRAGMA table_info(autopilot_queue);")
        aq_cols = [r[1] for r in cur.fetchall()]
        assert "tiktok_url" in aq_cols
        assert "retry_count" in aq_cols
        assert "published_at" in aq_cols
