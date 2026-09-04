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

import contextlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from core.logger import logger

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DB_PATH = os.path.join(_PROJECT_ROOT, "clipper.db")


def _utcnow() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _json_dump(value: Any) -> str | None:
    """Serialize *value* to a JSON string for storage in TEXT columns.

    ``None`` is passed through untouched; lists/dicts are JSON-encoded so
    they round-trip with :func:`json.loads` (e.g. video ``tags``).
    """
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


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
    upload_date  TEXT,
    has_heatmap  INTEGER DEFAULT 0,
    processed_at TEXT,
    process_after TEXT,
    delay_hours  INTEGER DEFAULT 0,
    status       TEXT DEFAULT 'pending',
    tags         TEXT,
    description  TEXT
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
    created_at       TEXT,
    description      TEXT,
    tags             TEXT,
    thumbnail_path   TEXT,
    render_mode      TEXT,
    has_facecam      INTEGER DEFAULT 0
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

_DDL_TRACKED_CHANNELS = """
CREATE TABLE IF NOT EXISTS tracked_channels (
    id              TEXT PRIMARY KEY,
    url             TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    min_score       INTEGER DEFAULT 90,
    target_playlist TEXT,
    auto_upload     INTEGER DEFAULT 1,
    last_checked    TEXT,
    active          INTEGER DEFAULT 1,
    created_at      TEXT NOT NULL
);
"""

_DDL_CHANNEL_PROCESSED_VIDEOS = """
CREATE TABLE IF NOT EXISTS channel_processed_videos (
    channel_url TEXT NOT NULL,
    video_id    TEXT NOT NULL,
    title       TEXT,
    processed_at TEXT NOT NULL,
    PRIMARY KEY (channel_url, video_id)
);
"""

