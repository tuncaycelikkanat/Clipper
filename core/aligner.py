import numpy as np
from typing import List, Dict, Any, Tuple
from core.transcript import TranscriptManager

class AlignmentEngine:
    """Refines candidate clip boundaries using audio energy minimums and transcript sentence boundaries."""

    @staticmethod
    def refine_cut_points(
        start_time: float,
        end_time: float,
        times: np.ndarray,
        rms: np.ndarray,
        transcript: List[Dict[str, Any]],
        max_drift_sec: float = 3.0
    ) -> Tuple[float, float]:
        """
        Cross-validates boundaries with transcript and audio energy dips (silences).
        """
        # 1. First priority: Sentence boundary snapping if transcript exists
        if transcript:
            snapped_start, snapped_end, _ = TranscriptManager.snap_boundaries(
                start_time, end_time, transcript, max_snap_sec=max_drift_sec + 2.0
            )
            return snapped_start, snapped_end

        # 2. Second priority: Find local audio energy minimum around boundaries
        if len(times) == 0 or len(rms) == 0:
            return round(start_time, 1), round(end_time, 1)

        # Refine start: look within [start_time - max_drift, start_time + max_drift] for lowest RMS
        start_mask = (times >= start_time - max_drift_sec) & (times <= start_time + max_drift_sec)
        refined_start = start_time
        if np.any(start_mask):
            min_idx = np.where(start_mask)[0][np.argmin(rms[start_mask])]
            refined_start = float(times[min_idx])

        # Refine end: look within [end_time - max_drift, end_time + max_drift] for lowest RMS
        end_mask = (times >= end_time - max_drift_sec) & (times <= end_time + max_drift_sec)
        refined_end = end_time
        if np.any(end_mask):
            min_idx = np.where(end_mask)[0][np.argmin(rms[end_mask])]
            refined_end = float(times[min_idx])

        # Safety check
        if refined_end <= refined_start or (refined_end - refined_start) < 10.0:
            refined_start = start_time
            refined_end = end_time

        return round(refined_start, 1), round(refined_end, 1)
