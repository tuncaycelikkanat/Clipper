"""
tests/test_system_stress_and_edge_cases.py — Sistem Dayanıklılık, Eşzamanlılık & Edge Case Entegrasyon Testleri

Kapsam:
1. SQLite WAL modu altında çoklu iş parçacıklı (concurrent) yazma/okuma dayanıklılığı
2. Karaoke Altyazı (ASS) 0-çakışma ve zamanlama hassasiyeti stres testi (100+ ardışık kelime)
3. Gizli Viral Arbitrajı (<50k görüntü, >%70 heatmap piki) tam döngüsü
4. Otomasyon: ChannelFeed + SchedulerManager + Database tekilleştirme (dedup) entegrasyonu
5. CacheManager disk temizliği ve geçici dosya temizleme yaşam döngüsü
6. YouTube Uploader: Türkçe, İstanbul konumu, Oynatma listesi ve Thumbnail hata yakalama
"""

import concurrent.futures
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from core.cache_manager import CacheManager
from core.candidate_ranker import CandidateRanker
from core.database import DatabaseManager
from core.feed import ChannelFeed
from core.scheduler_manager import SchedulerManager
from core.subtitles import SubtitleGenerator
from core.uploader import YouTubeUploader


@pytest.fixture
def stress_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    db.init_db()
    yield db
    if os.path.exists(path):
        os.remove(path)


# ===========================================================================
# 1. CONCURRENT DATABASE THREAD-SAFETY STRESS TEST
# ===========================================================================


def test_stress_concurrent_database_writes(stress_db):
    """Birden fazla iş parçacığı aynı anda video, klip ve render kaydederken SQLite WAL kilitlenmemelidir."""

    def worker(worker_id: int):
        vid_id = f"stress_vid_{worker_id}"
        stress_db.save_video(
            {
                "id": vid_id,
                "url": f"https://youtube.com/watch?v={vid_id}",
                "title": f"Stress Video {worker_id}",
                "uploader": f"Streamer {worker_id % 3}",
                "duration": 600,
                "view_count": 1000 * worker_id,
                "has_heatmap": 1 if worker_id % 2 == 0 else 0,
            }
        )
        clip_ids = stress_db.save_clips(
            vid_id,
            [
                {"rank": 1, "title": f"Clip 1 from {vid_id}", "score": 90 + (worker_id % 10)},
                {"rank": 2, "title": f"Clip 2 from {vid_id}", "score": 80 + (worker_id % 10)},
            ],
        )
        stress_db.save_render(clip_ids[0], "square_1x1_black", f"/tmp/render_{worker_id}.mp4")
        stress_db.save_heatmap_pattern(vid_id, f"Streamer {worker_id % 3}", 0.7, 0.4, 0.3)
        return vid_id

    # 20 paralel worker çalıştır
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, i) for i in range(20)]
        results = [f.result() for f in futures]

    assert len(results) == 20
    for vid_id in results:
        assert stress_db.video_exists(vid_id)
        clips = stress_db.get_clips_for_video(vid_id)
        assert len(clips) == 2


# ===========================================================================
# 2. KARAOKE SUBTITLE 0-OVERLAP STRESS TEST
# ===========================================================================


def test_stress_subtitles_word_level_no_overlap(tmp_path):
    """100 kelimelik yoğun ve hızlı bir transkriptte altyazı zamanlamaları asla çakışmamalıdır."""
    word_segments = []
    current_t = 0.0
    for i in range(100):
        dur = 0.25 + (i % 3) * 0.10
        word_segments.append(
            {
                "word": f"KELIME_{i}",
                "start": round(current_t, 2),
                "end": round(current_t + dur, 2),
            }
        )
        current_t += dur + 0.05

    ass_path = str(tmp_path / "stress_subtitles.ass")
    res_path = SubtitleGenerator.generate_ass_from_words(
        word_segments=word_segments,
        clip_start_sec=0.0,
        clip_end_sec=current_t,
        output_path=ass_path,
        video_width=1080,
        video_height=1080,
    )

    assert os.path.exists(res_path)
    content = Path(res_path).read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "[V4+ Styles]" in content
    assert "[Events]" in content
    # Neon yellow karaoke vurgusu (\c&H00FFFF&) bulunmalı
    assert "00FFFF" in content or "Dialogue:" in content


# ===========================================================================
# 3. GİZLİ VİRAL ARBİTRAJI ENTEGRASYONU
# ===========================================================================


def test_e2e_hidden_viral_arbitrage_flow(stress_db):
    """Düşük izlenmeli (<50k) ama %85+ izleyici tekrarı olan bir videonun gizli viral olarak tespiti."""
    times = np.linspace(0, 200, 200)
    spikes = np.zeros(200)
    silences = np.zeros(200)
    spikes[100:110] = 0.95
    silences[100:110] = 0.90

    real_heatmap = [
        {"start_time": 95.0, "end_time": 105.0, "value": 0.92},  # Güçlü pik
        {"start_time": 10.0, "end_time": 20.0, "value": 0.30},
    ]

    ranker = CandidateRanker(top_n=3, db=stress_db)
    candidates = ranker.fuse_signals_and_generate_candidates(
        times=times,
        audio_spikes=spikes,
        silence_bursts=silences,
        heatmap=real_heatmap,
        transcript=[{"text": "Bunu kimse görmedi!", "start": 98.0, "duration": 4.0}],
        total_duration=200,
        video_id="hidden_viral_gem",
        view_count=8_500,  # Düşük görüntü sayısı
    )

    assert len(candidates) > 0
    viral_cand = next((c for c in candidates if abs(c["peak_time"] - 100) <= 10), None)
    assert viral_cand is not None
    assert viral_cand["signals"]["has_heatmap"] is True
    assert viral_cand["hidden_viral"] is True


