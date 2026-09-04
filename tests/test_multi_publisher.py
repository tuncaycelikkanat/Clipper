"""
tests/test_multi_publisher.py — Unit tests for MultiPublisher orchestrator (100% coverage)
"""

from unittest.mock import MagicMock

import pytest

from core.multi_publisher import MultiPublisher


@pytest.fixture
def mock_uploaders():
    yt = MagicMock()
    ig = MagicMock()
    notif = MagicMock()
    return yt, ig, notif


def test_get_auth_status(mock_uploaders):
    yt, ig, notif = mock_uploaders
    yt.is_authenticated.return_value = True
    ig.is_authenticated.return_value = False

    pub = MultiPublisher(youtube_uploader=yt, instagram_uploader=ig, notifier=notif)
    status = pub.get_auth_status()
    assert status["youtube"] is True
    assert status["instagram"] is False


def test_publish_clip_all_success(mock_uploaders, tmp_path):
    yt, ig, notif = mock_uploaders
    yt.is_authenticated.return_value = True
    ig.is_authenticated.return_value = True

    yt.upload_short.return_value = {"video_id": "yt123", "url": "https://youtube.com/shorts/yt123"}
    ig.upload_reel.return_value = {"media_id": "ig123", "url": "https://instagram.com/reel/ig123"}

    fake_video = tmp_path / "clip.mp4"
    fake_video.write_bytes(b"data")

    pub = MultiPublisher(youtube_uploader=yt, instagram_uploader=ig, notifier=notif)
    results = pub.publish_clip(
        clip={"title": "Awesome Highlight", "hook_caption": "Unbelievable!"},
        render_path=str(fake_video),
        video_title="Main Stream",
        platforms=["youtube", "instagram"],
    )

    assert results["youtube"]["status"] == "success"
    assert results["instagram"]["status"] == "success"


def test_publish_clip_with_description_override(mock_uploaders, tmp_path):
    yt, ig, notif = mock_uploaders
    yt.is_authenticated.return_value = True
    ig.is_authenticated.return_value = True
    yt.upload_short.return_value = {"video_id": "yt123", "url": "https://youtube.com/shorts/yt123"}
    ig.upload_reel.return_value = {"media_id": "ig123", "url": "https://instagram.com/reel/ig123"}

    fake_video = tmp_path / "clip_desc.mp4"
    fake_video.write_bytes(b"data")

    pub = MultiPublisher(youtube_uploader=yt, instagram_uploader=ig, notifier=notif)
    results = pub.publish_clip(
        clip={"title": "Test Title", "video_id": "vid_src_01"},
        render_path=str(fake_video),
        description_override="Özel Açıklama Metni",
        source_video_id="vid_src_01",
        source_video_url="https://youtube.com/watch?v=vid_src_01",
        platforms=["youtube", "instagram"],
    )
    assert results["youtube"]["status"] == "success"
    assert results["instagram"]["status"] == "success"


def test_publish_clip_exceptions_handled(mock_uploaders, tmp_path):
    yt, ig, notif = mock_uploaders
    yt.is_authenticated.return_value = True
    ig.is_authenticated.return_value = True
    yt.upload_short.side_effect = Exception("YouTube Quota Error")
    ig.upload_reel.side_effect = Exception("Instagram Token Expired")

    fake_video = tmp_path / "clip_err.mp4"
    fake_video.write_bytes(b"data")

    pub = MultiPublisher(youtube_uploader=yt, instagram_uploader=ig, notifier=notif)
    results = pub.publish_clip(
        clip={"title": "Error Clip"}, render_path=str(fake_video), platforms=["youtube", "instagram"]
    )
    assert results["youtube"]["status"] == "failed"
    assert "YouTube Quota Error" in results["youtube"]["error"]
    assert results["instagram"]["status"] == "failed"
    assert "Instagram Token Expired" in results["instagram"]["error"]


def test_publish_clip_skips_unauthenticated(mock_uploaders, tmp_path):
    yt, ig, notif = mock_uploaders
    yt.is_authenticated.return_value = False
    ig.is_authenticated.return_value = False

    fake_video = tmp_path / "clip2.mp4"
    fake_video.write_bytes(b"data")

    pub = MultiPublisher(youtube_uploader=yt, instagram_uploader=ig, notifier=notif)
    results = pub.publish_clip(clip={"title": "Test"}, render_path=str(fake_video), platforms=["youtube", "instagram"])

    assert results["youtube"]["status"] == "skipped"
    assert results["instagram"]["status"] == "skipped"


def test_publish_clip_not_found(mock_uploaders):
    pub = MultiPublisher()
    with pytest.raises(FileNotFoundError):
        pub.publish_clip(clip={}, render_path="/non/existent/path.mp4")
