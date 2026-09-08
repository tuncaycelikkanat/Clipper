"""tests/test_phase2_performance.py — Tests for Phase 2 performance optimizations."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from numpy.lib.stride_tricks import sliding_window_view

from core.audio_dsp import AudioDSPAnalyzer
from core.cutter import VideoCutter
from core.llm_engine import GeminiHighlightEngine
from core.smart_layout import SmartLayoutEngine


def test_pitch_variance_vectorized_matches_loop():
    """Verify that vectorized sliding window pitch variance yields identical results to Python loop."""
    n_hops = 200
    win_hops = 8
    np.random.seed(42)
    zcr = np.random.uniform(0.0, 1.0, size=n_hops).astype(np.float32)

    # 1. Classical Python loop
    pitch_var_loop = np.zeros(n_hops, dtype=np.float32)
    for i in range(win_hops, n_hops):
        pitch_var_loop[i] = float(np.var(zcr[i - win_hops : i]))

    # 2. Vectorized sliding_window_view
    pitch_var_vec = np.zeros(n_hops, dtype=np.float32)
    windows = sliding_window_view(zcr[:n_hops], window_shape=win_hops)
    pitch_var_vec[win_hops:n_hops] = np.var(windows[: n_hops - win_hops], axis=1).astype(np.float32)

    # Assert mathematical equivalence
    np.testing.assert_allclose(pitch_var_vec, pitch_var_loop, atol=1e-6)


def test_silence_burst_vectorized_detects_shocks():
    """Verify vectorized silence burst detection finds abrupt audio explosions after quiet periods."""
    analyzer = AudioDSPAnalyzer()
    # Quiet period -> sudden loud jump -> drop
    rms = np.array([0.02, 0.03, 0.04, 0.01, 0.88, 0.95, 0.30, 0.10], dtype=np.float32)
    times = np.arange(len(rms), dtype=np.float32)

    peaks = AudioDSPAnalyzer.detect_signals(times, rms, silence_thresh=0.15)
    assert "silence_bursts" in peaks
    bursts = peaks["silence_bursts"]

    # Index 4 is sudden transition from 0.01 to 0.88
    assert bursts[4] > 0.8
    # Index 0..3 were silent, cannot be bursts
    assert bursts[0] == 0.0
    assert bursts[1] == 0.0


def test_facecam_cache_hits():
    """Verify that detect_facecam caches results per video_path and avoids repeating AI calls."""
    engine = SmartLayoutEngine()
    engine._facecam_cache.clear()

    dummy_result = {"found": True, "corner": "bottom_right", "box_1000": {"ymin": 700, "xmin": 700, "ymax": 950, "xmax": 950}}

    with patch.object(engine, "_detect_facecam_uncached", return_value=dummy_result) as mock_detect:
        # First call: cache miss, invokes _detect_facecam_uncached
        res1 = engine.detect_facecam("/path/to/video_gaming.mp4")
        assert res1["found"] is True
        assert mock_detect.call_count == 1

        # Second call with same video: cache hit, MUST NOT invoke _detect_facecam_uncached
        res2 = engine.detect_facecam("/path/to/video_gaming.mp4")
        assert res2["found"] is True
        assert mock_detect.call_count == 1  # Still 1!

        # Different video: cache miss
        engine.detect_facecam("/path/to/another_video.mp4")
        assert mock_detect.call_count == 2

    engine._facecam_cache.clear()


def test_stream_cache_bounded_lru():
    """Verify VideoCutter._STREAM_CACHE does not grow unboundedly and adheres to _MAX_STREAM_CACHE_SIZE."""
    VideoCutter._STREAM_CACHE.clear()

    with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_instance = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.side_effect = lambda url, download=False: {"url": url, "formats": []}

        # Request 40 unique URLs (limit is 32)
        for i in range(40):
            url = f"https://youtube.com/watch?v=vid_{i:03d}"
            info = VideoCutter._get_stream_info(url)
            assert info is not None
            assert info["url"] == url

        # Cache size must not exceed MAX (32)
        assert len(VideoCutter._STREAM_CACHE) == VideoCutter._MAX_STREAM_CACHE_SIZE

        # Oldest keys (e.g. vid_000, vid_001) should have been evicted
        assert "https://youtube.com/watch?v=vid_000" not in VideoCutter._STREAM_CACHE
        # Recent keys should still be present
        assert "https://youtube.com/watch?v=vid_039" in VideoCutter._STREAM_CACHE

    VideoCutter._STREAM_CACHE.clear()


def test_llm_models_to_try_are_valid():
    """Verify MODELS_TO_TRY does not contain invalid, non-existent Gemini model names."""
    models = GeminiHighlightEngine.MODELS_TO_TRY
    assert len(models) > 0

    # Ensure no fabricated models exist
    for bad_name in ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.7-flash", "gemini-3.6-flash"]:
        assert bad_name not in models

    # Ensure standard verified models are in list
    assert "gemini-2.5-flash" in models or "gemini-2.0-flash" in models or "gemini-1.5-flash" in models


def test_ffmpeg_preset_is_fast():
    """Verify FFmpeg builder uses 'fast' preset instead of 'slow' for performant rendering."""
    cutter = VideoCutter()

    # Complex vertical render
    cmd_complex = cutter._build_ffmpeg_cmd(
        input_path="in.mp4",
        output_path="out.mp4",
        filter_str="[0:v]scale=1080:1920[outv]",
        is_complex=True,
    )
    preset_idx = cmd_complex.index("-preset")
    assert cmd_complex[preset_idx + 1] == "fast"

    # Non-complex render
    cmd_simple = cutter._build_ffmpeg_cmd(
        input_path="in.mp4",
        output_path="out.mp4",
        filter_str="scale=1920:1080",
        is_complex=False,
    )
    preset_idx_simple = cmd_simple.index("-preset")
    assert cmd_simple[preset_idx_simple + 1] == "fast"
