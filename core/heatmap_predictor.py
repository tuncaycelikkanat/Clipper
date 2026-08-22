"""
core/heatmap_predictor.py — Tahmini Heatmap Üretici

Gerçek YouTube "Most Replayed" heatmap verisi olmayan videolar için:
1. Kanalın geçmiş heatmap'li videolarından ses→heatmap korelasyonu öğrenir (DB'den)
2. Yeni video için ses profiliyle tahmini heatmap eğrisi üretir
3. "Gizli Viral" anları tespit eder (düşük görüntü ama yüksek heatmap zirvesi)
4. confidence skoru ile birlikte candidate_ranker.py'ye enjekte edilebilir çıktı verir

Kullanım::

    predictor = HeatmapPredictor(db)
    predicted = predictor.predict(
        audio_times=times,
        audio_spikes=spikes,
        silence_bursts=silences,
        total_duration=duration,
        video_id="abc123",
    )
    # predicted["heatmap"]   → heatmap formatında liste [{start_time, end_time, value}]
    # predicted["confidence"] → 0.0-1.0
    # predicted["hidden_viral_peaks"] → [{time, score, reason}]
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import numpy as np
from scipy.signal import savgol_filter  # type: ignore[import-untyped]

from core.logger import logger

if TYPE_CHECKING:
    from core.database import DatabaseManager


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MIN_HISTORY_VIDEOS = 2          # En az bu kadar geçmiş heatmap'li video gerekir
_SEGMENT_DURATION_SEC = 5.0      # Heatmap segmentlerinin süresi (saniye)
_HIDDEN_VIRAL_VIEW_THRESHOLD = 50_000  # Görüntü sayısı bu değerin altıysa "düşük görüntü"
_HIDDEN_VIRAL_HEATMAP_THRESHOLD = 0.70  # Heatmap değeri bu eşiğin üstündeyse "gizli viral"


# ---------------------------------------------------------------------------
# HeatmapPredictor
# ---------------------------------------------------------------------------
class HeatmapPredictor:
    """
    Ses sinyali ile heatmap değerleri arasındaki korelasyonu öğrenir
    ve heatmap olmayan videolara tahmini heatmap eğrisi üretir.
    """

    def __init__(self, db: "DatabaseManager") -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(
        self,
        audio_times: np.ndarray,
        audio_spikes: np.ndarray,
        silence_bursts: np.ndarray,
        total_duration: float,
        video_id: Optional[str] = None,
        view_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Ses sinyali kullanarak tahmini heatmap eğrisi üretir.

        Args:
            audio_times:    Zaman ekseni (saniye cinsinden numpy dizisi)
            audio_spikes:   Ses ani artış sinyali (0-1 normalize)
            silence_bursts: Sessizlik patlaması sinyali (0-1 normalize)
            total_duration: Video toplam süresi (saniye)
            video_id:       Mevcut video ID (kanalın geçmişini çekmek için opsiyonel)
            view_count:     Videonun görüntülenme sayısı (gizli viral tespiti için)

        Returns:
            dict:
                - heatmap (list[dict]): [{start_time, end_time, value}] formatında tahmin
                - confidence (float): 0.0-1.0 güven skoru
                - source (str): "correlation_model" | "audio_proxy" | "uniform"
                - hidden_viral_peaks (list[dict]): [{time, score, reason}]
        """
        # Geçmiş korelasyonu öğrenmeye çalış
        correlation_weights = self._learn_correlation_weights()

        # Ses sinyalini birleştir → temel proxy
        combined_audio = self._combine_audio_signals(
            audio_spikes, silence_bursts, correlation_weights
        )

        # Düzleştir (gürültüyü azalt)
        smoothed = self._smooth_signal(combined_audio)

        # Boş sinyal — tüm segmentler sıfır olarak döner
        if len(smoothed) == 0:
            heatmap = self._to_heatmap_segments(audio_times, np.array([]), total_duration)
            return {
                "heatmap": heatmap,
                "confidence": 0.0,
                "source": "uniform",
                "hidden_viral_peaks": [],
            }

        # 0-1 arası normalize et
        normalized = self._normalize(smoothed)

        # Heatmap formatına dönüştür
        heatmap = self._to_heatmap_segments(audio_times, normalized, total_duration)

        # Güven skoru hesapla
        confidence, source = self._compute_confidence(correlation_weights)

        # Gizli viral tespiti
        hidden_peaks = self._detect_hidden_viral_peaks(
            audio_times, normalized, view_count
        )

        logger.info(
            "HeatmapPredictor: tahmin üretildi — source={} confidence={:.2f} "
            "hidden_viral={} segments={}",
            source, confidence, len(hidden_peaks), len(heatmap)
        )

        return {
            "heatmap": heatmap,
            "confidence": confidence,
            "source": source,
            "hidden_viral_peaks": hidden_peaks,
        }

    def detect_hidden_viral_from_real(
        self,
        heatmap: List[Dict[str, float]],
        view_count: int,
    ) -> List[Dict[str, Any]]:
        """
        GERÇEK heatmap verisinde gizli viral anları tespit eder.
        (Heatmap varken de kullanılabilir.)

        Args:
            heatmap:    Gerçek heatmap segmentleri
            view_count: Video görüntülenme sayısı

        Returns:
            Gizli viral an listesi: [{time, score, reason}]
        """
        if not heatmap or view_count > _HIDDEN_VIRAL_VIEW_THRESHOLD:
            return []

        peaks = []
        for seg in heatmap:
            val = seg.get("value", 0.0)
            if val >= _HIDDEN_VIRAL_HEATMAP_THRESHOLD:
                mid = (seg["start_time"] + seg["end_time"]) / 2.0
                peaks.append({
                    "time": round(mid, 1),
                    "score": round(val, 3),
                    "reason": (
                        f"Düşük görüntü ({view_count:,}) ama yüksek heatmap "
                        f"zirvesi ({val:.0%}) — henüz keşfedilmemiş viral an"
                    ),
                })
        peaks.sort(key=lambda x: x["score"], reverse=True)
        return peaks

    # ------------------------------------------------------------------
    # Internal — Model Learning
    # ------------------------------------------------------------------

    def _learn_correlation_weights(self) -> Dict[str, float]:
        """
        DB'deki heatmap'li geçmiş videolardan ses→heatmap korelasyon ağırlıklarını öğrenir.
        Yeterli veri yoksa None döner → audio_proxy fallback kullanılır.

        Returns:
            {"spike_weight": float, "silence_weight": float} veya None
        """
        try:
            history = self._db.get_videos_with_heatmap_patterns()
        except Exception:
            return {}

        if len(history) < _MIN_HISTORY_VIDEOS:
            logger.debug(
                "HeatmapPredictor: yeterli geçmiş yok ({}/{}), audio_proxy kullanılıyor",
                len(history), _MIN_HISTORY_VIDEOS
            )
            return {}

        # Her geçmiş video için saklanan korelasyonu topla
        spike_corrs: List[float] = []
        silence_corrs: List[float] = []
        for record in history:
            try:
                sc = record.get("spike_heatmap_corr")
                slc = record.get("silence_heatmap_corr")
                if sc is None or slc is None:
                    meta = json.loads(record.get("heatmap_meta_json") or "{}")
                    sc = sc if sc is not None else meta.get("spike_heatmap_corr")
                    slc = slc if slc is not None else meta.get("silence_heatmap_corr")
                if sc is not None:
                    spike_corrs.append(float(sc))
                if slc is not None:
                    silence_corrs.append(float(slc))
            except (json.JSONDecodeError, ValueError, TypeError):
                continue


        if not spike_corrs:
            return {}

        avg_spike = float(np.mean(spike_corrs))
        avg_silence = float(np.mean(silence_corrs)) if silence_corrs else 0.4

        # Negatif korelasyonları sıfırla (negatif ağırlık anlamsız)
        avg_spike = max(0.0, avg_spike)
        avg_silence = max(0.0, avg_silence)

        # Toplamı 1'e normalize et
        total = avg_spike + avg_silence
        if total == 0:
            return {}

        return {
            "spike_weight": avg_spike / total,
            "silence_weight": avg_silence / total,
        }

    # ------------------------------------------------------------------
    # Internal — Signal Processing
    # ------------------------------------------------------------------

    def _combine_audio_signals(
        self,
        audio_spikes: np.ndarray,
        silence_bursts: np.ndarray,
        weights: Dict[str, float],
    ) -> np.ndarray:
        """İki ses sinyalini ağırlıklı olarak birleştirir."""
        sw = weights.get("spike_weight", 0.60)
        slw = weights.get("silence_weight", 0.40)
        return (audio_spikes * sw) + (silence_bursts * slw)

    def _smooth_signal(self, signal: np.ndarray, window: int = 15) -> np.ndarray:
        """Savitzky-Golay filtresi ile sinyali düzleştirir."""
        n = len(signal)
        if n < window:
            return signal
        # window tek sayı olmalı
        if window % 2 == 0:
            window += 1
        try:
            return savgol_filter(signal, window_length=window, polyorder=3)
        except Exception:
            return signal

    def _normalize(self, signal: np.ndarray) -> np.ndarray:
        """Sinyali 0-1 aralığına normalize eder."""
        mn, mx = signal.min(), signal.max()
        if mx - mn < 1e-9:
            return np.zeros_like(signal)
        return (signal - mn) / (mx - mn)

    def _to_heatmap_segments(
        self,
        times: np.ndarray,
        normalized_signal: np.ndarray,
        total_duration: float,
    ) -> List[Dict[str, float]]:
        """
        Normalize edilmiş sinyali YouTube heatmap formatına dönüştürür:
        [{start_time, end_time, value}]
        """
        seg_dur = _SEGMENT_DURATION_SEC
        n_segments = max(1, int(total_duration / seg_dur))
        segments = []

        for i in range(n_segments):
            start = i * seg_dur
            end = min((i + 1) * seg_dur, total_duration)
            mid = (start + end) / 2.0

            # Bu segment için sinyal değerini bul (en yakın zaman noktası)
            if len(times) > 0:
                nearest_idx = int(np.argmin(np.abs(times - mid)))
                value = float(normalized_signal[nearest_idx])
            else:
                value = 0.0

            segments.append({
                "start_time": round(start, 1),
                "end_time": round(end, 1),
                "value": round(value, 4),
            })

        return segments

    def _compute_confidence(
        self, weights: Dict[str, float]
    ) -> tuple[float, str]:
        """
        Tahminin güven skorunu ve kaynağını hesaplar.

        Returns:
            (confidence: float 0-1, source: str)
        """
        if weights:
            # Korelasyon modeli kullanıldı
            return 0.65, "correlation_model"
        else:
            # Sadece ses proxy
            return 0.40, "audio_proxy"

    def _detect_hidden_viral_peaks(
        self,
        times: np.ndarray,
        normalized_signal: np.ndarray,
        view_count: int,
    ) -> List[Dict[str, Any]]:
        """
        Tahmini sinyalde gizli viral anları tespit eder.
        Koşul: düşük görüntü + yüksek tahmin değeri
        """
        if view_count > _HIDDEN_VIRAL_VIEW_THRESHOLD:
            return []

        peaks = []
        high_mask = normalized_signal >= _HIDDEN_VIRAL_HEATMAP_THRESHOLD

        # Bitişik yüksek değerli noktaları grupla
        in_peak = False
        peak_start_idx = 0
        for i, is_high in enumerate(high_mask):
            if is_high and not in_peak:
                in_peak = True
                peak_start_idx = i
            elif not is_high and in_peak:
                in_peak = False
                peak_slice = normalized_signal[peak_start_idx:i]
                peak_idx = peak_start_idx + int(np.argmax(peak_slice))
                peaks.append({
                    "time": round(float(times[peak_idx]), 1),
                    "score": round(float(normalized_signal[peak_idx]), 3),
                    "reason": (
                        f"Tahmini yüksek tekrar izleme anı "
                        f"(görüntü: {view_count:,}, tahmini değer: "
                        f"{normalized_signal[peak_idx]:.0%})"
                    ),
                })
        # Son grup kapanmadıysa
        if in_peak:
            peak_slice = normalized_signal[peak_start_idx:]
            peak_idx = peak_start_idx + int(np.argmax(peak_slice))
            peaks.append({
                "time": round(float(times[peak_idx]), 1),
                "score": round(float(normalized_signal[peak_idx]), 3),
                "reason": (
                    f"Tahmini yüksek tekrar izleme anı "
                    f"(görüntü: {view_count:,})"
                ),
            })

        peaks.sort(key=lambda x: x["score"], reverse=True)
        return peaks[:5]  # En fazla 5 adet
