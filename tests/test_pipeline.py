import os
import pytest
from unittest.mock import patch, MagicMock

from core.pipeline import ClipperPipeline

def test_pipeline_run_success():
    with patch("core.pipeline.YouTubeExtractor.get_video_data") as mock_extract, \
         patch("core.pipeline.AudioDSPAnalyzer.extract_audio_energy") as mock_audio, \
         patch("core.pipeline.AudioDSPAnalyzer.detect_signals") as mock_signals, \
         patch("core.pipeline.TranscriptManager.get_transcript") as mock_transcript, \
         patch("core.pipeline.CandidateRanker") as mock_ranker_cls, \
         patch("core.pipeline.GeminiHighlightEngine.batch_judge_gaming_candidates") as mock_judge, \
         patch("core.pipeline.AlignmentEngine") as mock_aligner_cls, \
         patch("core.pipeline.VideoCutter") as mock_cutter_cls, \
         patch("core.pipeline.DatabaseManager") as mock_db_cls:

        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.save_clips.return_value = ["clip_123"]

        mock_extract.return_value = {
            "id": "vid123",
            "url": "http://youtube.com/watch?v=vid123",
            "duration": 100,
            "title": "Test Video",
            "heatmap": []
        }

        mock_audio.return_value = ([0.0, 1.0], [0.1, 0.2])
        mock_signals.return_value = {
            "times": [0.0, 1.0],
            "audio_spikes": [0.1, 0.2],
            "silence_bursts": [0.0, 0.0]
        }

        mock_transcript.return_value = [{"start": 0.0, "end": 1.0, "text": "Hello"}]

        mock_ranker = MagicMock()
        mock_ranker_cls.return_value = mock_ranker
        mock_ranker.fuse_signals_and_generate_candidates.return_value = [{"start_time": 0.0, "end_time": 10.0}]

        mock_judge.return_value = [{
            "rank": 1,
            "title": "Clip 1",
            "category": "Action",
            "start_time": 0.0,
            "end_time": 10.0,
            "hook_caption": "Look!",
            "score": 90
        }]

        mock_aligner = MagicMock()
        mock_aligner_cls.return_value = mock_aligner
        mock_aligner.refine_cut_points.return_value = (0.0, 10.0)

        mock_cutter = MagicMock()
        mock_cutter_cls.return_value = mock_cutter
        mock_cutter.cut_clip.return_value = "/path/to/clip.mp4"

        progress_calls = []
        def cb(msg):
            progress_calls.append(msg)
            if "fail_cb" in msg:
                raise Exception("CB fail")

        results = ClipperPipeline.run(
            url="vid123",
            target_clips=1,
            progress_callback=cb
        )

        assert len(results) == 1
        assert results[0]["render_path"] == "/path/to/clip.mp4"
        assert results[0]["clip_db_id"] == "clip_123"
        assert mock_db.mark_video_done.called
        assert len(progress_calls) > 0


def test_pipeline_transcript_exception_and_render_exception():
    with patch("core.pipeline.YouTubeExtractor.get_video_data") as mock_extract, \
         patch("core.pipeline.AudioDSPAnalyzer.extract_audio_energy") as mock_audio, \
         patch("core.pipeline.AudioDSPAnalyzer.detect_signals") as mock_signals, \
         patch("core.pipeline.TranscriptManager.get_transcript") as mock_transcript, \
         patch("core.pipeline.CandidateRanker") as mock_ranker_cls, \
         patch("core.pipeline.GeminiHighlightEngine.batch_judge_gaming_candidates") as mock_judge, \
         patch("core.pipeline.AlignmentEngine") as mock_aligner_cls, \
         patch("core.pipeline.VideoCutter") as mock_cutter_cls, \
         patch("core.pipeline.DatabaseManager") as mock_db_cls, \
         patch("core.pipeline.logger") as mock_logger:

        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.save_clips.return_value = ["clip_123"]

        mock_extract.return_value = {
            "id": "vid123",
            "url": "http://youtube.com/watch?v=vid123",
            "duration": 100,
            "title": "Test Video"
        }

        mock_audio.return_value = ([], [])
        mock_signals.return_value = {"times": [], "audio_spikes": [], "silence_bursts": []}

        mock_transcript.side_effect = Exception("No subs")

        mock_ranker = MagicMock()
        mock_ranker_cls.return_value = mock_ranker
        mock_ranker.fuse_signals_and_generate_candidates.return_value = []

        mock_judge.return_value = [{"start_time": 0.0, "end_time": 10.0}]

        mock_aligner = MagicMock()
        mock_aligner_cls.return_value = mock_aligner
        mock_aligner.refine_cut_points.return_value = (0.0, 10.0)

        mock_cutter = MagicMock()
        mock_cutter_cls.return_value = mock_cutter
        mock_cutter.cut_clip.side_effect = Exception("FFmpeg failed")

        pipeline = ClipperPipeline(db=mock_db)
        
        # Test cb with exception
        def failing_cb(msg):
            raise Exception("cb exception")
            
        results = pipeline._execute(
            url="vid123",
            target_clips=1,
            render_mode="square_1x1_black",
            add_subtitles=True,
            add_hook_card=True,
            enhance_colors=True,
            api_key=None,
            progress_callback=failing_cb
        )

        assert len(results) == 1
        assert results[0]["render_path"] == ""

