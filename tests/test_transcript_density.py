"""
tests/test_transcript_density.py — Unit tests for TranscriptDensityAnalyzer
"""

import numpy as np
import pytest

from core.transcript_density import TranscriptDensityAnalyzer


@pytest.fixture
def analyzer():
    return TranscriptDensityAnalyzer()


def test_compute_density_curve_empty(analyzer):
    times = np.linspace(0, 100, 100)
    assert np.all(analyzer.compute_density_curve([], times, 100.0) == 0.0)
    assert len(analyzer.compute_density_curve([{"text": "hi"}], np.array([]), 100.0)) == 0
    assert np.all(analyzer.compute_density_curve([{"text": "hi"}], times, 0.0) == 0.0)


def test_score_segment_text_empty(analyzer):
    assert analyzer.score_segment_text("", 2.0) == 0.0
    assert analyzer.score_segment_text("   ", 2.0) == 0.0


def test_score_segment_text_normal_speech(analyzer):
    text = "Bugün nasılsınız arkadaşlar umarım iyisinizdir"
    score = analyzer.score_segment_text(text, duration_sec=3.0)
    assert 0.5 <= score <= 3.0


def test_score_segment_text_high_energy_keywords(analyzer):
    normal_text = "Şimdi buradan geçiyoruz"
    high_text = "Kaç kaç geliyor arkanda bomba patladı yardım et!"

    normal_score = analyzer.score_segment_text(normal_text, 3.0)
    high_score = analyzer.score_segment_text(high_text, 3.0)

    assert high_score > normal_score * 2.0


def test_score_segment_text_repetitions(analyzer):
    single_word = "dur oraya gitme"
    rep_word = "dur dur dur oraya gitme"

    score_single = analyzer.score_segment_text(single_word, 2.0)
    score_rep = analyzer.score_segment_text(rep_word, 2.0)

    assert score_rep > score_single


def test_score_segment_text_punctuation_boost(analyzer):
    no_punct = "inanılmaz bir vuruş"
    punct = "inanılmaz bir vuruş!!!"

    score_no = analyzer.score_segment_text(no_punct, 2.0)
    score_p = analyzer.score_segment_text(punct, 2.0)

    assert score_p > score_no


def test_score_segment_text_caps_lock(analyzer):
    lower = "allahım nolur ölme"
    caps = "ALLAHIM NOLUR ÖLME"

    score_lower = analyzer.score_segment_text(lower, 2.0)
    score_caps = analyzer.score_segment_text(caps, 2.0)

    assert score_caps > score_lower


def test_compute_density_curve_peak_timing(analyzer):
    segments = [
        {"text": "Normal sakin bir başlangıç", "start": 10.0, "duration": 4.0},
        {"text": "KAÇ KAÇ GELİYOR LAN BASTIM PATLADI VURDUM GG!!!", "start": 50.0, "duration": 5.0},
        {"text": "Sakin devam ediyoruz", "start": 80.0, "duration": 4.0},
    ]
    times = np.linspace(0, 100, 100)
    curve = analyzer.compute_density_curve(segments, times, total_duration=100.0)

    assert len(curve) == 100
    assert 0.0 <= curve.max() <= 1.0

    # Max peak should be near index 50-53 (50-55s mark)
    peak_idx = int(np.argmax(curve))
    assert 48 <= peak_idx <= 56


def test_extract_hotspots(analyzer):
    segments = [
        {"text": "Normal sakin konuşma", "start": 5.0, "duration": 3.0},
        {"text": "LAN OHA ÇÜŞ NASIL VURDU EFSANE!!!", "start": 40.0, "duration": 4.0},
        {"text": "DUR DUR DUR ÖLDÜM YARDIM HELP", "start": 70.0, "duration": 3.0},
    ]
    hotspots = analyzer.extract_hotspots(segments, top_k=2)

    assert len(hotspots) == 2
    assert hotspots[0]["energy_score"] > hotspots[1]["energy_score"]
    assert "LAN" in hotspots[0]["text"] or "DUR" in hotspots[0]["text"]
