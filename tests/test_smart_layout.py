"""
tests/test_smart_layout.py — Comprehensive tests for SmartLayoutEngine (100% target)
"""

from unittest.mock import MagicMock, patch

from core.smart_layout import SmartLayoutEngine


def test_smart_layout_filter_no_facecam():
    engine = SmartLayoutEngine()
    filter_str, has_cam = engine.build_ffmpeg_filter(
        src_w=1920, src_h=1080, facecam_info={"found": False, "corner": "none"}
    )
    assert has_cam is False
    assert "boxblur" in filter_str
    assert "scale=1080:1320" in filter_str
    assert "overlay=0:300" in filter_str


def test_smart_layout_filter_with_facecam():
    engine = SmartLayoutEngine()
    filter_str, has_cam = engine.build_ffmpeg_filter(
        src_w=1920,
        src_h=1080,
        facecam_info={
            "found": True,
            "corner": "left_center",
            "box_1000": {"ymin": 300, "xmin": 0, "ymax": 600, "xmax": 300},
        },
    )
    assert has_cam is True
    assert "vstack=inputs=2" in filter_str
    assert "scale=1080:" in filter_str


def test_smart_layout_detect_facecam_fallback_no_client():
    engine = SmartLayoutEngine()
    engine.client = None
    res = engine.detect_facecam("/fake/video.mp4")
    assert res["found"] is False
    assert res["corner"] == "none"


@patch("subprocess.run")
def test_smart_layout_detect_facecam_gemini_success(mock_subproc):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = (
        '{"found": true, "corner": "bottom_left", "box_1000": {"ymin": 500, "xmin": 0, "ymax": 900, "xmax": 400}}'
    )
    mock_client.models.generate_content.return_value = mock_response

    engine = SmartLayoutEngine()
    engine.client = mock_client

    # FFmpeg pipe output mock
    mock_proc = MagicMock()
    mock_proc.stdout = b"fake_jpeg_bytes" * 100
    mock_subproc.return_value = mock_proc

    res = engine.detect_facecam("/fake/video.mp4", sample_time_sec=2.0)
    assert res["found"] is True
    assert res["corner"] == "bottom_left"
    assert res["box_1000"]["ymax"] == 900


@patch("subprocess.run")
def test_smart_layout_detect_facecam_gemini_exception(mock_subproc):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("API Timeout")

    engine = SmartLayoutEngine()
    engine.client = mock_client

    mock_proc = MagicMock()
    mock_proc.stdout = b"fake_jpeg_bytes" * 100
    mock_subproc.return_value = mock_proc

    res = engine.detect_facecam("/fake/video.mp4")
    assert res["found"] is False
    assert res["corner"] == "none"


@patch("subprocess.run")
def test_smart_layout_detect_facecam_empty_ffmpeg_output(mock_subproc):
    mock_client = MagicMock()
    engine = SmartLayoutEngine()
    engine.client = mock_client

    mock_proc = MagicMock()
    mock_proc.stdout = b""
    mock_subproc.return_value = mock_proc

    res = engine.detect_facecam("/fake/video.mp4")
    assert res["found"] is False
