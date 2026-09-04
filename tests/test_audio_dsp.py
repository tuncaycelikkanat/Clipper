import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from core.audio_dsp import AudioDSPAnalyzer

def test_extract_chunk_short_audio():
    with patch('subprocess.Popen') as mock_popen:
        mock_process = MagicMock()
        # Return less than 1000 bytes
        mock_process.communicate.return_value = (b'short', b'')
        mock_popen.return_value = mock_process
        
        times, rms = AudioDSPAnalyzer._extract_chunk("url", 0, 2.0, 16000, 0.5)
        
        assert len(times) == 4
        assert len(rms) == 4
        assert np.all(rms == 0.0)

def test_extract_chunk_normal_audio():
    with patch('subprocess.Popen') as mock_popen:
        mock_process = MagicMock()
        # 16000 sample rate * 0.5 hop_sec = 8000 float32 (32000 bytes) per window
        # Create 2 windows (64000 bytes)
        fake_audio = np.ones(16000, dtype=np.float32)
        mock_process.communicate.return_value = (fake_audio.tobytes(), b'')
        mock_popen.return_value = mock_process
        
        times, rms = AudioDSPAnalyzer._extract_chunk("url", 0, 1.0, 16000, 0.5)
        
        assert len(times) == 2
        assert len(rms) == 2
        # rms of ones should be approx 1.0
        assert np.isclose(rms[0], 1.0)
        assert np.isclose(rms[1], 1.0)

@patch('core.audio_dsp.yt_dlp.YoutubeDL')
@patch.object(AudioDSPAnalyzer, '_extract_chunk')
def test_extract_audio_energy_success_main_url(mock_chunk, mock_ytdl):
    mock_instance = MagicMock()
    mock_ytdl.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {'url': 'http://stream'}
    
    mock_chunk.return_value = (np.array([0.0, 0.5]), np.array([1.0, 2.0]))
    
    times, rms = AudioDSPAnalyzer.extract_audio_energy("url", 4, num_chunks=2)
    assert len(times) == 4
    assert len(rms) == 4
    # Max rms across all chunks is 2.0, so values [1.0, 2.0, 1.0, 2.0] normalized -> [0.5, 1.0, 0.5, 1.0]
    assert np.allclose(rms, [0.5, 1.0, 0.5, 1.0])

@patch('core.audio_dsp.yt_dlp.YoutubeDL')
@patch.object(AudioDSPAnalyzer, '_extract_chunk')
def test_extract_audio_energy_success_format_fallback(mock_chunk, mock_ytdl):
    mock_instance = MagicMock()
    mock_ytdl.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {
        'url': None,
        'formats': [{'acodec': 'mp4a', 'url': 'http://stream2'}]
    }
    
    mock_chunk.return_value = (np.array([0.0]), np.array([0.0]))
    
    times, rms = AudioDSPAnalyzer.extract_audio_energy("url", 2, num_chunks=1)
    assert len(times) == 1
    assert len(rms) == 1
    # When max is 0, it falls back to max_rms=1.0, so [0.0] -> [0.0]
    assert rms[0] == 0.0

@patch('core.audio_dsp.yt_dlp.YoutubeDL')
def test_extract_audio_energy_no_url(mock_ytdl):
    mock_instance = MagicMock()
    mock_ytdl.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {}
    
    with pytest.raises(RuntimeError, match="Ses akış URL'si alınamadı."):
        AudioDSPAnalyzer.extract_audio_energy("url", 10)

def test_extract_audio_energy_empty_results():
    with patch('core.audio_dsp.yt_dlp.YoutubeDL') as mock_ytdl, \
         patch.object(AudioDSPAnalyzer, '_extract_chunk') as mock_chunk:
        
        mock_instance = MagicMock()
        mock_ytdl.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = {'url': 'http://stream'}
        
        # Mock empty chunk results
        mock_chunk.return_value = (np.array([]), np.array([]))
        
        times, rms = AudioDSPAnalyzer.extract_audio_energy("url", 4, num_chunks=2)
        assert len(times) == 0
        assert len(rms) == 0

def test_detect_signals_empty():
    res = AudioDSPAnalyzer.detect_signals(np.array([]), np.array([]))
    assert len(res["audio_spikes"]) == 0
    assert len(res["silence_bursts"]) == 0

def test_detect_signals_normal():
    # Create artificial rms to trigger shocks
    n = 20
    times = np.arange(n, dtype=float)
    rms = np.ones(n)
    
    # Create a silence burst at index 10
    rms[4:10] = 0.1 # silence
    rms[10:14] = 5.0 # explosion
    
    res = AudioDSPAnalyzer.detect_signals(times, rms)
    
    # Audio spikes
    assert np.any(res["audio_spikes"] > 0)
    
    # Shock burst
    # Window lookback = 6, lookahead = 4
    # i=10 looks back to 4:10 (mean=0.1), looks ahead 10:14 (mean=5.0)
    assert res["silence_bursts"][10] > 0.0


def test_detect_signals_with_vocal_energy():
    n = 20
    times = np.arange(n, dtype=float)
    rms = np.ones(n)
    vocal = np.zeros(n)
    vocal[10] = 5.0  # vocal spike at index 10

    res = AudioDSPAnalyzer.detect_signals(times, rms, vocal_energy=vocal)
    assert "vocal_spikes" in res
    assert res["vocal_spikes"][10] > 0.0

