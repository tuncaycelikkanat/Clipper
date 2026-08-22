import re
from typing import Dict, Any, List, Optional
import yt_dlp

class YouTubeExtractor:
    """Extracts metadata and Most Replayed (Heatmap) data from YouTube videos."""

    @staticmethod
    def clean_url(url_or_id: str) -> str:
        url_or_id = url_or_id.strip()
        # If it's a raw 11-char ID
        if re.match(r'^[a-zA-Z0-9_-]{11}$', url_or_id):
            return f"https://www.youtube.com/watch?v={url_or_id}"
        return url_or_id

    @classmethod
    def get_video_data(cls, url: str) -> Dict[str, Any]:
        """
        Fetches video info and heatmap data from YouTube.
        Returns a dictionary with title, duration, thumbnail, channel, heatmap list, etc.
        """
        cleaned_url = cls.clean_url(url)
        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(cleaned_url, download=False)
        except Exception as e:
            raise RuntimeError(f"Video bilgileri çekilemedi: {str(e)}")

        heatmap_raw = info.get("heatmap") or []
        
        # Format heatmap into standardized list of dicts
        heatmap = []
        for point in heatmap_raw:
            heatmap.append({
                "start_time": float(point.get("start_time", 0.0)),
                "end_time": float(point.get("end_time", 0.0)),
                "value": float(point.get("value", 0.0))
            })

        duration = int(info.get("duration", 0))
        
        return {
            "id": info.get("id"),
            "url": cleaned_url,
            "title": info.get("title", "Bilinmeyen Video"),
            "uploader": info.get("uploader") or info.get("channel", "Bilinmeyen Kanal"),
            "duration": duration,
            "duration_formatted": cls.format_seconds(duration),
            "thumbnail": info.get("thumbnail"),
            "view_count": info.get("view_count", 0),
            "has_heatmap": len(heatmap) > 0,
            "heatmap": heatmap
        }

    @classmethod
    def get_video_comments(cls, url: str, max_comments: int = 50) -> List[Dict[str, Any]]:
        """
        Fetches top comments for a video using yt-dlp.
        Returns a list of dicts: [{'text': str, 'like_count': int, 'author': str}]
        """
        cleaned_url = cls.clean_url(url)
        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'getcomments': True,
            'extractor_args': {
                'youtube': {
                    'max_comments': [str(max_comments), 'all', '0', '0']
                }
            },
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(cleaned_url, download=False)
                comments_raw = info.get("comments") or []
                formatted = []
                for c in comments_raw:
                    formatted.append({
                        "text": c.get("text", "") or "",
                        "like_count": int(c.get("like_count", 0) or 0),
                        "author": c.get("author", "") or "",
                    })
                return formatted
        except Exception:
            return []

    @staticmethod
    def format_seconds(seconds: float) -> str:
        """Formats seconds into mm:ss or hh:mm:ss string."""
        s = int(seconds)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

