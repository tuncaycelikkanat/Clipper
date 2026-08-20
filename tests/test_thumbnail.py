import os
import subprocess
from unittest import mock
import pytest
from core.thumbnail import ThumbnailGenerator

# --- extract_best_frame ---

def test_extract_best_frame_success(tmp_path):
    output_path = tmp_path / "thumb.jpg"
    with mock.patch("core.thumbnail.subprocess.run") as mock_run:
        with mock.patch("core.thumbnail.os.path.exists", return_value=True):
            with mock.patch("core.thumbnail.os.path.getsize", return_value=1000):
                res = ThumbnailGenerator.extract_best_frame(
                    video_path="dummy.mp4",
                    peak_time=15.0,
                    output_path=str(output_path),
                )
                assert res == str(output_path)
                mock_run.assert_called_once()
                cmd = mock_run.call_args[0][0]
                assert "ffmpeg" in cmd
                assert "dummy.mp4" in cmd

def test_extract_best_frame_subprocess_error(tmp_path):
    output_path = tmp_path / "thumb.jpg"
    with mock.patch("core.thumbnail.subprocess.run") as mock_run:
        error = subprocess.CalledProcessError(1, "ffmpeg", stderr=b"some error")
        mock_run.side_effect = error
        with pytest.raises(RuntimeError, match="FFmpeg thumbnail.*some error"):
            ThumbnailGenerator.extract_best_frame("dummy.mp4", 15.0, str(output_path))

def test_extract_best_frame_not_found_error(tmp_path):
    output_path = tmp_path / "thumb.jpg"
    with mock.patch("core.thumbnail.subprocess.run", side_effect=FileNotFoundError("ffmpeg not found")):
        with pytest.raises(RuntimeError, match="FFmpeg bulunamad\u0131"):
            ThumbnailGenerator.extract_best_frame("dummy.mp4", 15.0, str(output_path))

def test_extract_best_frame_empty_output(tmp_path):
    output_path = tmp_path / "thumb.jpg"
    with mock.patch("core.thumbnail.subprocess.run"):
        with mock.patch("core.thumbnail.os.path.exists", return_value=True):
            with mock.patch("core.thumbnail.os.path.getsize", return_value=0):
                with pytest.raises(RuntimeError, match="Thumbnail olu\u015fturulamad\u0131"):
                    ThumbnailGenerator.extract_best_frame("dummy.mp4", 15.0, str(output_path))

def test_extract_best_frame_missing_output(tmp_path):
    output_path = tmp_path / "thumb.jpg"
    with mock.patch("core.thumbnail.subprocess.run"):
        with mock.patch("core.thumbnail.os.path.exists", return_value=False):
            with pytest.raises(RuntimeError, match="Thumbnail olu\u015fturulamad\u0131"):
                ThumbnailGenerator.extract_best_frame("dummy.mp4", 15.0, str(output_path))

# --- extract_best_frame_from_url ---

@mock.patch("core.thumbnail.subprocess.run")
@mock.patch("yt_dlp.YoutubeDL")
def test_extract_best_frame_from_url_success_top_level_url(mock_ytdl_class, mock_run, tmp_path):
    output_path = tmp_path / "thumb.jpg"
    
    mock_ydl = mock.MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = {"url": "http://stream.m3u8"}
    mock_ytdl_class.return_value = mock_ydl

    with mock.patch("core.thumbnail.os.path.exists", return_value=True), \
         mock.patch("core.thumbnail.os.path.getsize", return_value=1000):
        res = ThumbnailGenerator.extract_best_frame_from_url(
            url="http://youtube.com/watch?v=123",
            start_time=10.0,
            peak_time=15.0,
            output_path=str(output_path)
        )
        assert res == str(output_path)
        cmd = mock_run.call_args[0][0]
        assert "http://stream.m3u8" in cmd
        assert "-ss" in cmd
        assert "5.0" in cmd  # relative peak (15.0 - 10.0)

@mock.patch("core.thumbnail.subprocess.run")
@mock.patch("yt_dlp.YoutubeDL")
def test_extract_best_frame_from_url_formats_fallback_and_negative_relative_peak(mock_ytdl_class, mock_run, tmp_path):
    output_path = tmp_path / "thumb.jpg"
    
    mock_ydl = mock.MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    # url missing at top level, fallback to formats
    mock_ydl.extract_info.return_value = {
        "formats": [
            {"vcodec": "none", "url": "audio_only"},
            {"vcodec": "h264", "url": "http://stream2.m3u8"}
        ]
    }
    mock_ytdl_class.return_value = mock_ydl

    with mock.patch("core.thumbnail.os.path.exists", return_value=True), \
         mock.patch("core.thumbnail.os.path.getsize", return_value=1000):
        res = ThumbnailGenerator.extract_best_frame_from_url(
            url="http://youtube.com/watch?v=123",
            start_time=20.0,
            peak_time=15.0, # relative_peak < 0 -> 0.0
            output_path=str(output_path)
        )
        assert res == str(output_path)
        cmd = mock_run.call_args[0][0]
        assert "http://stream2.m3u8" in cmd
        assert "0.0" in cmd  # relative peak clamped to 0.0

@mock.patch("yt_dlp.YoutubeDL")
def test_extract_best_frame_from_url_ytdlp_exception(mock_ytdl_class, tmp_path):
    output_path = tmp_path / "thumb.jpg"
    mock_ydl = mock.MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.side_effect = Exception("ytdl error")
    mock_ytdl_class.return_value = mock_ydl

    with pytest.raises(RuntimeError, match="yt-dlp stream URL \u00e7\u00f6z\u00fcmlenemedi: ytdl error"):
        ThumbnailGenerator.extract_best_frame_from_url("url", 0.0, 1.0, str(output_path))

