import os
from typing import List, Dict, Any

class TimedWord:
    def __init__(self, text: str, start: float, end: float):
        self.text = text
        self.start = start
        self.end = end

class SubtitleGenerator:
    """Generates ultra-bold, strictly single-line Karaoke ASS subtitles preventing any overlap."""

    @staticmethod
    def format_ass_time(seconds: float) -> str:
        """Converts seconds into ASS timestamp format H:MM:SS.cs"""
        seconds = max(0.0, seconds)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:d}:{minutes:02d}:{secs:05.2f}"

    @classmethod
    def generate_ass_file(
        cls,
        transcript_segments: List[Dict[str, Any]],
        clip_start_sec: float,
        clip_end_sec: float,
        output_path: str,
        video_width: int = 1080,
        video_height: int = 1080,
        font_size: int = 34,
        margin_v: int = 120
    ) -> str:
        """
        Creates max 3-word, single-line Karaoke subtitles.
        Fixes YouTube ASR overlapping segments by strictly flattening and sequentializing words.
        """
        ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ShortsKaraoke,DejaVu Sans,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,1,0,1,4.5,2.5,2,30,30,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        ACTIVE_TAG = r"{\c&H0000FFFF\fscx115\fscy115}"
        NORMAL_TAG = r"{\c&H00FFFFFF\fscx100\fscy100}"

        # 1. Flatten all segments into a strict, non-overlapping sequential timeline of words
        all_timed_words: List[TimedWord] = []
        last_end_time = 0.0

        for seg in transcript_segments:
            s_abs = float(seg["start"])
            e_abs = float(seg["end"])

            # Filter out out-of-bounds segments
            if e_abs <= clip_start_sec or s_abs >= clip_end_sec:
                continue

            # Convert to relative time
            s_rel = max(0.0, s_abs - clip_start_sec)
            e_rel = min(clip_end_sec - clip_start_sec, e_abs - clip_start_sec)

            # CRITICAL FIX FOR OVERLAPPING SEGMENTS: 
            # Push start time forward if it overlaps with the previous segment
            if s_rel < last_end_time:
                s_rel = last_end_time
                
            if e_rel <= s_rel:
                continue

            raw_text = seg["text"].replace("\n", " ").strip()
            words = [w.strip().upper() for w in raw_text.split() if w.strip()]
            if not words:
                continue

            # Distribute time among words based on character length
            total_chars = sum(len(w) for w in words)
            curr_w_start = s_rel
            
            for w in words:
                w_dur = (e_rel - s_rel) * (len(w) / max(1, total_chars))
                w_end = curr_w_start + w_dur
                all_timed_words.append(TimedWord(text=w, start=curr_w_start, end=w_end))
                curr_w_start = w_end

            last_end_time = e_rel

        # 2. Group into strict 3-word batches
        batch_size = 3
        word_batches = []
        for i in range(0, len(all_timed_words), batch_size):
            word_batches.append(all_timed_words[i:i + batch_size])

        # 3. Generate ASS Events
        for batch in word_batches:
            for w_idx, active_word in enumerate(batch):
                w_start = active_word.start
                w_end = active_word.end
                
                # Construct the single line with only one active word highlighted
                line_parts = []
                for i, w in enumerate(batch):
                    if i == w_idx:
                        line_parts.append(f"{ACTIVE_TAG}{w.text}{NORMAL_TAG}")
                    else:
                        line_parts.append(f"{NORMAL_TAG}{w.text}")
                
                formatted_line = " ".join(line_parts)
                start_str = cls.format_ass_time(w_start)
                end_str = cls.format_ass_time(w_end)
                
                events.append(f"Dialogue: 0,{start_str},{end_str},ShortsKaraoke,,0,0,0,,{formatted_line}")

        full_content = ass_header + "\n".join(events)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        return output_path

    @classmethod
    def generate_ass_from_words(
        cls,
        word_segments: List[Dict[str, Any]],
        clip_start_sec: float,
        clip_end_sec: float,
        output_path: str,
        video_width: int = 1080,
        video_height: int = 1080,
        font_size: int = 34,
        margin_v: int = 120,
    ) -> str:
        """
        Creates max 3-word, single-line Karaoke subtitles from exact Whisper word timestamps.

        Unlike generate_ass_file (which estimates per-word timing from segment boundaries),
        this method uses the precise start/end timestamps produced by faster-whisper's
        word_timestamps=True mode.  No overlap correction is necessary because the source
        data already has non-overlapping word boundaries.

        Args:
            word_segments:   List of {'word': str, 'start': float, 'end': float} dicts.
                             'start'/'end' are absolute seconds within the original video.
            clip_start_sec:  Clip start in seconds (absolute).
            clip_end_sec:    Clip end in seconds (absolute).
            output_path:     File path for the output .ass file.
            video_width:     PlayResX for the ASS header.
            video_height:    PlayResY for the ASS header.
            font_size:       Base font size for the karaoke style.
            margin_v:        Vertical margin (pixels from the bottom edge).

        Returns:
            output_path (the path written to).
        """
        ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ShortsKaraoke,DejaVu Sans,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,1,0,1,4.5,2.5,2,30,30,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events: List[str] = []
        ACTIVE_TAG = r"{\c&H0000FFFF\fscx115\fscy115}"
        NORMAL_TAG = r"{\c&H00FFFFFF\fscx100\fscy100}"

        clip_duration = clip_end_sec - clip_start_sec

        # 1. Filter and convert to relative timestamps
        relative_words: List[TimedWord] = []
        for seg in word_segments:
            s_abs = float(seg["start"])
            e_abs = float(seg["end"])

            # Skip words outside the clip window
            if e_abs <= clip_start_sec or s_abs >= clip_end_sec:
                continue

            s_rel = max(0.0, s_abs - clip_start_sec)
            e_rel = min(clip_duration, e_abs - clip_start_sec)

            if e_rel <= s_rel:
                continue

            text = seg["word"].strip().upper()
            if not text:
                continue

            relative_words.append(TimedWord(text=text, start=s_rel, end=e_rel))

        # 2. Group into max-3-word batches
        batch_size = 3
        word_batches: List[List[TimedWord]] = [
            relative_words[i : i + batch_size]
            for i in range(0, len(relative_words), batch_size)
        ]

        # 3. Generate ASS Events - one dialogue line per active word
        for batch in word_batches:
            for w_idx, active_word in enumerate(batch):
                w_start = active_word.start
                w_end = active_word.end

                line_parts: List[str] = []
                for i, w in enumerate(batch):
                    if i == w_idx:
                        line_parts.append(f"{ACTIVE_TAG}{w.text}{NORMAL_TAG}")
                    else:
                        line_parts.append(f"{NORMAL_TAG}{w.text}")

                formatted_line = " ".join(line_parts)
                start_str = cls.format_ass_time(w_start)
                end_str = cls.format_ass_time(w_end)

                events.append(
                    f"Dialogue: 0,{start_str},{end_str},ShortsKaraoke,,0,0,0,,{formatted_line}"
                )

        full_content = ass_header + "\n".join(events)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        return output_path
