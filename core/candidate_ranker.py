import numpy as np
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from core.extractor import YouTubeExtractor

if TYPE_CHECKING:
    from core.database import DatabaseManager


class CandidateRanker:
    """Combines multimodal signals (Audio Spikes, Silence-Burst, Heatmap, Transcripts) into Top-N Candidates."""

    def __init__(
        self,
        candidate_window_sec: int = 35,
        merge_threshold_sec: int = 8,
        top_n: int = 15,
        db: Optional["DatabaseManager"] = None,
    ):
        self.candidate_window_sec = candidate_window_sec
        self.merge_threshold_sec = merge_threshold_sec
        self.top_n = top_n
        self._db = db

    def fuse_signals_and_generate_candidates(
        self,
        times: np.ndarray,
        audio_spikes: np.ndarray,
        silence_bursts: np.ndarray,
        heatmap: List[Dict[str, float]],
        transcript: List[Dict[str, Any]],
        total_duration: int,
        video_id: Optional[str] = None,
        view_count: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Fuses signals on a unified timeline, clusters peaks, and extracts Top-N candidates.
        When no real heatmap is available and a DB is provided, uses HeatmapPredictor
        to generate a predicted heatmap curve.
        """

        if len(times) == 0:
            return []

        has_heatmap = len(heatmap) > 0
        n_points = len(times)
        predicted_confidence = 0.0
        hidden_viral_peaks: list = []

        # 1. Interpolate Heatmap onto audio timeline if present
        heatmap_curve = np.zeros(n_points)
        if has_heatmap:
            h_times = np.array([(p["start_time"] + p["end_time"]) / 2.0 for p in heatmap])
            h_vals = np.array([p["value"] for p in heatmap])
            if len(h_times) > 0:
                heatmap_curve = np.interp(times, h_times, h_vals, left=0.0, right=0.0)

            # Gizli viral tespiti (gerçek heatmap varken de çalışır)
            if self._db is not None and view_count > 0:
                try:
                    from core.heatmap_predictor import HeatmapPredictor
                    predictor = HeatmapPredictor(self._db)
                    hidden_viral_peaks = predictor.detect_hidden_viral_from_real(
                        heatmap, view_count
                    )
                except Exception:
                    pass

        elif self._db is not None:
            # Heatmap yok → HeatmapPredictor ile tahmin et
            try:
                from core.heatmap_predictor import HeatmapPredictor
                predictor = HeatmapPredictor(self._db)
                prediction = predictor.predict(
                    audio_times=times,
                    audio_spikes=audio_spikes,
                    silence_bursts=silence_bursts,
                    total_duration=float(total_duration),
                    video_id=video_id,
                    view_count=view_count,
                )
                pred_heatmap = prediction["heatmap"]
                predicted_confidence = prediction["confidence"]
                hidden_viral_peaks = prediction["hidden_viral_peaks"]

                if pred_heatmap:
                    ph_times = np.array(
                        [(p["start_time"] + p["end_time"]) / 2.0 for p in pred_heatmap]
                    )
                    ph_vals = np.array([p["value"] for p in pred_heatmap])
                    heatmap_curve = np.interp(times, ph_times, ph_vals, left=0.0, right=0.0)
            except Exception:
                heatmap_curve = np.zeros(n_points)

        # 2. Weighted Score Fusion
        if has_heatmap:
            # Gerçek heatmap: tam ağırlık
            composite_score = (
                (audio_spikes * 0.40) +
                (silence_bursts * 0.30) +
                (heatmap_curve * 0.30)
            )
        elif predicted_confidence > 0:
            # Tahmini heatmap: confidence ile ölçeklendirilmiş ağırlık
            heatmap_weight = 0.30 * predicted_confidence   # max 0.195
            audio_weight = 0.55 + (0.30 - heatmap_weight) * 0.55
            silence_weight = 0.45 + (0.30 - heatmap_weight) * 0.45
            total_w = audio_weight + silence_weight + heatmap_weight
            composite_score = (
                (audio_spikes * audio_weight / total_w) +
                (silence_bursts * silence_weight / total_w) +
                (heatmap_curve * heatmap_weight / total_w)
            )
        else:
            # Sadece ses sinyalleri
            composite_score = (
                (audio_spikes * 0.55) +
                (silence_bursts * 0.45)
            )


        # 3. Peak Finding & Cluster Merging
        # Filter points above threshold (e.g. 0.25)
        candidate_indices = np.where(composite_score > 0.20)[0]
        if len(candidate_indices) == 0:
            # Fallback to top indices
            candidate_indices = np.argsort(composite_score)[::-1][:self.top_n]

        # Group close peaks
        clusters = []
        for idx in candidate_indices:
            t = times[idx]
            score = float(composite_score[idx])
            
            # Check if can merge into existing cluster
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
                clusters.append({
                    "peak_time": t,
                    "score": score,
                    "indices": [idx]
                })

        # 4. Sort clusters by score descending
        clusters.sort(key=lambda x: x["score"], reverse=True)
        selected_clusters = clusters[:self.top_n]

        # 5. Build candidate objects with time windows and transcripts
        candidates = []
        half_win = self.candidate_window_sec / 2.0

        for cand_id, clus in enumerate(selected_clusters, start=1):
            peak_t = clus["peak_time"]
            start_t = max(0.0, peak_t - half_win)
            end_t = min(float(total_duration), peak_t + half_win)

            # Extract matching transcript text if available
            matching_text = []
            if transcript:
                for seg in transcript:
                    if seg["end"] >= start_t and seg["start"] <= end_t:
                        matching_text.append(seg["text"])

            transcript_snippet = " ".join(matching_text).strip()

            # Signal breakdown for Gemini inspection
            idx_near = np.argmin(np.abs(times - peak_t))
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
                    "has_heatmap": has_heatmap,
                    "heatmap_val": round(float(heatmap_curve[idx_near]), 2),
                    "heatmap_source": "real" if has_heatmap else (
                        "predicted" if predicted_confidence > 0 else "none"
                    ),
                    "predicted_confidence": round(predicted_confidence, 2),
                },
                "hidden_viral": any(
                    abs(hvp["time"] - peak_t) <= self.candidate_window_sec / 2.0
                    for hvp in hidden_viral_peaks
                ),
                "transcript_snippet": transcript_snippet or "Ses/Tepki ağırlıklı an (Konuşma transkripti yok)"
            })

        # Attach global hidden_viral_peaks list to first candidate for reference
        if candidates and hidden_viral_peaks:
            candidates[0]["_hidden_viral_peaks"] = hidden_viral_peaks

        # Order candidates chronologically for readability
        candidates.sort(key=lambda x: x["start_time"])
        return candidates

