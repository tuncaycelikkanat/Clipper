"""
core/copywriter.py — Bağımsız Başlık, Açıklama ve Hashtag Üretici Servis
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from core.deepseek_engine import DeepSeekEngine
from core.llm_engine import GeminiHighlightEngine


class CopywriterEngine:
    """Klipler için viral başlık, insansı açıklama ve hashtag üreten bağımsız servis."""

    def __init__(self, deepseek: DeepSeekEngine | None = None, gemini: GeminiHighlightEngine | None = None) -> None:
        self.deepseek = deepseek or DeepSeekEngine()
        self.gemini = gemini or GeminiHighlightEngine()

    def generate_shorts_metadata(
        self,
        clip: dict[str, Any],
        video_title: str = "",
        channel_name: str = "",
    ) -> dict[str, Any]:
        """
        Klip için başlık, açıklama ve etiketler üretir.
        Önce DeepSeek dener, hata alırsa Gemini veya akıllı şablon kuralına döner.
        """
        clip_title = clip.get("title", "Gaming Highlight")
        hook = clip.get("hook_caption", "")
        category = clip.get("category", "GAMING")

        # 1. DeepSeek ile dene
        try:
            res = self.deepseek.generate_shorts_copy(
                clip_title=clip_title,
                hook_caption=hook,
                category=category,
                video_title=video_title,
                channel_name=channel_name,
            )
            if res and res.get("title"):
                return res
        except Exception as e:
            logger.warning("DeepSeek copywriter failed, falling back: {}", e)

        # 2. Şablon Fallback
        clean_title = f"{clip_title} #Shorts" if not clip_title.endswith("#Shorts") else clip_title
        if len(clean_title) > 95:
            clean_title = clean_title[:90] + "... #Shorts"

        description_lines = [
            f"{hook or clip_title}",
            "",
            f"🎬 Orijinal Video: {video_title}" if video_title else "",
            f"👤 Yayıncı: {channel_name}" if channel_name else "",
            "",
            "#Shorts #Gaming #TürkçeGaming",
        ]
        description = "\n".join([line for line in description_lines if line is not None])

        return {
            "title": clean_title,
            "description": description.strip(),
            "tags": ["gaming", "shorts", "oyun", "highlight", category.lower()],
        }
