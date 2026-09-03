import os
import subprocess
import pytest
from unittest.mock import patch, MagicMock

from core.cutter import VideoCutter

@pytest.fixture
def cutter():
    return VideoCutter(output_dir="/tmp/outputs")


@patch("core.cutter.os.path.exists")
@patch("core.cutter.os.path.getsize")
def test_cut_clip_cached(mock_getsize, mock_exists, cutter):
    # If file exists and size > 1000, it returns the output_path early
    mock_exists.return_value = True
    mock_getsize.return_value = 1500
    
    progress_calls = []
    def progress_callback(msg):
        progress_calls.append(msg)
        
    result = cutter.cut_clip(
        url="http://youtube.com/watch?v=123",
        start_time=10.0,
        end_time=20.0,
        clip_id="abc",
        progress_callback=progress_callback
    )
    
    assert "abc" in result
    assert "Önbellekte bulundu" in progress_calls[0]


@patch("core.cutter.os.path.exists")
@patch("core.cutter.os.path.getsize")
@patch("core.cutter.yt_dlp.YoutubeDL")
@patch("core.cutter.subprocess.run")
@patch("core.cutter.os.remove")
@patch("core.cutter.SubtitleGenerator.generate_ass_file")
def test_cut_clip_full_success_no_whisper(mock_gen_ass, mock_remove, mock_run, mock_ytdl, mock_getsize, mock_exists, cutter):
    # Step 1: file doesn't exist, we download it. After download it exists and size > 0
    # Then we check ass file existence before adding to ffmpeg, return True
    # We check raw_cut existence before remove, return True
    
    def exists_side_effect(path):
        if "raw_cut_" in path and mock_ytdl.called: return True
        if "raw_cut_" in path: return False
        if "sub_" in path: return True
        if "clip_" in path and not mock_run.called: return False
        return True
        
    def getsize_side_effect(path):
        if "raw_cut_" in path: return 1024
        if "clip_" in path: return 1024
        return 0
        
    mock_exists.side_effect = exists_side_effect
    mock_getsize.side_effect = getsize_side_effect
    
    mock_ydl_instance = MagicMock()
    mock_ytdl.return_value.__enter__.return_value = mock_ydl_instance
    
    result = cutter.cut_clip(
        url="http://youtube.com/watch?v=123",
        start_time=10.0,
        end_time=20.0,
        clip_id="abc",
        video_title="Test Video!",
        hook_caption="Watch this",
        transcript_segments=[{"text": "Hello"}],
        render_mode="square_1x1_black",
        add_subtitles=True,
        add_hook_card=True,
        enhance_colors=True,
        use_whisper=False
    )
    
    assert result.endswith(".mp4")
    assert "Test_Video" in result
    
    mock_ytdl.assert_called()
    mock_ydl_instance.download.assert_called_once_with(["http://youtube.com/watch?v=123"])
    mock_gen_ass.assert_called_once()
    # subprocess.run called for stream URL fallback + final render
    assert mock_run.call_count >= 1
    mock_remove.assert_called()


@patch("core.cutter.os.path.exists")
@patch("core.cutter.os.path.getsize")
@patch("core.cutter.yt_dlp.YoutubeDL")
def test_cut_clip_download_fails(mock_ytdl, mock_getsize, mock_exists, cutter):
    mock_exists.return_value = False
    mock_getsize.return_value = 0
    
    # yt-dlp raises error on first attempt, fallback also somehow fails to make file > 0
    mock_ydl_instance = MagicMock()
    mock_ydl_instance.download.side_effect = [Exception("First attempt failed"), None]
    mock_ytdl.return_value.__enter__.return_value = mock_ydl_instance
    
    with pytest.raises(RuntimeError, match="Ham video kesiti oluşturulamadı."):
        cutter.cut_clip(
            url="http://youtube.com/watch?v=123",
            start_time=10.0,
            end_time=20.0,
            clip_id="abc"
        )
    
    assert mock_ytdl.call_count >= 2 # Called fallback



