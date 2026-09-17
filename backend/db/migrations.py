"""
backend/db/migrations.py — Otomatik schema migration.
Mevcut clipper.db'yi yeni şemaya geçirir.
"""

from __future__ import annotations

import contextlib
import sqlite3

from loguru import logger


def _safe_alter(conn: sqlite3.Connection, sql: str) -> None:
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute(sql)


def run_migrations(db) -> None:
    """Mevcut veritabanını yeni şemaya migrate eder."""
    with db.get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")

        # ── 1. clips tablosuna yeni sütunlar ──────────────────────────
        for col_sql in [
            "ALTER TABLE clips ADD COLUMN description TEXT",
            "ALTER TABLE clips ADD COLUMN tags TEXT",
            "ALTER TABLE clips ADD COLUMN thumbnail_path TEXT",
            "ALTER TABLE clips ADD COLUMN render_mode TEXT",
            "ALTER TABLE clips ADD COLUMN has_facecam INTEGER DEFAULT 0",
        ]:
            _safe_alter(conn, col_sql)

        # ── 2. videos tablosuna yeni sütunlar ─────────────────────────
        for col_sql in [
            "ALTER TABLE videos ADD COLUMN upload_date TEXT",
            "ALTER TABLE videos ADD COLUMN error_msg TEXT",
            "ALTER TABLE videos ADD COLUMN channel_id TEXT",
        ]:
            _safe_alter(conn, col_sql)

        # ── 3. tracked_channels → channels tablosuna köprüle ─────────
        # channels tablosu (DNA) varsa, tracked_channels verilerini ona merge et
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

        if "tracked_channels" in tables:
            _safe_alter(conn, "ALTER TABLE tracked_channels ADD COLUMN check_interval_h REAL DEFAULT 2.0")
            _safe_alter(conn, "ALTER TABLE tracked_channels ADD COLUMN last_video_id TEXT")
            _safe_alter(conn, "ALTER TABLE tracked_channels ADD COLUMN last_video_date TEXT")
            _safe_alter(conn, "ALTER TABLE tracked_channels ADD COLUMN youtube_username TEXT")
            _safe_alter(conn, "ALTER TABLE tracked_channels ADD COLUMN instagram_username TEXT")

        # ── 4. channel_seen_videos (channel_processed_videos'dan migrate) ──
        if "channel_processed_videos" in tables and "channel_seen_videos" not in tables:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS channel_seen_videos (
                    channel_id   TEXT NOT NULL,
                    video_id     TEXT NOT NULL,
                    title        TEXT,
                    upload_date  TEXT,
                    seen_at      TEXT NOT NULL,
                    processed    INTEGER DEFAULT 0,
                    skipped      INTEGER DEFAULT 0,
                    PRIMARY KEY (channel_id, video_id)
                )
            """)
            # Migrate existing anchor data
            # Join on url since old table uses channel_url
            if "tracked_channels" in tables:
                conn.execute("""
                    INSERT OR IGNORE INTO channel_seen_videos
                        (channel_id, video_id, title, seen_at, processed)
                    SELECT tc.id, cpv.video_id, cpv.title, cpv.processed_at, 1
                    FROM channel_processed_videos cpv
                    JOIN tracked_channels tc ON tc.url = cpv.channel_url
                """)
            logger.info("Migrated channel_processed_videos → channel_seen_videos")

        # ── 5. autopilot_queue → publish_queue column additions ───────
        if "autopilot_queue" in tables:
            for col_sql in [
                "ALTER TABLE autopilot_queue ADD COLUMN tiktok_url TEXT",
                "ALTER TABLE autopilot_queue ADD COLUMN retry_count INTEGER DEFAULT 0",
                "ALTER TABLE autopilot_queue ADD COLUMN published_at TEXT",
            ]:
                _safe_alter(conn, col_sql)

        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()

    logger.info("✅ Database migrations completed.")
