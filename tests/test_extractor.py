from unittest.mock import MagicMock, patch

import pytest

from core.extractor import YouTubeExtractor


def test_clean_url():
    # Test valid 11 char ID
    assert YouTubeExtractor.clean_url("dQw4w9WgXcQ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    # Test full url
    assert (
        YouTubeExtractor.clean_url("https://youtube.com/watch?v=dQw4w9WgXcQ")
        == "https://youtube.com/watch?v=dQw4w9WgXcQ"
    )
    # Test whitespace
    assert YouTubeExtractor.clean_url("  dQw4w9WgXcQ  ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_format_seconds():
    assert YouTubeExtractor.format_seconds(45) == "00:45"
    assert YouTubeExtractor.format_seconds(125) == "02:05"
    assert YouTubeExtractor.format_seconds(3665) == "01:01:05"


@patch("core.extractor.yt_dlp.YoutubeDL")
def test_get_video_data_success(mock_ytdl):
    mock_instance = MagicMock()
    mock_ytdl.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {
        "id": "dQw4w9WgXcQ",
        "title": "Rick Astley",
        "uploader": "Rick",
        "duration": 212,
        "thumbnail": "http://example.com/thumb.jpg",
        "view_count": 1000,
        "heatmap": [
            {"start_time": 0.0, "end_time": 10.0, "value": 0.5},
            {"start_time": 10.0, "end_time": 20.0, "value": 0.8},
        ],
    }

    result = YouTubeExtractor.get_video_data("dQw4w9WgXcQ")
    assert result["id"] == "dQw4w9WgXcQ"
    assert result["title"] == "Rick Astley"
    assert result["uploader"] == "Rick"
    assert result["duration"] == 212
    assert result["duration_formatted"] == "03:32"
    assert result["thumbnail"] == "http://example.com/thumb.jpg"
    assert result["view_count"] == 1000
    assert result["has_heatmap"] is True
    assert len(result["heatmap"]) == 2
    assert result["heatmap"][0]["value"] == 0.5


@patch("core.extractor.yt_dlp.YoutubeDL")
def test_get_video_data_defaults(mock_ytdl):
    mock_instance = MagicMock()
    mock_ytdl.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {}  # Empty info

    result = YouTubeExtractor.get_video_data("dQw4w9WgXcQ")
    assert result["title"] == "Bilinmeyen Video"
    assert result["uploader"] == "Bilinmeyen Kanal"
    assert result["duration"] == 0
    assert result["duration_formatted"] == "00:00"
    assert result["view_count"] == 0
    assert result["has_heatmap"] is False
    assert result["heatmap"] == []


@patch("core.extractor.yt_dlp.YoutubeDL")
def test_get_video_data_uploader_fallback(mock_ytdl):
    mock_instance = MagicMock()
    mock_ytdl.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {"channel": "Channel Name"}

    result = YouTubeExtractor.get_video_data("dQw4w9WgXcQ")
    assert result["uploader"] == "Channel Name"


@patch("core.extractor.yt_dlp.YoutubeDL")
def test_get_video_data_exception(mock_ytdl):
    mock_instance = MagicMock()
    mock_ytdl.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.side_effect = Exception("Network Error")

    with pytest.raises(RuntimeError, match="Video bilgileri çekilemedi: Network Error"):
        YouTubeExtractor.get_video_data("dQw4w9WgXcQ")


@patch("core.extractor.yt_dlp.YoutubeDL")
def test_get_video_comments_success(mock_ytdl):
    mock_instance = MagicMock()
    mock_ytdl.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {
        "comments": [
            {"text": "05:32 efsane", "like_count": 12, "author": "user1"},
            {"text": "güzel video", "like_count": 0, "author": "user2"},
        ]
    }

    comments = YouTubeExtractor.get_video_comments("dQw4w9WgXcQ")
    assert len(comments) == 2
    assert comments[0]["text"] == "05:32 efsane"
    assert comments[0]["like_count"] == 12


@patch("core.extractor.yt_dlp.YoutubeDL")
def test_get_video_comments_exception(mock_ytdl):
    mock_instance = MagicMock()
    mock_ytdl.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.side_effect = Exception("Disabled comments")

    comments = YouTubeExtractor.get_video_comments("dQw4w9WgXcQ")
    assert comments == []


def test_calculate_recommended_clips():
    # 2 min video
    res_short = YouTubeExtractor.calculate_recommended_clips(120)
    assert res_short["recommended_clips"] == 2
    assert res_short["tier_label"] == "Çok Kısa Video"

    # 10 min video
    res_med = YouTubeExtractor.calculate_recommended_clips(600)
    assert res_med["recommended_clips"] == 5

    # 37 min video
    res_37 = YouTubeExtractor.calculate_recommended_clips(2220)
    assert res_37["recommended_clips"] == 10
    assert "8 - 14" in res_37["clip_range"]

    # 75 min video
    res_long = YouTubeExtractor.calculate_recommended_clips(4500)
    assert res_long["recommended_clips"] == 15

    # 180 min marathon
    res_marathon = YouTubeExtractor.calculate_recommended_clips(10800)
    assert res_marathon["recommended_clips"] >= 20
