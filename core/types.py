"""
core/types.py — Shared TypedDict definitions for the clipper pipeline.

These types describe the data structures flowing between the pipeline stages:
extractor → ranker → llm_engine → aligner → cutter.
"""

from typing import Optional
from typing_extensions import TypedDict


class VideoData(TypedDict):
    """Metadata and heatmap data for a YouTube video."""

    id: str
    url: str
    title: str
    uploader: str
    duration: int
    duration_formatted: str
    thumbnail: Optional[str]
    view_count: int
    has_heatmap: bool
    heatmap: list


class ClipData(TypedDict):
    """A final, judged clip selected by the pipeline."""

    rank: int
    candidate_id: int
    title: str
    category: str
    score: int
    hook_caption: str
    reason: str
    start_time: float
    start_formatted: str
    end_time: float
    end_formatted: str
    duration: float
    duration_formatted: str
    text: str


class TranscriptSegment(TypedDict):
    """A single segment from the YouTube transcript API."""

    text: str
    start: float
    end: float
    duration: float


class WordSegment(TypedDict):
    """A word-level timing entry from Whisper."""

    word: str
    start: float
    end: float


class RenderResult(TypedDict):
    """Result returned after rendering/cutting a clip with FFmpeg."""

    clip_id: str
    render_path: str
    render_mode: str
    file_size: int
    success: bool
    error: Optional[str]
