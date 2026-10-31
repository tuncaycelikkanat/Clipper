"""
scripts/import_channels.py — Imports tracked channels and video history into clipper.db.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_DIR)
_DB_PATH = os.path.join(_PROJECT_ROOT, "clipper.db")
_SEED_PATH = os.path.join(_DIR, "channels_seed.json")


def main():
    if not os.path.exists(_SEED_PATH):
        print(f"Hata: {_SEED_PATH} bulunamadı!")
        sys.exit(1)

    with open(_SEED_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    channels = data.get("channels", [])
    processed_videos = data.get("processed_videos", [])

    print(f"Veritabanı hedefi: {_DB_PATH}")
    conn = sqlite3.connect(_DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tracked_channels (
        id              TEXT PRIMARY KEY,
        url             TEXT UNIQUE NOT NULL,
        name            TEXT NOT NULL,
        min_score       INTEGER DEFAULT 70,
        target_playlist TEXT,
        auto_upload     INTEGER DEFAULT 1,
        last_checked    TEXT,
        active          INTEGER DEFAULT 1,
        created_at      TEXT NOT NULL,
        check_interval_h REAL DEFAULT 2.0,
        last_video_id   TEXT,
        last_video_date TEXT,
        youtube_username TEXT,
        instagram_username TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS channel_processed_videos (
        channel_url   TEXT NOT NULL,
        video_id      TEXT NOT NULL,
        title         TEXT DEFAULT '',
        processed_at  TEXT NOT NULL,
        PRIMARY KEY (channel_url, video_id)
    );
    """)

    ch_count = 0
    for ch in channels:
        cur.execute("""
        INSERT OR REPLACE INTO tracked_channels (
            id, url, name, min_score, target_playlist, auto_upload,
            last_checked, active, created_at, check_interval_h,
            last_video_id, last_video_date, youtube_username, instagram_username
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            ch["id"],
            ch["url"],
            ch["name"],
            ch.get("min_score", 70),
            ch.get("target_playlist"),
            ch.get("auto_upload", 1),
            ch.get("last_checked"),
            ch.get("active", 1),
            ch["created_at"],
            ch.get("check_interval_h", 2.0),
            ch.get("last_video_id"),
            ch.get("last_video_date"),
            ch.get("youtube_username"),
            ch.get("instagram_username"),
        ))
        ch_count += 1

    vid_count = 0
    for v in processed_videos:
        cur.execute("""
        INSERT OR IGNORE INTO channel_processed_videos (
            channel_url, video_id, title, processed_at
        ) VALUES (?, ?, ?, ?);
        """, (v["channel_url"], v["video_id"], v.get("title", ""), v.get("processed_at", "")))
        vid_count += 1

    conn.commit()
    conn.close()

    print(f"✅ Başarılı! {ch_count} adet kanal ve {vid_count} adet geçmiş video çapa kaydı içe aktarıldı.")
    print("Artık Autopilot sadece bundan sonra yüklenen YENİ videoları tespit edip klip üretecektir.")


if __name__ == "__main__":
    main()