@mock.patch("yt_dlp.YoutubeDL")
def test_extract_best_frame_from_url_no_stream(mock_ytdl_class, tmp_path):
    output_path = tmp_path / "thumb.jpg"
    mock_ydl = mock.MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = {"formats": []} # no valid url
    mock_ytdl_class.return_value = mock_ydl

    with pytest.raises(RuntimeError, match="Ge\u00e7erli video stream URL'si bulunamad\u0131"):
        ThumbnailGenerator.extract_best_frame_from_url("url", 0.0, 1.0, str(output_path))

@mock.patch("core.thumbnail.subprocess.run")
@mock.patch("yt_dlp.YoutubeDL")
def test_extract_best_frame_from_url_subprocess_error(mock_ytdl_class, mock_run, tmp_path):
    output_path = tmp_path / "thumb.jpg"
    mock_ydl = mock.MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = {"url": "http://stream"}
    mock_ytdl_class.return_value = mock_ydl

    error = subprocess.CalledProcessError(1, "ffmpeg", stderr=b"ffmpeg err")
    mock_run.side_effect = error

    with pytest.raises(RuntimeError, match="Stream thumbnail \u00e7\u0131karma ba\u015far\u0131s\u0131z: ffmpeg err"):
        ThumbnailGenerator.extract_best_frame_from_url("url", 0.0, 1.0, str(output_path))

@mock.patch("core.thumbnail.subprocess.run")
@mock.patch("yt_dlp.YoutubeDL")
def test_extract_best_frame_from_url_not_found(mock_ytdl_class, mock_run, tmp_path):
    output_path = tmp_path / "thumb.jpg"
    mock_ydl = mock.MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = {"url": "http://stream"}
    mock_ytdl_class.return_value = mock_ydl

    mock_run.side_effect = FileNotFoundError("ffmpeg not found")

    with pytest.raises(RuntimeError, match="FFmpeg bulunamad\u0131"):
        ThumbnailGenerator.extract_best_frame_from_url("url", 0.0, 1.0, str(output_path))

@mock.patch("core.thumbnail.subprocess.run")
@mock.patch("yt_dlp.YoutubeDL")
def test_extract_best_frame_from_url_empty_output(mock_ytdl_class, mock_run, tmp_path):
    output_path = tmp_path / "thumb.jpg"
    mock_ydl = mock.MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = {"url": "http://stream"}
    mock_ytdl_class.return_value = mock_ydl

    with mock.patch("core.thumbnail.os.path.exists", return_value=True), \
         mock.patch("core.thumbnail.os.path.getsize", return_value=0):
        with pytest.raises(RuntimeError, match="Thumbnail olu\u015fturulamad\u0131"):
            ThumbnailGenerator.extract_best_frame_from_url("url", 0.0, 1.0, str(output_path))

# --- batch_generate_thumbnails ---

def test_batch_generate_thumbnails_local_file(tmp_path):
    output_dir = tmp_path / "thumbnails"
    clips = [{"rank": 1, "peak_time": 10.0}, {"rank": 2, "start_time": 5.0, "end_time": 15.0}]
    
    with mock.patch.object(ThumbnailGenerator, "extract_best_frame") as mock_extract:
        res = ThumbnailGenerator.batch_generate_thumbnails(
            clips=clips,
            video_path_or_url="dummy.mp4",
            output_dir=str(output_dir)
        )
        assert len(res) == 2
        assert mock_extract.call_count == 2

def test_batch_generate_thumbnails_url(tmp_path):
    output_dir = tmp_path / "thumbnails"
    clips = [{"rank": 1, "peak_time": 10.0}]
    
    with mock.patch.object(ThumbnailGenerator, "extract_best_frame_from_url") as mock_extract_url:
        res = ThumbnailGenerator.batch_generate_thumbnails(
            clips=clips,
            video_path_or_url="http://youtube.com/watch",
            output_dir=str(output_dir)
        )
        assert len(res) == 1
        assert mock_extract_url.call_count == 1

def test_batch_generate_thumbnails_exception_handled(tmp_path):
    output_dir = tmp_path / "thumbnails"
    clips = [{"rank": 1, "peak_time": 10.0}, {"rank": 2, "peak_time": 20.0}]
    
    with mock.patch.object(ThumbnailGenerator, "extract_best_frame") as mock_extract:
        # First call fails, second succeeds
        mock_extract.side_effect = [Exception("error"), None]
        res = ThumbnailGenerator.batch_generate_thumbnails(
            clips=clips,
            video_path_or_url="dummy.mp4",
            output_dir=str(output_dir)
        )
        assert len(res) == 1
        assert mock_extract.call_count == 2

def test_extract_candidates(tmp_path):
    clip = {"rank": 1, "start_time": 10.0, "end_time": 40.0, "peak_time": 25.0}
    with mock.patch.object(ThumbnailGenerator, "extract_best_frame") as mock_extract:
        res = ThumbnailGenerator.extract_candidates(clip, "fake_path.mp4", output_dir=str(tmp_path))
        assert mock_extract.call_count == 3
        assert len(res) == 3

    # Test URL branch with exception
    with mock.patch.object(ThumbnailGenerator, "extract_best_frame_from_url", side_effect=Exception("Stream error")):
        res_url = ThumbnailGenerator.extract_candidates(clip, "https://youtube.com/watch?v=123", output_dir=str(tmp_path))
        assert len(res_url) == 0
