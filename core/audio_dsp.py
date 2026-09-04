import subprocess
import numpy as np
from typing import Dict, List, Any, Tuple
import yt_dlp


_YDL_EXTRACTOR_ARGS = {
    'extractor_args': {'youtube': {'player_client': ['ios', 'android_creator', 'tv_embedded', 'web']}}
}


class AudioDSPAnalyzer:
    """Extracts and analyzes audio stream for Gaming highlight signals (energy spikes & shock patterns)."""

    @staticmethod
    def _get_stream_url(url: str) -> str:
        """Resolve the best audio stream URL via yt-dlp (shared helper)."""
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            **_YDL_EXTRACTOR_ARGS,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url = info.get('url')
            if not stream_url:
                for f in info.get('formats', []):
                    if f.get('acodec') != 'none' and f.get('url'):
                        stream_url = f.get('url')
                        break
        if not stream_url:
            raise RuntimeError("Ses akış URL'si alınamadı.")
        return stream_url

    @staticmethod
    def _extract_chunk(stream_url: str, start_sec: float, dur_sec: float, sample_rate: int, hop_sec: float) -> Tuple[np.ndarray, np.ndarray]:
        """Worker function to extract a specific chunk of audio with reconnect & timeout safety."""
        total_points = max(int(dur_sec / hop_sec), 1)
        fallback_times = np.linspace(start_sec, start_sec + dur_sec, total_points, endpoint=False)
        fallback_rms = np.zeros(total_points)

        cmd = [
            'ffmpeg',
            '-reconnect', '1',
            '-reconnect_at_eof', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', '2',
            '-ss', str(start_sec),
            '-i', stream_url,
            '-t', str(dur_sec),
            '-f', 'f32le',
            '-acodec', 'pcm_f32le',
            '-ac', '1',
            '-ar', str(sample_rate),
            '-v', 'quiet',
            '-'
        ]
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            timeout_sec = max(int(dur_sec * 1.5), 60)
            raw_audio, _ = process.communicate(timeout=timeout_sec)
        except (subprocess.TimeoutExpired, Exception):
            try:
                process.kill()
                process.communicate()
            except Exception:
                pass
            return fallback_times, fallback_rms

        if not raw_audio or len(raw_audio) < 1000:
            return fallback_times, fallback_rms

        audio = np.frombuffer(raw_audio, dtype=np.float32)
        window_size = int(sample_rate * hop_sec)
        num_windows = int(len(audio) / window_size)

        times = []
        rms_values = []
        for i in range(num_windows):
            chunk = audio[i * window_size : (i + 1) * window_size]
            rms = np.sqrt(np.mean(chunk**2) + 1e-12)
            times.append(start_sec + i * hop_sec)
            rms_values.append(rms)

        return np.array(times), np.array(rms_values)

    @staticmethod
    def extract_audio_energy(url: str, duration_sec: int, sample_rate: int = 16000, hop_sec: float = 0.5, num_chunks: int = 4) -> Tuple[np.ndarray, np.ndarray]:
        """
        Streams audio via FFmpeg in parallel chunks and computes RMS energy profile over time.
        Returns: (time_array, rms_energy_array)
        """
        stream_url = AudioDSPAnalyzer._get_stream_url(url)

        chunk_dur = duration_sec / num_chunks
        futures = []
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=num_chunks) as executor:
            for i in range(num_chunks):
                start_sec = i * chunk_dur
                dur_sec = chunk_dur if i < num_chunks - 1 else duration_sec - start_sec
                futures.append(executor.submit(AudioDSPAnalyzer._extract_chunk, stream_url, start_sec, dur_sec, sample_rate, hop_sec))

        all_times = []
        all_rms = []
        for future in futures:
            t, r = future.result()
            all_times.append(t)
            all_rms.append(r)

        times_arr = np.concatenate(all_times) if all_times else np.array([])
        rms_arr = np.concatenate(all_rms) if all_rms else np.array([])

        if len(rms_arr) > 0:
            max_rms = np.max(rms_arr) if np.max(rms_arr) > 0 else 1.0
            rms_norm = rms_arr / max_rms
        else:
            rms_norm = rms_arr

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
            return {"times": np.array([]), "rms": np.array([]), "audio_spikes": np.array([]), "silence_bursts": np.array([])}

        # 1. Audio Spikes: Rolling Z-score
        median = np.median(rms)
        std = np.std(rms) + 1e-6
        z_scores = (rms - median) / std
        spike_scores = np.clip(z_scores / 3.0, 0.0, 1.0)

        # 2. Silence -> Burst ("Shock Pattern")
        shock_scores = np.zeros(n)
        window_lookback = 6  # 3 seconds @ 0.5s hop
        window_lookahead = 4  # 2 seconds

        for i in range(window_lookback, n - window_lookahead):
            prev_window = rms[i - window_lookback: i]
            next_window = rms[i: i + window_lookahead]
            prev_energy = np.mean(prev_window)
            next_energy = np.mean(next_window)
            if next_energy > (prev_energy * 2.0) and next_energy > median:
                shock_scores[i] = min(1.0, (next_energy - prev_energy) / (np.max(rms) + 1e-6) * 2.0)

        return {
            "times": times,
            "rms": rms,
            "audio_spikes": spike_scores,
            "silence_bursts": shock_scores,
        }

    @staticmethod
    def extract_pitch_variance(
        url: str,
        duration_sec: int,
        sample_rate: int = 16000,
        hop_sec: float = 0.5,
        pitch_window_sec: float = 3.0,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Kahkaha tespiti için pitch/F0 varyans sinyali çıkarır.

        librosa gerektirmez. Zero-Crossing Rate (ZCR) proxy olarak kullanılır:
        - Kahkahanın tonal imzası = yüksek ZCR varyansı (ses titreşim frekansı çabuk değişir).
        - Bu sinyal RMS/desibel yüksekliği ölçemediği için ayrıdır; sessiz kahkahaları da yakalar.

        Returns:
            (times, pitch_variance_scores): 0-1 normalize zaman damgalı skor dizisi,
            audio_spikes ile aynı formatta.
        """
        try:
            stream_url = AudioDSPAnalyzer._get_stream_url(url)
        except Exception:
            return np.array([]), np.array([])

        # Tüm sesi tek seferde aktar (hafif — 16kHz mono yeter)
        cmd = [
            'ffmpeg',
            '-reconnect', '1', '-reconnect_at_eof', '1',
            '-reconnect_streamed', '1', '-reconnect_delay_max', '2',
            '-i', stream_url,
            '-t', str(duration_sec),
            '-f', 'f32le', '-acodec', 'pcm_f32le',
            '-ac', '1', '-ar', str(sample_rate),
            '-v', 'quiet', '-'
        ]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            timeout = max(int(duration_sec * 2), 120)
            raw_audio, _ = proc.communicate(timeout=timeout)
        except Exception:
            try:
                proc.kill()
                proc.communicate()
            except Exception:
                pass
            return np.array([]), np.array([])

        if not raw_audio or len(raw_audio) < 2000:
            return np.array([]), np.array([])

        audio = np.frombuffer(raw_audio, dtype=np.float32)
        hop_samples = int(sample_rate * hop_sec)
        n_hops = int(len(audio) / hop_samples)

        # Her hop için ZCR hesapla
        zcr_vals = []
        times_out = []
        for i in range(n_hops):
            frame = audio[i * hop_samples: (i + 1) * hop_samples]
            zcr = float(np.mean(np.abs(np.diff(np.sign(frame + 1e-9)))) / 2.0)
            zcr_vals.append(zcr)
            times_out.append(i * hop_sec)

        if not zcr_vals:
            return np.array([]), np.array([])

        zcr_arr = np.array(zcr_vals, dtype=np.float32)
        times_arr = np.array(times_out, dtype=np.float32)

        # Kayan pencerede ZCR varyansı → kahkaha/coşku tespiti
        win_hops = max(1, int(pitch_window_sec / hop_sec))
        variance_curve = np.zeros(len(zcr_arr), dtype=np.float32)
        for i in range(win_hops, len(zcr_arr)):
            window = zcr_arr[max(0, i - win_hops): i]
            variance_curve[i] = float(np.var(window))

        # 0-1 normalize
        mx = variance_curve.max()
        if mx > 1e-9:
            variance_curve = variance_curve / mx

        return times_arr, variance_curve
