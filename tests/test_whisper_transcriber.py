from unittest.mock import MagicMock, patch

import pytest

from core.whisper_transcriber import WhisperTranscriber


@pytest.fixture
def mock_transcriber():
    return WhisperTranscriber(model_size="tiny", device="cpu", compute_type="int8")


@patch("core.whisper_transcriber.os.path.exists")
def test_transcribe_audio_segment_file_not_found(mock_exists, mock_transcriber):
    mock_exists.return_value = False
    result = mock_transcriber.transcribe_audio_segment("nonexistent.wav")
    assert result == []


@patch("core.whisper_transcriber.os.path.exists")
def test_transcribe_from_video_file_not_found(mock_exists, mock_transcriber):
    mock_exists.return_value = False
    result = mock_transcriber.transcribe_from_video("nonexistent.mp4")
    assert result == []


def test_load_model_not_available(mock_transcriber):
    with patch("core.whisper_transcriber._FASTER_WHISPER_AVAILABLE", False):
        assert mock_transcriber._load_model() is False


@patch("core.whisper_transcriber.WhisperModel")
def test_load_model_success(mock_whisper_model, mock_transcriber):
    with patch("core.whisper_transcriber._FASTER_WHISPER_AVAILABLE", True):
        assert mock_transcriber._load_model() is True
        assert mock_transcriber._model is not None

        # Second time should just return True
        assert mock_transcriber._load_model() is True
        mock_whisper_model.assert_called_once()


@patch("core.whisper_transcriber.WhisperModel")
def test_load_model_exception(mock_whisper_model, mock_transcriber):
    mock_whisper_model.side_effect = Exception("Failed to load")
    with patch("core.whisper_transcriber._FASTER_WHISPER_AVAILABLE", True):
        assert mock_transcriber._load_model() is False


@patch("core.whisper_transcriber.subprocess.run")
@patch("core.whisper_transcriber.tempfile.mkstemp")
@patch("core.whisper_transcriber.os.close")
def test_extract_audio_to_tempfile_success(mock_close, mock_mkstemp, mock_run):
    mock_mkstemp.return_value = (1, "/tmp/test.wav")

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_run.return_value = mock_result

    result = WhisperTranscriber._extract_audio_to_tempfile("test.mp4")
    assert result == "/tmp/test.wav"
    mock_run.assert_called_once()


@patch("core.whisper_transcriber.subprocess.run")
@patch("core.whisper_transcriber.tempfile.mkstemp")
@patch("core.whisper_transcriber.os.close")
@patch("core.whisper_transcriber.os.unlink")
def test_extract_audio_to_tempfile_failure(mock_unlink, mock_close, mock_mkstemp, mock_run):
    mock_mkstemp.return_value = (1, "/tmp/test.wav")

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = b"ffmpeg error"
    mock_run.return_value = mock_result

    with pytest.raises(RuntimeError, match="ffmpeg audio extraction failed"):
        WhisperTranscriber._extract_audio_to_tempfile("test.mp4")

    mock_unlink.assert_called_once_with("/tmp/test.wav")


@patch("core.whisper_transcriber.WhisperTranscriber._load_model")
def test_run_transcription_model_fail(mock_load, mock_transcriber):
    mock_load.return_value = False
    result = mock_transcriber._run_transcription("test.wav", "en")
    assert result == []


@patch("core.whisper_transcriber.WhisperTranscriber._load_model")
def test_run_transcription_exception(mock_load, mock_transcriber):
    mock_load.return_value = True
    mock_model = MagicMock()
    mock_model.transcribe.side_effect = Exception("Transcribe failed")
    mock_transcriber._model = mock_model

    result = mock_transcriber._run_transcription("test.wav", "en")
    assert result == []


