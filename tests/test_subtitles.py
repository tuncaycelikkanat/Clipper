"""
tests/test_subtitles.py
Pytest tests for core/subtitles.py — both generate_ass_file and generate_ass_from_words.
"""

import os
import re

from core.subtitles import SubtitleGenerator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_dialogue_lines(ass_content: str):
    """Return a list of parsed Dialogue tuples (start_sec, end_sec, text)."""
    pattern = re.compile(r"^Dialogue:\s*\d+,(\d+:\d+:\d+\.\d+),(\d+:\d+:\d+\.\d+),.+?,,\d+,\d+,\d+,,(.*)$")
    results = []
    for line in ass_content.splitlines():
        m = pattern.match(line.strip())
        if m:
            results.append(
                (
                    _ass_time_to_sec(m.group(1)),
                    _ass_time_to_sec(m.group(2)),
                    m.group(3),
                )
            )
    return results


def _ass_time_to_sec(ts: str) -> float:
    """Convert ASS timestamp 'H:MM:SS.cs' to float seconds."""
    h, rest = ts.split(":", 1)
    m, s = rest.split(":", 1)
    return int(h) * 3600 + int(m) * 60 + float(s)


# ---------------------------------------------------------------------------
# generate_ass_file tests
# ---------------------------------------------------------------------------


class TestGenerateAssFile:
    """Tests for SubtitleGenerator.generate_ass_file (YouTube ASR path)."""

    def _make_segments(self):
        """Minimal transcript segments spanning 10–16 s (absolute)."""
        return [
            {"start": 10.0, "end": 12.0, "text": "Hello world test"},
            {"start": 12.5, "end": 14.5, "text": "Another segment here"},
            {"start": 15.0, "end": 16.0, "text": "Final"},
        ]

    def test_generate_ass_file_creates_file(self, tmp_path):
        """Output .ass file must be created and non-empty."""
        out = str(tmp_path / "out.ass")
        result = SubtitleGenerator.generate_ass_file(
            transcript_segments=self._make_segments(),
            clip_start_sec=10.0,
            clip_end_sec=16.0,
            output_path=out,
        )
        assert result == out
        assert os.path.exists(out)
        assert os.path.getsize(out) > 0

    def test_generate_ass_file_no_overlap(self, tmp_path):
        """
        No two Dialogue lines within the same clip should have overlapping time ranges.
        Timestamps must be strictly sequential (end_i <= start_{i+1}).
        """
        out = str(tmp_path / "no_overlap.ass")
        # Use segments that overlap in absolute time to stress the de-overlap logic
        overlapping_segs = [
            {"start": 5.0, "end": 9.0, "text": "Word one two"},
            {"start": 7.0, "end": 11.0, "text": "three four five"},  # overlaps prev
            {"start": 10.0, "end": 13.0, "text": "six seven"},
        ]
        SubtitleGenerator.generate_ass_file(
            transcript_segments=overlapping_segs,
            clip_start_sec=5.0,
            clip_end_sec=13.0,
            output_path=out,
        )
        with open(out, encoding="utf-8") as f:
            content = f.read()

        dialogues = _parse_dialogue_lines(content)
        assert len(dialogues) > 0, "Expected at least one Dialogue line"

        for i in range(1, len(dialogues)):
            prev_end = dialogues[i - 1][1]
            curr_start = dialogues[i][0]
            assert curr_start >= prev_end - 1e-6, (
                f"Overlap at index {i}: prev_end={prev_end:.3f} > curr_start={curr_start:.3f}"
            )

    def test_generate_ass_file_out_of_range_segments_ignored(self, tmp_path):
        """Segments entirely outside the clip window should produce no dialogue."""
        out = str(tmp_path / "empty.ass")
        segs = [
            {"start": 0.0, "end": 5.0, "text": "Before clip"},
            {"start": 20.0, "end": 25.0, "text": "After clip"},
        ]
        SubtitleGenerator.generate_ass_file(
            transcript_segments=segs,
            clip_start_sec=10.0,
            clip_end_sec=15.0,
            output_path=out,
        )
        with open(out, encoding="utf-8") as f:
            content = f.read()
        dialogues = _parse_dialogue_lines(content)
        assert len(dialogues) == 0


# ---------------------------------------------------------------------------
# generate_ass_from_words tests
# ---------------------------------------------------------------------------


