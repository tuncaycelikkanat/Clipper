import subprocess
import numpy as np
from typing import Dict, List, Any, Tuple
import yt_dlp

class AudioDSPAnalyzer:
    """Extracts and analyzes audio stream for Gaming highlight signals (energy spikes & shock patterns)."""

    @staticmethod
    def extract_audio_energy(url: str, duration_sec: int, sample_rate: int = 16000, hop_sec: float = 0.5) -> Tuple[np.ndarray, np.ndarray]:
        """
        Streams audio via FFmpeg and computes RMS energy profile over time.
        Returns: (time_array, rms_energy_array)
        """
        # Get audio direct stream URL using yt-dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url = info.get('url')
            if not stream_url:
                # Find direct format url
                for f in info.get('formats', []):
                    if f.get('acodec') != 'none' and f.get('url'):
                        stream_url = f.get('url')
                        break

        if not stream_url:
            raise RuntimeError("Ses akış URL'si alınamadı.")

        # Stream raw PCM audio via FFmpeg pipe
        # Limit to duration or full stream, convert to 16kHz mono float32
        cmd = [
            'ffmpeg',
            '-ss', '0',
            '-i', stream_url,
            '-t', str(duration_sec),
            '-f', 'f32le',
            '-acodec', 'pcm_f32le',
            '-ac', '1',
            '-ar', str(sample_rate),
            '-v', 'quiet',
            '-'
        ]

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        raw_audio, _ = process.communicate()

        if len(raw_audio) < 1000:
            # Fallback mock/synthetic if stream blocked
            total_points = int(duration_sec / hop_sec)
            times = np.linspace(0, duration_sec, total_points)
            rms = np.zeros(total_points)
            return times, rms

        # Convert raw bytes to numpy float32
        audio = np.frombuffer(raw_audio, dtype=np.float32)

        # Windowed RMS calculation
        window_size = int(sample_rate * hop_sec)
        num_windows = int(len(audio) / window_size)
        
        times = []
        rms_values = []
        
        for i in range(num_windows):
            chunk = audio[i * window_size : (i + 1) * window_size]
            rms = np.sqrt(np.mean(chunk**2) + 1e-12)
            times.append(i * hop_sec)
            rms_values.append(rms)

        times_arr = np.array(times)
        rms_arr = np.array(rms_values)

        # Normalize RMS between 0.0 and 1.0
        max_rms = np.max(rms_arr) if len(rms_arr) > 0 and np.max(rms_arr) > 0 else 1.0
        rms_norm = rms_arr / max_rms

        return times_arr, rms_norm

    @classmethod
    def detect_signals(cls, times: np.ndarray, rms: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Detects:
        1. audio_spike: High audio volume spikes (screams, gunshots, explosions).
        2. silence_burst: Silence followed immediately by sudden explosion (Shock/clutch signature).
        """
        n = len(rms)
        if n == 0:
            return {"audio_spikes": np.array([]), "silence_bursts": np.array([])}

        # 1. Audio Spikes: Rolling Z-score or values above 80th percentile
        median = np.median(rms)
        std = np.std(rms) + 1e-6
        z_scores = (rms - median) / std
        spike_scores = np.clip(z_scores / 3.0, 0.0, 1.0)

        # 2. Silence -> Burst ("Shock Pattern"):
        # Look back 3 seconds (e.g. 6 steps with 0.5s hop) and look ahead 2 seconds
        # Low energy before + High energy after = high shock score
        shock_scores = np.zeros(n)
        window_lookback = 6  # 3 seconds
        window_lookahead = 4 # 2 seconds

        for i in range(window_lookback, n - window_lookahead):
            prev_window = rms[i - window_lookback : i]
            next_window = rms[i : i + window_lookahead]

            prev_energy = np.mean(prev_window)
            next_energy = np.mean(next_window)

            # Condition: previous energy is quiet (< median), next energy is loud (> 2x previous)
            if next_energy > (prev_energy * 2.0) and next_energy > median:
                shock_scores[i] = min(1.0, (next_energy - prev_energy) / (np.max(rms) + 1e-6) * 2.0)

        return {
            "times": times,
            "rms": rms,
            "audio_spikes": spike_scores,
            "silence_bursts": shock_scores
        }
