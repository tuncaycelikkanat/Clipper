"""
core/whisper_transcriber.py
Word-level audio transcription using faster-whisper.
Falls back gracefully (returns empty list) if faster-whisper is not available.
"""

import os
import subprocess
import tempfile
from typing import List, Dict

try:
    from faster_whisper import WhisperModel
    _FASTER_WHISPER_AVAILABLE = True
except ImportError:
    _FASTER_WHISPER_AVAILABLE = False

from loguru import logger


class WhisperTranscriber:
    """
    Wraps faster-whisper for word-level audio/video transcription.

    Uses the 'base' model by default — small (~150 MB), fast on CPU.
    Falls back gracefully to returning an empty list if the library is
    not installed or any runtime error occurs.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        """
        Initialise the transcriber.

        Args:
            model_size:    faster-whisper model size ('tiny', 'base', 'small', ...).
            device:        Inference device ('cpu' or 'cuda').
            compute_type:  Quantisation type ('int8', 'float16', 'float32').
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model: object = None  # Lazy-loaded on first use

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_model(self) -> bool:
        """
        Lazy-load the WhisperModel.  Returns True on success, False on failure.
        """
        if self._model is not None:
            return True

        if not _FASTER_WHISPER_AVAILABLE:
            logger.warning(
                "faster-whisper is not installed. "
                "Run: .venv/bin/pip install faster-whisper"
            )
            return False

        try:
            logger.info(
                "Loading faster-whisper model '{}' on {} ({}) ...",
                self.model_size,
                self.device,
                self.compute_type,
            )
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            logger.info("faster-whisper model loaded successfully.")
            return True
        except Exception as exc:
            logger.warning("Could not load faster-whisper model: {}", exc)
            return False

    @staticmethod
    def _extract_audio_to_tempfile(video_path: str) -> str:
        """
        Pipe audio from *video_path* to a temporary WAV file (16 kHz mono).

        Returns the path to the temp file.  The caller is responsible for
        deleting it after use.
        """
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        os.close(tmp_fd)

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",                     # no video
            "-acodec", "pcm_s16le",    # 16-bit PCM
            "-ar", "16000",            # 16 kHz - Whisper's native rate
            "-ac", "1",                # mono
            tmp_path,
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            os.unlink(tmp_path)
            raise RuntimeError(
                f"ffmpeg audio extraction failed: {result.stderr.decode(errors='replace')}"
            )
        return tmp_path

    def _run_transcription(
        self, audio_path: str, language: str
    ) -> List[Dict]:
        """
        Core transcription logic shared by both public methods.

        Returns a list of word-level dicts:
            [{'word': 'HELLO', 'start': 0.24, 'end': 0.68}, ...]
        """
        if not self._load_model():
            return []

        try:
            segments, _info = self._model.transcribe(  # type: ignore[union-attr]
                audio_path,
                language=language,
                word_timestamps=True,
                beam_size=5,
            )

            words: List[Dict] = []
            for segment in segments:
                if segment.words is None:
                    continue
                for word in segment.words:
                    text = word.word.strip().upper()
                    if not text:
                        continue
                    words.append(
                        {
                            "word": text,
                            "start": round(float(word.start), 3),
                            "end": round(float(word.end), 3),
                        }
                    )

            logger.info(
                "faster-whisper transcribed {} words from '{}'.",
                len(words),
                audio_path,
            )
            return words

        except Exception as exc:
            logger.warning("faster-whisper transcription failed: {}", exc)
            return []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transcribe_audio_segment(
        self,
        audio_file_path: str,
        language: str = "tr",
    ) -> List[Dict]:
        """
        Transcribe a pre-existing audio file and return word-level segments.

        Args:
            audio_file_path: Absolute path to an audio file (WAV, MP3, ...).
            language:        BCP-47 language code, e.g. 'tr', 'en'.

        Returns:
            List of dicts: [{'word': str, 'start': float, 'end': float}, ...]
            Returns [] on any error or if faster-whisper is unavailable.
        """
        if not os.path.exists(audio_file_path):
            logger.warning("Audio file not found: {}", audio_file_path)
            return []

        return self._run_transcription(audio_file_path, language)

    def transcribe_from_video(
        self,
        video_path: str,
        language: str = "tr",
    ) -> List[Dict]:
        """
        Extract audio from a video via FFmpeg pipe and transcribe word-by-word.

        Args:
            video_path: Absolute path to a video file (.mp4, .mkv, ...).
            language:   BCP-47 language code, e.g. 'tr', 'en'.

        Returns:
            List of dicts: [{'word': str, 'start': float, 'end': float}, ...]
            Returns [] on any error or if faster-whisper is unavailable.
        """
        if not os.path.exists(video_path):
            logger.warning("Video file not found: {}", video_path)
            return []

        tmp_audio: str = ""
        try:
            logger.info("Extracting audio from '{}' for Whisper ...", video_path)
            tmp_audio = self._extract_audio_to_tempfile(video_path)
            return self._run_transcription(tmp_audio, language)
        except Exception as exc:
            logger.warning(
                "Failed to extract/transcribe audio from '{}': {}",
                video_path,
                exc,
            )
            return []
        finally:
            if tmp_audio and os.path.exists(tmp_audio):
                try:
                    os.unlink(tmp_audio)
                except Exception:
                    pass

    def transcribe_to_sentence_segments(
        self,
        media_path: str,
        language: str = "tr",
    ) -> List[Dict]:
        """
        Transcribe an audio/video file or stream into sentence-level segments.

        Args:
            media_path: Path or URL to audio/video file.
            language:   BCP-47 language code (default 'tr').

        Returns:
            List of dicts: [{'text': str, 'start': float, 'end': float, 'duration': float}, ...]
        """
        if not self._load_model():
            return []

        tmp_audio = ""
        target_path = media_path
        try:
            if not os.path.exists(media_path) and media_path.startswith(("http://", "https://")):
                tmp_audio = self._extract_audio_to_tempfile(media_path)
                target_path = tmp_audio
            elif os.path.exists(media_path) and not media_path.endswith((".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus")):
                tmp_audio = self._extract_audio_to_tempfile(media_path)
                target_path = tmp_audio

            segments, _ = self._model.transcribe(  # type: ignore[union-attr]
                target_path,
                language=language,
                beam_size=5,
            )

            result: List[Dict] = []
            for seg in segments:
                text = seg.text.strip()
                if text:
                    st = round(float(seg.start), 2)
                    en = round(float(seg.end), 2)
                    dur = round(en - st, 2)
                    result.append({
                        "text": text,
                        "start": st,
                        "end": en,
                        "duration": dur,
                    })

            logger.info(
                "faster-whisper transcribed {} sentence segments from '{}'.",
                len(result),
                media_path,
            )
            return result

        except Exception as exc:
            logger.warning("faster-whisper sentence transcription failed: {}", exc)
            return []
        finally:
            if tmp_audio and os.path.exists(tmp_audio):
                try:
                    os.unlink(tmp_audio)
                except OSError:
                    pass
