"""
tests/test_multi_publisher.py — Unit tests for MultiPublisher orchestrator
"""

from unittest.mock import MagicMock
import pytest

from core.multi_publisher import MultiPublisher


@pytest.fixture
def mock_uploaders():
    yt = MagicMock()
    ig = MagicMock()
    tt = MagicMock()
    notif = MagicMock()
    return yt, ig, tt, notif


def test_get_auth_status(mock_uploaders):
    yt, ig, tt, notif = mock_uploaders
    yt.is_authenticated.return_value = True
    ig.is_authenticated.return_value = False
    tt.is_authenticated.return_value = True

    pub = MultiPublisher(youtube_uploader=yt, instagram_uploader=ig, tiktok_uploader=tt, notifier=notif)
    status = pub.get_auth_status()
    assert status == {"youtube": True, "instagram": False, "tiktok": True}


def test_publish_clip_all_success(mock_uploaders, tmp_path):
    yt, ig, tt, notif = mock_uploaders
    yt.is_authenticated.return_value = True
    ig.is_authenticated.return_value = True
    tt.is_authenticated.return_value = True

    yt.upload_short.return_value = {"video_id": "yt123", "url": "https://youtube.com/shorts/yt123"}
    ig.upload_reel.return_value = {"media_id": "ig123", "url": "https://instagram.com/reel/ig123"}
    tt.upload_video.return_value = {"publish_id": "tt123", "url": "https://tiktok.com"}

    fake_video = tmp_path / "clip.mp4"
    fake_video.write_bytes(b"data")

    pub = MultiPublisher(youtube_uploader=yt, instagram_uploader=ig, tiktok_uploader=tt, notifier=notif)
    results = pub.publish_clip(
        clip={"title": "Awesome Highlight", "hook_caption": "Unbelievable!"},
        render_path=str(fake_video),
        platforms=["youtube", "instagram", "tiktok"],
        video_title="Main Stream",
    )

    assert results["youtube"]["status"] == "success"
    assert results["instagram"]["status"] == "success"
    assert results["tiktok"]["status"] == "success"


def test_publish_clip_skips_unauthenticated(mock_uploaders, tmp_path):
    yt, ig, tt, notif = mock_uploaders
    yt.is_authenticated.return_value = False
    ig.is_authenticated.return_value = False
    tt.is_authenticated.return_value = False

    fake_video = tmp_path / "clip2.mp4"
    fake_video.write_bytes(b"data")

    pub = MultiPublisher(youtube_uploader=yt, instagram_uploader=ig, tiktok_uploader=tt, notifier=notif)
    results = pub.publish_clip(
        clip={"title": "Test"},
        render_path=str(fake_video),
        platforms=["youtube", "instagram", "tiktok"],
    )

    assert results["youtube"]["status"] == "skipped"
    assert results["instagram"]["status"] == "skipped"
    assert results["tiktok"]["status"] == "skipped"