_DDL_AUTOPILOT_QUEUE = """
CREATE TABLE IF NOT EXISTS autopilot_queue (
    id             TEXT PRIMARY KEY,
    video_id       TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    clip_id        TEXT,
    channel_url    TEXT NOT NULL,
    title          TEXT NOT NULL,
    render_path    TEXT NOT NULL,
    thumbnail_path TEXT,
    viral_score    INTEGER NOT NULL,
    scheduled_at   TEXT NOT NULL,
    status         TEXT DEFAULT 'QUEUED',
    youtube_url    TEXT,
    instagram_url  TEXT,
    error_msg      TEXT,
    description    TEXT,
    created_at     TEXT NOT NULL
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
            conn.execute(_DDL_TRACKED_CHANNELS)
            conn.execute(_DDL_CHANNEL_PROCESSED_VIDEOS)
            conn.execute(_DDL_AUTOPILOT_QUEUE)
            # Mevcut veritabanları için yeni sütunları güvenle ekle
            for col_sql in (
                "ALTER TABLE autopilot_queue ADD COLUMN description TEXT;",
                "ALTER TABLE clips ADD COLUMN description TEXT;",
                "ALTER TABLE clips ADD COLUMN tags TEXT;",
                "ALTER TABLE clips ADD COLUMN thumbnail_path TEXT;",
                "ALTER TABLE clips ADD COLUMN render_mode TEXT;",
                "ALTER TABLE clips ADD COLUMN has_facecam INTEGER DEFAULT 0;",
                "ALTER TABLE clips ADD COLUMN score_band TEXT;",
                "ALTER TABLE clips ADD COLUMN rationale TEXT;",
                "ALTER TABLE videos ADD COLUMN process_after TEXT;",
                "ALTER TABLE videos ADD COLUMN delay_hours INTEGER DEFAULT 0;",
                "ALTER TABLE videos ADD COLUMN upload_date TEXT;",
            ):
                with contextlib.suppress(Exception):
                    conn.execute(col_sql)
            conn.commit()
        logger.info("Database initialised at {}", self.db_path)

    # ------------------------------------------------------------------
    # Video operations
    # ------------------------------------------------------------------

    def video_exists(self, video_id: str) -> bool:
        """Return True if *video_id* is in the videos table."""
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM videos WHERE id = ?;", (video_id,)).fetchone()
            return row is not None

    def get_video(self, video_id: str) -> dict[str, Any] | None:
        """Return video metadata if it exists, otherwise None."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM videos WHERE id = ?;", (video_id,)).fetchone()
            if row:
                return dict(row)
            return None

    def save_video(self, video_data: dict[str, Any]) -> str:
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
                                view_count, upload_date, has_heatmap, processed_at, process_after, delay_hours, status, tags, description)
            VALUES (:id, :url, :title, :uploader, :duration,
                    :view_count, :upload_date, :has_heatmap, :processed_at, :process_after, :delay_hours, :status, :tags, :description)
            ON CONFLICT(id) DO UPDATE SET
                url           = excluded.url,
                title         = excluded.title,
                uploader      = excluded.uploader,
                duration      = excluded.duration,
                view_count    = excluded.view_count,
                upload_date   = COALESCE(excluded.upload_date, videos.upload_date),
                has_heatmap   = excluded.has_heatmap,
                processed_at  = excluded.processed_at,
                process_after = COALESCE(excluded.process_after, videos.process_after),
                delay_hours   = COALESCE(excluded.delay_hours, videos.delay_hours),
                status        = excluded.status,
                tags          = excluded.tags,
                description   = excluded.description;
        """
        params: dict[str, Any] = {
            "id": vid_id,
            "url": video_data.get("url", ""),
            "title": video_data.get("title", ""),
            "uploader": video_data.get("uploader", ""),
            "duration": video_data.get("duration", 0),
            "view_count": video_data.get("view_count", 0),
            "upload_date": video_data.get("upload_date", ""),
            "has_heatmap": 1 if video_data.get("has_heatmap") else 0,
            "processed_at": video_data.get("processed_at", _utcnow()),
            "process_after": video_data.get("process_after"),
            "delay_hours": video_data.get("delay_hours", 0),
            "status": video_data.get("status", "pending"),
            "tags": _json_dump(video_data.get("tags")),
            "description": video_data.get("description"),
        }
        with self._connect() as conn:
            conn.execute(sql, params)
            conn.commit()
        logger.debug("Upserted video id={}", vid_id)
        return vid_id

    def update_video_delay(self, video_id: str, delay_hours: int = 24) -> None:
        """Set or clear process_after delay for a video."""
        import datetime
        if delay_hours > 0:
            process_after = (
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=delay_hours)
            ).isoformat()
        else:
            process_after = None
            delay_hours = 0
        with self._connect() as conn:
            conn.execute(
                "UPDATE videos SET delay_hours = ?, process_after = ? WHERE id = ?;",
                (delay_hours, process_after, video_id),
            )
            conn.commit()
        logger.info("Updated video id={} delay_hours={} process_after={}", video_id, delay_hours, process_after)

    def get_unprocessed_videos(self) -> list[dict[str, Any]]:
        """Return all video rows whose status is ``'pending'``."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM videos WHERE status = 'pending';").fetchall()
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

    def save_clips(self, video_id: str, clips: list[dict[str, Any]]) -> list[str]:
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
                 created_at, description, tags, thumbnail_path, score_band, rationale)
            VALUES
                (:id, :video_id, :rank, :title, :category, :start_time,
                 :end_time, :duration, :hook_caption, :score,
                 :viral_confidence, :render_path, :created_at,
                 :description, :tags, :thumbnail_path, :score_band, :rationale);
        """
        inserted_ids: list[str] = []
        with self._connect() as conn:
            for clip in clips:
                rank = clip.get("rank", 0)
                clip_id = f"{video_id}_clip_{rank}"
                # Store the id back into the clip dict so the caller can use it
                clip["id"] = clip_id
                params: dict[str, Any] = {
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
                    "description": clip.get("description", ""),
                    "tags": clip.get("tags", ""),
                    "thumbnail_path": clip.get("thumbnail_path", None),
                    "score_band": clip.get("score_band", ""),
                    "rationale": clip.get("rationale", ""),
                }
                conn.execute(sql, params)
                inserted_ids.append(clip_id)
            conn.commit()
        logger.info("Saved {} clips for video {}", len(inserted_ids), video_id)
        return inserted_ids

    def get_clips_for_video(self, video_id: str) -> list[dict[str, Any]]:
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
            conn.execute(
                "UPDATE clips SET render_path = ?, render_mode = ? WHERE id = ?;",
                (file_path, render_mode, clip_id),
            )
            conn.commit()
        logger.debug("Saved render id={} clip_id={} path={}", render_id, clip_id, file_path)
        return render_id

    # ------------------------------------------------------------------
    # Channel operations
    # ------------------------------------------------------------------

    def save_channel(self, channel_data: dict[str, Any]) -> str:
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
        params: dict[str, Any] = {
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

    def get_channel(self, channel_id_or_name: str) -> dict[str, Any] | None:
        """Return channel metadata by id or name if it exists, otherwise None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE id = ? OR name = ? LIMIT 1;",
                (channel_id_or_name, channel_id_or_name),
            ).fetchone()
            if row:
                return dict(row)
            return None

    def get_channel_clips(self, channel_name_or_uploader: str, limit: int = 50) -> list[dict[str, Any]]:
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
        heatmap_meta: dict[str, Any] | None = None,
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
                (video_id, channel_id, spike_heatmap_corr, silence_heatmap_corr, peak_ratio, meta_json, _utcnow()),
            )
            conn.commit()
        logger.debug("Saved heatmap pattern for video {}", video_id)

    def get_videos_with_heatmap_patterns(self, channel_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
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
    # AutoPilot & Tracked Channels operations
    # ------------------------------------------------------------------

    def add_tracked_channel(
        self,
        url: str,
        name: str,
        min_score: int = 90,
        target_playlist: str | None = None,
        auto_upload: int = 1,
    ) -> str:
        """Kanalı otomatik takip listesine ekler veya günceller."""
        channel_id = str(uuid.uuid4())
        sql = """
            INSERT INTO tracked_channels
                (id, url, name, min_score, target_playlist, auto_upload, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(url) DO UPDATE SET
                name            = excluded.name,
                min_score       = excluded.min_score,
                target_playlist = excluded.target_playlist,
                auto_upload     = excluded.auto_upload,
                active          = 1;
        """
        with self._connect() as conn:
            conn.execute(
                sql,
                (channel_id, url.strip(), name.strip(), int(min_score), target_playlist, int(auto_upload), _utcnow()),
            )
            conn.commit()
        logger.info("Tracked channel added/updated: {} ({})", name, url)
        return channel_id

    def get_tracked_channels(self, active_only: bool = True) -> list[dict[str, Any]]:
        """Takip edilen kanalları listeler."""
        sql = "SELECT * FROM tracked_channels"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY created_at DESC;"

        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]

    def remove_tracked_channel(self, channel_id_or_url: str) -> None:
        """Kanalı takip listesinden kaldırır."""
        sql = "DELETE FROM tracked_channels WHERE id = ? OR url = ?;"
        with self._connect() as conn:
            conn.execute(sql, (channel_id_or_url, channel_id_or_url))
            conn.commit()
        logger.info("Removed tracked channel: {}", channel_id_or_url)

    def update_tracked_channel_checked(self, channel_url: str) -> None:
        """Kanalın son kontrol edilme tarihini günceller."""
        sql = "UPDATE tracked_channels SET last_checked = ? WHERE url = ?;"
        with self._connect() as conn:
            conn.execute(sql, (_utcnow(), channel_url))
            conn.commit()

    # ------------------------------------------------------------------
    # Per-channel processed video tracking (anchor-based new detection)
    # ------------------------------------------------------------------

    def record_processed_video(self, channel_url: str, video_id: str, title: str = "") -> None:
        """Bir kanal için bir videoyu 'işlendi' olarak işaretler.

        Bu kayıt, o kanaldaki en son işlenmiş video çapasını (anchor) oluşturur.
        Bir sonraki taramada, bu videodan daha yeni olanlar 'yeni video' sayılır.
        """
        sql = """
            INSERT OR REPLACE INTO channel_processed_videos
                (channel_url, video_id, title, processed_at)
            VALUES (?, ?, ?, ?);
        """
        with self._connect() as conn:
            conn.execute(sql, (channel_url.strip(), str(video_id), title or "", _utcnow()))
            conn.commit()
        logger.debug("Kanal {} için video {} işlendi olarak işaretlendi", channel_url, video_id)

    def get_processed_video_ids(self, channel_url: str) -> set:
        """Bir kanal için daha önce işlenmiş (kayıtlı) video ID'lerinin kümesini döner."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT video_id FROM channel_processed_videos WHERE channel_url = ?;",
                (channel_url.strip(),),
            ).fetchall()
        return {r["video_id"] for r in rows}

    def is_channel_video_processed(self, channel_url: str, video_id: str) -> bool:
        """Belirli bir video ID'sinin bu kanal için zaten işlenmiş olup olmadığını döner."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM channel_processed_videos WHERE channel_url = ? AND video_id = ?;",
                (channel_url.strip(), str(video_id)),
            ).fetchone()
        return row is not None

    def get_last_processed_video_id(self, channel_url: str) -> str | None:
        """Bu kanal için en son işlenmiş video ID'sini (çapa) döner, yoksa None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT video_id FROM channel_processed_videos "
                "WHERE channel_url = ? ORDER BY processed_at DESC LIMIT 1;",
                (channel_url.strip(),),
            ).fetchone()
        return row["video_id"] if row else None

    def add_to_autopilot_queue(
        self,
        video_id: str,
        clip_id: str | None,
        channel_url: str,
        title: str,
        render_path: str,
        thumbnail_path: str | None,
        viral_score: int,
        scheduled_at: str,
        status: str = "QUEUED",
        youtube_url: str | None = None,
        description: str | None = None,
    ) -> str:
        """Zamanlanmış veya stoklanmış klibi autopilot kuyruğuna kaydeder."""
        queue_id = str(uuid.uuid4())
        sql = """
            INSERT INTO autopilot_queue
                (id, video_id, clip_id, channel_url, title, render_path,
                 thumbnail_path, viral_score, scheduled_at, status, youtube_url, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self._connect() as conn:
            conn.execute(
                sql,
                (
                    queue_id,
                    video_id,
                    clip_id,
                    channel_url,
                    title,
                    render_path,
                    thumbnail_path,
                    int(viral_score),
                    scheduled_at,
                    status,
                    youtube_url,
                    description,
                    _utcnow(),
                ),
            )
            conn.commit()
        logger.info("Added to autopilot queue id={} score={} scheduled_at={}", queue_id, viral_score, scheduled_at)
        return queue_id

    def get_autopilot_queue(self, limit: int = 50) -> list[dict[str, Any]]:
        """Autopilot kuyruğundaki tüm klipleri tarih sırasıyla listeler."""
        sql = "SELECT * FROM autopilot_queue ORDER BY scheduled_at DESC LIMIT ?;"
        with self._connect() as conn:
            rows = conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def update_autopilot_queue_status(
        self,
        queue_id: str,
        status: str,
        youtube_url: str | None = None,
        error_msg: str | None = None,
    ) -> None:
        """Kuyruk öğesinin durumunu günceller."""
        sql = """
            UPDATE autopilot_queue
            SET status = ?, youtube_url = COALESCE(?, youtube_url), error_msg = ?
            WHERE id = ?;
        """
        with self._connect() as conn:
            conn.execute(sql, (status, youtube_url, error_msg, queue_id))
            conn.commit()
        logger.debug("Updated autopilot queue {} status={}", queue_id, status)

    def get_latest_scheduled_time(self) -> str | None:
        """Kuyrukta en ileri tarihe planlanmış klibin ISO tarihini döner."""
        sql = "SELECT scheduled_at FROM autopilot_queue WHERE status IN ('QUEUED', 'SCHEDULED') ORDER BY scheduled_at DESC LIMIT 1;"
        with self._connect() as conn:
            row = conn.execute(sql).fetchone()
        return row["scheduled_at"] if row else None

    def delete_from_autopilot_queue(self, queue_id: str) -> None:
        """Kuyruk öğesini veritabanından siler."""
        sql = "DELETE FROM autopilot_queue WHERE id = ?;"
        with self._connect() as conn:
            conn.execute(sql, (queue_id,))
            conn.commit()
        logger.info("Deleted autopilot queue item: {}", queue_id)

    def update_autopilot_queue_scheduled_time(self, queue_id: str, scheduled_at: str) -> None:
        """Kuyruk öğesinin planlanan yayın saatini günceller."""
        sql = "UPDATE autopilot_queue SET scheduled_at = ? WHERE id = ?;"
        with self._connect() as conn:
            conn.execute(sql, (scheduled_at, queue_id))
            conn.commit()
        logger.debug("Updated autopilot queue {} scheduled_at={}", queue_id, scheduled_at)

    def get_all_active_scheduled_queue(self) -> list[dict[str, Any]]:
        """Planlanmış ve stoktaki tüm klipleri kronolojik sırayla döner."""
        sql = "SELECT * FROM autopilot_queue WHERE status IN ('QUEUED', 'SCHEDULED') ORDER BY scheduled_at ASC;"
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def clear_database(self, keep_tracked_channels: bool = True) -> None:
        """Clear videos, clips, renders, heatmap patterns and autopilot queue."""
        with self._connect() as conn:
            conn.execute("DELETE FROM renders;")
            conn.execute("DELETE FROM clips;")
            conn.execute("DELETE FROM videos;")
            conn.execute("DELETE FROM heatmap_patterns;")
            conn.execute("DELETE FROM autopilot_queue;")
            if not keep_tracked_channels:
                conn.execute("DELETE FROM tracked_channels;")
            conn.commit()
        logger.info("Cleared records from database (keep_tracked_channels={}).", keep_tracked_channels)

    # ------------------------------------------------------------------
    # Targeted cleanup (keep planned schedule, re-anchor published videos)
    # ------------------------------------------------------------------

    def cleanup_keep_planned(self, tz_offset_hours: int = 3) -> dict[str, Any]:
        """Planlı (gelecekteki) kuyruk öğelerini ve bunlarla ilişkili kayıtları
        koruyarak veritabanını temizler.

        - ``tracked_channels`` dokunulmaz (korunur).
        - ``autopilot_queue`` içinde *gelecekte* planlanmış öğeler (ve zamanı
          bilinmeyenler) korunur; geçmişte kalanlar (yayınlanmış/eski) silinir.
        - Korunan öğelerin video/klip/render kayıtları silinmez.
        - ``videos``, ``clips``, ``renders``, ``heatmap_patterns`` tabloları
          korunanlar dışında tamamen temizlenir.
        - YouTube'a yüklenmiş (``youtube_url`` olan) videolar ile korunan planlı
          videolar, ``channel_processed_videos`` (işlenmiş/anchor) listesine eklenir;
          böylece bir sonraki taramada yeniden işlenmezler.

        Returns:
            Özet metrikler.
        """

        now_utc = datetime.now(timezone.utc)

        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute("SELECT * FROM autopilot_queue;").fetchall()]

            kept: list[dict[str, Any]] = []
            yt_anchors: list[tuple[str, str]] = []  # (channel_url, video_id)
            for r in rows:
                sched = r.get("scheduled_at") or ""
                keep = False
                if not sched:
                    keep = True  # Zamanı belirsizse koru (güvenli tarafta kal)
                else:
                    try:
                        dt = datetime.fromisoformat(sched.replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        keep = dt >= now_utc
                    except Exception:
                        keep = True
                if keep:
                    kept.append(r)
                # YouTube'a atılmış olanları anchor listesine ekle
                yt = r.get("youtube_url")
                if yt and str(yt).strip() and r.get("channel_url") and r.get("video_id"):
                    yt_anchors.append((str(r.get("channel_url")), str(r.get("video_id"))))

            kept_ids = [r["id"] for r in kept]

            # 1. autopilot_queue: korunanlar dışındakileri sil
            if kept_ids:
                qph = ",".join("?" * len(kept_ids))
                conn.execute(f"DELETE FROM autopilot_queue WHERE id NOT IN ({qph});", kept_ids)
            else:
                conn.execute("DELETE FROM autopilot_queue;")

            # Korunan öğelerin klip & video ID'lerini topla
            if kept_ids:
                kept_rows = [
                    dict(r)
                    for r in conn.execute(
                        f"SELECT clip_id, video_id, channel_url FROM autopilot_queue WHERE id IN ({qph});",
                        kept_ids,
                    ).fetchall()
                ]
            else:
                kept_rows = []

            kept_clip_ids = [r["clip_id"] for r in kept_rows if r.get("clip_id")]
            kept_video_ids = [r["video_id"] for r in kept_rows if r.get("video_id")]
            # Korunan planlı videoları da anchor'a ekle
            for r in kept_rows:
                if r.get("video_id") and r.get("channel_url"):
                    yt_anchors.append((str(r.get("channel_url")), str(r.get("video_id"))))
            kept_video_ids = list(set(kept_video_ids))

            # 2. clips
            if kept_clip_ids:
                cph = ",".join("?" * len(kept_clip_ids))
                conn.execute(f"DELETE FROM clips WHERE id NOT IN ({cph});", kept_clip_ids)
            else:
                conn.execute("DELETE FROM clips;")

            # 3. videos
            if kept_video_ids:
                vph = ",".join("?" * len(kept_video_ids))
                conn.execute(f"DELETE FROM videos WHERE id NOT IN ({vph});", kept_video_ids)
            else:
                conn.execute("DELETE FROM videos;")

            # 4. renders (korunan klipler hariç)
            if kept_clip_ids:
                rph = ",".join("?" * len(kept_clip_ids))
                conn.execute(f"DELETE FROM renders WHERE clip_id NOT IN ({rph});", kept_clip_ids)
            else:
                conn.execute("DELETE FROM renders;")

            # 5. heatmap_patterns (hepsi; yeniden öğrenilecek)
            conn.execute("DELETE FROM heatmap_patterns;")

            # 6. Anchor ekleme: YouTube'a atılmış + korunan planlı videolar
            now_iso = _utcnow()
            anchors_added = 0
            for ch_url, vid in set(yt_anchors):
                if ch_url and vid:
                    conn.execute(
                        "INSERT OR REPLACE INTO channel_processed_videos "
                        "(channel_url, video_id, title, processed_at) VALUES (?, ?, ?, ?);",
                        (ch_url, vid, "", now_iso),
                    )
                    anchors_added += 1

            conn.commit()

        logger.info(
            "cleanup_keep_planned: kept_queue={} kept_videos={} kept_clips={} anchors_added={}",
            len(kept),
            len(kept_video_ids),
            len(kept_clip_ids),
            anchors_added,
        )
        return {
            "kept_queue": len(kept),
            "kept_videos": len(kept_video_ids),
            "kept_clips": len(kept_clip_ids),
            "anchors_added": anchors_added,
        }

    # -----------------------------------------------------------------------
    # Interactive Slot & Pool Management
    # -----------------------------------------------------------------------

    def assign_clip_to_slot(self, queue_id: str, scheduled_iso: str) -> bool:
        """Klibi belirli bir slot zamanına atar ve durumunu QUEUED yapar."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE autopilot_queue SET scheduled_at = ?, status = 'QUEUED' WHERE id = ?;",
                (scheduled_iso, queue_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def unassign_clip_to_pool(self, queue_id: str) -> bool:
        """Klibi slottan çıkarıp havuza (UNASSIGNED) çeker."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE autopilot_queue SET scheduled_at = '', status = 'UNASSIGNED' WHERE id = ?;",
                (queue_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    def swap_clip_slots(self, queue_id_1: str, queue_id_2: str) -> bool:
        """İki klibin slot zamanlarını (scheduled_at) birbiriyle takas eder."""
        with self._connect() as conn:
            row1 = conn.execute(
                "SELECT scheduled_at, status FROM autopilot_queue WHERE id = ?;", (queue_id_1,)
            ).fetchone()
            row2 = conn.execute(
                "SELECT scheduled_at, status FROM autopilot_queue WHERE id = ?;", (queue_id_2,)
            ).fetchone()
            if not row1 or not row2:
                return False
            time1, status1 = row1["scheduled_at"], row1["status"]
            time2, status2 = row2["scheduled_at"], row2["status"]

            conn.execute(
                "UPDATE autopilot_queue SET scheduled_at = ?, status = ? WHERE id = ?;", (time2, status2, queue_id_1)
            )
            conn.execute(
                "UPDATE autopilot_queue SET scheduled_at = ?, status = ? WHERE id = ?;", (time1, status1, queue_id_2)
            )
            conn.commit()
            return True

    def get_pool_clips(self) -> list[dict[str, Any]]:
        """Slota atanmamış (UNASSIGNED) veya henüz yayınlanmamış stoktaki klipleri getirir."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM autopilot_queue WHERE status = 'UNASSIGNED' OR scheduled_at = '' OR scheduled_at IS NULL ORDER BY created_at DESC;"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_day_slot_items(self, date_str: str, tz_offset_hours: int = 3) -> list[dict[str, Any]]:
        """Belirli bir güne ait (Türkiye saatine göre) planlanmış tüm kuyruk kliplerini getirir."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM autopilot_queue WHERE scheduled_at IS NOT NULL AND status IN ('QUEUED', 'SCHEDULED', 'PUBLISHED') ORDER BY scheduled_at ASC;"
            ).fetchall()
            day_items = []
            for r in rows:
                row_dict = dict(r)
                sched = row_dict.get("scheduled_at", "")
                if sched:
                    try:
                        from datetime import timedelta

                        dt_utc = datetime.fromisoformat(sched.replace("Z", "+00:00"))
                        dt_local = dt_utc + timedelta(hours=tz_offset_hours)
                        if dt_local.strftime("%Y-%m-%d") == date_str:
                            row_dict["local_dt"] = dt_local
                            row_dict["slot_time"] = dt_local.strftime("%H:%M")
                            day_items.append(row_dict)
                    except Exception:
                        pass
            return day_items
