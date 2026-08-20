import pytest
from unittest import mock
from core.feed import ChannelFeed

def test_get_channel_videos_success():
    with mock.patch("core.feed.yt_dlp.YoutubeDL") as mock_ytdl:
        instance = mock_ytdl.return_value.__enter__.return_value
        instance.extract_info.return_value = {
            "entries": [
                {
                    "id": "vid1",
                    "title": "Test Video 1",
                    "upload_date": "20231010",
                    "duration": 300,
                    "view_count": 1000
                },
                {
                    "id": "vid2",
                    "title": "Test Video 2",
                    "upload_date": "20231011",
                    "duration": 400,
                    "view_count": 2000
                }
            ]
        }
        
        videos = ChannelFeed.get_channel_videos("http://test.url", max_count=2)
        assert len(videos) == 2
        # Should be sorted by upload_date descending
        assert videos[0]["id"] == "vid2"
        assert videos[1]["id"] == "vid1"

def test_get_channel_videos_missing_data():
    with mock.patch("core.feed.yt_dlp.YoutubeDL") as mock_ytdl:
        instance = mock_ytdl.return_value.__enter__.return_value
        instance.extract_info.return_value = {
            "entries": [
                None,
                {"title": "No ID"},
                {"id": "vid3"},  # Missing title, date, etc.
            ]
        }
        
        videos = ChannelFeed.get_channel_videos("http://test.url", max_count=10)
        assert len(videos) == 1
        assert videos[0]["id"] == "vid3"
        assert videos[0]["title"] == "Ba\u015fl\u0131ks\u0131z"
        assert videos[0]["upload_date"] == ""
        assert videos[0]["duration"] == 0
        assert videos[0]["view_count"] == 0

def test_get_channel_videos_yt_dlp_exception():
    with mock.patch("core.feed.yt_dlp.YoutubeDL") as mock_ytdl:
        instance = mock_ytdl.return_value.__enter__.return_value
        instance.extract_info.side_effect = Exception("ytdl error")
        with pytest.raises(RuntimeError, match="Kanal/oynatma listesi bilgileri al\u0131namad\u0131"):
            ChannelFeed.get_channel_videos("http://test.url")

def test_get_channel_videos_info_none():
    with mock.patch("core.feed.yt_dlp.YoutubeDL") as mock_ytdl:
        instance = mock_ytdl.return_value.__enter__.return_value
        instance.extract_info.return_value = None
        with pytest.raises(RuntimeError, match="veri d\u00f6nd\u00fcrmedi"):
            ChannelFeed.get_channel_videos("http://test.url")

def test_get_channel_videos_entries_none():
    with mock.patch("core.feed.yt_dlp.YoutubeDL") as mock_ytdl:
        instance = mock_ytdl.return_value.__enter__.return_value
        instance.extract_info.return_value = {}  # no 'entries' key
        videos = ChannelFeed.get_channel_videos("http://test.url")
        assert videos == []

def test_get_new_videos_filters_processed():
    with mock.patch.object(ChannelFeed, "get_channel_videos") as mock_get_channel_videos:
        mock_get_channel_videos.return_value = [
            {"id": "vid3", "title": "Vid 3", "upload_date": "20231012"},
            {"id": "vid2", "title": "Vid 2", "upload_date": "20231011"},
            {"id": "vid1", "title": "Vid 1", "upload_date": "20231010"},
        ]
        
        processed = ["vid2", "vid1"]
        new_videos = ChannelFeed.get_new_videos("http://test.url", processed_ids=processed, max_count=5)
        
        assert len(new_videos) == 1
        assert new_videos[0]["id"] == "vid3"

def test_get_new_videos_truncates():
    with mock.patch.object(ChannelFeed, "get_channel_videos") as mock_get_channel_videos:
        mock_get_channel_videos.return_value = [
            {"id": "vid3", "title": "Vid 3", "upload_date": "20231012"},
            {"id": "vid2", "title": "Vid 2", "upload_date": "20231011"},
            {"id": "vid1", "title": "Vid 1", "upload_date": "20231010"},
        ]
        
        processed = []
        new_videos = ChannelFeed.get_new_videos("http://test.url", processed_ids=processed, max_count=2)
        
        assert len(new_videos) == 2
        assert new_videos[0]["id"] == "vid3"
        assert new_videos[1]["id"] == "vid2"

def test_get_video_ids_from_playlist_success():
    with mock.patch("core.feed.yt_dlp.YoutubeDL") as mock_ytdl:
        instance = mock_ytdl.return_value.__enter__.return_value
        instance.extract_info.return_value = {
            "entries": [
                {"id": "vidA"},
                None,
                {"title": "No ID"},
                {"id": "vidB"}
            ]
        }
        ids = ChannelFeed.get_video_ids_from_playlist("http://playlist")
        assert ids == ["vidA", "vidB"]

def test_get_video_ids_from_playlist_info_none():
    with mock.patch("core.feed.yt_dlp.YoutubeDL") as mock_ytdl:
        instance = mock_ytdl.return_value.__enter__.return_value
        instance.extract_info.return_value = None
        ids = ChannelFeed.get_video_ids_from_playlist("http://playlist")
        assert ids == []

def test_get_video_ids_from_playlist_entries_none():
    with mock.patch("core.feed.yt_dlp.YoutubeDL") as mock_ytdl:
        instance = mock_ytdl.return_value.__enter__.return_value
        instance.extract_info.return_value = {} # missing entries
        ids = ChannelFeed.get_video_ids_from_playlist("http://playlist")
        assert ids == []

def test_get_video_ids_from_playlist_exception():
    with mock.patch("core.feed.yt_dlp.YoutubeDL") as mock_ytdl:
        instance = mock_ytdl.return_value.__enter__.return_value
        instance.extract_info.side_effect = Exception("ytdl error")
        with pytest.raises(RuntimeError, match="Oynatma listesi ID'leri al\u0131namad\u0131"):
            ChannelFeed.get_video_ids_from_playlist("http://playlist")
