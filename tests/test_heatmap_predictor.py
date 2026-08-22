"""
tests/test_heatmap_predictor.py — HeatmapPredictor birim testleri
"""

import json
from unittest import mock

import numpy as np
import pytest

from core.heatmap_predictor import HeatmapPredictor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    db = mock.MagicMock()
    db.get_videos_with_heatmap_patterns.return_value = []
    return db


@pytest.fixture
def predictor(mock_db):
    return HeatmapPredictor(mock_db)


def _make_audio_signals(n=200):
    times = np.linspace(0, 100, n)
    spikes = np.random.rand(n)
    silences = np.random.rand(n)
    return times, spikes, silences


# ---------------------------------------------------------------------------
# predict() — temel çıktı yapısı
# ---------------------------------------------------------------------------

def test_predict_returns_correct_keys(predictor):
    times, spikes, silences = _make_audio_signals()
    result = predictor.predict(
        audio_times=times,
        audio_spikes=spikes,
        silence_bursts=silences,
        total_duration=100.0,
    )
    assert "heatmap" in result
    assert "confidence" in result
    assert "source" in result
    assert "hidden_viral_peaks" in result


def test_predict_heatmap_has_correct_segment_count(predictor):
    times, spikes, silences = _make_audio_signals()
    result = predictor.predict(
        audio_times=times,
        audio_spikes=spikes,
        silence_bursts=silences,
        total_duration=50.0,  # 50 sn / 5 seg = 10 segment
    )
    assert len(result["heatmap"]) == 10


def test_predict_heatmap_values_normalized(predictor):
    times, spikes, silences = _make_audio_signals()
    result = predictor.predict(
        audio_times=times,
        audio_spikes=spikes,
        silence_bursts=silences,
        total_duration=100.0,
    )
    for seg in result["heatmap"]:
        assert 0.0 <= seg["value"] <= 1.0


def test_predict_heatmap_segment_format(predictor):
    times, spikes, silences = _make_audio_signals()
    result = predictor.predict(
        audio_times=times,
        audio_spikes=spikes,
        silence_bursts=silences,
        total_duration=30.0,
    )
    for seg in result["heatmap"]:
        assert "start_time" in seg
        assert "end_time" in seg
        assert "value" in seg
        assert seg["end_time"] > seg["start_time"]


# ---------------------------------------------------------------------------
# confidence & source
# ---------------------------------------------------------------------------

def test_predict_source_audio_proxy_when_no_history(predictor):
    times, spikes, silences = _make_audio_signals()
    result = predictor.predict(times, spikes, silences, 100.0)
    assert result["source"] == "audio_proxy"
    assert result["confidence"] == pytest.approx(0.40)


def test_predict_source_correlation_model_when_history_present(mock_db):
    mock_db.get_videos_with_heatmap_patterns.return_value = [
        {"heatmap_meta_json": json.dumps({"spike_heatmap_corr": 0.7, "silence_heatmap_corr": 0.4})},
        {"heatmap_meta_json": json.dumps({"spike_heatmap_corr": 0.6, "silence_heatmap_corr": 0.3})},
    ]
    predictor = HeatmapPredictor(mock_db)
    times, spikes, silences = _make_audio_signals()
    result = predictor.predict(times, spikes, silences, 100.0)
    assert result["source"] == "correlation_model"
    assert result["confidence"] == pytest.approx(0.65)


# ---------------------------------------------------------------------------
# Gizli Viral Tespiti
# ---------------------------------------------------------------------------

def test_hidden_viral_not_detected_high_view_count(predictor):
    times, spikes, silences = _make_audio_signals()
    result = predictor.predict(
        audio_times=times,
        audio_spikes=spikes,
        silence_bursts=silences,
        total_duration=100.0,
        view_count=200_000,  # Yüksek görüntü → gizli viral değil
    )
    assert result["hidden_viral_peaks"] == []


def test_hidden_viral_detected_low_view_count(predictor):
    n = 200
    times = np.linspace(0, 100, n)
    # Sinyal: düşük baseline üzerine birkaç yüksek pik
    spikes = np.zeros(n)
    silences = np.zeros(n)
    # Ortada güçlü pikler ekle
    spikes[90:110] = 1.0
    silences[90:110] = 1.0
    result = predictor.predict(
        audio_times=times,
        audio_spikes=spikes,
        silence_bursts=silences,
        total_duration=100.0,
        view_count=10_000,  # Düşük görüntü → gizli viral tetiklenmeli
    )
    assert len(result["hidden_viral_peaks"]) > 0
    for peak in result["hidden_viral_peaks"]:
        assert "time" in peak
        assert "score" in peak
        assert "reason" in peak



def test_hidden_viral_peaks_capped_at_5(predictor):
    times = np.linspace(0, 100, 500)
    # Hep yüksek → çok fazla peak oluşur
    spikes = np.ones(500)
    silences = np.ones(500)
    result = predictor.predict(
        audio_times=times,
        audio_spikes=spikes,
        silence_bursts=silences,
        total_duration=100.0,
        view_count=5_000,
    )
    assert len(result["hidden_viral_peaks"]) <= 5


def test_detect_hidden_viral_from_real_heatmap(predictor):
    heatmap = [
        {"start_time": 0, "end_time": 5, "value": 0.3},
        {"start_time": 5, "end_time": 10, "value": 0.85},  # Gizli viral
        {"start_time": 10, "end_time": 15, "value": 0.2},
    ]
    peaks = predictor.detect_hidden_viral_from_real(heatmap, view_count=20_000)
    assert len(peaks) == 1
    assert peaks[0]["score"] == pytest.approx(0.85)


def test_detect_hidden_viral_from_real_heatmap_high_views(predictor):
    heatmap = [{"start_time": 0, "end_time": 5, "value": 0.9}]
    peaks = predictor.detect_hidden_viral_from_real(heatmap, view_count=200_000)
    assert peaks == []


# ---------------------------------------------------------------------------
# Boş sinyal edge cases
# ---------------------------------------------------------------------------

def test_predict_empty_signal_returns_uniform_heatmap(predictor):
    times = np.array([])
    spikes = np.array([])
    silences = np.array([])
    result = predictor.predict(times, spikes, silences, 30.0)
    # Segmentler yine de üretilmeli (uniform sıfır)
    assert len(result["heatmap"]) > 0
    for seg in result["heatmap"]:
        assert seg["value"] == pytest.approx(0.0)


def test_predict_constant_signal(predictor):
    """Sabit sinyal → normalize sonrası sıfır olmalı."""
    n = 100
    times = np.linspace(0, 50, n)
    spikes = np.ones(n)
    silences = np.ones(n)
    result = predictor.predict(times, spikes, silences, 50.0)
    for seg in result["heatmap"]:
        assert seg["value"] == pytest.approx(0.0, abs=1e-6)
