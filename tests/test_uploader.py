import os
from unittest import mock
import pytest
from pathlib import Path

from core.uploader import YouTubeUploader

@pytest.fixture
def uploader(tmp_path):
    creds_path = tmp_path / "credentials.json"
    token_path = tmp_path / "token.json"
    return YouTubeUploader(credentials_path=str(creds_path), token_path=str(token_path))

def test_is_authenticated_false_when_no_token(uploader):
    assert uploader.is_authenticated() is False

@mock.patch("core.uploader.Credentials")
def test_is_authenticated_valid(mock_creds_cls, uploader):
    # Setup token file
    with open(uploader.token_path, "w") as f:
        f.write("{}")
    
    mock_creds = mock.MagicMock()
    mock_creds.valid = True
    mock_creds_cls.from_authorized_user_file.return_value = mock_creds
    
    assert uploader.is_authenticated() is True
    assert uploader._credentials == mock_creds

@mock.patch("core.uploader.Request")
@mock.patch("core.uploader.Credentials")
def test_is_authenticated_refresh(mock_creds_cls, mock_req_cls, uploader):
    with open(uploader.token_path, "w") as f:
        f.write("{}")
    
    mock_creds = mock.MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "some_token"
    mock_creds.to_json.return_value = '{"token": "new"}'
    mock_creds_cls.from_authorized_user_file.return_value = mock_creds
    
    assert uploader.is_authenticated() is True
    assert uploader._credentials == mock_creds
    mock_creds.refresh.assert_called_once()
    
    with open(uploader.token_path, "r") as f:
        assert f.read() == '{"token": "new"}'

@mock.patch("core.uploader.Credentials")
def test_is_authenticated_exception(mock_creds_cls, uploader):
    with open(uploader.token_path, "w") as f:
        f.write("{}")
    
    mock_creds_cls.from_authorized_user_file.side_effect = Exception("error")
    assert uploader.is_authenticated() is False

def test_authenticate_no_credentials_file(uploader):
    with pytest.raises(FileNotFoundError, match="YouTube API credentials not found"):
        uploader.authenticate()

@mock.patch("core.uploader.InstalledAppFlow")
def test_authenticate_success(mock_flow_cls, uploader):
    with open(uploader.credentials_path, "w") as f:
        f.write("{}")
    
    mock_flow = mock.MagicMock()
    mock_creds = mock.MagicMock()
    mock_creds.to_json.return_value = '{"test": "creds"}'
    mock_flow.run_local_server.return_value = mock_creds
    mock_flow_cls.from_client_secrets_file.return_value = mock_flow
    
    uploader.authenticate()
    
    assert uploader._credentials == mock_creds
    with open(uploader.token_path, "r") as f:
        assert f.read() == '{"test": "creds"}'

def test_get_credentials_already_valid(uploader):
    mock_creds = mock.MagicMock()
    mock_creds.valid = True
    uploader._credentials = mock_creds
    
    assert uploader._get_credentials() == mock_creds

@mock.patch.object(YouTubeUploader, "is_authenticated")
def test_get_credentials_calls_is_authenticated(mock_is_auth, uploader):
    mock_is_auth.return_value = True
    mock_creds = mock.MagicMock()
    uploader._credentials = mock_creds
    
    assert uploader._get_credentials() == mock_creds

@mock.patch.object(YouTubeUploader, "is_authenticated")
def test_get_credentials_unauthenticated(mock_is_auth, uploader):
    mock_is_auth.return_value = False
    with pytest.raises(RuntimeError, match="Not authenticated"):
        uploader._get_credentials()

def test_upload_short_file_not_found(uploader):
    with pytest.raises(FileNotFoundError, match="Video file not found"):
        uploader.upload_short("nonexistent.mp4", "Title")

@mock.patch("core.uploader.MediaFileUpload")
@mock.patch("core.uploader.build")
@mock.patch.object(YouTubeUploader, "_get_credentials")
def test_upload_short_success(mock_get_creds, mock_build, mock_media_upload, uploader, tmp_path):
    video_path = tmp_path / "test.mp4"
    with open(video_path, "w") as f:
        f.write("dummy video data")
        
    mock_get_creds.return_value = mock.MagicMock()
    mock_youtube = mock.MagicMock()
    mock_build.return_value = mock_youtube
    
    mock_request = mock.MagicMock()
    # next_chunk returns (status, response)
    # first call: (progress, None)
    # second call: (None, response)
    mock_status = mock.MagicMock()
    mock_status.progress.return_value = 0.5
    mock_request.next_chunk.side_effect = [
        (mock_status, None),
        (None, {"id": "test_video_id", "status": {"uploadStatus": "uploaded"}})
    ]
    mock_youtube.videos().insert.return_value = mock_request
    
    res = uploader.upload_short(
        video_path=str(video_path),
        title="My Title",
        description="My description without tag",
        tags=["gaming", "minecraft"]
    )
    
    assert res == {
        "video_id": "test_video_id",
        "url": "https://www.youtube.com/shorts/test_video_id",
        "status": "uploaded"
    }
    
    # Check that "#Shorts" was appended
    insert_kwargs = mock_youtube.videos().insert.call_args[1]
    body = insert_kwargs["body"]
    assert "#Shorts" in body["snippet"]["description"]
    assert body["snippet"]["title"] == "My Title"

def test_generate_description_contains_hook():
    clip = {
        "hook_caption": "Wait for the end!",
        "category": "Gaming",
        "reason": "Epic fail",
        "start_formatted": "01:00",
        "end_formatted": "01:30"
    }
    desc = YouTubeUploader.generate_description(clip, "My Minecraft Stream")
    assert "Wait for the end!" in desc
    assert "Gaming" in desc
    assert "Epic fail" in desc
    assert "My Minecraft Stream" in desc

def test_generate_description_no_hook_or_reason():
    clip = {
        "category": "IRL",
        "start_formatted": "00:00",
        "end_formatted": "00:30"
    }
    desc = YouTubeUploader.generate_description(clip, "Stream")
    assert "📌 Category: IRL" in desc
    assert "📺 Source: Stream" in desc
    assert "🎯" not in desc
    assert "💬" not in desc
