import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from core.transcript import TranscriptManager

try:
    from core.scene_detector import SceneDetector
    _SCENE_DETECTOR_AVAILABLE = True
except ImportError:
    _SCENE_DETECTOR_AVAILABLE = False


class AlignmentEngine:
    """Refines candidate clip boundaries using scene cuts, transcript sentence
    boundaries, and audio energy minimums.

    Priority order (highest first):
    1. Scene cut boundaries (if *scene_cuts* provided).
    2. Transcript sentence boundaries (if transcript available).
    3. Audio energy dip (lowest RMS within drift window).
    """

    @staticmethod
    def refine_cut_points(
        start_time: float,
        end_time: float,
        times: np.ndarray,
        rms: np.ndarray,
        transcript: List[Dict[str, Any]],
        max_drift_sec: float = 3.0,
        scene_cuts: Optional[List[float]] = None,
    ) -> Tuple[float, float]:
        """Cross-validates boundaries with scene cuts, transcript, and audio dips.

        Args:
            start_time:    Candidate clip start (seconds).
            end_time:      Candidate clip end (seconds).
            times:         Audio time array from AudioDSPAnalyzer.
            rms:           Normalised RMS energy array.
            transcript:    YouTube ASR transcript segments.
            max_drift_sec: Maximum seconds the boundary may shift (default 3.0).
            scene_cuts:    Optional list of detected scene-change timestamps from
                           :class:`~core.scene_detector.SceneDetector`.  When
                           provided, scene boundaries are preferred over audio dips.

        Returns:
            Tuple of (refined_start, refined_end) in seconds.
        """
        # 1. First priority: Scene cut snapping
        if scene_cuts and _SCENE_DETECTOR_AVAILABLE:
            snapped_start = SceneDetector.snap_to_scene_boundary(
                start_time, scene_cuts, max_snap_sec=max_drift_sec
            )
            snapped_end = SceneDetector.snap_to_scene_boundary(
                end_time, scene_cuts, max_snap_sec=max_drift_sec
            )
            # Only use scene boundaries if they produce a valid clip duration
            if snapped_end > snapped_start and (snapped_end - snapped_start) >= 10.0:
                return round(snapped_start, 1), round(snapped_end, 1)

        # 2. Second priority: Sentence boundary snapping if transcript exists
        if transcript:
            snapped_start, snapped_end, _ = TranscriptManager.snap_boundaries(
                start_time, end_time, transcript, max_snap_sec=max_drift_sec + 2.0
            )
            return snapped_start, snapped_end

        # 3. Third priority: Find local audio energy minimum around boundaries
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
