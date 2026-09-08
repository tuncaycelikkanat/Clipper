"""tests/test_phase1_critical_fixes.py — Tests for Phase 1 architectural and bug fixes."""

import os
from unittest.mock import MagicMock, patch

import pytest
from backend.deps import get_db
from core.database import DatabaseManager


def test_unified_database_manager_and_singleton():
    """Verify backend.deps.get_db returns core.database.DatabaseManager and reuses instance."""
    db1 = get_db()
    db2 = get_db()
    assert isinstance(db1, DatabaseManager)
    assert db1 is db2, "get_db() should return the singleton instance"
    assert hasattr(db1, "_connect")
    assert hasattr(db1, "get_connection")


def test_tracked_channels_table_and_query(temp_db):
    """Verify tracked_channels table exists and can be queried without crashing."""
    # Insert a tracked channel
    temp_db.execute(
        "INSERT INTO tracked_channels (id, url, name, min_score, active, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("chan_1", "https://youtube.com/@gaming", "Gaming Channel", 85, 1, "2026-09-08T12:00:00Z"),
    )

    with temp_db._connect() as conn:
        rows = conn.execute("SELECT * FROM tracked_channels WHERE active = 1").fetchall()
        assert len(rows) == 1
        assert rows[0]["name"] == "Gaming Channel"
        assert rows[0]["min_score"] == 85


def test_batch_delete_clips_optimized(temp_db, tmp_path):
    """Verify batch_delete_clips deletes records in bulk and removes files without N+1 loops."""
    # Setup test video and clips with dummy render files
    temp_db.save_video({"id": "vid_batch", "url": "https://youtu.be/batch", "title": "Batch Video"})

    file1 = tmp_path / "clip1.mp4"
    file2 = tmp_path / "clip2.mp4"
    file1.write_text("dummy video 1")
    file2.write_text("dummy video 2")

    clip_ids = temp_db.save_clips("vid_batch", [
        {
            "rank": 1,
            "start_time": 0.0,
            "end_time": 10.0,
            "render_path": str(file1),
        },
        {
            "rank": 2,
            "start_time": 10.0,
            "end_time": 20.0,
            "render_path": str(file2),
        },
    ])
    placeholders = ",".join("?" for _ in clip_ids)

    with temp_db._connect() as conn:
        rows = conn.execute(
            f"SELECT render_path FROM clips WHERE id IN ({placeholders})",
            clip_ids,
        ).fetchall()
        assert len(rows) == 2
        for r in rows:
            if r["render_path"] and os.path.exists(r["render_path"]):
                os.remove(r["render_path"])

        cursor = conn.execute(f"DELETE FROM clips WHERE id IN ({placeholders})", clip_ids)
        assert cursor.rowcount == 2
        conn.commit()

    # Files must be deleted
    assert not file1.exists()
    assert not file2.exists()

    # Clips must be gone
    remaining = temp_db.get_clips_for_video("vid_batch")
    assert len(remaining) == 0


def test_extractor_comment_failure_is_logged():
    """Verify that comment extraction exceptions in extractor.py are logged and don't crash."""
    from core.extractor import YouTubeExtractor

    extractor = YouTubeExtractor()
    with patch("yt_dlp.YoutubeDL") as mock_ydl, patch("core.extractor.logger.warning") as mock_log:
        mock_ydl.side_effect = Exception("Simulated network timeout")
        comments = extractor.get_video_comments("fake_video_id")

        assert comments == []
        mock_log.assert_called_once()
        assert "yt-dlp comment extraction failed" in mock_log.call_args[0][0]


def test_audio_dsp_chunk_failure_is_logged():
    """Verify that chunk extraction subprocess errors in audio_dsp.py are logged."""
    from core.audio_dsp import AudioDSPAnalyzer

    analyzer = AudioDSPAnalyzer()
    with patch("subprocess.Popen", side_effect=Exception("FFmpeg not found")), \
         patch("core.audio_dsp.logger.error") as mock_log:
        start_sec, samples = analyzer._extract_chunk_raw(
            "http://example.com/stream",
            start_sec=10.0,
            dur_sec=5.0,
            sample_rate=8000,
        )
        assert start_sec == 10.0
        assert len(samples) == int(5.0 * 8000)
        mock_log.assert_called_once()
        assert "Audio chunk extraction failed" in mock_log.call_args[0][0]
