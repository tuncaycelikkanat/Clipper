import numpy as np

from core.candidate_ranker import CandidateRanker


def test_candidate_ranker_empty():
    ranker = CandidateRanker()
    res = ranker.fuse_signals_and_generate_candidates(
        times=np.array([]),
        audio_spikes=np.array([]),
        silence_bursts=np.array([]),
        heatmap=[],
        transcript=[],
        total_duration=100,
    )
    assert res == []


def test_candidate_ranker_no_heatmap_fallback():
    # Test without heatmap, and scores < 0.20 to trigger fallback
    ranker = CandidateRanker(top_n=2)
    times = np.array([10.0, 20.0, 30.0])
    audio_spikes = np.array([0.1, 0.2, 0.15])  # 0.55 * spike + 0.45 * burst
    silence_bursts = np.array([0.1, 0.2, 0.1])
    # scores: [0.1, 0.2, 0.1275] -> max is 0.20, which is not > 0.20, so fallback triggered

    res = ranker.fuse_signals_and_generate_candidates(
        times=times,
        audio_spikes=audio_spikes,
        silence_bursts=silence_bursts,
        heatmap=[],
        transcript=[],
        total_duration=100,
    )
    assert len(res) == 2
    # The highest score should be at 20.0s, and second highest at 30.0s
    assert res[0]["peak_time"] == 20.0  # sorted chronologically
    assert res[1]["peak_time"] == 30.0


def test_candidate_ranker_with_heatmap_and_clustering():
    ranker = CandidateRanker(merge_threshold_sec=5, candidate_window_sec=10, top_n=2)
    times = np.array([10.0, 12.0, 14.0, 50.0])
    audio_spikes = np.array([1.0, 0.9, 0.8, 1.0])
    silence_bursts = np.array([1.0, 1.0, 1.0, 1.0])

    heatmap = [
        {"start_time": 9.0, "end_time": 11.0, "value": 1.0},
        {"start_time": 49.0, "end_time": 51.0, "value": 1.0},
    ]

    transcript = [{"start": 9.0, "end": 11.0, "text": "Hello"}, {"start": 12.0, "end": 15.0, "text": "World"}]

    res = ranker.fuse_signals_and_generate_candidates(
        times=times,
        audio_spikes=audio_spikes,
        silence_bursts=silence_bursts,
        heatmap=heatmap,
        transcript=transcript,
        total_duration=100,
    )

    # We should have 2 clusters: one around 10-14, one at 50
    assert len(res) == 2

    # Cluster 1: peak at 10.0 because it has highest score (heatmap peaks at 10)
    c1 = res[0]
    assert c1["peak_time"] == 10.0
    assert c1["start_time"] == 5.0
    assert c1["end_time"] == 15.0
    assert "Hello World" in c1["transcript_snippet"]
    assert c1["signals"]["has_heatmap"] is True

    # Cluster 2: peak at 50.0
    c2 = res[1]
    assert c2["peak_time"] == 50.0
    assert c2["start_time"] == 45.0
    assert c2["end_time"] == 55.0
    assert c2["transcript_snippet"] == "Ses/Tepki ağırlıklı an (Konuşma transkripti yok)"


def test_candidate_ranker_bounds():
    ranker = CandidateRanker(candidate_window_sec=20)
    times = np.array([5.0, 95.0])
    audio_spikes = np.array([1.0, 1.0])
    silence_bursts = np.array([1.0, 1.0])

    res = ranker.fuse_signals_and_generate_candidates(
        times=times,
        audio_spikes=audio_spikes,
        silence_bursts=silence_bursts,
        heatmap=[],
        transcript=[],
        total_duration=100,
    )

    assert res[0]["start_time"] == 0.0
    assert res[0]["end_time"] == 15.0
    assert res[1]["start_time"] == 85.0
    assert res[1]["end_time"] == 100.0


def test_candidate_ranker_empty_heatmap_val():
    # Heatmap passed but has empty list of times (shouldn't really happen but code handles it)
    ranker = CandidateRanker(top_n=1)
    times = np.array([10.0])
    audio_spikes = np.array([1.0])
    silence_bursts = np.array([1.0])

    heatmap = []

    res = ranker.fuse_signals_and_generate_candidates(
        times=times,
        audio_spikes=audio_spikes,
        silence_bursts=silence_bursts,
        heatmap=heatmap,  # trigger empty heatmap logic
        transcript=[],
        total_duration=100,
    )

    assert res[0]["signals"]["has_heatmap"] is False
    assert res[0]["signals"]["heatmap_val"] == 0.0


def test_candidate_ranker_empty_heatmap_but_has_item():
    # Heatmap passed but has empty list of times (shouldn't really happen but code handles it)
    ranker = CandidateRanker(top_n=1)
    times = np.array([10.0])
    audio_spikes = np.array([1.0])
    silence_bursts = np.array([1.0])

    heatmap = [{"start_time": 9.0, "end_time": 11.0, "value": 1.0}]

    res = ranker.fuse_signals_and_generate_candidates(
        times=times,
        audio_spikes=audio_spikes,
        silence_bursts=silence_bursts,
        heatmap=heatmap,
        transcript=[],
        total_duration=100,
    )

    assert res[0]["signals"]["has_heatmap"] is True
    assert res[0]["signals"]["heatmap_val"] > 0.0


