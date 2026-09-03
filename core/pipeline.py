"""Headless batch pipeline for the clipper project with full Dependency Injection.

Runs the full 6-layer pipeline:
    Extract → AudioDSP → CandidateRank → LLM → Align → Cut
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional
import numpy as np

from core.aligner import AlignmentEngine
from core.audio_dsp import AudioDSPAnalyzer
from core.candidate_ranker import CandidateRanker
from core.cutter import VideoCutter
from core.database import DatabaseManager
from core.extractor import YouTubeExtractor
from core.llm_engine import GeminiHighlightEngine
from core.logger import logger
from core.transcript import TranscriptManager
from core.copywriter import CopywriterEngine


class ClipperPipeline:
    """Orchestrates the full clip-extraction pipeline in headless mode."""

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        output_dir: str = "outputs/clips",
        extractor: Optional[YouTubeExtractor] = None,
        audio_dsp: Optional[AudioDSPAnalyzer] = None,
        ranker: Optional[CandidateRanker] = None,
        llm: Optional[GeminiHighlightEngine] = None,
        aligner: Optional[AlignmentEngine] = None,
        cutter: Optional[VideoCutter] = None,
        transcript_manager: Optional[TranscriptManager] = None,
        copywriter: Optional[CopywriterEngine] = None,
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
        api_key: Optional[str] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
        db: Optional[DatabaseManager] = None,
    ) -> List[Dict[str, Any]]:
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
        api_key: Optional[str] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Executes the pipeline layers sequentially."""
        def safe_cb(msg: str):
            if progress_callback:
                try:
                    progress_callback(msg)
                except Exception:
                    pass

        safe_cb("🚀 Pipeline başlatılıyor...")

        # 1. Extract
        safe_cb("📥 Video bilgileri ve heatmap alınıyor...")
        video_data = YouTubeExtractor.get_video_data(url)
        video_id = video_data.get("id") or "vid"
        video_title = video_data.get("title", "Gaming Video")
        duration = int(video_data.get("duration", 0))
        self.db.save_video(video_data)

        # 2. Audio DSP & Transcripts
        safe_cb("🎵 Ses frekansı ve transkript analiz ediliyor...")
        times, audio_energy = np.array([]), np.array([])
        signals = {"times": times, "audio_spikes": np.array([]), "silence_bursts": np.array([])}
        try:
            times, audio_energy = AudioDSPAnalyzer.extract_audio_energy(url, duration_sec=duration)
            signals = AudioDSPAnalyzer.detect_signals(times, audio_energy)
        except Exception as e:
            logger.warning("Audio DSP extraction skipped: {}", e)

        transcripts = []
        try:
            transcripts = TranscriptManager.get_transcript(video_id)
        except Exception as e:
            logger.warning("Transcript retrieval failed: {}", e)

        # 3. Candidate Ranking
        safe_cb("📊 Potansiyel klip adayları sıralanıyor...")
        ranker = CandidateRanker(top_n=target_clips * 2)
        candidates = ranker.fuse_signals_and_generate_candidates(
            times=signals.get("times", np.array([])),
            audio_spikes=signals.get("audio_spikes", np.array([])),
            silence_bursts=signals.get("silence_bursts", np.array([])),
            heatmap=video_data.get("heatmap", []),
            transcript=transcripts,
            total_duration=duration,
            video_id=video_id,
        )

        # 4. LLM Judgement
        safe_cb("🤖 Yapay Zeka anları değerlendiriyor...")
        evaluated_clips = GeminiHighlightEngine.batch_judge_gaming_candidates(
            candidates=candidates,
            video_title=video_title,
            total_duration=duration,
            target_clips=target_clips,
            api_key=api_key,
        )

        # 5. Boundary Alignment
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
            )
            clip_copy["start_time"] = ref_start
            clip_copy["end_time"] = ref_end
            clip_copy["duration"] = ref_end - ref_start
            aligned_clips.append(clip_copy)

        # 5.5. Game Detection & Human Metadata Enrichment
        from core.game_detector import GameDetector
        from core.metadata_engine import HumanMetadataEngine

        detected_game = GameDetector.detect_game(
            description=video_data.get("description", ""),
            title=video_title
        )
        streamer_name = video_data.get("uploader") or "Yayıncı"

        enriched_clips = []
        for clip in aligned_clips:
            clip_copy = dict(clip)
            try:
                meta = HumanMetadataEngine.generate_metadata(
                    transcript_snippet=clip.get("text") or clip.get("transcript_snippet") or "",
                    streamer_name=streamer_name,
                    video_title=video_title,
                    game_name=detected_game,
                    duration_sec=clip.get("duration", 30.0)
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
            enriched_clips.append(clip_copy)

        saved_ids = self.db.save_clips(video_id, enriched_clips)

        # 6. Video Cutting
        safe_cb("🎬 Klipler dikey formatta işleniyor...")
        cutter = VideoCutter(output_dir=self.output_dir)
        rendered_results = []
        for i, clip in enumerate(enriched_clips):
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
                self.db.save_render(
                    clip_id=cid,
                    render_mode=render_mode,
                    file_path=render_path,
                )
                rendered_results.append(clip_res)
            except Exception as e:
                logger.error("Clip render failed for #{}: {}", cid, e)
                clip_res = dict(clip)
                clip_res["clip_id"] = cid
                clip_res["clip_db_id"] = cid
                clip_res["render_path"] = ""
                rendered_results.append(clip_res)

        self.db.mark_video_done(video_id)
        safe_cb("🎉 Pipeline tamamlandı!")
        return rendered_results