@patch("core.cutter.os.path.exists")
@patch("core.cutter.os.path.getsize")
@patch("core.cutter.yt_dlp.YoutubeDL")
@patch("core.cutter.subprocess.run")
@patch("core.cutter._WHISPER_AVAILABLE", True)
@patch("core.cutter.WhisperTranscriber")
@patch("core.cutter.SubtitleGenerator.generate_ass_from_words")
@patch("core.cutter.SubtitleGenerator.generate_ass_file")
def test_cut_clip_with_whisper_success(mock_gen_ass_file, mock_gen_ass_words, mock_transcriber_class, mock_run, mock_ytdl, mock_getsize, mock_exists, cutter):
    # Mocking exists and getsize
    mock_exists.return_value = True
    mock_getsize.return_value = 1024
    # But output file shouldn't exist initially
    def exists_se(path):
        if "clip_" in path and not mock_run.called: return False
        return True
    mock_exists.side_effect = exists_se
    
    mock_transcriber = MagicMock()
    mock_transcriber_class.return_value = mock_transcriber
    mock_transcriber.transcribe_from_video.return_value = [{"word": "Test", "start": 0.0, "end": 1.0}]
    
    cutter.cut_clip(
        url="http://youtube.com/watch?v=123",
        start_time=10.0,
        end_time=20.0,
        clip_id="abc",
        use_whisper=True,
        render_mode="shorts_9x16_black"
    )
    
    mock_transcriber.transcribe_from_video.assert_called_once()
    mock_gen_ass_words.assert_called_once()
    mock_gen_ass_file.assert_not_called()


@patch("core.cutter.os.path.exists")
@patch("core.cutter.os.path.getsize")
@patch("core.cutter.yt_dlp.YoutubeDL")
@patch("core.cutter.subprocess.run")
@patch("core.cutter._WHISPER_AVAILABLE", True)
@patch("core.cutter.WhisperTranscriber")
@patch("core.cutter.SubtitleGenerator.generate_ass_file")
def test_cut_clip_whisper_fallback_to_asr(mock_gen_ass_file, mock_transcriber_class, mock_run, mock_ytdl, mock_getsize, mock_exists, cutter):
    def exists_se(path):
        if "clip_" in path and not mock_run.called: return False
        return True
    mock_exists.side_effect = exists_se
    mock_getsize.return_value = 1024
    
    mock_transcriber = MagicMock()
    mock_transcriber_class.return_value = mock_transcriber
    # Transcribe returns empty list, causing fallback
    mock_transcriber.transcribe_from_video.return_value = []
    
    progress_calls = []
    cutter.cut_clip(
        url="http://youtube.com/watch?v=123",
        start_time=10.0,
        end_time=20.0,
        clip_id="abc",
        use_whisper=True,
        transcript_segments=[{"text": "Fallback"}],
        progress_callback=lambda x: progress_calls.append(x)
    )
    
    mock_gen_ass_file.assert_called_once()
    assert any("Whisper kelime bulamadı" in c for c in progress_calls)


@patch("core.cutter.os.path.exists")
@patch("core.cutter.os.path.getsize")
@patch("core.cutter.yt_dlp.YoutubeDL")
@patch("core.cutter.subprocess.run")
@patch("core.cutter._WHISPER_AVAILABLE", True)
@patch("core.cutter.WhisperTranscriber")
@patch("core.cutter.SubtitleGenerator.generate_ass_file")
def test_cut_clip_whisper_exception_fallback(mock_gen_ass_file, mock_transcriber_class, mock_run, mock_ytdl, mock_getsize, mock_exists, cutter):
    def exists_se(path):
        if "clip_" in path and not mock_run.called: return False
        return True
    mock_exists.side_effect = exists_se
    mock_getsize.return_value = 1024
    
    mock_transcriber = MagicMock()
    mock_transcriber_class.return_value = mock_transcriber
    mock_transcriber.transcribe_from_video.side_effect = Exception("Whisper error")
    
    progress_calls = []
    cutter.cut_clip(
        url="http://youtube.com/watch?v=123",
        start_time=10.0,
        end_time=20.0,
        clip_id="abc",
        use_whisper=True,
        transcript_segments=[{"text": "Fallback"}],
        progress_callback=lambda x: progress_calls.append(x)
    )
    
    mock_gen_ass_file.assert_called_once()
    assert any("Whisper hatası" in c for c in progress_calls)


