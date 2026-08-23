"""
tests/test_tiktok_uploader.py — Unit tests for TikTokUploader (Direct Post API v2)
"""

from unittest.mock import MagicMock, patch
import pytest

from core.tiktok_uploader import TikTokUploader


@pytest.fixture
def tt_uploader():
    return TikTokUploader(access_token="fake_tiktok_token_abc")


def test_is_authenticated_true(tt_uploader):
    assert tt_uploader.is_authenticated() is True


def test_is_authenticated_false():
    uploader = TikTokUploader(access_token="")
    assert uploader.is_authenticated() is False


@patch("requests.post")
def test_init_video_upload_success(mock_post, tt_uploader):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "publish_id": "pub_tt_123",
            "upload_url": "https://open-upload.tiktokapis.com/video/pub_tt_123",
        },
        "error": {"code": "ok", "message": ""},
    }
    mock_post.return_value = mock_resp

    res = tt_uploader.init_video_upload(file_size=5000000, title="Efsane Klip")
    assert res["publish_id"] == "pub_tt_123"
    assert "open-upload.tiktokapis.com" in res["upload_url"]


@patch("requests.post")
def test_init_video_upload_error(mock_post, tt_uploader):
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {
        "error": {"code": "invalid_params", "message": "Video size too large"}
    }
    mock_post.return_value = mock_resp

    with pytest.raises(RuntimeError, match="TikTok upload başlatılamadı"):
        tt_uploader.init_video_upload(file_size=999999999, title="Too big")


@patch("requests.put")
def test_upload_video_binary(mock_put, tt_uploader, tmp_path):
    video_file = tmp_path / "tt_clip.mp4"
    video_file.write_bytes(b"tiktok_sample_bytes")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_put.return_value = mock_resp

    success = tt_uploader.upload_video_binary(
        upload_url="https://open-upload.tiktokapis.com/upload",
        video_path=str(video_file),
    )
    assert success is True


@patch("requests.post")
def test_check_publish_status(mock_post, tt_uploader):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "status": "PUBLISH_COMPLETE",
            "fail_reason": "",
        }
    }
    mock_post.return_value = mock_resp

    res = tt_uploader.check_publish_status("pub_tt_123")
    assert res["status"] == "PUBLISH_COMPLETE"


def test_generate_caption():
    clip = {
        "title": "Oyunun En Komik Anı #Shorts",
        "hook_caption": "Gözlerime inanamadım!",
    }
    caption = TikTokUploader.generate_caption(clip)
    assert "Gözlerime inanamadım!" in caption
    assert "#fyp" in caption
    assert len(caption) <= 150


@patch.object(TikTokUploader, "init_video_upload")
@patch.object(TikTokUploader, "upload_video_binary")
def test_upload_video_end_to_end(mock_bin, mock_init, tt_uploader, tmp_path):
    video = tmp_path / "tt_sample.mp4"
    video.write_bytes(b"sample_tiktok_data")

    mock_init.return_value = {"publish_id": "p123", "upload_url": "https://upload.tiktok.com/p123"}
    mock_bin.return_value = True

    res = tt_uploader.upload_video(str(video), title="Sample Title")
    assert res["publish_id"] == "p123"
    assert res["status"] == "uploaded"


def test_upload_video_file_not_found(tt_uploader):
    with pytest.raises(FileNotFoundError):
        tt_uploader.upload_video("/non/existent/path.mp4", title="Title")

