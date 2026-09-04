"""
core/visual_dsp.py — Frame-Diff Görsel Sahne Değişimi Tespiti

FFmpeg ile saniyede 1-2 kare çekerek ardışık kareler arasındaki
piksel farklılığını hesaplar. Ses sinyallerinin kör kaldığı olayları yakalar:
kill feed, zafer/yenilgi ekranı, ani parlama, köklü sahne değişimi.

Sinyal formatı: audio_spikes ile aynı — (times_array, scores_array) [0-1 normalize].
"""

from __future__ import annotations

import subprocess
import tempfile

import numpy as np

from core.logger import logger


class VisualDSPAnalyzer:
    """FFmpeg tabanlı frame-diff görsel sinyal çıkarıcı."""

    @staticmethod
    def extract_frame_diff(
        url: str,
        duration_sec: int,
        fps: float = 1.0,
        scale: str = "160:90",
        spike_window_sec: float = 2.0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Videodan düşük çözünürlüklü kareler çekerek frame-to-frame piksel farklarını hesaplar.

        Args:
            url:              YouTube URL (ya da yerel dosya yolu).
            duration_sec:     Toplam video süresi (saniye).
            fps:              Kaç saniyede bir kare çekilecek (1.0 = saniyede 1 kare).
            scale:            FFmpeg çıktı çözünürlüğü (küçük = hızlı).
            spike_window_sec: Yerel tepe-düzleme penceresi (saniye).

        Returns:
            (times, frame_diff_scores): 0-1 normalize zaman damgalı skor dizisi.
        """
        if duration_sec <= 0:
            return np.array([]), np.array([])

        # Eğer uzaktan bir YouTube URL ise stream URL'ini çöz
        input_source = url
        if url.startswith("http://") or url.startswith("https://"):
            try:
                from core.audio_dsp import AudioDSPAnalyzer

                input_source = AudioDSPAnalyzer._get_stream_url(url)
            except Exception as e:
                logger.debug("VisualDSP stream URL resolution failed, trying direct: {}", e)
                input_source = url

        with tempfile.TemporaryDirectory():
            # FFmpeg ile gri tonlamalı küçük kareler çıkar — pipe üzerinden numpy'a al
            cmd = [
                "ffmpeg",
                "-reconnect",
                "1",
                "-reconnect_at_eof",
                "1",
                "-reconnect_streamed",
                "1",
                "-i",
                input_source,
                "-vf",
                f"fps={fps},scale={scale},format=gray",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "gray",
                "-an",
                "-v",
                "quiet",
                "-",
            ]
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                timeout = max(int(duration_sec * 1.5), 120)
                raw_frames, _ = proc.communicate(timeout=timeout)
            except Exception as exc:
                logger.debug("VisualDSP frame extract failed: {}", exc)
                try:
                    proc.kill()
                    proc.communicate()
                except Exception:
                    pass
                return np.array([]), np.array([])

        if not raw_frames:
            return np.array([]), np.array([])

        # Çözünürlüğü scale'den parse et
        try:
            w_str, h_str = scale.split(":")
            W, H = int(w_str), int(h_str)
        except Exception:
            W, H = 160, 90

        frame_size = W * H
        if frame_size == 0 or len(raw_frames) < frame_size:
            return np.array([]), np.array([])

        n_frames = len(raw_frames) // frame_size
        if n_frames < 2:
            return np.array([]), np.array([])

        raw_arr = np.frombuffer(raw_frames[: n_frames * frame_size], dtype=np.uint8)
        frames = raw_arr.reshape(n_frames, H, W).astype(np.float32) / 255.0

        hop_sec = 1.0 / fps
        times = np.array([i * hop_sec for i in range(n_frames)], dtype=np.float32)

        # Ardışık kare farkı (L1 norm, piksel bazında ortalama)
        diffs = np.zeros(n_frames, dtype=np.float32)
        for i in range(1, n_frames):
            diffs[i] = float(np.mean(np.abs(frames[i] - frames[i - 1])))

        # Kayan pencerede maksimum alma — ani sıçramaları vurgula
        win = max(1, int(spike_window_sec * fps))
        smoothed = np.zeros_like(diffs)
        for i in range(len(diffs)):
            lo = max(0, i - win)
            smoothed[i] = diffs[lo : i + 1].max()

        # 0-1 normalize
        mx = smoothed.max()
        if mx > 1e-9:
            smoothed = smoothed / mx

        logger.debug("VisualDSP: {} kare analiz edildi, max_diff={:.3f}", n_frames, float(mx))
        return times, smoothed

    @staticmethod
    def interpolate_to_timeline(
        vis_times: np.ndarray,
        vis_scores: np.ndarray,
        target_times: np.ndarray,
    ) -> np.ndarray:
        """
        frame_diff sinyalini audio timeline'ına (0.5s hop) interpole eder.
        Diğer sinyal eğrileriyle aynı uzunluğa getirir.
        """
        if len(vis_times) == 0 or len(target_times) == 0:
            return np.zeros(len(target_times), dtype=np.float32)
        return np.interp(target_times, vis_times, vis_scores, left=0.0, right=0.0).astype(np.float32)
