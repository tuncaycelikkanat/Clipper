"""
tests/test_instagram_uploader.py — Unit tests for InstagramUploader (Meta Graph API)
"""

import os
from unittest.mock import MagicMock, patch
import pytest
import requests

from core.instagram_uploader import InstagramUploader


@pytest.fixture
def ig_uploader():
    return InstagramUploader(
        access_token="fake_meta_token_123",
        instagram_account_id="17841400000000",
    )


def test_is_authenticated_true(ig_uploader):
    assert ig_uploader.is_authenticated() is True


def test_is_authenticated_false():
    uploader = InstagramUploader(access_token="", instagram_account_id="")
    assert uploader.is_authenticated() is False


@patch("requests.post")
def test_create_resumable_container_success(mock_post, ig_uploader):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "container_999",
        "uri": "https://rupload.facebook.com/ig-reels-upload/container_999",
    }
    mock_post.return_value = mock_resp

    res = ig_uploader.create_resumable_container(file_size=1024 * 1024, caption="Test Reel")
    assert res["container_id"] == "container_999"
    assert "rupload.facebook.com" in res["upload_url"]


@patch("requests.post")
def test_create_resumable_container_error(mock_post, ig_uploader):
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {"error": {"message": "Invalid token"}}
    mock_post.return_value = mock_resp

    with pytest.raises(RuntimeError, match="Instagram Reels container oluşturulamadı"):
        ig_uploader.create_resumable_container(file_size=1000)


@patch("requests.post")
def test_upload_binary_to_container(mock_post, ig_uploader, tmp_path):
    video_file = tmp_path / "reel.mp4"
    video_file.write_bytes(b"dummy_video_bytes")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_post.return_value = mock_resp

    success = ig_uploader.upload_binary_to_container(
        upload_url="https://rupload.facebook.com/upload",
        video_path=str(video_file),
    )
    assert success is True


@patch("requests.get")
def test_check_container_status_finished(mock_get, ig_uploader):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status_code": "FINISHED"}
    mock_get.return_value = mock_resp

    status = ig_uploader.check_container_status("container_999", timeout=5, interval=0.1)
    assert status == "FINISHED"


@patch("requests.get")
def test_check_container_status_error(mock_get, ig_uploader):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status_code": "ERROR", "status": "Corrupt file"}
    mock_get.return_value = mock_resp

    with pytest.raises(RuntimeError, match="Instagram video işleme hatası"):
        ig_uploader.check_container_status("container_999", timeout=5, interval=0.1)


@patch("requests.post")
def test_publish_container_success(mock_post, ig_uploader):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "ig_media_12345"}
    mock_post.return_value = mock_resp

    res = ig_uploader.publish_container("container_999")
    assert res["media_id"] == "ig_media_12345"
    assert res["status"] == "published"
    assert "12345" in res["url"]


def test_generate_caption():
    clip = {
        "title": "İnanılmaz Vuruş #Shorts",
        "hook_caption": "Bunu kimse beklemiyordu!",
    }
    caption = InstagramUploader.generate_caption(clip, "Mithrain GTA")
    assert "Bunu kimse beklemiyordu!" in caption
    assert "#reels" in caption
    assert "Mithrain GTA" in caption


@patch.object(InstagramUploader, "create_resumable_container")
@patch.object(InstagramUploader, "upload_binary_to_container")
@patch.object(InstagramUploader, "check_container_status")
@patch.object(InstagramUploader, "publish_container")
def test_upload_reel_end_to_end(mock_pub, mock_chk, mock_bin, mock_init, ig_uploader, tmp_path):
    video = tmp_path / "sample_reel.mp4"
    video.write_bytes(b"sample_data")

    mock_init.return_value = {"container_id": "c123", "upload_url": "https://rupload.com/c123"}
    mock_bin.return_value = True
    mock_chk.return_value = "FINISHED"
    mock_pub.return_value = {"media_id": "m123", "url": "https://instagram.com/reel/m123", "status": "published"}

    res = ig_uploader.upload_reel(str(video), caption="Test Caption")
    assert res["media_id"] == "m123"
    assert res["status"] == "published"


def test_upload_reel_file_not_found(ig_uploader):
    with pytest.raises(FileNotFoundError):
        ig_uploader.upload_reel("/non/existent/file.mp4")


@patch("requests.get")
def test_check_container_status_timeout(mock_get, ig_uploader):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status_code": "IN_PROGRESS"}
    mock_get.return_value = mock_resp

    with pytest.raises(TimeoutError):
        ig_uploader.check_container_status("c123", timeout=0.1, interval=0.05)

