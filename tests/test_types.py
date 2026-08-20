"""Tests for core/types.py."""

from core.types import (
    VideoData,
    ClipData,
    TranscriptSegment,
    WordSegment,
    RenderResult,
)


def test_types_instantiation():
    v: VideoData = {
        "id": "123",
        "url": "https://example.com",
        "title": "Title",
        "uploader": "Uploader",
        "duration": 100,
        "duration_formatted": "01:40",
        "thumbnail": None,
        "view_count": 50,
        "has_heatmap": False,
        "heatmap": [],
    }
    assert v["id"] == "123"

    c: ClipData = {
        "rank": 1,
        "candidate_id": 10,
        "title": "Clip",
        "category": "EPIC",
        "score": 90,
        "hook_caption": "Hook",
        "reason": "Reason",
        "start_time": 0.0,
        "start_formatted": "00:00",
        "end_time": 10.0,
        "end_formatted": "00:10",
        "duration": 10.0,
        "duration_formatted": "10s",
        "text": "Text",
    }
    assert c["rank"] == 1

    t: TranscriptSegment = {
        "text": "Hello",
        "start": 0.0,
        "end": 1.0,
        "duration": 1.0,
    }
    assert t["text"] == "Hello"

    w: WordSegment = {
        "word": "Hello",
        "start": 0.0,
        "end": 0.5,
    }
    assert w["word"] == "Hello"

    r: RenderResult = {
        "clip_id": "c1",
        "render_path": "/path/to/clip.mp4",
        "render_mode": "square",
        "file_size": 1024,
        "success": True,
        "error": None,
    }
    assert r["success"] is True
