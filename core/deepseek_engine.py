"""
core/deepseek_engine.py — DeepSeek V3 / R1 creative engine for viral hooks,
Shorts titles, and Turkish gaming context analysis.
"""

from __future__ import annotations

import os
import json
from typing import Dict, Any, Optional, List
from openai import OpenAI
from loguru import logger


class DeepSeekEngine:
    """Uses DeepSeek V3 / R1 via OpenAI-compatible endpoint."""

    BASE_URL = "https://api.deepseek.com"
    DEFAULT_MODEL = "deepseek-chat"  # DeepSeek-V3

    @classmethod
    def is_available(cls, api_key: Optional[str] = None) -> bool:
        """Check if a valid DeepSeek API key is configured."""
        key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        return bool(key and key.strip())

    @classmethod
    def generate_shorts_copy(
        cls,
        clip_title: str,
        hook_caption: str,
        category: str,
        video_title: str = "",
        api_key: Optional[str] = None,
        model: str = "deepseek-chat",
    ) -> Dict[str, Any]:
        """Generate high-CTR viral Turkish title, SEO description, and tags using DeepSeek."""
        key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise ValueError("DEEPSEEK_API_KEY bulunamadı.")

        client = OpenAI(api_key=key, base_url=cls.BASE_URL)

        system_prompt = (
            "Sen Türkiye'nin en popüler YouTube Shorts ve TikTok Gaming kanallarının baş editörüsün. "
            "Görevin: Verilen oyun klibi için ASLA 'AI slop' (yapay zeka klişesi) olmayan, "
            "tamamen Türk internet jargonuna, mizahına ve oyunun dinamiklerine uygun "
            "viral başlık, açıklama ve etiketler üretmek. Yanıtı saf JSON olarak döndür."
        )

        user_prompt = f"""
Klip Bilgileri:
- Orijinal Video / Kanal: {video_title}
- Klip Başlığı: {clip_title}
- Kategori: {category}
- Kanca Cümle / Olay: "{hook_caption}"

Lütfen şu JSON şemasında çıktı ver:
{{
  "title": "Maksimum 90 karakterlik, aşırı merak veya kahkaha uyandıran, BÜYÜK HARF vurgulu, emojili ve sonunda #Shorts etiketi olan Türkçe başlık",
  "description": "İlk satırda izleyiciyi vuran samimi kanca, klibin komedisini/aksiyonunu anlatan kısa paragraf, oyun adı ve 5 trend hashtag (#OyunAdi #Shorts #Gaming vb.)",
  "tags": ["oyunun_tam_adi", "klipteki_olay", "turkce_oyun_terimleri", "nis_arama_etiketleri_10_14_adet"]
}}
"""

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=1000,
            )
            raw_text = response.choices[0].message.content or "{}"
            data = json.loads(raw_text)
            logger.info(f"DeepSeek successfully generated Shorts copy for '{clip_title}'")
            return {
                "title": data.get("title", f"{clip_title} #Shorts"),
                "description": data.get("description", f"{hook_caption}\n\n#Shorts"),
                "tags": data.get("tags", [video_title.lower(), "shorts", "gaming"]),
            }
        except Exception as exc:
            logger.error(f"DeepSeek API error: {exc}")
            raise
