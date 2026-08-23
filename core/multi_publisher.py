"""
core/multi_publisher.py — Multi-Platform Video Publisher Orchestrator

Coordinates distribution of rendered clips across YouTube Shorts, Instagram Reels, and TikTok.
Handles platform-specific copywriting adaptations and status reporting.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from loguru import logger

from core.instagram_uploader import InstagramUploader
from core.notifier import Notifier
from core.tiktok_uploader import TikTokUploader
from core.uploader import YouTubeUploader


class MultiPublisher:
    """Orchestrates multi-platform publishing across YouTube, Instagram, and TikTok."""

    def __init__(
        self,
        youtube_uploader: Optional[YouTubeUploader] = None,
        instagram_uploader: Optional[InstagramUploader] = None,
        tiktok_uploader: Optional[TikTokUploader] = None,
        notifier: Optional[Notifier] = None,
    ) -> None:
        self.youtube = youtube_uploader or YouTubeUploader()
        self.instagram = instagram_uploader or InstagramUploader()
        self.tiktok = tiktok_uploader or TikTokUploader()
        self.notifier = notifier or Notifier()

    def get_auth_status(self) -> Dict[str, bool]:
        """Return authentication status for all supported platforms."""
        return {
            "youtube": self.youtube.is_authenticated(),
            "instagram": self.instagram.is_authenticated(),
            "tiktok": self.tiktok.is_authenticated(),
        }

    def publish_clip(
        self,
        clip: Dict[str, Any],
        render_path: str,
        thumbnail_path: Optional[str] = None,
        platforms: Optional[List[str]] = None,
        video_title: str = "",
        scheduled_at: Optional[str] = None,
        playlist_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Publish a rendered clip to selected platforms (YouTube Shorts, Instagram Reels, TikTok).

        Args:
            clip: Clip metadata dictionary.
            render_path: Local path to the .mp4 file.
            thumbnail_path: Optional custom thumbnail path.
            platforms: List of target platforms, e.g. ['youtube', 'instagram', 'tiktok'].
            video_title: Source video title.
            scheduled_at: ISO-8601 UTC timestamp for YouTube scheduling.
            playlist_id: YouTube playlist ID.

        Returns:
            Dict mapping platform name to result dict {"status": "success"/"failed", "url": ..., "error": ...}.
        """
        target_platforms = [p.lower().strip() for p in (platforms or ["youtube"])]
        results: Dict[str, Any] = {}

        if not os.path.exists(render_path):
            raise FileNotFoundError(f"Render dosyası bulunamadı: {render_path}")

        # 1. YouTube Shorts
        if "youtube" in target_platforms:
            if self.youtube.is_authenticated():
                try:
                    title = clip.get("title", "Gaming Highlight #Shorts")
                    if "#Shorts" not in title:
                        title = f"{title} #Shorts"
                    desc = YouTubeUploader.generate_description(clip, video_title)
                    tags = ["shorts", "gaming", "oyun", "highlights"]

                    yt_res = self.youtube.upload_short(
                        video_path=render_path,
                        title=title,
                        description=desc,
                        tags=tags,
                        thumbnail_path=thumbnail_path,
                        playlist_id=playlist_id,
                        publish_at=scheduled_at,
                    )
                    results["youtube"] = {
                        "status": "success",
                        "video_id": yt_res.get("video_id"),
                        "url": yt_res.get("url"),
                    }
                    logger.success(f"MultiPublisher: YouTube Shorts başarıyla yüklendi → {yt_res.get('url')}")
                except Exception as exc:
                    logger.error(f"MultiPublisher: YouTube upload hatası: {exc}")
                    results["youtube"] = {"status": "failed", "error": str(exc)}
            else:
                results["youtube"] = {"status": "skipped", "error": "YouTube oturumu açık değil."}

        # 2. Instagram Reels
        if "instagram" in target_platforms:
            if self.instagram.is_authenticated():
                try:
                    ig_caption = InstagramUploader.generate_caption(clip, video_title)
                    ig_res = self.instagram.upload_reel(
                        video_path=render_path,
                        caption=ig_caption,
                        share_to_feed=True,
                    )
                    results["instagram"] = {
                        "status": "success",
                        "media_id": ig_res.get("media_id"),
                        "url": ig_res.get("url"),
                    }
                    logger.success(f"MultiPublisher: Instagram Reel başarıyla yüklendi → {ig_res.get('url')}")
                except Exception as exc:
                    logger.error(f"MultiPublisher: Instagram upload hatası: {exc}")
                    results["instagram"] = {"status": "failed", "error": str(exc)}
            else:
                results["instagram"] = {"status": "skipped", "error": "Instagram oturumu açık değil."}

        # 3. TikTok
        if "tiktok" in target_platforms:
            if self.tiktok.is_authenticated():
                try:
                    tt_title = TikTokUploader.generate_caption(clip, video_title)
                    tt_res = self.tiktok.upload_video(
                        video_path=render_path,
                        title=tt_title,
                        privacy_level="PUBLIC_TO_EVERYONE",
                    )
                    results["tiktok"] = {
                        "status": "success",
                        "publish_id": tt_res.get("publish_id"),
                        "url": tt_res.get("url"),
                    }
                    logger.success(f"MultiPublisher: TikTok videosu başarıyla yüklendi → {tt_res.get('publish_id')}")
                except Exception as exc:
                    logger.error(f"MultiPublisher: TikTok upload hatası: {exc}")
                    results["tiktok"] = {"status": "failed", "error": str(exc)}
            else:
                results["tiktok"] = {"status": "skipped", "error": "TikTok oturumu açık değil."}

        return results
