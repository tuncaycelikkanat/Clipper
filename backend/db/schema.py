SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS channels (
    id               TEXT PRIMARY KEY,
    url              TEXT UNIQUE NOT NULL,
    name             TEXT NOT NULL,
    channel_yt_id    TEXT,
    is_tracked       INTEGER DEFAULT 0,
    active           INTEGER DEFAULT 1,
    min_score        INTEGER DEFAULT 90,
    target_playlist  TEXT,
    auto_upload      INTEGER DEFAULT 1,
    check_interval_h REAL DEFAULT 2.0,
    dna_json         TEXT,
    last_checked     TEXT,
    last_video_id    TEXT,
    last_video_date  TEXT,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id           TEXT PRIMARY KEY,
    channel_id   TEXT REFERENCES channels(id) ON DELETE SET NULL,
    url          TEXT NOT NULL,
    title        TEXT,
    uploader     TEXT,
    duration     INTEGER,
    view_count   INTEGER,
    upload_date  TEXT,
    has_heatmap  INTEGER DEFAULT 0,
    processed_at TEXT,
    status       TEXT DEFAULT 'pending' CHECK(status IN ('pending','processing','done','failed')),
    tags         TEXT,
    description  TEXT,
    error_msg    TEXT
);

CREATE TABLE IF NOT EXISTS clips (
    id               TEXT PRIMARY KEY,
    video_id         TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    rank             INTEGER,
    title            TEXT,
    description      TEXT,
    tags             TEXT,
    hook_caption     TEXT,
    category         TEXT,
    start_time       REAL,
    end_time         REAL,
    duration         REAL,
    score            INTEGER,
    thumbnail_path   TEXT,
    render_path      TEXT,
    render_mode      TEXT,
    has_facecam      INTEGER DEFAULT 0,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS channel_seen_videos (
    channel_id   TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    video_id     TEXT NOT NULL,
    title        TEXT,
    upload_date  TEXT,
    seen_at      TEXT NOT NULL,
    processed    INTEGER DEFAULT 0,
    skipped      INTEGER DEFAULT 0,
    PRIMARY KEY (channel_id, video_id)
);

CREATE TABLE IF NOT EXISTS publish_queue (
    id             TEXT PRIMARY KEY,
    clip_id        TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    channel_id     TEXT REFERENCES channels(id) ON DELETE SET NULL,
    scheduled_at   TEXT,
    status         TEXT DEFAULT 'pool' CHECK(status IN ('pool','scheduled','publishing','published','failed','cancelled')),
    youtube_url    TEXT,
    instagram_url  TEXT,
    tiktok_url     TEXT,
    title          TEXT,
    description    TEXT,
    error_msg      TEXT,
    retry_count    INTEGER DEFAULT 0,
    published_at   TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS renders (
    id          TEXT PRIMARY KEY,
    clip_id     TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    render_mode TEXT,
    file_path   TEXT,
    file_size   INTEGER,
    created_at  TEXT,
    exported    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS heatmap_patterns (
    video_id              TEXT PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
    channel_id            TEXT,
    spike_heatmap_corr    REAL,
    silence_heatmap_corr  REAL,
    peak_ratio            REAL,
    heatmap_meta_json     TEXT,
    recorded_at           TEXT
);

CREATE TABLE IF NOT EXISTS pipeline_jobs (
    id           TEXT PRIMARY KEY,
    video_url    TEXT NOT NULL,
    status       TEXT DEFAULT 'queued' CHECK(status IN ('queued','running','done','failed','cancelled')),
    progress     INTEGER DEFAULT 0,
    current_step TEXT,
    result_json  TEXT,
    error_msg    TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
"""
