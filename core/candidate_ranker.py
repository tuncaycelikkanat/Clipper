import numpy as np
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from loguru import logger

from core.extractor import YouTubeExtractor

if TYPE_CHECKING:
    from core.database import DatabaseManager


def _zscore_normalize(arr: np.ndarray) -> np.ndarray:
    """Z-score normalize et, ardından 0-1 aralığına clip et.

    Video-bazında normalizasyon: her sinyali kendi dağılımına göre ölçekler.
    Heatmap sinyali gibi dışarıdan gelen mutlak sayıların ağırlığını dengeler.
    """
    if len(arr) == 0:
        return arr
    median = np.median(arr)
    std = np.std(arr) + 1e-9
    normalized = (arr - median) / std
    # 0-1 sıkıştır: negatif → 0, z≥3 → 1.0
    return np.clip(normalized / 3.0, 0.0, 1.0)


class CandidateRanker:
    """Combines multimodal signals (Audio Spikes, Silence-Burst, Transcripts, Visual, Pitch) into Top-N Candidates."""

    def __init__(
        self,
        candidate_window_sec: int = 35,
        merge_threshold_sec: int = 8,
        top_n: int = 15,
        db: Optional["DatabaseManager"] = None,
        min_diversity_ratio: float = 0.10,
        dynamic_window: bool = True,
        min_window_sec: float = 8.0,
        max_window_sec: float = 60.0,
    ):
        self.candidate_window_sec = candidate_window_sec
        self.merge_threshold_sec = merge_threshold_sec
        self.top_n = top_n
        self._db = db
        # Çeşitlilik kısıtı: iki aday en az video süresinin bu oranı kadar uzakta olmalı
        self.min_diversity_ratio = min_diversity_ratio
        # Dinamik pencere: sabit 35sn yerine sinyal eğrisine göre pencere belirle
        self.dynamic_window = dynamic_window
        self.min_window_sec = min_window_sec
        self.max_window_sec = max_window_sec

    def fuse_signals_and_generate_candidates(
        self,
        times: np.ndarray,
        audio_spikes: np.ndarray,
        silence_bursts: np.ndarray,
        heatmap: List[Dict[str, float]],  # ARTIK KULLANILMIYOR — parametre uyum için tutuldu
        transcript: List[Dict[str, Any]],
        total_duration: int,
        video_id: Optional[str] = None,
        view_count: int = 0,
        comments: Optional[List[Any]] = None,
        pitch_variance: Optional[np.ndarray] = None,
        frame_diff: Optional[np.ndarray] = None,
    ) -> List[Dict[str, Any]]:
        """
        Tüm sinyalleri tek bir bileşik skora kaynaştırır ve Top-N aday klip üretir.

        Değişiklikler (v2):
        - Heatmap sinyali füzyondan çıkarıldı (yeni videolarda veri yok).
        - Her sinyal video-bazında z-score ile normalize edilir.
        - Pitch variance (ZCR tabanlı) ve frame-diff sinyalleri eklendi.
        - Konuşma hızı ivmesi (speech_rate_accel) eklendi.
        - Aday havuzuna çeşitlilik kısıtı eklendi.
        - Dinamik pencere: sinyal baseline'a dönüş noktasına göre pencere belirlenir.
        """

        if len(times) == 0:
            return []

        n_points = len(times)

        # ----------------------------------------------------------------
        # 1. Yorumları İşle
        # ----------------------------------------------------------------
        comment_curve = np.zeros(n_points)
        comment_clusters: List[Dict[str, Any]] = []
        has_comments = False
        if comments:
            try:
                from core.comment_miner import CommentMiner
                miner = CommentMiner()
                comment_res = miner.process_comments(
                    comments=comments,
                    total_duration=float(total_duration),
                    timeline_times=times,
                )
                comment_curve = comment_res.get("comment_signal", np.zeros(n_points))
                comment_clusters = comment_res.get("timestamp_clusters", [])
                has_comments = len(comment_clusters) > 0
            except Exception as e:
                logger.debug("Comment mining failed, using zero signal: {}", e)
                comment_curve = np.zeros(n_points)

        # ----------------------------------------------------------------
        # 2. Transkript Yoğunluğu + Konuşma Hızı İvmesi
        # ----------------------------------------------------------------
        transcript_curve = np.zeros(n_points)
        speech_rate_curve = np.zeros(n_points)
        has_transcript_density = False
        if transcript:
            try:
                from core.transcript_density import TranscriptDensityAnalyzer
                t_analyzer = TranscriptDensityAnalyzer()
                transcript_curve = t_analyzer.compute_density_curve(
                    transcript_segments=transcript,
                    timeline_times=times,
                    total_duration=float(total_duration),
                )
                has_transcript_density = bool(np.any(transcript_curve > 0.05))

                speech_rate_curve = t_analyzer.compute_speech_rate_acceleration(
                    transcript_segments=transcript,
                    timeline_times=times,
                    total_duration=float(total_duration),
                )
            except Exception as e:
                logger.debug("Transcript/speech-rate analysis failed, using zero signal: {}", e)
                transcript_curve = np.zeros(n_points)
                speech_rate_curve = np.zeros(n_points)

        # ----------------------------------------------------------------
        # 3. Heatmap — DEVRE DIŞI (yeni videolarda veri yok)
        # (parametre geriye-uyum için kabul edilir ama skor füzyonuna katılmaz)
        # ----------------------------------------------------------------
        # Gizli viral tespit DB'ye bağımlı; hafif opsiyonel devam.
        hidden_viral_peaks: list = []
        if self._db is not None and view_count > 0 and len(heatmap) > 0:
            try:
                from core.heatmap_predictor import HeatmapPredictor
                predictor = HeatmapPredictor(self._db)
                hidden_viral_peaks = predictor.detect_hidden_viral_from_real(
                    heatmap, view_count
                )
            except Exception as e:
                logger.debug("Hidden viral detection skipped: {}", e)

        # ----------------------------------------------------------------
        # 4. Pitch Variance & Frame-Diff — timeline'a interpolate et
        # ----------------------------------------------------------------
        pitch_curve = np.zeros(n_points)
        if pitch_variance is not None and len(pitch_variance) > 0:
            if len(pitch_variance) == n_points:
                pitch_curve = pitch_variance
            else:
                # Farklı uzunluktaysa lineer interpolasyon
                pv_times = np.linspace(float(times[0]), float(times[-1]), len(pitch_variance))
                pitch_curve = np.interp(times, pv_times, pitch_variance, left=0.0, right=0.0)

        frame_diff_curve = np.zeros(n_points)
        if frame_diff is not None and len(frame_diff) > 0:
            if len(frame_diff) == n_points:
                frame_diff_curve = frame_diff
            else:
                fd_times = np.linspace(float(times[0]), float(times[-1]), len(frame_diff))
                frame_diff_curve = np.interp(times, fd_times, frame_diff, left=0.0, right=0.0)

        has_pitch = bool(np.any(pitch_curve > 0.05))
        has_frame_diff = bool(np.any(frame_diff_curve > 0.05))

        # ----------------------------------------------------------------
        # 5. Video-bazında Z-score normalizasyon (her sinyal kendi dağılımına göre)
        # ----------------------------------------------------------------
        audio_norm = _zscore_normalize(audio_spikes)
        silence_norm = _zscore_normalize(silence_bursts)
        transcript_norm = _zscore_normalize(transcript_curve) if has_transcript_density else transcript_curve
        comment_norm = _zscore_normalize(comment_curve) if has_comments else comment_curve
        speech_norm = _zscore_normalize(speech_rate_curve) if np.any(speech_rate_curve > 0) else speech_rate_curve
        pitch_norm = _zscore_normalize(pitch_curve) if has_pitch else pitch_curve
        fdiff_norm = _zscore_normalize(frame_diff_curve) if has_frame_diff else frame_diff_curve

        # ----------------------------------------------------------------
        # 6. Adaptif Ağırlık Füzyonu (Heatmap yok, 7 sinyal)
        # ----------------------------------------------------------------
        # Sinyal varlığına göre ağırlıklar dinamik olarak ayarlanır.
        # Temel ağırlık: audio %35, silence %30 (en güvenilir çekirdek sinyaller)
        # Opsiyonel: transcript, comment, speech_rate, pitch, frame_diff

        base_audio_w = 0.35
        base_silence_w = 0.30
        # Kalan %35'i mevcut opsiyonel sinyallere dağıt
        optional_signals = []
        if has_transcript_density:
            optional_signals.append(("transcript", transcript_norm, 0.12))
        if has_comments:
            optional_signals.append(("comment", comment_norm, 0.10))
        if np.any(speech_rate_curve > 0):
            optional_signals.append(("speech_rate", speech_norm, 0.08))
        if has_pitch:
            optional_signals.append(("pitch", pitch_norm, 0.08))
        if has_frame_diff:
            optional_signals.append(("frame_diff", fdiff_norm, 0.07))

        opt_total_w = sum(w for _, _, w in optional_signals)
        remaining = 1.0 - (base_audio_w + base_silence_w)
        if opt_total_w > 0:
            scale = min(1.0, remaining / opt_total_w)
        else:
            scale = 1.0
            # Opsiyonel sinyal yoksa fazla ağırlığı çekirdeğe ekle
            base_audio_w += remaining * 0.55
            base_silence_w += remaining * 0.45

        composite_score = (audio_norm * base_audio_w) + (silence_norm * base_silence_w)
        for _, arr, w in optional_signals:
            composite_score = composite_score + arr * (w * scale)

        # ----------------------------------------------------------------
        # 7. Peak Bulma & Cluster Birleştirme
        # ----------------------------------------------------------------
        candidate_indices = np.where(composite_score > 0.20)[0]
        if len(candidate_indices) == 0:
            # Fallback: en iyi N noktayı al
            candidate_indices = np.argsort(composite_score)[::-1][:self.top_n]

        clusters = []
        for idx in candidate_indices:
            t = times[idx]
            score = float(composite_score[idx])
            merged = False
            for c in clusters:
                if abs(t - c["peak_time"]) <= self.merge_threshold_sec:
                    if score > c["score"]:
                        c["peak_time"] = t
                        c["score"] = score
                    c["indices"].append(idx)
                    merged = True
                    break
            if not merged:
                clusters.append({"peak_time": t, "score": score, "indices": [idx]})

        # ----------------------------------------------------------------
        # 8. Çeşitlilik Kısıtı — art arda yakın adayları eleştir
        # ----------------------------------------------------------------
        clusters.sort(key=lambda x: x["score"], reverse=True)
        min_gap_sec = float(total_duration) * self.min_diversity_ratio
        min_gap_sec = max(min_gap_sec, float(self.merge_threshold_sec) * 2)

        diverse_clusters = []
        for clu in clusters:
            too_close = any(
                abs(clu["peak_time"] - accepted["peak_time"]) < min_gap_sec
                for accepted in diverse_clusters
            )
            if not too_close:
                diverse_clusters.append(clu)
            if len(diverse_clusters) >= self.top_n:
                break

        selected_clusters = diverse_clusters

        # ----------------------------------------------------------------
        # 9. Aday nesneleri oluştur (Dinamik Pencere dahil)
        # ----------------------------------------------------------------
        candidates = []
        half_win_default = self.candidate_window_sec / 2.0

        for cand_id, clus in enumerate(selected_clusters, start=1):
            peak_t = clus["peak_time"]

            # --- Dinamik Pencere: sinyal baseline'a dönüş noktasını bul ---
            if self.dynamic_window and len(times) > 1:
                idx_peak = int(np.argmin(np.abs(times - peak_t)))
                baseline = float(np.median(composite_score))

                # Başlangıç: geriye git, sinyal baseline altına düşene kadar
                win_start_idx = idx_peak
                for j in range(idx_peak - 1, -1, -1):
                    if composite_score[j] <= baseline:
                        win_start_idx = j
                        break

                # Bitiş: ileriye git, sinyal baseline altına düşene kadar
                win_end_idx = idx_peak
                for j in range(idx_peak + 1, len(times)):
                    if composite_score[j] <= baseline:
                        win_end_idx = j
                        break

                dyn_start = float(times[win_start_idx])
                dyn_end = float(times[win_end_idx])
                dyn_half = (dyn_end - dyn_start) / 2.0

                # Min/max sınırları uygula
                dyn_half = np.clip(dyn_half, self.min_window_sec / 2.0, self.max_window_sec / 2.0)
                half_win = float(dyn_half)
            else:
                half_win = half_win_default

            start_t = max(0.0, peak_t - half_win)
            end_t = min(float(total_duration), peak_t + half_win)

            # Minimum klip süresi garantisi
            if (end_t - start_t) < self.min_window_sec:
                extra = (self.min_window_sec - (end_t - start_t)) / 2.0
                start_t = max(0.0, start_t - extra)
                end_t = min(float(total_duration), end_t + extra)

            # Transkript metni
            matching_text = []
            if transcript:
                for seg in transcript:
                    seg_start = float(seg.get("start", 0.0))
                    seg_end = float(seg.get("end", seg_start + float(seg.get("duration", 0.0))))
                    if seg_end >= start_t and seg_start <= end_t:
                        matching_text.append(seg.get("text", ""))
            transcript_snippet = " ".join(matching_text).strip()

            idx_near = int(np.argmin(np.abs(times - peak_t)))

            # Yorum kümesi eşleştir
            matched_comment_cl = None
            for cl in comment_clusters:
                if abs(cl["time"] - peak_t) <= half_win:
                    matched_comment_cl = cl
                    break

            candidates.append({
                "candidate_id": cand_id,
                "peak_time": round(float(peak_t), 1),
                "peak_formatted": YouTubeExtractor.format_seconds(peak_t),
                "start_time": round(float(start_t), 1),
                "start_formatted": YouTubeExtractor.format_seconds(start_t),
                "end_time": round(float(end_t), 1),
                "end_formatted": YouTubeExtractor.format_seconds(end_t),
                "duration": round(float(end_t - start_t), 1),
                "fusion_score": int(clus["score"] * 100),
                "signals": {
                    "audio_spike": round(float(audio_spikes[idx_near]), 2),
                    "silence_burst": round(float(silence_bursts[idx_near]), 2),
                    "has_heatmap": False,  # Heatmap kaldırıldı
                    "heatmap_val": 0.0,
                    "heatmap_source": "disabled",
                    "predicted_confidence": 0.0,
                    "comment_density": round(float(comment_curve[idx_near]), 2) if has_comments else 0.0,
                    "comment_reaction": matched_comment_cl.get("dominant_reaction") if matched_comment_cl else None,
                    "comment_count": matched_comment_cl.get("count", 0) if matched_comment_cl else 0,
                    "transcript_density": round(float(transcript_curve[idx_near]), 2) if has_transcript_density else 0.0,
                    "speech_rate_accel": round(float(speech_rate_curve[idx_near]), 2),
                    "pitch_variance": round(float(pitch_curve[idx_near]), 2),
                    "frame_diff": round(float(frame_diff_curve[idx_near]), 2),
                },
                "hidden_viral": any(
                    abs(hvp["time"] - peak_t) <= half_win
                    for hvp in hidden_viral_peaks
                ),
                "comment_samples": matched_comment_cl.get("samples", []) if matched_comment_cl else [],
                "transcript_snippet": transcript_snippet or "Ses/Tepki ağırlıklı an (Konuşma transkripti yok)"
            })

        # Kronolojik sırayla döndür
        candidates.sort(key=lambda x: x["start_time"])
        return candidates
