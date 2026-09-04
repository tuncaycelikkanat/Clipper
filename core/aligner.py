from typing import Any

import numpy as np

from core.transcript import TranscriptManager

try:
    from core.scene_detector import SceneDetector

    _SCENE_DETECTOR_AVAILABLE = True
except ImportError:
    _SCENE_DETECTOR_AVAILABLE = False


class AlignmentEngine:
    """Refines candidate clip boundaries using scene cuts, frame-diff peaks,
    transcript sentence boundaries, and audio energy minimums.

    Priority order (highest first):
    1. Scene cut boundaries (if *scene_cuts* provided).
    2. Frame-diff visual scene boundaries (if *frame_diff_times* / *frame_diff_scores* provided).
    3. Transcript sentence boundaries (if transcript available).
    4. Audio energy dip (lowest RMS within drift window).
    """

    @staticmethod
    def refine_cut_points(
        start_time: float,
        end_time: float,
        times: np.ndarray,
        rms: np.ndarray,
        transcript: list[dict[str, Any]],
        max_drift_sec: float = 3.0,
        scene_cuts: list[float] | None = None,
        frame_diff_times: np.ndarray | None = None,
        frame_diff_scores: np.ndarray | None = None,
    ) -> tuple[float, float]:
        """Cross-validates boundaries with scene cuts, frame-diff, transcript, and audio dips.

        Args:
            start_time:         Candidate clip start (seconds).
            end_time:           Candidate clip end (seconds).
            times:              Audio time array from AudioDSPAnalyzer.
            rms:                Normalised RMS energy array.
            transcript:         YouTube ASR transcript segments.
            max_drift_sec:      Maximum seconds the boundary may shift (default 3.0).
            scene_cuts:         Optional list of detected scene-change timestamps from
                                :class:`~core.scene_detector.SceneDetector`.
            frame_diff_times:   Optional time axis from VisualDSPAnalyzer.extract_frame_diff().
            frame_diff_scores:  Optional frame-diff score array (0-1). Scene change peaks
                                are used as additional snapping candidates when *scene_cuts*
                                is not available.

        Returns:
            Tuple of (refined_start, refined_end) in seconds.
        """
        # 1. First priority: SceneDetector hard cuts
        if scene_cuts and _SCENE_DETECTOR_AVAILABLE:
            snapped_start = SceneDetector.snap_to_scene_boundary(start_time, scene_cuts, max_snap_sec=max_drift_sec)
            snapped_end = SceneDetector.snap_to_scene_boundary(end_time, scene_cuts, max_snap_sec=max_drift_sec)
            if snapped_end > snapped_start and (snapped_end - snapped_start) >= 10.0:
                return round(snapped_start, 1), round(snapped_end, 1)

        # 2. Second priority: Frame-diff visual scene boundary snapping
        if (
            frame_diff_times is not None
            and frame_diff_scores is not None
            and len(frame_diff_times) > 0
            and len(frame_diff_scores) > 0
        ):
            refined_start, refined_end = AlignmentEngine._snap_to_frame_diff(
                start_time, end_time, frame_diff_times, frame_diff_scores, max_drift_sec
            )
            if refined_end > refined_start and (refined_end - refined_start) >= 10.0:
                return round(refined_start, 1), round(refined_end, 1)

        # 3. Third priority: Sentence boundary snapping
        if transcript:
            snapped_start, snapped_end, _ = TranscriptManager.snap_boundaries(
                start_time, end_time, transcript, max_snap_sec=max_drift_sec + 2.0
            )
            return snapped_start, snapped_end

        # 4. Fourth priority: Local audio energy minimum
        if len(times) == 0 or len(rms) == 0:
            return round(start_time, 1), round(end_time, 1)

        start_mask = (times >= start_time - max_drift_sec) & (times <= start_time + max_drift_sec)
        refined_start = start_time
        if np.any(start_mask):
            min_idx = np.where(start_mask)[0][np.argmin(rms[start_mask])]
            refined_start = float(times[min_idx])

        end_mask = (times >= end_time - max_drift_sec) & (times <= end_time + max_drift_sec)
        refined_end = end_time
        if np.any(end_mask):
            min_idx = np.where(end_mask)[0][np.argmin(rms[end_mask])]
            refined_end = float(times[min_idx])

        if refined_end <= refined_start or (refined_end - refined_start) < 10.0:
            refined_start = start_time
            refined_end = end_time

        return round(refined_start, 1), round(refined_end, 1)

    @staticmethod
    def _snap_to_frame_diff(
        start_time: float,
        end_time: float,
        fd_times: np.ndarray,
        fd_scores: np.ndarray,
        max_drift_sec: float,
    ) -> tuple[float, float]:
        """Frame-diff skor dizisindeki local maxima'ya en yakın sınır noktasını bulur.

        Yüksek frame-diff = sahne değişimi = ideal klip başlangıcı/bitişi.
        """

        # Sınır etrafındaki pencerede en yüksek frame-diff zirvesini bul
        def _find_best_snap(boundary: float) -> float:
            mask = (fd_times >= boundary - max_drift_sec) & (fd_times <= boundary + max_drift_sec)
            if not np.any(mask):
                return boundary
            local_times = fd_times[mask]
            local_scores = fd_scores[mask]
            best_idx = np.argmax(local_scores)
            # Eşik: en az 0.25 — düşük değişimler sınırı kaydırmasın
            if local_scores[best_idx] >= 0.25:
                return float(local_times[best_idx])
            return boundary

        snapped_start = _find_best_snap(start_time)
        snapped_end = _find_best_snap(end_time)
        return snapped_start, snapped_end
