"""tests/test_dsp_vectorized.py — Verify vectorized DSP calculations produce valid results."""

import numpy as np
from core.audio_dsp import AudioDSPAnalyzer


def test_pitch_variance_vectorized():
    """Verify that sliding_window_view pitch variance correctly calculates variance over hops."""
    from numpy.lib.stride_tricks import sliding_window_view

    n_hops = 100
    win_hops = 6
    zcr = np.sin(np.linspace(0, 20, n_hops, dtype=np.float32)) ** 2

    # Loop version
    pitch_var_loop = np.zeros(n_hops, dtype=np.float32)
    for i in range(win_hops, n_hops):
        pitch_var_loop[i] = float(np.var(zcr[i - win_hops : i]))

    # Vectorized version
    pitch_var_vec = np.zeros(n_hops, dtype=np.float32)
    windows = sliding_window_view(zcr[:n_hops], window_shape=win_hops)
    pitch_var_vec[win_hops:n_hops] = np.var(windows[: n_hops - win_hops], axis=1).astype(np.float32)

    np.testing.assert_allclose(pitch_var_vec, pitch_var_loop, atol=1e-6)


def test_silence_burst_vectorized():
    """Verify vectorized silence bursts detects sudden rise from silence."""
    analyzer = AudioDSPAnalyzer()

    # Create synthetic RMS array with a quiet zone followed by loud burst
    rms = np.array([0.05, 0.04, 0.03, 0.02, 0.85, 0.90, 0.20, 0.15], dtype=np.float32)
    times = np.arange(len(rms), dtype=np.float32)

    peaks = analyzer._detect_audio_peaks(times, rms, silence_thresh=0.15)
    assert "silence_bursts" in peaks
    bursts = peaks["silence_bursts"]

    # Index 4 (rms 0.85 after silence 0.02) should be detected as a burst
    assert bursts[4] > 0.5
