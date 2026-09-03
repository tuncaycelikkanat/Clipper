"""
tests/test_ai_thumbnail_engine.py — Unit tests for AIThumbnailEngine
"""

import io
import os
import pytest
from unittest.mock import MagicMock, patch
from PIL import Image

from core.ai_thumbnail_engine import AIThumbnailEngine
from core.thumbnail import ThumbnailGenerator


@pytest.fixture
def sample_image_path(tmp_path):
    img = Image.new("RGB", (1280, 720), color=(255, 0, 0))
    path = str(tmp_path / "sample_16x9.jpg")
    img.save(path, "JPEG")
    return path


def test_extract_youtube_id():
    assert AIThumbnailEngine.extract_youtube_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert AIThumbnailEngine.extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert AIThumbnailEngine.extract_youtube_id("https://youtu.be/dQw4w9WgXcQ?t=10") == "dQw4w9WgXcQ"
    assert AIThumbnailEngine.extract_youtube_id("invalid_url_without_id") is None
    assert AIThumbnailEngine.extract_youtube_id("") is None
    assert AIThumbnailEngine.extract_youtube_id(None) is None


def test_download_youtube_cover_success(tmp_path):
    engine = AIThumbnailEngine(api_key="fake_key")
    out_path = str(tmp_path / "cover.jpg")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b"x" * 3000
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = engine.download_youtube_cover("https://youtu.be/dQw4w9WgXcQ", out_path)
        assert result == out_path
        assert os.path.exists(out_path)


def test_download_youtube_cover_not_found(tmp_path):
    engine = AIThumbnailEngine(api_key="fake_key")
    out_path = str(tmp_path / "cover.jpg")

    with patch("urllib.request.urlopen", side_effect=Exception("404 Not Found")):
        result = engine.download_youtube_cover("dQw4w9WgXcQ", out_path)
        assert result is None


def test_download_youtube_cover_invalid_id(tmp_path):
    engine = AIThumbnailEngine(api_key="fake_key")
    out_path = str(tmp_path / "cover.jpg")
    result = engine.download_youtube_cover("invalid", out_path)
    assert result is None


def test_generate_vertical_thumbnail_missing_source():
    engine = AIThumbnailEngine(api_key="fake_key")
    with pytest.raises(FileNotFoundError):
        engine.generate_vertical_thumbnail("non_existent.jpg", "out.jpg")


def test_generate_vertical_thumbnail_no_client(sample_image_path, tmp_path):
    engine = AIThumbnailEngine(api_key=None)
    engine.client = None
    out_path = str(tmp_path / "out_vertical.jpg")
    res = engine.generate_vertical_thumbnail(sample_image_path, out_path)
    assert res is None


def test_generate_vertical_thumbnail_ai_success(sample_image_path, tmp_path):
    engine = AIThumbnailEngine(api_key="fake_key")
    out_path = str(tmp_path / "out_vertical.jpg")

    # Create dummy returned image bytes
    dummy_img = Image.new("RGB", (720, 1080), color=(0, 255, 0))
    buf = io.BytesIO()
    dummy_img.save(buf, "JPEG")
    dummy_bytes = buf.getvalue()

    mock_part = MagicMock()
    mock_part.inline_data.data = dummy_bytes

    mock_candidate = MagicMock()
    mock_candidate.content.parts = [mock_part]

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]

    engine.client = MagicMock()
    engine.client.models.generate_content.return_value = mock_response

    res = engine.generate_vertical_thumbnail(sample_image_path, out_path, aspect_ratio="2:3")
    assert res == out_path
    assert os.path.exists(out_path)

    # Verify generated image is valid
    saved_img = Image.open(out_path)
    assert saved_img.size == (720, 1080)


def test_generate_vertical_thumbnail_fallback_crop(sample_image_path, tmp_path):
    engine = AIThumbnailEngine(api_key="fake_key")
    out_path = str(tmp_path / "out_vertical_crop.jpg")

    # Mock AI failure on all models
    engine.client = MagicMock()
    engine.client.models.generate_content.side_effect = Exception("API Quota Error")

    res = engine.generate_vertical_thumbnail(sample_image_path, out_path, aspect_ratio="2:3")
    assert res == out_path
    assert os.path.exists(out_path)

    # Verify 2:3 ratio aspect
    saved_img = Image.open(out_path)
    w, h = saved_img.size
    assert abs((w / h) - (2.0 / 3.0)) < 0.05


def test_fallback_local_crop_ratios(sample_image_path, tmp_path):
    engine = AIThumbnailEngine(api_key="fake_key")

    out_2x3 = str(tmp_path / "crop_2x3.jpg")
    res1 = engine._fallback_local_crop(sample_image_path, out_2x3, aspect_ratio="2:3")
    assert res1 == out_2x3
    img1 = Image.open(out_2x3)
    assert abs((img1.width / img1.height) - (2.0 / 3.0)) < 0.05

    out_9x16 = str(tmp_path / "crop_9x16.jpg")
    res2 = engine._fallback_local_crop(sample_image_path, out_9x16, aspect_ratio="9:16")
    assert res2 == out_9x16
    img2 = Image.open(out_9x16)
    assert abs((img2.width / img2.height) - (9.0 / 16.0)) < 0.05

    # Test failure branch
    res3 = engine._fallback_local_crop("invalid_file.jpg", "out.jpg")
    assert res3 is None


def test_process_video_to_thumbnail_end_to_end(sample_image_path, tmp_path):
    engine = AIThumbnailEngine(api_key="fake_key")
    out_path = str(tmp_path / "final_thumb.jpg")

    with patch.object(engine, "download_youtube_cover", return_value=sample_image_path), \
         patch.object(engine, "generate_vertical_thumbnail", return_value=out_path):
        res = engine.process_video_to_thumbnail("https://youtu.be/dQw4w9WgXcQ", out_path)
        assert res == out_path


def test_process_video_to_thumbnail_download_fails(tmp_path):
    engine = AIThumbnailEngine(api_key="fake_key")
    out_path = str(tmp_path / "final_thumb.jpg")

    with patch.object(engine, "download_youtube_cover", return_value=None):
        res = engine.process_video_to_thumbnail("invalid", out_path)
        assert res is None


def test_thumbnail_generator_ai_vertical_method(sample_image_path, tmp_path):
    out_path = str(tmp_path / "gen_ai_vertical.jpg")
    with patch("core.ai_thumbnail_engine.AIThumbnailEngine.process_video_to_thumbnail", return_value=out_path):
        res = ThumbnailGenerator.generate_ai_vertical_thumbnail("https://youtu.be/dQw4w9WgXcQ", out_path)
        assert res == out_path

    # Test error fallback branch
    with patch("core.ai_thumbnail_engine.AIThumbnailEngine.process_video_to_thumbnail", side_effect=Exception("boom")):
        res_fail = ThumbnailGenerator.generate_ai_vertical_thumbnail("bad_url", out_path)
        assert res_fail is None