@patch("core.whisper_transcriber.WhisperTranscriber._load_model")
def test_run_transcription_success(mock_load, mock_transcriber):
    mock_load.return_value = True
    mock_model = MagicMock()

    class MockWord:
        def __init__(self, word, start, end):
            self.word = word
            self.start = start
            self.end = end

    class MockSegment:
        def __init__(self, words):
            self.words = words

    mock_segment_1 = MockSegment([MockWord(" Hello ", 0.0, 1.0), MockWord("", 1.0, 1.2)])
    mock_segment_2 = MockSegment(None)  # Testing segment with words is None
    mock_segment_3 = MockSegment([MockWord("world", 1.2, 2.0)])

    mock_model.transcribe.return_value = ([mock_segment_1, mock_segment_2, mock_segment_3], None)
    mock_transcriber._model = mock_model

    result = mock_transcriber._run_transcription("test.wav", "en")

    assert len(result) == 2
    assert result[0] == {"word": "HELLO", "start": 0.0, "end": 1.0}
    assert result[1] == {"word": "WORLD", "start": 1.2, "end": 2.0}


@patch("core.whisper_transcriber.os.path.exists")
@patch("core.whisper_transcriber.WhisperTranscriber._run_transcription")
def test_transcribe_audio_segment_success(mock_run_transcription, mock_exists, mock_transcriber):
    mock_exists.return_value = True
    mock_run_transcription.return_value = [{"word": "TEST", "start": 0.0, "end": 1.0}]

    result = mock_transcriber.transcribe_audio_segment("test.wav", "en")
    assert len(result) == 1
    assert result[0]["word"] == "TEST"


@patch("core.whisper_transcriber.os.path.exists")
@patch("core.whisper_transcriber.WhisperTranscriber._extract_audio_to_tempfile")
@patch("core.whisper_transcriber.WhisperTranscriber._run_transcription")
@patch("core.whisper_transcriber.os.unlink")
def test_transcribe_from_video_success(
    mock_unlink, mock_run_transcription, mock_extract, mock_exists, mock_transcriber
):
    # Setup exists to return True for video, and True for temp audio in finally block
    mock_exists.side_effect = [True, True]
    mock_extract.return_value = "/tmp/audio.wav"
    mock_run_transcription.return_value = [{"word": "VIDEO", "start": 0.0, "end": 1.0}]

    result = mock_transcriber.transcribe_from_video("test.mp4", "en")

    assert len(result) == 1
    assert result[0]["word"] == "VIDEO"
    mock_extract.assert_called_once_with("test.mp4")
    mock_run_transcription.assert_called_once_with("/tmp/audio.wav", "en")
    mock_unlink.assert_called_once_with("/tmp/audio.wav")


@patch("core.whisper_transcriber.os.path.exists")
@patch("core.whisper_transcriber.WhisperTranscriber._extract_audio_to_tempfile")
@patch("core.whisper_transcriber.os.unlink")
def test_transcribe_from_video_extract_fails(mock_unlink, mock_extract, mock_exists, mock_transcriber):
    # Exists for video
    mock_exists.return_value = True
    mock_extract.side_effect = Exception("Extract fail")

    result = mock_transcriber.transcribe_from_video("test.mp4", "en")

    assert result == []
    mock_unlink.assert_not_called()


@patch("core.whisper_transcriber.os.path.exists")
@patch("core.whisper_transcriber.WhisperTranscriber._extract_audio_to_tempfile")
@patch("core.whisper_transcriber.WhisperTranscriber._run_transcription")
@patch("core.whisper_transcriber.os.unlink")
def test_transcribe_from_video_unlink_fails(
    mock_unlink, mock_run_transcription, mock_extract, mock_exists, mock_transcriber
):
    mock_exists.side_effect = [True, True]
    mock_extract.return_value = "/tmp/audio.wav"
    mock_run_transcription.return_value = []
    mock_unlink.side_effect = Exception("Unlink fail")

    # Should not raise exception
    result = mock_transcriber.transcribe_from_video("test.mp4", "en")
    assert result == []