def test_candidate_ranker_with_comments():
    ranker = CandidateRanker(top_n=2)
    times = np.linspace(0, 100, 100)
    audio_spikes = np.zeros(100)
    silence_bursts = np.zeros(100)
    audio_spikes[50] = 0.5
    silence_bursts[50] = 0.5

    comments = [
        {"text": "00:50 efsane komik sahne koptum 😂", "like_count": 10},
        {"text": "@00:52 ahahaha 😂", "like_count": 5},
    ]

    res = ranker.fuse_signals_and_generate_candidates(
        times=times,
        audio_spikes=audio_spikes,
        silence_bursts=silence_bursts,
        heatmap=[],
        transcript=[],
        total_duration=100,
        comments=comments,
    )

    assert len(res) > 0
    candidate_50 = next((c for c in res if abs(c["peak_time"] - 50) <= 5), None)
    assert candidate_50 is not None
    assert candidate_50["signals"]["comment_reaction"] == "FUNNY"
    assert candidate_50["signals"]["comment_count"] == 2
    assert candidate_50["signals"]["comment_density"] > 0.0


def test_candidate_ranker_with_comments_and_heatmap():
    ranker = CandidateRanker(top_n=2)
    times = np.linspace(0, 100, 100)
    audio_spikes = np.ones(100) * 0.5
    silence_bursts = np.ones(100) * 0.5
    heatmap = [{"start_time": 40.0, "end_time": 60.0, "value": 0.9}]
    comments = [{"text": "00:50 harika vuruş 🔥", "like_count": 10}]

    res = ranker.fuse_signals_and_generate_candidates(
        times=times,
        audio_spikes=audio_spikes,
        silence_bursts=silence_bursts,
        heatmap=heatmap,
        transcript=[],
        total_duration=100,
        comments=comments,
    )

    assert len(res) > 0
    c = res[0]
    assert c["signals"]["has_heatmap"] is True
    assert c["signals"]["comment_reaction"] == "EPIC"


def test_candidate_ranker_with_db_predicted_heatmap():
    from unittest.mock import MagicMock

    mock_db = MagicMock()
    mock_db.get_videos_with_heatmap_patterns.return_value = []

    ranker = CandidateRanker(top_n=2, db=mock_db)
    times = np.linspace(0, 100, 100)
    audio_spikes = np.zeros(100)
    silence_bursts = np.zeros(100)
    audio_spikes[30] = 1.0
    silence_bursts[30] = 1.0

    res = ranker.fuse_signals_and_generate_candidates(
        times=times,
        audio_spikes=audio_spikes,
        silence_bursts=silence_bursts,
        heatmap=[],
        transcript=[],
        total_duration=100,
        video_id="v_test",
        view_count=5000,
    )

    assert len(res) > 0
    assert res[0]["signals"]["heatmap_source"] in ["predicted", "real"]


def test_candidate_ranker_with_db_real_heatmap_hidden_viral():
    from unittest.mock import MagicMock

    mock_db = MagicMock()

    ranker = CandidateRanker(top_n=2, db=mock_db)
    times = np.linspace(0, 100, 100)
    audio_spikes = np.ones(100) * 0.3
    silence_bursts = np.ones(100) * 0.3
    heatmap = [{"start_time": 20.0, "end_time": 40.0, "value": 0.95}]

    res = ranker.fuse_signals_and_generate_candidates(
        times=times,
        audio_spikes=audio_spikes,
        silence_bursts=silence_bursts,
        heatmap=heatmap,
        transcript=[],
        total_duration=100,
        view_count=5000,  # low views -> triggers hidden viral
    )

    assert len(res) > 0
    assert res[0]["signals"]["has_heatmap"] is True


def test_candidate_ranker_with_transcript_density():
    ranker = CandidateRanker(top_n=2)
    times = np.linspace(0, 100, 100)
    audio_spikes = np.zeros(100)
    silence_bursts = np.zeros(100)
    audio_spikes[50] = 0.5
    silence_bursts[50] = 0.5

    transcript = [{"text": "LAN OHA ÇÜŞ NASIL VURDU EFSANE!!!", "start": 48.0, "duration": 5.0}]

    res = ranker.fuse_signals_and_generate_candidates(
        times=times,
        audio_spikes=audio_spikes,
        silence_bursts=silence_bursts,
        heatmap=[],
        transcript=transcript,
        total_duration=100,
    )

    assert len(res) > 0
    c = res[0]
    assert c["signals"]["transcript_density"] > 0.0


def test_candidate_ranker_with_comment_vip_injection():
    ranker = CandidateRanker(top_n=3)
    times = np.linspace(0, 600, 600)
    audio_spikes = np.ones(600) * 0.05
    silence_bursts = np.ones(600) * 0.05

    comments = [
        {"text": "5.13 burası çok komikti ya koptum 😂", "like_count": 25},
        {"text": "05:13 ahahaha yarıldım", "like_count": 10},
    ]

    res = ranker.fuse_signals_and_generate_candidates(
        times=times,
        audio_spikes=audio_spikes,
        silence_bursts=silence_bursts,
        heatmap=[],
        transcript=[],
        total_duration=600,
        comments=comments,
    )

    assert len(res) > 0
    vip_candidates = [c for c in res if c.get("is_vip")]
    assert len(vip_candidates) >= 1
    vip = vip_candidates[0]
    assert abs(vip["peak_time"] - 313.0) <= 5.0
    assert vip["from_comment"] is True
    assert vip["signals"]["comment_reaction"] == "FUNNY"
    assert vip["signals"]["comment_count"] == 2
