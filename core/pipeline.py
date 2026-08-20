"""Headless batch pipeline for the clipper project.

Runs the full 5-layer pipeline without any Streamlit dependency:

    Extract → AudioDSP → CandidateRank → LLM → Align → Cut

Usage::

    from core.pipeline import ClipperPipeline

    paths = ClipperPipeline.run(
        url="https://youtu.be/dQw4w9WgXcQ",
        target_clips=3,
        render_mode="square_1x1_black",
    )
    for p in paths:
        print(p)
"""

import os
from typing import Any, Dict, List, Optional

from core.aligner import AlignmentEngine
from core.audio_dsp import AudioDSPAnalyzer
from core.candidate_ranker import CandidateRanker
from core.cutter import VideoCutter
from core.database import DatabaseManager
from core.extractor import YouTubeExtractor
from core.llm_engine import GeminiHighlightEngine
from core.logger import logger
from core.transcript import TranscriptManager


class ClipperPipeline:
    """Orchestrates the full clip-extraction pipeline in headless mode.

    All intermediate results (video metadata, clips, renders) are persisted
    to the SQLite database automatically.
    """

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        output_dir: str = "outputs/clips",
    ) -> None:
        """
        Args:
            db:         :class:`~core.database.DatabaseManager` instance.
                        A default one (``clipper.db`` at project root) is
                        created when *None* is passed.
            output_dir: Directory where rendered MP4 files will be stored.
        """
        self.db = db or DatabaseManager()
        self.db.init_db()
        self.output_dir = output_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def run(
        cls,
        url: str,
        target_clips: int = 3,
        render_mode: str = "square_1x1_black",
        add_subtitles: bool = True,
        add_hook_card: bool = True,
        enhance_colors: bool = True,
        api_key: Optional[str] = None,
        progress_callback: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Execute the full pipeline for a single YouTube URL.

        The pipeline runs these layers in order:

        1. **Extract** – fetch video metadata and heatmap via yt-dlp.
        2. **Audio DSP** – parallel RMS energy analysis and signal detection.
        3. **Candidate Rank** – multi-signal fusion → Top-N candidates.
        4. **LLM** – Gemini batch judgement → keep/drop + captions.
        5. **Align** – refine cut points using audio dips / transcript seams.
        6. **Cut** – FFmpeg render with colour, subtitles, and hook card.

        Everything is saved to the database; render paths are returned.

        Args:
            url:              YouTube video URL or 11-char video ID.
            target_clips:     How many final clips to produce (default 3).
            render_mode:      FFmpeg preset – ``"square_1x1_black"``,
                              ``"shorts_9x16_black"``, ``"shorts_9x16_blur"``,
                              or ``"original_16x9"``.
            add_subtitles:    Burn Karaoke subtitles into the output.
            add_hook_card:    Overlay the first-3-second hook title card.
            enhance_colors:   Apply vibrancy/contrast colour grading.
            api_key:          Gemini API key (falls back to ``GEMINI_API_KEY``
                              environment variable).
            progress_callback: Optional callable ``(msg: str) -> None`` that
                               receives human-readable progress strings.

        Returns:
            List of result dicts, each containing at minimum:
            ``rank``, ``title``, ``render_path``, ``start_time``,
            ``end_time``, ``duration``.
        """
        pipeline = cls()
        return pipeline._execute(
            url=url,
            target_clips=target_clips,
            render_mode=render_mode,
            add_subtitles=add_subtitles,
            add_hook_card=add_hook_card,
            enhance_colors=enhance_colors,
            api_key=api_key,
            progress_callback=progress_callback,
        )

    # ------------------------------------------------------------------
    # Internal implementation
    # ------------------------------------------------------------------

    def _log(self, msg: str, cb: Optional[Any]) -> None:
        """Emit *msg* to the logger and, optionally, to the progress callback."""
        logger.info(msg)
        if cb is not None:
            try:
                cb(msg)
            except Exception:
                pass

    def _execute(
        self,
        url: str,
        target_clips: int,
        render_mode: str,
        add_subtitles: bool,
        add_hook_card: bool,
        enhance_colors: bool,
        api_key: Optional[str],
        progress_callback: Optional[Any],
    ) -> List[Dict[str, Any]]:
        cb = progress_callback

        # ----------------------------------------------------------------
        # Layer 1 — Extract
        # ----------------------------------------------------------------
        self._log("🔍 [1/6] Extracting video metadata…", cb)
        video_data = YouTubeExtractor.get_video_data(url)
        video_id: str = video_data["id"]
        clean_url: str = video_data["url"]
        duration: int = video_data["duration"]
        heatmap: List[Dict] = video_data.get("heatmap", [])

        self.db.save_video(video_data)
        self._log(f"   ✓ '{video_data['title']}' ({duration}s)", cb)

        # ----------------------------------------------------------------
        # Layer 2 — Audio DSP (parallel chunked analysis)
        # ----------------------------------------------------------------
        self._log("🎵 [2/6] Analysing audio energy (parallel)…", cb)
        times, rms = AudioDSPAnalyzer.extract_audio_energy(
            url=clean_url,
            duration_sec=duration,
        )
        signals = AudioDSPAnalyzer.detect_signals(times, rms)
        self._log(f"   ✓ {len(times)} audio frames analysed", cb)

        # ----------------------------------------------------------------
        # Layer 3 — Transcript (best-effort)
        # ----------------------------------------------------------------
        self._log("📝 [3/6] Fetching transcript…", cb)
        transcript: List[Dict] = []
        try:
            transcript = TranscriptManager.get_transcript(video_id)
            self._log(f"   ✓ {len(transcript)} transcript segments", cb)
        except Exception as exc:
            self._log(f"   ⚠ Transcript unavailable: {exc}", cb)

        # ----------------------------------------------------------------
        # Layer 3b — Candidate Rank
        # ----------------------------------------------------------------
        self._log("📊 [3b/6] Fusing signals → Top-N candidates…", cb)
        ranker = CandidateRanker(top_n=max(target_clips * 3, 10))
        candidates = ranker.fuse_signals_and_generate_candidates(
            times=signals["times"],
            audio_spikes=signals["audio_spikes"],
            silence_bursts=signals["silence_bursts"],
            heatmap=heatmap,
            transcript=transcript,
            total_duration=duration,
        )
        self._log(f"   ✓ {len(candidates)} candidates generated", cb)

        # ----------------------------------------------------------------
        # Layer 4 — LLM batch judgement
        # ----------------------------------------------------------------
        self._log("🤖 [4/6] Gemini batch judgement…", cb)
        selected_clips = GeminiHighlightEngine.batch_judge_gaming_candidates(
            candidates=candidates,
            video_title=video_data["title"],
            total_duration=duration,
            target_clips=target_clips,
            api_key=api_key,
        )
        self._log(f"   ✓ {len(selected_clips)} clips selected by LLM", cb)

        # ----------------------------------------------------------------
        # Layer 5 — Align (refine cut points)
        # ----------------------------------------------------------------
        self._log("🎯 [5/6] Aligning cut points…", cb)
        aligner = AlignmentEngine()
        for clip in selected_clips:
            refined_start, refined_end = aligner.refine_cut_points(
                start_time=clip["start_time"],
                end_time=clip["end_time"],
                times=signals["times"],
                rms=rms,
                transcript=transcript,
            )
            clip["start_time"] = refined_start
            clip["end_time"] = refined_end
            clip["duration"] = round(refined_end - refined_start, 1)
        self._log("   ✓ Cut points refined", cb)

        # Persist clips to DB
        clip_ids = self.db.save_clips(video_id, selected_clips)

        # ----------------------------------------------------------------
        # Layer 6 — Cut / Render
        # ----------------------------------------------------------------
        self._log("✂️  [6/6] Rendering clips…", cb)
        cutter = VideoCutter(output_dir=self.output_dir)

        results: List[Dict[str, Any]] = []
        for idx, (clip, clip_db_id) in enumerate(
            zip(selected_clips, clip_ids), start=1
        ):
            self._log(
                f"   Rendering clip {idx}/{len(selected_clips)}: "
                f"'{clip.get('title', '')}'…",
                cb,
            )
            try:
                render_path = cutter.cut_clip(
                    url=clean_url,
                    start_time=clip["start_time"],
                    end_time=clip["end_time"],
                    clip_id=clip_db_id,
                    video_title=video_data["title"],
                    hook_caption=clip.get("hook_caption", ""),
                    transcript_segments=transcript,
                    render_mode=render_mode,
                    add_subtitles=add_subtitles,
                    add_hook_card=add_hook_card,
                    enhance_colors=enhance_colors,
                    progress_callback=cb,
                )
                self.db.save_render(clip_db_id, render_mode, render_path)
                clip["render_path"] = render_path
                self._log(f"   ✓ Saved → {render_path}", cb)
            except Exception as exc:
                logger.error("Render failed for clip {}: {}", clip_db_id, exc)
                render_path = ""
                clip["render_path"] = render_path

            results.append(
                {
                    "rank": clip.get("rank", idx),
                    "title": clip.get("title", ""),
                    "category": clip.get("category", ""),
                    "start_time": clip["start_time"],
                    "end_time": clip["end_time"],
                    "duration": clip["duration"],
                    "hook_caption": clip.get("hook_caption", ""),
                    "score": clip.get("score", 0),
                    "render_path": clip["render_path"],
                    "clip_db_id": clip_db_id,
                }
            )

        self.db.mark_video_done(video_id)
        self._log(
            f"🎉 Pipeline complete — {len(results)} clips ready.", cb
        )
        return results
