"""SQLite database manager for the clipper project.

Tables
------
* videos  – one row per YouTube video processed
* clips   – one row per extracted clip (linked to a video)
* channels – watched channel metadata + channel-DNA JSON
* renders – one row per rendered output file (linked to a clip)

Usage::

    from core.database import DatabaseManager

    db = DatabaseManager()
    db.init_db()
    db.save_video(video_data)
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.logger import logger

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DB_PATH = os.path.join(_PROJECT_ROOT, "clipper.db")


def _utcnow() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------
_DDL_VIDEOS = """
CREATE TABLE IF NOT EXISTS videos (
    id           TEXT PRIMARY KEY,
    url          TEXT NOT NULL,
    title        TEXT,
    uploader     TEXT,
    duration     INTEGER,
    view_count   INTEGER,
    has_heatmap  INTEGER DEFAULT 0,
    processed_at TEXT,
    status       TEXT DEFAULT 'pending'
);
"""

_DDL_CLIPS = """
CREATE TABLE IF NOT EXISTS clips (
    id               TEXT PRIMARY KEY,
    video_id         TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    rank             INTEGER,
    title            TEXT,
    category         TEXT,
    start_time       REAL,
    end_time         REAL,
    duration         REAL,
    hook_caption     TEXT,
    score            INTEGER,
    viral_confidence INTEGER,
    render_path      TEXT,
    created_at       TEXT
);
"""

_DDL_CHANNELS = """
CREATE TABLE IF NOT EXISTS channels (
    id           TEXT PRIMARY KEY,
    url          TEXT NOT NULL,
    name         TEXT,
    last_checked TEXT,
    dna_json     TEXT
);
"""

_DDL_RENDERS = """
CREATE TABLE IF NOT EXISTS renders (
    id          TEXT PRIMARY KEY,
    clip_id     TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    render_mode TEXT,
    file_path   TEXT,
    file_size   INTEGER,
    created_at  TEXT,
    exported    INTEGER DEFAULT 0
);
"""

_DDL_HEATMAP_PATTERNS = """
CREATE TABLE IF NOT EXISTS heatmap_patterns (
    video_id              TEXT PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
    channel_id            TEXT,
    spike_heatmap_corr    REAL,
    silence_heatmap_corr  REAL,
    peak_ratio            REAL,
    heatmap_meta_json     TEXT,
    recorded_at           TEXT
);
"""


# ---------------------------------------------------------------------------
# DatabaseManager
# ---------------------------------------------------------------------------
class DatabaseManager:
    """Thin SQLite wrapper providing CRUD operations for the clipper schema."""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        """
        Args:
            db_path: Absolute path to the SQLite database file.
                     Defaults to ``<project_root>/clipper.db``.
        """
        self.db_path = db_path
        logger.debug("DatabaseManager initialised — db_path={}", self.db_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open a connection with WAL journal mode and foreign-key support."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    # ------------------------------------------------------------------
    # Schema initialisation
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        """Create all tables if they do not already exist."""
        with self._connect() as conn:
            conn.execute(_DDL_VIDEOS)
            conn.execute(_DDL_CLIPS)
            conn.execute(_DDL_CHANNELS)
            conn.execute(_DDL_RENDERS)
            conn.execute(_DDL_HEATMAP_PATTERNS)
            conn.commit()
        logger.info("Database initialised at {}", self.db_path)

    # ------------------------------------------------------------------
    # Video operations
    # ------------------------------------------------------------------

    def video_exists(self, video_id: str) -> bool:
        """Return True if *video_id* is in the videos table."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM videos WHERE id = ?;", (video_id,)
            ).fetchone()
            return row is not None

    def get_video(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Return video metadata if it exists, otherwise None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM videos WHERE id = ?;", (video_id,)
            ).fetchone()
            if row:
                return dict(row)
            return None

    def save_video(self, video_data: Dict[str, Any]) -> str:
        """Upsert a video record.

        Args:
            video_data: Dictionary containing video metadata.  Expected keys
                mirror the ``videos`` table columns; ``id`` is mandatory.

        Returns:
            The video ID that was upserted.
        """
        vid_id: str = video_data["id"]
        sql = """
            INSERT INTO videos (id, url, title, uploader, duration,
                                view_count, has_heatmap, processed_at, status)
            VALUES (:id, :url, :title, :uploader, :duration,
                    :view_count, :has_heatmap, :processed_at, :status)
            ON CONFLICT(id) DO UPDATE SET
                url          = excluded.url,
                title        = excluded.title,
                uploader     = excluded.uploader,
                duration     = excluded.duration,
                view_count   = excluded.view_count,
                has_heatmap  = excluded.has_heatmap,
                processed_at = excluded.processed_at,
                status       = excluded.status;
        """
        params: Dict[str, Any] = {
            "id": vid_id,
            "url": video_data.get("url", ""),
            "title": video_data.get("title", ""),
            "uploader": video_data.get("uploader", ""),
            "duration": video_data.get("duration", 0),
            "view_count": video_data.get("view_count", 0),
            "has_heatmap": 1 if video_data.get("has_heatmap") else 0,
            "processed_at": video_data.get("processed_at", _utcnow()),
            "status": video_data.get("status", "pending"),
        }
        with self._connect() as conn:
            conn.execute(sql, params)
            conn.commit()
        logger.debug("Upserted video id={}", vid_id)
        return vid_id

    def get_unprocessed_videos(self) -> List[Dict[str, Any]]:
        """Return all video rows whose status is ``'pending'``."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM videos WHERE status = 'pending';"
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_video_done(self, video_id: str) -> None:
        """Set the status of *video_id* to ``'done'``.

        Args:
            video_id: The YouTube video ID to mark as processed.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE videos SET status = 'done', processed_at = ? WHERE id = ?;",
                (_utcnow(), video_id),
            )
            conn.commit()
        logger.debug("Marked video {} as done", video_id)

    # ------------------------------------------------------------------
    # Clip operations
    # ------------------------------------------------------------------

    def save_clips(self, video_id: str, clips: List[Dict[str, Any]]) -> List[str]:
        """Bulk-insert clips linked to *video_id*.

        Existing rows are skipped (INSERT OR IGNORE) to avoid duplicates
        when the pipeline is re-run.

        Args:
            video_id: Parent video ID that clips belong to.
            clips:    List of clip dicts (as produced by
                      :class:`~core.llm_engine.GeminiHighlightEngine`).

        Returns:
            List of the newly inserted clip IDs.
        """
        sql = """
            INSERT OR REPLACE INTO clips
                (id, video_id, rank, title, category, start_time, end_time,
                 duration, hook_caption, score, viral_confidence, render_path,
                 created_at)
            VALUES
                (:id, :video_id, :rank, :title, :category, :start_time,
                 :end_time, :duration, :hook_caption, :score,
                 :viral_confidence, :render_path, :created_at);
        """
        inserted_ids: List[str] = []
        with self._connect() as conn:
            for clip in clips:
                rank = clip.get("rank", 0)
                clip_id = f"{video_id}_clip_{rank}"
                # Store the id back into the clip dict so the caller can use it
                clip["id"] = clip_id
                params: Dict[str, Any] = {
                    "id": clip_id,
                    "video_id": video_id,
                    "rank": clip.get("rank", 0),
                    "title": clip.get("title", ""),
                    "category": clip.get("category", ""),
                    "start_time": clip.get("start_time", 0.0),
                    "end_time": clip.get("end_time", 0.0),
                    "duration": clip.get("duration", 0.0),
                    "hook_caption": clip.get("hook_caption", ""),
                    "score": clip.get("score", 0),
                    "viral_confidence": clip.get("viral_confidence", clip.get("score", 0)),
                    "render_path": clip.get("render_path", None),
                    "created_at": _utcnow(),
                }
                conn.execute(sql, params)
                inserted_ids.append(clip_id)
            conn.commit()
        logger.info("Saved {} clips for video {}", len(inserted_ids), video_id)
        return inserted_ids

    def get_clips_for_video(self, video_id: str) -> List[Dict[str, Any]]:
        """Return all clip rows for *video_id*, ordered by rank.

        Args:
            video_id: The parent video ID.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM clips WHERE video_id = ? ORDER BY rank;",
                (video_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Render operations
    # ------------------------------------------------------------------

    def save_render(
        self,
        clip_id: str,
        render_mode: str,
        file_path: str,
    ) -> str:
        """Insert a render record for *clip_id*.

        Args:
            clip_id:     Parent clip UUID.
            render_mode: Render preset string, e.g. ``"square_1x1_black"``.
            file_path:   Absolute path to the rendered MP4 file.

        Returns:
            The new render row ID.
        """
        render_id = str(uuid.uuid4())
        file_size: int = 0
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)

        sql = """
            INSERT INTO renders (id, clip_id, render_mode, file_path,
                                 file_size, created_at, exported)
            VALUES (?, ?, ?, ?, ?, ?, 0);
        """
        with self._connect() as conn:
            conn.execute(
                sql,
                (render_id, clip_id, render_mode, file_path, file_size, _utcnow()),
            )
            conn.commit()
        logger.debug(
            "Saved render id={} clip_id={} path={}", render_id, clip_id, file_path
        )
        return render_id

    # ------------------------------------------------------------------
    # Channel operations
    # ------------------------------------------------------------------

    def save_channel(self, channel_data: Dict[str, Any]) -> str:
        """Upsert a channel record.

        Args:
            channel_data: Dict with keys: ``id``, ``url``, ``name``,
                          ``last_checked``, ``dna_json`` (optional dict/str).

        Returns:
            The channel ID.
        """
        chan_id: str = channel_data.get("id", str(uuid.uuid4()))
        dna = channel_data.get("dna_json")
        if isinstance(dna, dict):
            dna = json.dumps(dna, ensure_ascii=False)

        sql = """
            INSERT INTO channels (id, url, name, last_checked, dna_json)
            VALUES (:id, :url, :name, :last_checked, :dna_json)
            ON CONFLICT(id) DO UPDATE SET
                url          = excluded.url,
                name         = excluded.name,
                last_checked = excluded.last_checked,
                dna_json     = excluded.dna_json;
        """
        params: Dict[str, Any] = {
            "id": chan_id,
            "url": channel_data.get("url", ""),
            "name": channel_data.get("name", ""),
            "last_checked": channel_data.get("last_checked", _utcnow()),
            "dna_json": dna,
        }
        with self._connect() as conn:
            conn.execute(sql, params)
            conn.commit()
        logger.debug("Upserted channel id={}", chan_id)
        return chan_id

    def get_channel(self, channel_id_or_name: str) -> Optional[Dict[str, Any]]:
        """Return channel metadata by id or name if it exists, otherwise None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE id = ? OR name = ? LIMIT 1;",
                (channel_id_or_name, channel_id_or_name),
            ).fetchone()
            if row:
                return dict(row)
            return None

    def get_channel_clips(self, channel_name_or_uploader: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Return past clips for a given channel / uploader by joining videos and clips tables.
        """
        sql = """
            SELECT c.*, v.uploader, v.title AS video_title
            FROM clips c
            JOIN videos v ON c.video_id = v.id
            WHERE v.uploader = ? OR v.uploader LIKE ?
            ORDER BY c.created_at DESC
            LIMIT ?;
        """
        with self._connect() as conn:
            rows = conn.execute(
                sql,
                (channel_name_or_uploader, f"%{channel_name_or_uploader}%", limit),
            ).fetchall()
        return [dict(r) for r in rows]


    def save_heatmap_pattern(
        self,
        video_id: str,
        channel_id: str,
        spike_heatmap_corr: float,
        silence_heatmap_corr: float,
        peak_ratio: float,
        heatmap_meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Bir videonun ses→heatmap korelasyon verilerini saklar.
        HeatmapPredictor tarafından model öğrenmesi için kullanılır.

        Args:
            video_id:              YouTube video ID
            channel_id:            Kanal ID
            spike_heatmap_corr:    Ses spike ile heatmap korelasyonu (-1 ile 1)
            silence_heatmap_corr:  Sessizlik patlaması ile heatmap korelasyonu
            peak_ratio:            Toplam sürenin kaçında heatmap zirvesi var (0-1)
            heatmap_meta:          Ek meta veriler (JSON olarak saklanır)
        """
        meta_json = json.dumps(heatmap_meta or {}, ensure_ascii=False)
        sql = """
            INSERT INTO heatmap_patterns
                (video_id, channel_id, spike_heatmap_corr, silence_heatmap_corr,
                 peak_ratio, heatmap_meta_json, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                channel_id           = excluded.channel_id,
                spike_heatmap_corr   = excluded.spike_heatmap_corr,
                silence_heatmap_corr = excluded.silence_heatmap_corr,
                peak_ratio           = excluded.peak_ratio,
                heatmap_meta_json    = excluded.heatmap_meta_json,
                recorded_at          = excluded.recorded_at;
        """
        with self._connect() as conn:
            conn.execute(
                sql,
                (video_id, channel_id, spike_heatmap_corr,
                 silence_heatmap_corr, peak_ratio, meta_json, _utcnow()),
            )
            conn.commit()
        logger.debug("Saved heatmap pattern for video {}", video_id)

    def get_videos_with_heatmap_patterns(
        self, channel_id: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Geçmiş heatmap korelasyon kayıtlarını döner.
        HeatmapPredictor model öğrenmesi için kullanır.

        Args:
            channel_id: Filtrelenecek kanal ID (None ise tüm kanallar)
            limit:      Maksimum kayıt sayısı

        Returns:
            heatmap_patterns satırlarının listesi
        """
        if channel_id:
            sql = """
                SELECT * FROM heatmap_patterns
                WHERE channel_id = ?
                ORDER BY recorded_at DESC LIMIT ?;
            """
            params: tuple = (channel_id, limit)
        else:
            sql = "SELECT * FROM heatmap_patterns ORDER BY recorded_at DESC LIMIT ?;"
            params = (limit,)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def clear_database(self) -> None:
        """Clear all videos, clips, and renders records."""
        with self._connect() as conn:
            conn.execute("DELETE FROM renders;")
            conn.execute("DELETE FROM clips;")
            conn.execute("DELETE FROM videos;")
            conn.execute("DELETE FROM heatmap_patterns;")
            conn.commit()
        logger.info("Cleared all records from database.")

