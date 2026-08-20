"""
core/scene_detector.py — Scene Cut Detection via FFmpeg

Detects scene boundaries in local video files using the FFmpeg ``scdet``
filter and provides a helper to snap arbitrary timestamps to the nearest
detected scene cut.
"""

from __future__ import annotations

import re
import subprocess
from typing import List

try:
    from core.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class SceneDetector:
    """Detects scene changes in video files and snaps timestamps to boundaries."""

    @staticmethod
    def detect_scenes(
        video_path: str,
        threshold: float = 30.0,
    ) -> List[float]:
        """Find scene-change timestamps in a local video file.

        Runs FFmpeg's ``scdet`` filter over the video stream (no audio
        decode) and parses the ``lavfi.scd.score`` metadata printed to
        stderr.  Only frame timestamps whose score meets the *threshold*
        are returned.

        Args:
            video_path: Absolute or relative path to the video file.
            threshold:  Scene-change sensitivity (0–100). Higher values
                        require more dramatic changes before registering a
                        cut.  Default 30.0 works well for gaming footage.

        Returns:
            Sorted list of scene-change timestamps in seconds (float).
            Returns an empty list if FFmpeg fails or no changes are found.

        Example::

            cuts = SceneDetector.detect_scenes("/tmp/clip.mp4", threshold=25.0)
            # [3.417, 12.083, 27.0, ...]
        """
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vf", f"scdet=threshold={threshold}",
            "-an",                   # skip audio decode
            "-f", "null",
            "-",
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,         # we parse output regardless of exit code
            )
            stderr_text = result.stderr.decode("utf-8", errors="replace")
        except FileNotFoundError:
            logger.error("FFmpeg bulunamadı. Lütfen kurulu olduğundan emin olun.")
            return []
        except Exception as exc:
            logger.error("scdet çalıştırma hatası: %s", exc)
            return []

        # FFmpeg scdet output lines look like:
        #   [Parsed_scdet_0 @ 0xADDR] lavfi.scd.score: 45.23, lavfi.scd.time: 12.083
        timestamps: List[float] = []
        pattern = re.compile(r"lavfi\.scd\.time:\s*([\d.]+)")

        for line in stderr_text.splitlines():
            match = pattern.search(line)
            if match:
                try:
                    timestamps.append(float(match.group(1)))
                except ValueError:
                    continue

        timestamps.sort()
        logger.info(
            "detect_scenes: %d sahne kesimi bulundu (eşik=%.1f, dosya=%s)",
            len(timestamps),
            threshold,
            video_path,
        )
        return timestamps

    @staticmethod
    def snap_to_scene_boundary(
        timestamp: float,
        scene_cuts: List[float],
        max_snap_sec: float = 2.0,
    ) -> float:
        """Snap *timestamp* to the nearest scene cut within *max_snap_sec*.

        If no scene cut falls within [timestamp - max_snap_sec,
        timestamp + max_snap_sec], the original *timestamp* is returned
        unchanged.

        Args:
            timestamp:    The candidate cut-point in seconds.
            scene_cuts:   List of detected scene-change timestamps (from
                          :meth:`detect_scenes`).
            max_snap_sec: Maximum distance (seconds) for snapping. Cuts
                          farther away are ignored.  Default 2.0 s.

        Returns:
            Snapped timestamp (float, same precision as inputs).

        Example::

            cuts = [3.4, 12.1, 27.0]
            SceneDetector.snap_to_scene_boundary(12.8, cuts, max_snap_sec=2.0)
            # 12.1  (within 2s window)
            SceneDetector.snap_to_scene_boundary(20.0, cuts, max_snap_sec=2.0)
            # 20.0  (no cut nearby)
        """
        if not scene_cuts:
            return timestamp

        # Find the nearest cut within the allowed window
        best_cut: float = timestamp
        best_dist: float = max_snap_sec  # exclusive upper bound

        for cut in scene_cuts:
            dist = abs(cut - timestamp)
            if dist < best_dist:
                best_dist = dist
                best_cut = cut

        # If we never beat max_snap_sec, best_cut remains timestamp
        if best_cut == timestamp and best_dist == max_snap_sec:
            return timestamp  # no nearby cut found

        logger.debug(
            "snap_to_scene_boundary: %.3f -> %.3f (Δ=%.3f s)",
            timestamp,
            best_cut,
            best_dist,
        )
        return best_cut
