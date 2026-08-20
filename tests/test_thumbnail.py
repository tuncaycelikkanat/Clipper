import os
from unittest import mock
import pytest
from core.thumbnail import ThumbnailGenerator

def test_extract_best_frame_calls_ffmpeg(tmp_path):
    output_path = tmp_path / "thumb.jpg"
    
    with mock.patch("core.thumbnail.subprocess.run") as mock_run:
        with mock.patch("core.thumbnail.os.path.exists") as mock_exists:
            with mock.patch("core.thumbnail.os.path.getsize") as mock_getsize:
                mock_exists.return_value = True
                mock_getsize.return_value = 1000  # Fake size so it doesn't think it's empty
                
                res = ThumbnailGenerator.extract_best_frame(
                    video_path="dummy.mp4",
                    peak_time=15.0,
                    output_path=str(output_path),
                    width=1280,
                    height=720
                )
                
                assert res == str(output_path)
                mock_run.assert_called_once()
                args, kwargs = mock_run.call_args
                cmd = args[0]
                assert "ffmpeg" in cmd
                assert "-ss" in cmd
                assert "15.0" in cmd
                assert "dummy.mp4" in cmd

def test_batch_generate_thumbnails_creates_dir(tmp_path):
    output_dir = tmp_path / "thumbnails"
    clips = [{"rank": 1, "peak_time": 10.0}, {"rank": 2, "start_time": 5.0, "end_time": 15.0}]
    
    with mock.patch.object(ThumbnailGenerator, "extract_best_frame") as mock_extract:
        # Prevent it from actually extracting anything
        res = ThumbnailGenerator.batch_generate_thumbnails(
            clips=clips,
            video_path_or_url="dummy.mp4",
            output_dir=str(output_dir)
        )
        
        assert len(res) == 2
        assert os.path.exists(str(output_dir))
        assert mock_extract.call_count == 2
