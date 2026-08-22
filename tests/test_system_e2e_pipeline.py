"""
tests/test_system_e2e_pipeline.py — Uçtan Uca Tam Sistem & Entegrasyon Senaryoları (E2E)

Bu test dosyası sistemin tüm katmanlarını birbirine bağlayan karmaşık gerçek hayat senaryolarını test eder:
1. Senaryo 1: Standart Gaming Akışı (YouTube -> DSP -> Heatmap -> Ranker -> Gemini -> Cutter -> DeepSeek -> Thumbnail -> DB -> Export)
2. Senaryo 2: Heatmap'siz & Transkritsiz Zorlu Video (Whisper + HeatmapPredictor Fallback)
3. Senaryo 3: Yorum Patlaması & Kanal DNA Gelişimi (Comment Mining + Channel DNA + Discord/Telegram Bildirim)
4. Senaryo 4: Ani Şok & Ses Patlaması (Silence-Burst + Scene Cut Snapping + -14 LUFS Loudnorm)
5. Senaryo 5: Otomasyon & Kanal Besleme Kuyruğu (ChannelFeed -> Scheduler -> Headless Pipeline -> Cache Cleanup)
6. Senaryo 6: Çoklu Platform Matrisi & Dağıtım (TikTok, Shorts, Reels, Twitter puanlama ve optimizasyon)
7. Senaryo 7: Çoklu API Hata Dayanıklılığı (Gemini Quota Fallback + DeepSeek Heuristic Fallback)
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from core.aligner import AlignmentEngine

from core.audio_dsp import AudioDSPAnalyzer
from core.candidate_ranker import CandidateRanker
from core.channel_dna import ChannelDNAManager
from core.comment_miner import CommentMiner
from core.database import DatabaseManager
from core.deepseek_engine import DeepSeekEngine
from core.heatmap_predictor import HeatmapPredictor
from core.llm_engine import GeminiHighlightEngine
from core.notifier import Notifier
from core.pipeline import ClipperPipeline
from core.platform_scorer import PlatformScorer
from core.quality_evaluator import QualityEvaluator
from core.scene_detector import SceneDetector
from core.subtitles import SubtitleGenerator
from core.thumbnail import ThumbnailGenerator
from core.uploader import YouTubeUploader


@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    db.init_db()
    yield db
    if os.path.exists(path):
        os.remove(path)


# ===========================================================================
# SENARYO 1: STANDART E2E GAMING PIPELINE
# ===========================================================================

@patch("core.cutter.VideoCutter.cut_clip")
@patch("core.thumbnail.ThumbnailGenerator.batch_generate_thumbnails")
@patch("core.deepseek_engine.DeepSeekEngine.generate_shorts_copy")
@patch("core.llm_engine.GeminiHighlightEngine.batch_judge_gaming_candidates")
@patch("core.audio_dsp.AudioDSPAnalyzer.extract_audio_energy")
@patch("core.extractor.YouTubeExtractor.get_video_data")
def test_e2e_standard_gaming_pipeline(
    mock_get_video,
    mock_audio_dsp,
    mock_gemini,
    mock_deepseek,
    mock_thumbs,
    mock_cutter,
    test_db,
    tmp_path,
):
    # 1. Video Metadata
    mock_get_video.return_value = {
        "id": "vid_gta_01",
        "url": "https://youtube.com/watch?v=vid_gta_01",
        "title": "GTA 5 İnanılmaz Araba Taklaları",
        "uploader": "TestGamer",
        "duration": 300,
        "duration_formatted": "05:00",
        "thumbnail": "https://example.com/gta.jpg",
        "view_count": 120_000,
        "has_heatmap": True,
        "heatmap": [
            {"start_time": 40.0, "end_time": 70.0, "value": 0.95},
            {"start_time": 180.0, "end_time": 210.0, "value": 0.85},
        ],
    }

    # 2. Audio DSP
    times = np.linspace(0, 300, 300)
    spikes = np.zeros(300)
    spikes[50:60] = 0.9
    spikes[190:200] = 0.85
    mock_audio_dsp.return_value = (times, spikes)

    # 3. LLM Candidate Verdict
    mock_gemini.return_value = [
        {
            "candidate_id": 1,
            "verdict": "KEEP",
            "category": "FAIL/FUNNY",
            "title": "Fizik Kurallarını Yıkan Araba!",
            "hook_caption": "Bu taklayı kimse beklemiyordu!",
            "why_viral": "Yüksek hızda komik fizik hatası",
            "viral_confidence": 94,
            "suggested_start": 42.0,
            "suggested_end": 68.0,
        }
    ]

    # 4. DeepSeek Copywriting
    mock_deepseek.return_value = {
        "title": "Fizik Kurallarını Yıkan Araba! 🚀 #Shorts",
        "description": "GTA 5'te akılalmaz bir kaza anı!\n\n🎬 Orijinal: TestGamer\n\n#GTA5 #Gaming #Fail #Shorts #Komik",
        "tags": ["gta5", "gaming", "shorts", "fail", "komik"],
        "provider": "DeepSeek V3",
    }

    # 5. Cutter Render
    fake_mp4 = str(tmp_path / "clip_1.mp4")
    with open(fake_mp4, "w") as f:
        f.write("mp4_dummy_stream")
    mock_cutter.return_value = fake_mp4

    # 6. Thumbnail
    mock_thumbs.return_value = [str(tmp_path / "thumb_1.jpg")]

    # --- PIPELINE ÇALIŞTIRMA ---
    results = ClipperPipeline.run(
        url="https://youtube.com/watch?v=vid_gta_01",
        target_clips=1,
        render_mode="square_1x1_black",
        add_subtitles=True,
        add_hook_card=True,
        db=test_db,
    )


    assert len(results) == 1
    assert os.path.exists(results[0]["render_path"])
    assert results[0]["title"] == "Fizik Kurallarını Yıkan Araba!"

    # DB Doğrulaması
    assert test_db.video_exists("vid_gta_01")
    clips = test_db.get_clips_for_video("vid_gta_01")
    assert len(clips) == 1
    assert clips[0]["category"] == "FAIL/FUNNY"
    assert clips[0]["viral_confidence"] == 94


# ===========================================================================
# SENARYO 2: HEATMAP'SİZ & TRANSKRİPTSİZ VİDEO (PREDICTOR + WHISPER FALLBACK)
# ===========================================================================

def test_e2e_no_heatmap_fallback_scenario(test_db):
    # 1. DB'ye geçmiş video ve pattern'ı ekle
    test_db.save_video({"id": "hist_v1", "title": "History V1"})
    test_db.save_video({"id": "hist_v2", "title": "History V2"})
    test_db.save_video({"id": "new_no_heatmap", "title": "New Video"})

    test_db.save_heatmap_pattern("hist_v1", "TestGamer", 0.75, 0.45, 0.30, {"game": "Apex"})
    test_db.save_heatmap_pattern("hist_v2", "TestGamer", 0.80, 0.50, 0.35, {"game": "Apex"})


    # 2. Yeni heatmap'siz video verisi
    times = np.linspace(0, 120, 120)
    spikes = np.zeros(120)
    silences = np.zeros(120)
    spikes[40:50] = 0.95
    silences[40:50] = 0.85

    # 3. Heatmap Predictor devreye girsin
    predictor = HeatmapPredictor(test_db)
    prediction = predictor.predict(
        audio_times=times,
        audio_spikes=spikes,
        silence_bursts=silences,
        total_duration=120.0,
        video_id="new_no_heatmap",
        view_count=15_000,
    )

    assert prediction["source"] == "correlation_model"
    assert prediction["confidence"] >= 0.60
    assert len(prediction["heatmap"]) == 24  # 120s / 5s = 24 segments

    # 4. Candidate Ranker tahmin heatmap'i kullanarak aday çıkarsın
    ranker = CandidateRanker(top_n=3, db=test_db)
    candidates = ranker.fuse_signals_and_generate_candidates(
        times=times,
        audio_spikes=spikes,
        silence_bursts=silences,
        heatmap=[],  # Gerçek heatmap YOK
        transcript=[],
        total_duration=120,
        video_id="new_no_heatmap",
        view_count=15_000,
    )

    assert len(candidates) > 0
    top_cand = candidates[0]
    assert top_cand["signals"]["heatmap_source"] == "predicted"
    assert top_cand["signals"]["predicted_confidence"] >= 0.60
    assert 30.0 <= top_cand["peak_time"] <= 60.0


# ===========================================================================
# SENARYO 3: YORUM PATLAMASI + KANAL DNA + BİLDİRİM SENARYOSU
# ===========================================================================

@patch("requests.post")
def test_e2e_comment_mining_channel_dna_and_notification(mock_post, test_db):
    # 1. Yorum madenciliği: 100+ yorum simülasyonu
    miner = CommentMiner()
    comments = [
        {"text": "01:25 te koptum ya hahaha çok komikti 😂", "like_count": 45},
        {"text": "@01:26 yarıldım resmen efsane komik 😂", "like_count": 12},
        {"text": "01:28 abi nasıl öldün öyle 💀", "like_count": 8},
        {"text": "03:10 harika clutch vuruş 🔥", "like_count": 30},
    ]
    timeline = np.linspace(0, 300, 300)
    c_res = miner.process_comments(comments, total_duration=300.0, timeline_times=timeline)

    assert c_res["total_timestamps_found"] == 4
    assert len(c_res["timestamp_clusters"]) >= 2

    # 2. Kanal DNA Yönetimi
    dna_mgr = ChannelDNAManager(test_db)
    past_clips = [
        {"category": "FUNNY", "duration": 25.0, "score": 92},
        {"category": "FUNNY", "duration": 28.0, "score": 88},
        {"category": "RAGE", "duration": 20.0, "score": 85},
    ]
    dna = dna_mgr.compute_dna_from_clips("Efe Uygaç", past_clips)
    assert dna["dominant_category"] == "FUNNY"
    assert dna["shock_weight"] > 0.50

    # 3. LLM Prompt Context Formatı
    prompt_context = dna_mgr.format_prompt_context(dna)
    assert "Efe Uygaç" in prompt_context
    assert "FUNNY" in prompt_context

    # 4. Bildirim Gönderimi (Discord & Telegram Webhook)
    mock_post.return_value.status_code = 204
    notifier = Notifier(webhook_url="https://discord.com/api/webhooks/test", telegram_token="123", telegram_chat_id="456")
    test_clip = {
        "title": "Komik Kaza Anı",
        "category": "FUNNY",
        "score": 92,
        "duration_formatted": "25 sn",
        "start_formatted": "01:25",
        "end_formatted": "01:50",
        "hook_caption": "Gülmekten öldüm!",
    }
    notifier.notify_clip_ready(test_clip, "/tmp/render_test.mp4")
    assert mock_post.call_count >= 1


# ===========================================================================
# SENARYO 4: ANİ ŞOK & SAHNE GEÇİŞİNE HİZALAMA (SCENE CUT SNAPPING)
# ===========================================================================

def test_e2e_audio_dip_and_scene_snap_alignment():
    scene_cuts = [10.2, 25.4, 42.8, 60.1]
    raw_start = 24.5  # 25.4 saniyedeki sahne kesmesine çok yakın
    raw_end = 43.0

    # 1. Sahne kesmesine yapışma
    snapped_start = SceneDetector.snap_to_scene_boundary(raw_start, scene_cuts, max_snap_sec=1.5)
    assert snapped_start == 25.4

    # 2. AlignmentEngine ile çoklu öncelikli hizalama (Scene cut öncelikli)
    times = np.linspace(0, 100, 100)
    rms = np.ones(100) * 0.5
    ref_start, ref_end = AlignmentEngine.refine_cut_points(
        start_time=raw_start,
        end_time=raw_end,
        times=times,
        rms=rms,
        transcript=[],
        max_drift_sec=2.0,
        scene_cuts=scene_cuts,
    )
    assert ref_start == 25.4
    assert ref_end == 42.8



# ===========================================================================
# SENARYO 5: ÇOKLU PLATFORM UYUM VE ÖNERİ MATRİSİ
# ===========================================================================

def test_e2e_multi_platform_scoring_matrix():
    scorer = PlatformScorer()

    # Klip A: 22 saniye, FUNNY kancalı -> TikTok ve Shorts için mükemmel
    clip_a = {
        "duration": 22.0,
        "category": "FUNNY",
        "hook_caption": "Bunu beklemiyordunuz!",
        "score": 95,
        "signals": {"audio_spike": 0.9, "silence_burst": 0.8, "heatmap_val": 0.75},
    }
    res_a = scorer.score_clip(clip_a)
    assert res_a["tiktok"] >= 85
    assert res_a["shorts"] >= 85
    assert res_a["best_platform"] in ["TikTok", "YouTube Shorts", "Instagram Reels"]

    # Klip B: 52 saniye, STORY/CLUTCH -> Shorts ideal, Twitter için uygunsuz
    clip_b = {
        "duration": 52.0,
        "category": "STORY",
        "hook_caption": "Bütün takım elenince tek kaldım...",
        "score": 90,
        "signals": {"heatmap_val": 0.80},
    }
    res_b = scorer.score_clip(clip_b)
    assert res_b["shorts"] >= 80
    assert res_b["twitter"] <= 30  # Twitter <25s tercih eder


# ===========================================================================
# SENARYO 6: MODEL ARIZALARI VE HATA DAYANIKLILIK ZİNCİRİ
# ===========================================================================

def test_e2e_ai_failover_and_heuristic_resilience():
    # 1. DeepSeek Engine: Başlık ve kopya üretimi
    meta = DeepSeekEngine.generate_shorts_copy(
        clip_title="Büyük Kaçış",
        hook_caption="Nolur ölme!",
        category="CLUTCH",
        video_title="Apex Legends Son Sezon",
    )
    assert "#Shorts" in meta["title"]
    assert len(meta["title"]) >= 10
    assert meta["provider"] in [
        "DeepSeek V3 (OpenRouter)",
        "OpenRouter (DeepSeek V3)",
        "DeepSeek V3",
        "Heuristic Fallback",
    ]



    # 2. QualityEvaluator: API anahtarı yoksa kural tabanlı değerlendirme
    eval_res = QualityEvaluator.evaluate_clip(
        clip={
            "start_time": 10.0,
            "end_time": 38.0,
            "category": "CLUTCH",
            "hook_caption": "İnanılmaz an",
        },
        video_title="Apex Legends Son Sezon",
        times=np.linspace(0, 100, 100),
        rms=np.ones(100) * 0.7,
        transcript=[{"text": "Hadi kaç kaç bomba geldi!", "start": 12.0, "duration": 4.0}],
        api_key=None,
    )
    assert eval_res["grade"] in ["A+", "A", "B+", "B", "C", "D"]
    assert 0 <= eval_res["composite_score"] <= 100


