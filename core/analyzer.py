from typing import List, Dict, Any, Optional
import numpy as np
from scipy.signal import find_peaks
from core.extractor import YouTubeExtractor
from core.transcript import TranscriptManager

class HeatmapAnalyzer:
    """Analyzes YouTube Most Replayed heatmap to detect optimal viral/replayed clip segments."""

    def __init__(
        self,
        min_clip_duration: int = 30,
        max_clip_duration: int = 60,
        min_distance_sec: int = 90,
        target_clips: int = 3,
        auto_snap_transcript: bool = True
    ):
        self.min_clip_duration = min_clip_duration
        self.max_clip_duration = max_clip_duration
        self.min_distance_sec = min_distance_sec
        self.target_clips = target_clips
        self.auto_snap_transcript = auto_snap_transcript

    def analyze(
        self,
        heatmap: List[Dict[str, float]],
        total_duration: int,
        transcript_segments: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyzes the heatmap and returns the top clips with boundaries, scores, and optional transcript text.
        """
        if not heatmap:
            return []

        # Convert to numpy arrays
        times = np.array([(p["start_time"] + p["end_time"]) / 2.0 for p in heatmap])
        values = np.array([p["value"] for p in heatmap])

        if len(times) == 0:
            return []

        # Estimate average time interval between heatmap points
        dt = (times[-1] - times[0]) / max(1, len(times) - 1) if len(times) > 1 else 1.0
        min_dist_points = max(1, int(self.min_distance_sec / max(dt, 0.1)))

        # Find peaks with prominence
        peaks, properties = find_peaks(values, distance=min_dist_points, prominence=0.03)

        # Fallback if too few peaks found
        if len(peaks) < self.target_clips:
            peaks, properties = find_peaks(values, distance=max(1, min_dist_points // 2), prominence=0.01)

        if len(peaks) < self.target_clips:
            # Fallback to top value points respecting minimum distance
            sorted_indices = np.argsort(values)[::-1]
            selected = []
            for idx in sorted_indices:
                if all(abs(times[idx] - times[p]) >= (self.min_distance_sec // 2) for p in selected):
                    selected.append(idx)
                if len(selected) >= self.target_clips:
                    break
            peaks = np.array(selected)

        # Calculate scores for candidate peaks
        scored_peaks = []
        for p_idx in peaks:
            val = values[p_idx]
            prom = 0.0
            if "prominences" in properties and len(properties["prominences"]) > 0:
                match_indices = np.where(peaks == p_idx)[0]
                if len(match_indices) > 0 and match_indices[0] < len(properties["prominences"]):
                    prom = float(properties["prominences"][match_indices[0]])
            
            score = (float(val) * 0.7) + (prom * 0.3)
            score_100 = min(100, max(1, int(score * 100)))
            scored_peaks.append({
                "peak_index": p_idx,
                "peak_time": float(times[p_idx]),
                "intensity": float(val),
                "prominence": float(prom),
                "score": score_100
            })

        # Sort by score descending and take top target_clips
        scored_peaks.sort(key=lambda x: x["score"], reverse=True)
        top_candidates = scored_peaks[:self.target_clips]

        # Generate clip boundaries
        clips = []
        for rank, cand in enumerate(top_candidates, start=1):
            peak_time = cand["peak_time"]
            half_win = self.min_clip_duration / 2.0
            
            start = max(0.0, peak_time - half_win)
            end = min(float(total_duration), peak_time + half_win)

            if start == 0.0:
                end = min(float(total_duration), float(self.min_clip_duration))
            elif end == float(total_duration):
                start = max(0.0, float(total_duration) - self.min_clip_duration)

            snippet_text = ""
            # If transcript is available and auto_snap is enabled, snap to sentence boundaries
            if self.auto_snap_transcript and transcript_segments:
                start, end, snippet_text = TranscriptManager.snap_boundaries(
                    start,
                    end,
                    transcript_segments
                )

            duration = round(end - start, 1)

            clips.append({
                "rank": rank,
                "score": cand["score"],
                "intensity": round(cand["intensity"] * 100, 1),
                "peak_time": round(peak_time, 1),
                "peak_formatted": YouTubeExtractor.format_seconds(peak_time),
                "start_time": round(start, 1),
                "start_formatted": YouTubeExtractor.format_seconds(start),
                "end_time": round(end, 1),
                "end_formatted": YouTubeExtractor.format_seconds(end),
                "duration": duration,
                "duration_formatted": f"{int(duration)} sn",
                "text": snippet_text
            })

        # Order clips chronologically by start_time
        clips.sort(key=lambda c: c["start_time"])
        return clips