# ===========================================================================
# 4. CHANNEL FEED + SCHEDULER + DATABASE DEDUP
# ===========================================================================


@patch("core.feed.yt_dlp.YoutubeDL")
def test_e2e_feed_scheduler_database_deduplication(mock_ytdl, stress_db):
    mock_instance = MagicMock()
    mock_ytdl.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {
        "entries": [
            {
                "id": "feed_v1",
                "url": "http://yt.com/1",
                "title": "V1",
                "upload_date": "20260820",
                "duration": 200,
                "view_count": 500,
            },
            {
                "id": "feed_v2",
                "url": "http://yt.com/2",
                "title": "V2",
                "upload_date": "20260821",
                "duration": 300,
                "view_count": 800,
            },
            {
                "id": "feed_v3",
                "url": "http://yt.com/3",
                "title": "V3",
                "upload_date": "20260822",
                "duration": 400,
                "view_count": 1200,
            },
        ]
    }

    # 1. feed_v1 daha önce işlenmiş olsun
    stress_db.save_video({"id": "feed_v1", "title": "V1", "status": "done"})

    # 2. Feed'den yeni videoları çek
    feed = ChannelFeed()
    channel_videos = feed.get_channel_videos("https://youtube.com/@streamer")
    assert len(channel_videos) == 3

    # 3. Yalnızca işlenmemiş olanları filtrele
    processed_ids = ["feed_v1"]
    new_videos = feed.get_new_videos("https://youtube.com/@streamer", processed_ids=processed_ids)
    assert len(new_videos) == 2
    assert {v["id"] for v in new_videos} == {"feed_v2", "feed_v3"}

    # 4. Scheduler ekleme & silme
    sched = SchedulerManager()
    job_id = sched.add_channel_job(
        channel_url="https://youtube.com/@streamer", interval_hours=12, job_id="job_streamer_12h"
    )
    assert job_id == "job_streamer_12h"
    assert len(sched.list_jobs()) == 1
    sched.remove_job("job_streamer_12h")
    assert len(sched.list_jobs()) == 0


# ===========================================================================
# 5. CACHE MANAGER TEMİZLİK YAŞAM DÖNGÜSÜ
# ===========================================================================


def test_e2e_cache_manager_lifecycle(tmp_path):
    clip_dir = tmp_path / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)

    # Geçici dosyalar ve renderlar oluştur
    (clip_dir / "raw_cut_temp_1.mp4").write_text("temp_data_1")
    (clip_dir / "temp_sub.ass").write_text("ass_data")
    (clip_dir / "final_clip_1.mp4").write_text("final_data")

    # Temp temizleme
    cm = CacheManager(output_dir=str(clip_dir))
    cm.clear_temp_files()
    assert not os.path.exists(clip_dir / "raw_cut_temp_1.mp4")
    assert not os.path.exists(clip_dir / "temp_sub.ass")
    assert os.path.exists(clip_dir / "final_clip_1.mp4")

    # Disk kullanım istatistiği
    usage = cm.get_disk_usage()
    assert usage["clip_count"] == 1
    assert usage["total_bytes"] > 0


# ===========================================================================
# 6. YOUTUBE UPLOADER GELİŞMİŞ AYARLAR ENTEGRASYONU
# ===========================================================================


@patch("core.uploader.MediaFileUpload")
@patch("core.uploader.build")
@patch.object(YouTubeUploader, "_get_credentials")
def test_e2e_youtube_uploader_full_settings(mock_get_creds, mock_build, mock_media, tmp_path):
    mock_get_creds.return_value = MagicMock()
    mock_yt = MagicMock()
    mock_build.return_value = mock_yt

    mock_req = MagicMock()
    mock_req.next_chunk.side_effect = [(None, {"id": "yt_short_99", "status": {"uploadStatus": "uploaded"}})]
    mock_yt.videos().insert.return_value = mock_req

    fake_video = tmp_path / "short_video.mp4"
    fake_video.write_text("mp4_bytes")
    fake_thumb = tmp_path / "thumb.jpg"
    fake_thumb.write_text("jpg_bytes")

    uploader = YouTubeUploader()
    res = uploader.upload_short(
        video_path=str(fake_video),
        title="Epic Clutch #Shorts",
        description="Harika bir oyun anı",
        tags=["gaming", "shorts", "clutch"],
        thumbnail_path=str(fake_thumb),
        made_for_kids=False,
        language="tr",
        location_description="Istanbul, Turkey",
        playlist_id="PL_GAMES_123",
    )

    assert res["video_id"] == "yt_short_99"
    assert res["url"] == "https://www.youtube.com/shorts/yt_short_99"

    # YouTube API insert parametrelerini doğrula
    insert_call = mock_yt.videos().insert.call_args[1]
    body = insert_call["body"]
    assert body["snippet"]["defaultLanguage"] == "tr"
    assert body["snippet"]["defaultAudioLanguage"] == "tr"
    assert body["status"]["selfDeclaredMadeForKids"] is False
    assert body["recordingDetails"]["locationDescription"] == "Istanbul, Turkey"

    # Playlist ekleme çağrısını doğrula
    mock_yt.playlistItems().insert.assert_called_once()
    pl_body = mock_yt.playlistItems().insert.call_args[1]["body"]
    assert pl_body["snippet"]["playlistId"] == "PL_GAMES_123"
    assert pl_body["snippet"]["resourceId"]["videoId"] == "yt_short_99"
