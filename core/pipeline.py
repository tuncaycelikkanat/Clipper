"""Headless batch pipeline for the clipper project with full Dependency Injection.

Runs the full 6-layer pipeline:
    Extract → AudioDSP → CandidateRank → LLM → Align → Cut
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable
from typing import Any

import numpy as np

from core.aligner import AlignmentEngine
from core.audio_dsp import AudioDSPAnalyzer
from core.candidate_ranker import CandidateRanker
from core.copywriter import CopywriterEngine
from core.cutter import VideoCutter
from core.database import DatabaseManager
from core.extractor import YouTubeExtractor
from core.llm_engine import GeminiHighlightEngine
from core.logger import logger
from core.transcript import TranscriptManager
from core.visual_dsp import VisualDSPAnalyzer


class ClipperPipeline:
    """Orchestrates the full clip-extraction pipeline in headless mode."""

    def __init__(
        self,
        db: DatabaseManager | None = None,
        output_dir: str = "outputs/clips",
        extractor: YouTubeExtractor | None = None,
        audio_dsp: AudioDSPAnalyzer | None = None,
        ranker: CandidateRanker | None = None,
        llm: GeminiHighlightEngine | None = None,
        aligner: AlignmentEngine | None = None,
        cutter: VideoCutter | None = None,
        transcript_manager: TranscriptManager | None = None,
        copywriter: CopywriterEngine | None = None,
    ) -> None:
        self.db = db or DatabaseManager()
        self.db.init_db()
        self.output_dir = output_dir

        self.extractor = extractor or YouTubeExtractor()
        self.audio_dsp = audio_dsp or AudioDSPAnalyzer()
        self.ranker = ranker or CandidateRanker()
        self.llm = llm or GeminiHighlightEngine()
        self.aligner = aligner or AlignmentEngine()
        self.cutter = cutter or VideoCutter(output_dir=output_dir)
        self.transcript_manager = transcript_manager or TranscriptManager()
        self.copywriter = copywriter or CopywriterEngine()

    @classmethod
    def run(
        cls,
        url: str,
        target_clips: int = 3,
        render_mode: str = "shorts_9x16_blur",
        add_subtitles: bool = False,
        add_hook_card: bool = False,
        enhance_colors: bool = True,
        api_key: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
        db: DatabaseManager | None = None,
    ) -> list[dict[str, Any]]:
        """Convenience factory method to execute the pipeline."""
        pipeline = cls(db=db)
        return pipeline.execute(
            url=url,
            target_clips=target_clips,
            render_mode=render_mode,
            add_subtitles=add_subtitles,
            add_hook_card=add_hook_card,
            enhance_colors=enhance_colors,
            api_key=api_key,
            progress_callback=progress_callback,
        )

    def _execute(self, *args, **kwargs):
        return self.execute(*args, **kwargs)

    def execute(
        self,
        url: str,
        target_clips: int = 3,
        render_mode: str = "shorts_9x16_black",
        add_subtitles: bool = True,
        add_hook_card: bool = True,
        enhance_colors: bool = True,
        api_key: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Executes the pipeline layers sequentially."""
        import time

        step_timings: dict[str, float] = {}
        t_pipeline_start = time.perf_counter()

        def safe_cb(msg: str):
            if progress_callback:
                with contextlib.suppress(Exception):
                    progress_callback(msg)

        safe_cb("🚀 Pipeline başlatılıyor...")

        # 1. Extract
        t0 = time.perf_counter()
        safe_cb("📥 Video bilgileri ve heatmap alınıyor...")
        video_data = YouTubeExtractor.get_video_data(url)
        video_id = video_data.get("id") or "vid"
        video_title = video_data.get("title", "Gaming Video")
        duration = int(video_data.get("duration", 0))
        self.db.save_video(video_data)
        step_timings["1. Video Metadata & Info"] = time.perf_counter() - t0

        # 2. Parallel Multi-Signal Extraction (Audio DSP + Pitch in 1-pass, Transcripts, Frame-Diff)
        t0 = time.perf_counter()
        safe_cb("🎵 Ses frekansı, transkript, izleyici yorumları ve görsel sahne eşzamanlı analiz ediliyor...")

        from concurrent.futures import ThreadPoolExecutor

        audio_res = {}
        transcripts = []
        comments_res = []
        fd_times, fd_scores = np.array([]), np.array([])

        def _task_audio():
            try:
                return AudioDSPAnalyzer.extract_all_signals_fast(url, duration_sec=duration)
            except Exception as exc:
                logger.warning("Fast Audio DSP extraction skipped: {}", exc)
                return {}

        def _task_transcript():
            try:
                return TranscriptManager.get_transcript(video_id, audio_path_or_url=url)
            except Exception as exc:
                logger.warning("Transcript retrieval failed: {}", exc)
                return []

        def _task_comments():
            try:
                return YouTubeExtractor.get_video_comments(url, max_comments=100)
            except Exception as exc:
                logger.warning("Comments retrieval skipped: {}", exc)
                return []

        def _task_framediff():
            try:
                return VisualDSPAnalyzer.extract_frame_diff(url, duration_sec=duration, fps=1.0)
            except Exception as exc:
                logger.warning("Frame-diff extraction skipped: {}", exc)
                return np.array([]), np.array([])

        with ThreadPoolExecutor(max_workers=4) as executor:
            fut_audio = executor.submit(_task_audio)
            fut_trans = executor.submit(_task_transcript)
            fut_comm = executor.submit(_task_comments)
            fut_fd = executor.submit(_task_framediff)

            audio_res = fut_audio.result()
            transcripts = fut_trans.result()
            comments_res = fut_comm.result()
            fd_times, fd_scores = fut_fd.result()

        times = audio_res.get("times", np.array([]))
        audio_energy = audio_res.get("rms", np.array([]))
        signals = audio_res.get(
            "signals", {"times": times, "audio_spikes": np.array([]), "silence_bursts": np.array([])}
        )
        pitch_times = audio_res.get("pitch_times", np.array([]))
        pitch_var = audio_res.get("pitch_var", np.array([]))

        # Pitch varyansını audio timeline'ına hizala
        pitch_on_audio = np.array([])
        if len(pitch_times) > 0 and len(signals.get("times", np.array([]))) > 0:
            audio_times = signals.get("times", np.array([]))
            pitch_on_audio = np.interp(audio_times, pitch_times, pitch_var, left=0.0, right=0.0)

        # Frame-diff sinyalini audio timeline'ına hizala
        fd_on_audio = np.array([])
        if len(fd_times) > 0 and len(signals.get("times", np.array([]))) > 0:
            audio_times = signals.get("times", np.array([]))
            fd_on_audio = VisualDSPAnalyzer.interpolate_to_timeline(fd_times, fd_scores, audio_times)

        step_timings["2. Parallel Signal Extraction"] = time.perf_counter() - t0

        # 3. Candidate Ranking
        t0 = time.perf_counter()
        safe_cb("📊 Potansiyel klip adayları sıralanıyor (İzleyici yorumları, vokal & sinyal füzyonu)...")
        ranker = CandidateRanker(top_n=target_clips * 2)
        candidates = ranker.fuse_signals_and_generate_candidates(
            times=signals.get("times", np.array([])),
            audio_spikes=signals.get("audio_spikes", np.array([])),
            silence_bursts=signals.get("silence_bursts", np.array([])),
            heatmap=video_data.get("heatmap", []),
            transcript=transcripts,
            total_duration=duration,
            video_id=video_id,
            view_count=video_data.get("view_count", 0),
            comments=comments_res,
            pitch_variance=pitch_on_audio if len(pitch_on_audio) > 0 else None,
            frame_diff=fd_on_audio if len(fd_on_audio) > 0 else None,
            vocal_spikes=signals.get("vocal_spikes") if len(signals.get("vocal_spikes", [])) > 0 else None,
        )
        step_timings["3. Candidate Ranking & Fusion"] = time.perf_counter() - t0

        # 4. LLM Judgement
        t0 = time.perf_counter()
        safe_cb("🤖 Yapay Zeka anları değerlendiriyor...")
        evaluated_clips = GeminiHighlightEngine.batch_judge_gaming_candidates(
            candidates=candidates,
            video_title=video_title,
            total_duration=duration,
            target_clips=target_clips,
            api_key=api_key,
        )
        step_timings["4. Gemini Flash Viral Judgement"] = time.perf_counter() - t0

        # 5. Boundary Alignment (Frame-diff dahil)
        t0 = time.perf_counter()
        safe_cb("⏱️ Klip başlangıç ve bitiş sınırları hassas hizalanıyor...")
        aligner = AlignmentEngine()
        aligned_clips = []
        for clip in evaluated_clips:
            clip_copy = dict(clip)
            ref_start, ref_end = aligner.refine_cut_points(
                start_time=clip.get("start_time", 0.0),
                end_time=clip.get("end_time", 10.0),
                times=signals.get("times", np.array([])),
                rms=audio_energy,
                transcript=transcripts,
                frame_diff_times=fd_times if len(fd_times) > 0 else None,
                frame_diff_scores=fd_scores if len(fd_scores) > 0 else None,
            )
            clip_copy["start_time"] = ref_start
            clip_copy["end_time"] = ref_end
            clip_copy["duration"] = ref_end - ref_start
            aligned_clips.append(clip_copy)
        step_timings["5. Boundary Alignment"] = time.perf_counter() - t0

        # 5.5. Game Detection & Human Metadata Enrichment
        t0 = time.perf_counter()
        from core.game_detector import GameDetector
        from core.metadata_engine import HumanMetadataEngine

        detected_game = GameDetector.detect_game(description=video_data.get("description", ""), title=video_title)
        streamer_name = video_data.get("uploader") or "Yayıncı"

        # 5.6. Video-level Thumbnail (Manuel kullanıcı yüklemesi için boş bırakılıyor)
        thumb_dir = os.path.join("outputs", "thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)
        video_thumb_path = None

        enriched_clips = []
        for clip in aligned_clips:
            clip_copy = dict(clip)
            try:
                meta = HumanMetadataEngine.generate_metadata(
                    transcript_snippet=clip.get("text") or clip.get("transcript_snippet") or "",
                    streamer_name=streamer_name,
                    video_title=video_title,
                    game_name=detected_game,
                    duration_sec=clip.get("duration", 30.0),
                )
                if meta.get("recommended_title"):
                    clip_copy["title"] = meta["recommended_title"]
                if meta.get("hook_caption"):
                    clip_copy["hook_caption"] = meta["hook_caption"]
                clip_copy["description"] = meta.get("description", "")
                clip_copy["tags"] = meta.get("tags_comma_separated", "")
                clip_copy["all_titles"] = meta.get("titles", {})
            except Exception as e:
                logger.warning("Human metadata enrichment skipped: {}", e)

            if video_thumb_path:
                clip_copy["thumbnail_path"] = video_thumb_path
            enriched_clips.append(clip_copy)

        saved_ids = self.db.save_clips(video_id, enriched_clips)
        step_timings["6. Metadata & Title Generation"] = time.perf_counter() - t0

        # 6. Video Cutting & Rendering (Paralel)
        t0 = time.perf_counter()
        safe_cb("🎬 Klipler dikey formatta işleniyor...")
        cutter = VideoCutter(output_dir=self.output_dir)

        def render_single_clip(i_clip_tuple):
            i, clip = i_clip_tuple
            cid = saved_ids[i] if (saved_ids and i < len(saved_ids)) else str(clip.get("rank", i + 1))
            try:
                render_path = cutter.cut_clip(
                    url=url,
                    start_time=clip["start_time"],
                    end_time=clip["end_time"],
                    clip_id=cid,
                    video_title=video_title,
                    hook_caption=clip.get("hook_caption", ""),
                    transcript_segments=transcripts,
                    render_mode=render_mode,
                    add_subtitles=add_subtitles,
                    add_hook_card=add_hook_card,
                    enhance_colors=enhance_colors,
                    progress_callback=safe_cb,
                )
                clip_res = dict(clip)
                clip_res["clip_id"] = cid
                clip_res["clip_db_id"] = cid
                clip_res["render_path"] = render_path

                # Thumbnail fallback if video_thumb_path wasn't generated
                thumb_path = clip_res.get("thumbnail_path")
                if (not thumb_path or not os.path.exists(thumb_path)) and render_path and os.path.exists(render_path):
                    cand_thumb = os.path.join(thumb_dir, f"thumb_{cid}.jpg")
                    try:
                        from core.thumbnail import ThumbnailGenerator

                        ThumbnailGenerator.extract_best_frame(
                            video_path=render_path,
                            peak_time=1.0,
                            output_path=cand_thumb,
                        )
                        if os.path.exists(cand_thumb):
                            thumb_path = cand_thumb
                            clip_res["thumbnail_path"] = thumb_path
                            with self.db._connect() as conn:
                                conn.execute("UPDATE clips SET thumbnail_path = ? WHERE id = ?", (thumb_path, cid))
                                conn.commit()
                    except Exception as te:
                        logger.warning("Thumbnail fallback extraction skipped for #{}: {}", cid, te)

                self.db.save_render(
                    clip_id=cid,
                    render_mode=render_mode,
                    file_path=render_path,
                )
                return clip_res
            except Exception as exc:
                logger.error("Clip render failed for #{}: {}", cid, exc)
                clip_res = dict(clip)
                clip_res["clip_id"] = cid
                clip_res["clip_db_id"] = cid
                clip_res["render_path"] = ""
                return clip_res

        rendered_results = []
        if len(enriched_clips) > 1:
            with ThreadPoolExecutor(max_workers=min(4, len(enriched_clips))) as executor:
                rendered_results = list(executor.map(render_single_clip, enumerate(enriched_clips)))
        elif len(enriched_clips) == 1:
            rendered_results = [render_single_clip((0, enriched_clips[0]))]

        step_timings["7. Video Rendering & Cutting (Parallel)"] = time.perf_counter() - t0
        total_duration_sec = time.perf_counter() - t_pipeline_start

        # Profiling Loglama & Konsol Tablosu
        logger.info("=" * 70)
        logger.info("⏱️ PIPELINE PERFORMANCE BENCHMARK (Süre Ölçümü)")
        logger.info("=" * 70)
        for step_name, elapsed in step_timings.items():
            pct = (elapsed / total_duration_sec) * 100 if total_duration_sec > 0 else 0
            logger.info("  * {:<32}: {:>6.2f}s  ({:>5.1f}%)", step_name, elapsed, pct)
        logger.info("-" * 70)
        logger.info("  * {:<32}: {:>6.2f}s  (100.0%)", "TOPLAM SÜRE", total_duration_sec)
        logger.info("=" * 70)

        self.db.mark_video_done(video_id)
        safe_cb(f"🎉 Pipeline tamamlandı! Toplam süre: {total_duration_sec:.1f}sn")
        return rendered_results
