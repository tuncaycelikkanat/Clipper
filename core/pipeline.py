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
from core.visual_dsp import VisualDSPAnalyzer


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

        # 2b. Pitch Variance (ZCR tabanlı — kahkaha tespiti)
        safe_cb("🎙️ Pitch/F0 varyans analizi yapılıyor...")
        pitch_times, pitch_var = np.array([]), np.array([])
        try:
            pitch_times, pitch_var = AudioDSPAnalyzer.extract_pitch_variance(url, duration_sec=duration)
        except Exception as e:
            logger.warning("Pitch variance extraction skipped: {}", e)

        # Pitch varyansını audio timeline'ına hizala
        pitch_on_audio = np.array([])
        if len(pitch_times) > 0 and len(signals.get("times", np.array([]))) > 0:
            audio_times = signals.get("times", np.array([]))
            pitch_on_audio = np.interp(audio_times, pitch_times, pitch_var, left=0.0, right=0.0)

        # 2c. Frame-Diff — görsel sahne değişimi tespiti
        safe_cb("🖼️ Görsel sahne değişimi analiz ediliyor...")
        fd_times, fd_scores = np.array([]), np.array([])
        try:
            fd_times, fd_scores = VisualDSPAnalyzer.extract_frame_diff(url, duration_sec=duration, fps=1.0)
        except Exception as e:
            logger.warning("Frame-diff extraction skipped: {}", e)

        # Frame-diff sinyalini audio timeline'ına hizala
        fd_on_audio = np.array([])
        if len(fd_times) > 0 and len(signals.get("times", np.array([]))) > 0:
            audio_times = signals.get("times", np.array([]))
            fd_on_audio = VisualDSPAnalyzer.interpolate_to_timeline(fd_times, fd_scores, audio_times)

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
            pitch_variance=pitch_on_audio if len(pitch_on_audio) > 0 else None,
            frame_diff=fd_on_audio if len(fd_on_audio) > 0 else None,
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

        # 5. Boundary Alignment (Frame-diff dahil)
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

        # 5.5. Game Detection & Human Metadata Enrichment
        from core.game_detector import GameDetector
        from core.metadata_engine import HumanMetadataEngine

        detected_game = GameDetector.detect_game(
            description=video_data.get("description", ""),
            title=video_title
        )
        streamer_name = video_data.get("uploader") or "Yayıncı"

        # 5.6. Video-level AI Vertical Thumbnail (Shared across all clips of this video)
        safe_cb("🖼️ Orijinal kapak görseli dikey formata dönüştürülüyor (AI Thumbnail)...")
        thumb_dir = os.path.join("outputs", "thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)
        video_thumb_path = os.path.join(thumb_dir, f"thumb_{video_id}.jpg")
        try:
            from core.thumbnail import ThumbnailGenerator
            gen_thumb = ThumbnailGenerator.generate_ai_vertical_thumbnail(
                video_url_or_id=url,
                output_path=video_thumb_path,
                aspect_ratio="2:3",
                api_key=api_key,
            )
            if not gen_thumb or not os.path.exists(video_thumb_path):
                video_thumb_path = None
        except Exception as te:
            logger.warning("AI Thumbnail generation skipped for video {}: {}", video_id, te)
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

            if video_thumb_path:
                clip_copy["thumbnail_path"] = video_thumb_path
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