@patch("core.cutter.os.path.exists")
@patch("core.cutter.os.path.getsize")
@patch("core.cutter.yt_dlp.YoutubeDL")
@patch("core.cutter.subprocess.run")
def test_cut_clip_render_modes_and_fallback(mock_run, mock_ytdl, mock_getsize, mock_exists, cutter):
    def exists_se(path):
        if "clip_" in path and not mock_run.called: return False
        return True
    mock_exists.side_effect = exists_se
    mock_getsize.return_value = 1024
    
    # Test shorts_9x16_blur
    # Also test subprocess.run failing and falling back
    mock_run.side_effect = [subprocess.CalledProcessError(1, "ffmpeg"), None]
    
    result = cutter.cut_clip(
        url="http://youtube.com/watch?v=123",
        start_time=10.0,
        end_time=20.0,
        clip_id="abc",
        render_mode="shorts_9x16_blur",
        add_subtitles=False,
        add_hook_card=False,
        enhance_colors=False
    )
    
    assert mock_run.call_count == 2
    # Check that fallback removes 'ass=' (not applicable here since we turned off subs, but tests the branch)

@patch("core.cutter.os.path.exists")
@patch("core.cutter.os.path.getsize")
@patch("core.cutter.yt_dlp.YoutubeDL")
@patch("core.cutter.subprocess.run")
def test_cut_clip_ffmpeg_fallback_with_ass(mock_run, mock_ytdl, mock_getsize, mock_exists, cutter):
    def exists_se(path):
        if "clip_" in path and mock_run.call_count >= 1: return True
        if "clip_" in path: return False
        return True
    mock_exists.side_effect = exists_se
    mock_getsize.return_value = 1024
    
    # Fails first with libass error
    mock_run.side_effect = [subprocess.CalledProcessError(1, "ffmpeg"), MagicMock()]
    
    cutter.cut_clip(
        url="http://youtube.com/watch?v=123",
        start_time=10.0,
        end_time=20.0,
        clip_id="abc",
        render_mode="original",
        add_subtitles=True,
        use_whisper=False
    )
    
    assert mock_run.call_count == 2
    args, kwargs = mock_run.call_args_list[1]
    # Verify the fallback cmd does not have 'ass=' filter
    cmd = args[0]
    vf_idx = cmd.index("-vf")
    vf_arg = cmd[vf_idx + 1]
    assert "ass=" not in vf_arg


@patch("core.cutter.os.path.exists")
@patch("core.cutter.os.path.getsize")
@patch("core.cutter.yt_dlp.YoutubeDL")
@patch("core.cutter.subprocess.run")
@patch("core.cutter.os.remove")
def test_cut_clip_remove_exception(mock_remove, mock_run, mock_ytdl, mock_getsize, mock_exists, cutter):
    def exists_se(path):
        if "clip_" in path and not mock_run.called: return False
        return True
    mock_exists.side_effect = exists_se
    mock_getsize.return_value = 1024
    
    mock_remove.side_effect = OSError("Cannot remove")
    
    # Should not raise exception
    cutter.cut_clip(
        url="http://youtube.com/watch?v=123",
        start_time=10.0,
        end_time=20.0,
        clip_id="abc"
    )
    
    mock_remove.assert_called()

@patch("core.cutter.os.path.exists")
@patch("core.cutter.os.path.getsize")
@patch("core.cutter.yt_dlp.YoutubeDL")
@patch("core.cutter.subprocess.run")
@patch("core.cutter._WHISPER_AVAILABLE", True)
@patch("core.cutter.WhisperTranscriber")
@patch("core.cutter.SubtitleGenerator.generate_ass_from_words")
def test_cut_clip_with_whisper_and_progress_callback(mock_gen_ass_words, mock_transcriber_class, mock_run, mock_ytdl, mock_getsize, mock_exists, cutter):
    mock_exists.side_effect = lambda p: not ("clip_" in p and not mock_run.called)
    mock_getsize.return_value = 1024
    
    mock_transcriber = MagicMock()
    mock_transcriber_class.return_value = mock_transcriber
    mock_transcriber.transcribe_from_video.return_value = [{"word": "Test", "start": 0.0, "end": 1.0}]
    
    progress_calls = []
    cutter.cut_clip(
        url="http://youtube.com/watch?v=123",
        start_time=10.0,
        end_time=20.0,
        clip_id="abc",
        use_whisper=True,
        progress_callback=lambda x: progress_calls.append(x)
    )
    assert len(progress_calls) > 0
