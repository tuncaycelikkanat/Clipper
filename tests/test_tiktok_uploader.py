"""
tests/test_tiktok_uploader.py — Unit tests for TikTokUploader (Direct Post API v2)
"""

from unittest.mock import MagicMock, patch
import pytest

from core.tiktok_uploader import TikTokUploader


@pytest.fixture
def tt_uploader():
    return TikTokUploader(access_token="fake_tiktok_token_abc", session_id="")


def test_is_authenticated_true(tt_uploader):
    assert tt_uploader.is_authenticated() is True


def test_is_authenticated_false():
    uploader = TikTokUploader(access_token="", session_id="")
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
@patch.object(TikTokUploader, "check_publish_status")
def test_upload_video_end_to_end(mock_check, mock_binary, mock_init, tt_uploader, tmp_path):
    video_file = tmp_path / "tt_clip2.mp4"
    video_file.write_bytes(b"tiktok_test_binary")

    mock_init.return_value = {
        "publish_id": "pub_e2e_1",
        "upload_url": "https://upload.tiktok.com/pub_e2e_1",
    }
    mock_binary.return_value = True
    mock_check.return_value = {"status": "PUBLISH_COMPLETE"}

    res = tt_uploader.upload_video(
        video_path=str(video_file),
        title="Test Reel",
    )
    assert res["status"] == "uploaded"
    assert res["publish_id"] == "pub_e2e_1"



def test_upload_video_file_not_found(tt_uploader):
    with pytest.raises(FileNotFoundError):
        tt_uploader.upload_video("/non/existent/path/vid.mp4", title="Title")


def test_get_authorization_url():
    url = TikTokUploader.get_authorization_url(client_key="test_key_123")
    assert "https://www.tiktok.com/v2/auth/authorize/" in url
    assert "client_key=test_key_123" in url
    assert "video.publish" in url


@patch("requests.post")
def test_exchange_code_for_token_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "access_token": "act.test_token_123",
            "open_id": "_000test_open_id",
            "refresh_token": "rft.test_refresh_123",
            "expires_in": 86400,
        },
        "error": {"code": "ok", "message": ""},
    }
    mock_post.return_value = mock_resp

    res = TikTokUploader.exchange_code_for_token(
        code="auth_code_xyz",
        client_key="k1",
        client_secret="s1",
    )
    assert res["access_token"] == "act.test_token_123"
    assert res["open_id"] == "_000test_open_id"


@patch("requests.post")
def test_exchange_code_for_token_error(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {
        "error": {"code": "invalid_grant", "message": "Code expired"}
    }
    mock_post.return_value = mock_resp

    with pytest.raises(RuntimeError, match="TikTok token değişimi başarısız"):
        TikTokUploader.exchange_code_for_token(
            code="expired_code",
            client_key="k1",
            client_secret="s1",
        )


@patch("subprocess.run")
def test_upload_video_session_cookie_success(mock_subproc, tmp_path):
    uploader = TikTokUploader(session_id="fake_session_123", access_token="")
    assert uploader.is_authenticated() is True

    video_file = tmp_path / "tt_cookie.mp4"
    video_file.write_bytes(b"data")

    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "SUCCESS"
    mock_subproc.return_value = mock_res

    res = uploader.upload_video(str(video_file), title="Cookie Clip")
    assert res["status"] == "uploaded"
    assert res["publish_id"] == "cookie_session_post"
    mock_subproc.assert_called_once()


@patch("subprocess.run")
def test_upload_video_session_cookie_error(mock_subproc, tmp_path):
    uploader = TikTokUploader(session_id="fake_session_123", access_token="")
    video_file = tmp_path / "tt_cookie2.mp4"
    video_file.write_bytes(b"data")

    mock_res = MagicMock()
    mock_res.returncode = 1
    mock_res.stderr = "Login failed"
    mock_subproc.return_value = mock_res

    with pytest.raises(RuntimeError, match="TikTok çerez ile yükleme başarısız"):
        uploader.upload_video(str(video_file), title="Cookie Clip")


