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
        """Resolve the best audio stream URL via yt-dlp with resilient fallback strategies."""
        # Tier 1: Try format selection with standard clients
        strategies = [
            # Strateji 1: Standart yt-dlp format seçimi (en yüksek uyumluluk)
            {
                'format': 'bestaudio/ba/b/best',
                'quiet': True,
                'no_warnings': True,
            },
            # Strateji 2: Mobil web & web client ile
            {
                'format': 'ba/b/bestaudio/best',
                'quiet': True,
                'no_warnings': True,
                'extractor_args': {'youtube': {'player_client': ['mweb', 'web', 'android']}},
            },
            # Strateji 3: Herhangi bir akış formatı (audio/video birleşik dahil)
            {
                'format': 'worst/best',
                'quiet': True,
                'no_warnings': True,
            }
        ]

        last_err = None
        for opts in strategies:
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        continue
                    stream_url = info.get('url')
                    if stream_url:
                        return stream_url
                    # Format listesinden doğrudan geçerli ses veya video akış URL'si bul
                    for f in info.get('formats', []):
                        if (f.get('acodec') != 'none' or f.get('vcodec') != 'none') and f.get('url'):
                            return f['url']
            except Exception as e:
                last_err = e
                continue

        raise RuntimeError(f"Ses akış URL'si alınamadı: {last_err}")

    @staticmethod
    def _extract_chunk_raw(stream_url: str, start_sec: float, dur_sec: float, sample_rate: int) -> Tuple[float, np.ndarray]:
        """Extracts raw mono float32 PCM samples for a specific time window via FFmpeg stream."""
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
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            timeout_sec = max(int(dur_sec * 1.5), 30)
            raw_data, _ = proc.communicate(timeout=timeout_sec)
            if raw_data and len(raw_data) >= 8:
                samples = np.frombuffer(raw_data, dtype=np.float32)
                return start_sec, samples
        except Exception:
            try:
                proc.kill()
                proc.communicate()
            except Exception:
                pass
        expected_len = int(dur_sec * sample_rate)
        return start_sec, np.zeros(expected_len, dtype=np.float32)

    @staticmethod
    def extract_all_signals_fast(
        url: str,
        duration_sec: int,
        sample_rate: int = 8000,
        hop_sec: float = 0.5,
        num_workers: int = 8,
        pitch_window_sec: float = 3.0
    ) -> Dict[str, Any]:
        """
        Ultra-fast unified Audio DSP extraction:
        Resolves stream URL once, downloads parallel chunks, and vectorizes RMS,
        zero-crossing rate (pitch variance), audio spikes, and silence bursts in a single pass.
        Runs in 2-5 seconds instead of minutes.
        """
        if duration_sec <= 0:
            empty = np.array([], dtype=np.float32)
            return {
                "times": empty,
                "rms": empty,
                "signals": {"times": empty, "audio_spikes": empty, "silence_bursts": empty},
                "pitch_times": empty,
                "pitch_var": empty,
            }

        import tempfile
        import os

        audio = None
        # 1. Hızlı Yerel Decode / yt-dlp Çoklu Parça İndirme (20-30s)
        if not url.startswith(("http://", "https://")) and os.path.exists(url):
            try:
                cmd = [
                    'ffmpeg', '-y',
                    '-i', url,
                    '-f', 'f32le',
                    '-acodec', 'pcm_f32le',
                    '-ac', '1',
                    '-ar', str(sample_rate),
                    '-v', 'quiet',
                    '-'
                ]
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                raw_data, _ = proc.communicate(timeout=60)
                if raw_data and len(raw_data) >= 8:
                    audio = np.frombuffer(raw_data, dtype=np.float32)
            except Exception:
                pass
        else:
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_pattern = os.path.join(tmp_dir, "audio.%(ext)s")
                    ydl_opts = {
                        'format': 'ba/bestaudio[ext=m4a]/bestaudio/best',
                        'outtmpl': tmp_pattern,
                        'concurrent_fragment_downloads': 8,
                        'buffersize': 1048576,
                        'quiet': True,
                        'no_warnings': True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        ext = info.get("ext", "opus") if info else "opus"
                        downloaded_path = os.path.join(tmp_dir, f"audio.{ext}")
                        if not os.path.exists(downloaded_path):
                            for cand in os.listdir(tmp_dir):
                                downloaded_path = os.path.join(tmp_dir, cand)
                                break
                        if os.path.exists(downloaded_path):
                            cmd = [
                                'ffmpeg', '-y',
                                '-i', downloaded_path,
                                '-f', 'f32le',
                                '-acodec', 'pcm_f32le',
                                '-ac', '1',
                                '-ar', str(sample_rate),
                                '-v', 'quiet',
                                '-'
                            ]
                            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            raw_data, _ = proc.communicate(timeout=60)
                            if raw_data and len(raw_data) >= 8:
                                audio = np.frombuffer(raw_data, dtype=np.float32)
            except Exception:
                audio = None

        # Fallback: Paralel Akış Parçalama (Chunk streaming)
        if audio is None or len(audio) == 0:
            try:
                stream_url = AudioDSPAnalyzer._get_stream_url(url)
                chunk_dur = duration_sec / num_workers
                from concurrent.futures import ThreadPoolExecutor

                futures = []
                with ThreadPoolExecutor(max_workers=num_workers) as executor:
                    for i in range(num_workers):
                        s_sec = i * chunk_dur
                        d_sec = chunk_dur if i < num_workers - 1 else duration_sec - s_sec
                        futures.append(executor.submit(AudioDSPAnalyzer._extract_chunk_raw, stream_url, s_sec, d_sec, sample_rate))

                chunk_results = [f.result() for f in futures]
                chunk_results.sort(key=lambda x: x[0])

                all_samples = [c[1] for c in chunk_results if len(c[1]) > 0]
                if all_samples:
                    audio = np.concatenate(all_samples)
            except Exception:
                audio = None

        if audio is None or len(audio) == 0:
            empty = np.array([], dtype=np.float32)
            return {
                "times": empty,
                "rms": empty,
                "signals": {"times": empty, "audio_spikes": empty, "silence_bursts": empty},
                "pitch_times": empty,
                "pitch_var": empty,
            }
        hop_samples = int(sample_rate * hop_sec)
        n_hops = int(len(audio) / hop_samples)
        if n_hops <= 0:
            empty = np.array([], dtype=np.float32)
            return {
                "times": empty,
                "rms": empty,
                "signals": {"times": empty, "audio_spikes": empty, "silence_bursts": empty},
                "pitch_times": empty,
                "pitch_var": empty,
            }

        # Vektörize matrise dönüştür: (n_hops, hop_samples)
        audio_matrix = audio[: n_hops * hop_samples].reshape((n_hops, hop_samples))
        times = np.linspace(0, n_hops * hop_sec, n_hops, endpoint=False, dtype=np.float32)

        # 1. Vectorized RMS Profile
        rms = np.sqrt(np.mean(audio_matrix ** 2, axis=1) + 1e-12)
        mx_rms = np.max(rms)
        rms_norm = rms / (mx_rms + 1e-6) if mx_rms > 0 else rms

        # 2. Vectorized Zero-Crossing Rate (ZCR)
        signs = np.sign(audio_matrix + 1e-9)
        zcr = np.mean(np.abs(np.diff(signs, axis=1)), axis=1) / 2.0

        # 3. Kayan Pencere ZCR Varyansı (Kahkaha / Coşku)
        win_hops = max(1, int(pitch_window_sec / hop_sec))
        pitch_var = np.zeros(n_hops, dtype=np.float32)
        if n_hops > win_hops:
            for i in range(win_hops, n_hops):
                pitch_var[i] = float(np.var(zcr[i - win_hops : i]))
            mx_pv = pitch_var.max()
            if mx_pv > 1e-9:
                pitch_var = pitch_var / mx_pv

        # 4. Spikes & Silence Shock Detection
        signals = AudioDSPAnalyzer.detect_signals(times, rms_norm)

        return {
            "times": times,
            "rms": rms_norm,
            "signals": signals,
            "pitch_times": times,
            "pitch_var": pitch_var,
        }

    @staticmethod
    def extract_audio_energy(url: str, duration_sec: int, sample_rate: int = 8000, hop_sec: float = 0.5, num_chunks: int = 8) -> Tuple[np.ndarray, np.ndarray]:
        """Fast fallback wrapper for backward compatibility."""
        res = AudioDSPAnalyzer.extract_all_signals_fast(url, duration_sec, sample_rate=sample_rate, hop_sec=hop_sec, num_workers=num_chunks)
        return res["times"], res["rms"]

    @staticmethod
    def detect_signals(times: np.ndarray, rms: np.ndarray, z_thresh: float = 2.0, silence_thresh: float = 0.15) -> Dict[str, np.ndarray]:
        """
        Detects highlight signal markers from RMS energy:
        1. audio_spikes: High-energy shouting / reactions (z-score >= threshold).
        2. silence_bursts: High dynamic jump from silence to explosion (tension release).
        """
        if len(rms) == 0:
            return {"times": times, "audio_spikes": np.array([]), "silence_bursts": np.array([])}

        mean = np.mean(rms)
        std = np.std(rms) + 1e-6
        z_scores = (rms - mean) / std

        # 1. Z-Score Spikes (0 to 1 normalized)
        audio_spikes = np.clip((z_scores - z_thresh) / (np.max(z_scores) - z_thresh + 1e-6), 0.0, 1.0)

        # 2. Silence to Burst (Shock pattern)
        silence_bursts = np.zeros_like(rms)
        for i in range(2, len(rms)):
            pre_min = np.min(rms[max(0, i-4):i])
            cur = rms[i]
            if pre_min < silence_thresh and cur > 0.6:
                silence_bursts[i] = min(1.0, (cur - pre_min) / 0.8)

        return {
            "times": times,
            "rms": rms,
            "audio_spikes": audio_spikes,
            "silence_bursts": silence_bursts
        }

    @staticmethod
    def extract_pitch_variance(
        url: str,
        duration_sec: int,
        sample_rate: int = 8000,
        hop_sec: float = 0.5,
        pitch_window_sec: float = 3.0,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Fast pitch variance wrapper for backward compatibility."""
        res = AudioDSPAnalyzer.extract_all_signals_fast(url, duration_sec, sample_rate=sample_rate, hop_sec=hop_sec, pitch_window_sec=pitch_window_sec)
        return res["pitch_times"], res["pitch_var"]
