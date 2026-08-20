from unittest import mock
import pytest
from core.feed import ChannelFeed

def test_get_channel_videos_returns_list():
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
        assert videos[0]["title"] == "Test Video 2"
        assert videos[1]["title"] == "Test Video 1"
        assert videos[0]["url"] == "https://www.youtube.com/watch?v=vid2"

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
