import os
import re
from typing import Any

import yt_dlp


class YouTubeExtractor:
    """Extracts metadata and Most Replayed (Heatmap) data from YouTube videos."""

    @staticmethod
    def clean_url(url_or_id: str) -> str:
        url_or_id = url_or_id.strip()
        # If it's a raw 11-char ID
        if re.match(r"^[a-zA-Z0-9_-]{11}$", url_or_id):
            return f"https://www.youtube.com/watch?v={url_or_id}"
        return url_or_id

    @classmethod
    def get_video_data(cls, url: str) -> dict[str, Any]:
        """
        Fetches video info and heatmap data from YouTube.
        Returns a dictionary with title, duration, thumbnail, channel, heatmap list, etc.
        """
        cleaned_url = cls.clean_url(url)
        ydl_opts = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(cleaned_url, download=False)
        except Exception as e:
            raise RuntimeError(f"Video bilgileri çekilemedi: {e}") from e

        heatmap_raw = info.get("heatmap") or []

        # Format heatmap into standardized list of dicts
        heatmap = []
        for point in heatmap_raw:
            heatmap.append(
                {
                    "start_time": float(point.get("start_time", 0.0)),
                    "end_time": float(point.get("end_time", 0.0)),
                    "value": float(point.get("value", 0.0)),
                }
            )

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
            "heatmap": heatmap,
            "tags": info.get("tags", []),
            "description": info.get("description", ""),
        }

    @classmethod
    def get_video_comments(cls, url: str, max_comments: int = 250) -> list[dict[str, Any]]:
        """
        Fetches top comments and relevant replies for a video using yt-dlp (with YouTube API fallback).
        Returns a list of dicts: [{'text': str, 'like_count': int, 'author': str}]
        """
        cleaned_url = cls.clean_url(url)
        formatted: list[dict[str, Any]] = []

        # 1. yt-dlp ile hızlı ve limitsiz yorum çekme
        ydl_opts = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "getcomments": True,
            "extractor_args": {"youtube": {"max_comments": [str(max_comments)]}},
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(cleaned_url, download=False)
                comments_raw = info.get("comments") or []
                for c in comments_raw:
                    txt = c.get("text", "") or ""
                    if txt:
                        formatted.append(
                            {
                                "text": txt,
                                "like_count": int(c.get("like_count", 0) or 0),
                                "author": c.get("author", "") or "",
                            }
                        )
        except Exception:
            pass

        # 2. Eğer yt-dlp yorum bulamadıysa ve YouTube Data API anahtarı varsa API üzerinden dene
        if not formatted:
            api_key = os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if api_key:
                try:
                    from googleapiclient.discovery import build

                    youtube = build("youtube", "v3", developerKey=api_key)
                    # Video ID ayıkla
                    vid_match = re.search(r"(?:v=|\/embed\/|youtu\.be\/|\/v\/)([a-zA-Z0-9_-]{11})", cleaned_url)
                    vid_id = vid_match.group(1) if vid_match else None
                    if vid_id:
                        req = youtube.commentThreads().list(
                            part="snippet",
                            videoId=vid_id,
                            maxResults=min(100, max_comments),
                            order="relevance",
                            textFormat="plainText",
                        )
                        res = req.execute()
                        for item in res.get("items", []):
                            top_comment = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                            txt = top_comment.get("textDisplay", "") or ""
                            if txt:
                                formatted.append(
                                    {
                                        "text": txt,
                                        "like_count": int(top_comment.get("likeCount", 0) or 0),
                                        "author": top_comment.get("authorDisplayName", "") or "",
                                    }
                                )
                except Exception:
                    pass

        return formatted

    @staticmethod
    def format_seconds(seconds: float) -> str:
        """Formats seconds into mm:ss or hh:mm:ss string."""
        s = int(seconds)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    @staticmethod
    def calculate_recommended_clips(duration_sec: int) -> dict[str, Any]:
        """Calculates generous, duration-based recommended clip count for gaming videos."""
        minutes = max(1, round(duration_sec / 60))
        if minutes <= 3:
            recommended = 2
            clip_range = "1 - 3"
            tier_label = "Çok Kısa Video"
        elif minutes <= 8:
            recommended = 3
            clip_range = "2 - 4"
            tier_label = "Kısa Video"
        elif minutes <= 15:
            recommended = 5
            clip_range = "4 - 7"
            tier_label = "Orta Süreli Video"
        elif minutes <= 30:
            recommended = 7
            clip_range = "5 - 10"
            tier_label = "Standart Gaming Videosu"
        elif minutes <= 45:  # e.g. 37 min
            recommended = 10
            clip_range = "8 - 14"
            tier_label = "Uzun Gaming / Maç Videosu"
        elif minutes <= 60:
            recommended = 12
            clip_range = "10 - 16"
            tier_label = "1 Saatlik Kayıt"
        elif minutes <= 90:
            recommended = 15
            clip_range = "12 - 20"
            tier_label = "Uzun Canlı Yayın Tekrarı"
        else:
            recommended = min(25, max(15, round(minutes / 4.5)))
            clip_range = f"{max(10, recommended - 4)} - {min(25, recommended + 5)}"
            tier_label = "Maraton Canlı Yayın"

        return {
            "duration_minutes": minutes,
            "recommended_clips": recommended,
            "clip_range": clip_range,
            "tier_label": tier_label,
            "explanation": f"{minutes} dakikalık {tier_label.lower()} için önerilen bol klip havuzu: {recommended} klip ({clip_range} adet).",
        }