class TestGenerateAssFromWords:
    """Tests for SubtitleGenerator.generate_ass_from_words (Whisper path)."""

    def _make_word_segments(self):
        """
        Simulate faster-whisper word-level output (absolute timestamps).
        8 words spanning 2.0–4.0 s → 3 batches: [3, 3, 2].
        """
        return [
            {"word": "Merhaba", "start": 2.0, "end": 2.4},
            {"word": "dünya", "start": 2.4, "end": 2.7},
            {"word": "nasılsın", "start": 2.7, "end": 3.1},
            {"word": "iyi", "start": 3.1, "end": 3.3},
            {"word": "misin", "start": 3.3, "end": 3.6},
            {"word": "bugün", "start": 3.6, "end": 3.8},
            {"word": "hava", "start": 3.8, "end": 3.9},
            {"word": "güzel", "start": 3.9, "end": 4.0},
        ]

    def test_generate_ass_from_words_exact_timing(self, tmp_path):
        """
        Each Dialogue line should reflect the *exact* start/end from the word segment,
        converted to clip-relative time (word.start - clip_start_sec).
        """
        clip_start = 2.0
        clip_end = 4.0
        out = str(tmp_path / "words.ass")
        SubtitleGenerator.generate_ass_from_words(
            word_segments=self._make_word_segments(),
            clip_start_sec=clip_start,
            clip_end_sec=clip_end,
            output_path=out,
        )
        assert os.path.exists(out)

        with open(out, encoding="utf-8") as f:
            content = f.read()

        dialogues = _parse_dialogue_lines(content)
        assert len(dialogues) > 0, "Expected Dialogue lines"

        # First word: 'Merhaba' start=2.0, end=2.4 → relative 0.0–0.4
        first_start, first_end, _ = dialogues[0]
        assert abs(first_start - 0.0) < 0.02, f"First dialogue start mismatch: {first_start}"
        assert abs(first_end - 0.4) < 0.02, f"First dialogue end mismatch: {first_end}"

        # All timestamps must be within [0, clip_duration]
        clip_duration = clip_end - clip_start
        for s, e, _ in dialogues:
            assert s >= -1e-6, f"Negative relative start: {s}"
            assert e <= clip_duration + 1e-6, f"End beyond clip duration: {e}"

    def test_max_3_words_per_batch(self, tmp_path):
        """
        Each Dialogue line must contain at most 3 words in its text payload.
        Word count per line is determined by splitting on spaces after stripping
        the ASS override tags.
        """
        out = str(tmp_path / "batch.ass")
        SubtitleGenerator.generate_ass_from_words(
            word_segments=self._make_word_segments(),
            clip_start_sec=2.0,
            clip_end_sec=4.0,
            output_path=out,
        )

        with open(out, encoding="utf-8") as f:
            content = f.read()

        dialogues = _parse_dialogue_lines(content)
        ass_tag_re = re.compile(r"\{[^}]+\}")

        for _s, _e, text in dialogues:
            clean_text = ass_tag_re.sub("", text).strip()
            word_count = len(clean_text.split())
            assert word_count <= 3, f"Batch has more than 3 words ({word_count}): '{clean_text}'"

    def test_generate_ass_from_words_creates_file(self, tmp_path):
        """Output file must exist and be non-empty."""
        out = str(tmp_path / "created.ass")
        result = SubtitleGenerator.generate_ass_from_words(
            word_segments=self._make_word_segments(),
            clip_start_sec=2.0,
            clip_end_sec=4.0,
            output_path=out,
        )
        assert result == out
        assert os.path.exists(out)
        assert os.path.getsize(out) > 0

    def test_generate_ass_from_words_uppercase(self, tmp_path):
        """Words must be uppercased in the ASS output."""
        out = str(tmp_path / "upper.ass")
        SubtitleGenerator.generate_ass_from_words(
            word_segments=[
                {"word": "hello", "start": 1.0, "end": 1.5},
                {"word": "world", "start": 1.5, "end": 2.0},
            ],
            clip_start_sec=1.0,
            clip_end_sec=2.0,
            output_path=out,
        )
        with open(out, encoding="utf-8") as f:
            content = f.read()

        ass_tag_re = re.compile(r"\{[^}]+\}")
        for line in content.splitlines():
            if line.startswith("Dialogue:"):
                text_part = line.split(",,", 9)[-1]
                clean = ass_tag_re.sub("", text_part).strip()
                assert clean == clean.upper(), f"Text not uppercase: '{clean}'"

    def test_generate_ass_from_words_empty_segments(self, tmp_path):
        """Empty word_segments list should produce a valid .ass file with no Dialogue lines."""
        out = str(tmp_path / "empty.ass")
        SubtitleGenerator.generate_ass_from_words(
            word_segments=[],
            clip_start_sec=0.0,
            clip_end_sec=10.0,
            output_path=out,
        )
        assert os.path.exists(out)
        with open(out, encoding="utf-8") as f:
            content = f.read()
        dialogues = _parse_dialogue_lines(content)
        assert len(dialogues) == 0


def test_generate_ass_file_edge_cases(tmp_path):
    out = str(tmp_path / "edge.ass")
    segs = [
        {"start": 10.0, "end": 10.0, "text": "zero dur"},
        {"start": 11.0, "end": 12.0, "text": "   "},  # empty text
    ]
    SubtitleGenerator.generate_ass_file(
        transcript_segments=segs,
        clip_start_sec=10.0,
        clip_end_sec=15.0,
        output_path=out,
    )
    assert os.path.exists(out)


def test_generate_ass_from_words_edge_cases(tmp_path):
    out = str(tmp_path / "edge_words.ass")
    words = [
        {"word": "out_of_range", "start": 0.0, "end": 5.0},
        {"word": "zero_dur", "start": 10.0, "end": 10.0},
        {"word": "   ", "start": 11.0, "end": 12.0},
    ]
    SubtitleGenerator.generate_ass_from_words(
        word_segments=words,
        clip_start_sec=10.0,
        clip_end_sec=15.0,
        output_path=out,
    )
    assert os.path.exists(out)
