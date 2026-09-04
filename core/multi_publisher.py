"""
core/multi_publisher.py — Multi-Platform Video Publisher Orchestrator

Coordinates distribution of rendered clips across YouTube Shorts, Instagram Reels, and TikTok.
Handles platform-specific copywriting adaptations and status reporting.
"""

from __future__ import annotations

import os
from typing import Any

from loguru import logger

from core.database import DatabaseManager
from core.deepseek_engine import DeepSeekEngine
from core.instagram_uploader import InstagramUploader
from core.notifier import Notifier
from core.uploader import YouTubeUploader


class MultiPublisher:
    """Orchestrates multi-platform publishing across YouTube, Instagram, and TikTok."""

    def __init__(
        self,
        youtube_uploader: YouTubeUploader | None = None,
        instagram_uploader: InstagramUploader | None = None,
        notifier: Notifier | None = None,
        db: DatabaseManager | None = None,
    ) -> None:
        self.youtube = youtube_uploader or YouTubeUploader()
        self.instagram = instagram_uploader or InstagramUploader()
        self.notifier = notifier or Notifier()
        self.db = db or DatabaseManager()

    def get_auth_status(self) -> dict[str, bool]:
        """Return authentication status for all supported platforms."""
        return {
            "youtube": self.youtube.is_authenticated(),
            "instagram": self.instagram.is_authenticated(),
        }

    def publish_clip(
        self,
        clip: dict[str, Any],
        render_path: str,
        thumbnail_path: str | None = None,
        platforms: list[str] | None = None,
        video_title: str = "",
        scheduled_at: str | None = None,
        playlist_id: str | None = None,
        description_override: str | None = None,
        source_video_id: str | None = None,
        source_video_url: str | None = None,
    ) -> dict[str, Any]:
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
        results: dict[str, Any] = {}

        if not os.path.exists(render_path):
            raise FileNotFoundError(f"Render dosyası bulunamadı: {render_path}")

        # 1. YouTube Shorts
        if "youtube" in target_platforms:
            if self.youtube.is_authenticated():
                try:
                    # --- DEEPSEEK SEO METADATA ENTEGRASYONU ---
                    # Kuyrukta daha önce üretilmiş başlık/açıklama varsa
                    # (run_cycle içinde DeepSeek ile üretilip orijinal link eklenmiş)
                    # tekrar API çağrısı yapmadan onları kullan.
                    if description_override and description_override.strip():
                        desc = description_override
                        title = clip.get("title", "Gaming Highlight #Shorts")
                        if "#Shorts" not in title:
                            title = f"{title} #Shorts"
                        tags = ["shorts", "gaming", "oyun", "highlights"]
                        logger.info("Kuyruktaki açıklama doğrudan kullanılıyor (ek DeepSeek çağrısı yok).")
                    else:
                        try:
                            logger.info("DeepSeek ile SEO uyumlu baslik, aciklama ve etiketler uretiliyor...")
                            # Orijinal etiketleri DB'den cek
                            orig_tags_list = []
                            vid_id_for_tags = clip.get("video_id")
                            if vid_id_for_tags:
                                try:
                                    v_data = self.db.get_video(vid_id_for_tags)
                                    if v_data and v_data.get("tags"):
                                        import json

                                        orig_tags_list = json.loads(v_data["tags"])
                                except Exception as e:
                                    logger.debug("Could not fetch original tags for {}: {}", vid_id_for_tags, e)

                            seo_data = DeepSeekEngine.generate_shorts_copy(
                                clip_title=clip.get("title", ""),
                                hook_caption=clip.get("hook_caption", ""),
                                category=clip.get("category", "GAMING"),
                                video_title=video_title,
                                original_tags=orig_tags_list,
                            )
                            title = seo_data.get("title", f"{clip.get('title')} #Shorts")
                            desc = seo_data.get("description", YouTubeUploader.generate_description(clip, video_title))
                            tags = seo_data.get("tags", ["shorts", "gaming", "oyun", "highlights"])
                            logger.success("DeepSeek SEO metadatasi basariyla alindi!")
                        except Exception as e:
                            logger.warning(f"DeepSeek SEO uretimi basarisiz (Fallback kullaniliyor): {e}")
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
                    # Shorts ile birebir aynı açıklamayı ve etiketleri kullan
                    ig_caption = desc or clip.get("description") or InstagramUploader.generate_caption(clip, video_title)
                    ig_res = self.instagram.upload_reel(
                        video_path=render_path,
                        caption=ig_caption,
                        thumbnail_path=thumbnail_path,
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

        return results
