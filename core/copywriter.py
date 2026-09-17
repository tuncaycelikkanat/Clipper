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
        youtube_username: str = "",
        instagram_username: str = "",
    ) -> dict[str, Any]:
        """
        Klip için başlık, açıklama ve etiketler üretir.
        Önce DeepSeek dener, hata alırsa Gemini veya akıllı şablon kuralına döner.
        """
        clip_title = clip.get("title", "")
        hook = clip.get("hook_caption", "")
        category = clip.get("category", "GAMING")

        yt_credit = f"@{youtube_username}" if youtube_username else (f"@{channel_name}" if channel_name else "")

        # 1. DeepSeek ile dene
        try:
            res = self.deepseek.generate_shorts_copy(
                clip_title=clip_title,
                hook_caption=hook,
                category=category,
                video_title=video_title,
                channel_name=channel_name,
                youtube_username=youtube_username,
                instagram_username=instagram_username,
            )
            if res and res.get("title"):
                return res
        except Exception as e:
            logger.warning("DeepSeek copywriter failed, falling back: {}", e)

        # 2. İnsansı Şablon Fallback
        category_up = str(category).upper()
        if any(k in category_up for k in ["CLUTCH", "EPIC"]):
            fallback_title = f"Son saniyede gelen o {clip_title.split()[0] if clip_title else 'kaçış'} 🎯 #Shorts"
        elif any(k in category_up for k in ["FUNNY", "FAIL"]):
            fallback_title = f"Bunu beklemiyordu ahahah 😂 #Shorts"
        elif any(k in category_up for k in ["RAGE", "TILT"]):
            fallback_title = f"Dayanamadı 😭 #Shorts"
        else:
            hook_words = hook.split()[:4] if hook else []
            fallback_title = (" ".join(hook_words) + "... #Shorts") if hook_words else f"{clip_title or 'Bu an'} 🎮 #Shorts"

        if len(fallback_title) > 100:
            fallback_title = fallback_title[:95] + "... #Shorts"

        credit_line = f"\n\n🎮 {yt_credit}" if yt_credit else ""
        description_lines = [
            hook or clip_title,
            "",
            "Siz bu durumda ne yapardınız? Yorumlarda buluşalım 👇",
            credit_line,
            "",
            "#Shorts #Gaming #OyunKesitleri #Oyun #Twitch",
        ]
        description = "\n".join([line for line in description_lines if line is not None])

        return {
            "title": fallback_title,
            "description": description.strip(),
            "tags": ["gaming", "shorts", "oyun", "highlight", category.lower()],
        }

