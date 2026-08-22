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
        comments: Optional[List[Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fuses signals on a unified timeline, clusters peaks, and extracts Top-N candidates.
        Supports Audio Spikes, Silence-Burst, Heatmap (Real/Predicted), Transcripts,
        and YouTube Comment Mining with reaction detection.
        """

        if len(times) == 0:
            return []

        has_heatmap = len(heatmap) > 0
        n_points = len(times)
        predicted_confidence = 0.0
        hidden_viral_peaks: list = []

        # 1. Process Comments (if provided)
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
            except Exception:
                comment_curve = np.zeros(n_points)

        # 2. Process Transcript Density (if transcript provided)
        transcript_curve = np.zeros(n_points)
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
            except Exception:
                transcript_curve = np.zeros(n_points)

        # 3. Interpolate Heatmap onto audio timeline if present
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

        # 4. Weighted Score Fusion (Adaptive Multimodal)
        t_w = 0.15 if has_transcript_density else 0.0
        c_w = 0.15 if has_comments else 0.0

        if has_heatmap:
            rem = max(0.20, 1.0 - (0.30 + t_w + c_w))
            audio_w = rem * (0.40 / 0.70)
            silence_w = rem * (0.30 / 0.70)
            composite_score = (
                (audio_spikes * audio_w) +
                (silence_bursts * silence_w) +
                (heatmap_curve * 0.30) +
                (transcript_curve * t_w) +
                (comment_curve * c_w)
            )
        elif predicted_confidence > 0:
            h_w = 0.20 * predicted_confidence
            rem = max(0.30, 1.0 - (h_w + t_w + c_w))
            audio_w = rem * 0.55
            silence_w = rem * 0.45
            composite_score = (
                (audio_spikes * audio_w) +
                (silence_bursts * silence_w) +
                (heatmap_curve * h_w) +
                (transcript_curve * t_w) +
                (comment_curve * c_w)
            )
        else:
            rem = max(0.40, 1.0 - (t_w + c_w))
            audio_w = rem * 0.55
            silence_w = rem * 0.45
            composite_score = (
                (audio_spikes * audio_w) +
                (silence_bursts * silence_w) +
                (transcript_curve * t_w) +
                (comment_curve * c_w)
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
                    seg_start = float(seg.get("start", 0.0))
                    seg_end = float(seg.get("end", seg_start + float(seg.get("duration", 0.0))))
                    if seg_end >= start_t and seg_start <= end_t:
                        matching_text.append(seg.get("text", ""))

            transcript_snippet = " ".join(matching_text).strip()


            # Signal breakdown for Gemini inspection
            idx_near = int(np.argmin(np.abs(times - peak_t)))

            # Find matching comment cluster if any
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
                    "has_heatmap": has_heatmap,
                    "heatmap_val": round(float(heatmap_curve[idx_near]), 2),
                    "heatmap_source": "real" if has_heatmap else (
                        "predicted" if predicted_confidence > 0 else "none"
                    ),
                    "predicted_confidence": round(predicted_confidence, 2),
                    "comment_density": round(float(comment_curve[idx_near]), 2) if has_comments else 0.0,
                    "comment_reaction": matched_comment_cl.get("dominant_reaction") if matched_comment_cl else None,
                    "comment_count": matched_comment_cl.get("count", 0) if matched_comment_cl else 0,
                    "transcript_density": round(float(transcript_curve[idx_near]), 2) if has_transcript_density else 0.0,
                },
                "hidden_viral": any(
                    abs(hvp["time"] - peak_t) <= self.candidate_window_sec / 2.0
                    for hvp in hidden_viral_peaks
                ),
                "comment_samples": matched_comment_cl.get("samples", []) if matched_comment_cl else [],
                "transcript_snippet": transcript_snippet or "Ses/Tepki ağırlıklı an (Konuşma transkripti yok)"
            })

        # Attach global hidden_viral_peaks list to first candidate for reference
        if candidates and hidden_viral_peaks:
            candidates[0]["_hidden_viral_peaks"] = hidden_viral_peaks


        # Order candidates chronologically for readability
        candidates.sort(key=lambda x: x["start_time"])
        return candidates

