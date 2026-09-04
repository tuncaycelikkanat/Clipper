import os

from backend.db.database import DatabaseManager
from backend.db.schema import SCHEMA_SQL


def test_database_manager_init(tmp_path):
    db_file = tmp_path / "sub" / "test.db"
    DatabaseManager(db_path=str(db_file))
    assert os.path.exists(tmp_path / "sub")

    # Test when dir already exists
    db2 = DatabaseManager(db_path=str(db_file))
    assert db2.db_path == str(db_file)


def test_database_manager_connection(tmp_path):
    db_file = tmp_path / "test.db"
    db = DatabaseManager(db_path=str(db_file))
    conn = db.get_connection()
    assert conn is not None
    cur = conn.execute("PRAGMA foreign_keys;")
    row = cur.fetchone()
    assert row[0] == 1
    conn.close()


def test_database_manager_init_db(tmp_path):
    db_file = tmp_path / "test_init.db"
    db = DatabaseManager(db_path=str(db_file))
    db.init_db()
    with db.get_connection() as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "videos" in tables
        assert "clips" in tables
        assert "channels" in tables
        assert "channel_seen_videos" in tables
        assert "publish_queue" in tables
        assert "renders" in tables
        assert "pipeline_jobs" in tables


def test_schema_sql_content():
    assert "CREATE TABLE IF NOT EXISTS videos" in SCHEMA_SQL
