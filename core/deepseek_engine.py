"""
core/deepseek_engine.py — DeepSeek V3 / R1 creative engine (via OpenRouter or direct DeepSeek API).
"""

from __future__ import annotations

import os
import json
from typing import Dict, Any, Optional, List, Tuple
from openai import OpenAI
from loguru import logger


class DeepSeekEngine:
    """Uses DeepSeek V3 / R1 via OpenRouter or direct OpenAI-compatible endpoint."""

    @classmethod
    def get_client_and_model(cls, api_key: Optional[str] = None) -> Tuple[OpenAI, str, str]:
        """Returns (client, model_name, provider_label)."""
        or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        ds_key = (api_key or os.environ.get("DEEPSEEK_API_KEY", "")).strip()

        if or_key:
            client = OpenAI(
                api_key=or_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://github.com/clipper",
                    "X-Title": "Gaming AI Clipper",
                },
            )
            return client, "deepseek/deepseek-chat", "DeepSeek V3 (OpenRouter)"

        if ds_key:
            client = OpenAI(
                api_key=ds_key,
                base_url="https://api.deepseek.com",
            )
            return client, "deepseek-chat", "DeepSeek V3 (Direct)"

        raise ValueError("Neither OPENROUTER_API_KEY nor DEEPSEEK_API_KEY found.")

    @classmethod
    def is_available(cls, api_key: Optional[str] = None) -> bool:
        """Check if OpenRouter or direct DeepSeek API is configured."""
        or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        ds_key = (api_key or os.environ.get("DEEPSEEK_API_KEY", "")).strip()
        return bool(or_key or ds_key)

    @classmethod
    def generate_shorts_copy(
        cls,
        clip_title: str,
        hook_caption: str,
        category: str,
        video_title: str = "",
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate high-CTR viral Turkish title, SEO description, and tags using DeepSeek."""
        client, model, provider_label = cls.get_client_and_model(api_key)

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

Lütfen şu JSON formatında yanıt ver:
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
            logger.info(f"{provider_label} successfully generated Shorts copy for '{clip_title}'")
            return {
                "title": data.get("title", f"{clip_title} #Shorts"),
                "description": data.get("description", f"{hook_caption}\n\n#Shorts"),
                "tags": data.get("tags", [video_title.lower(), "shorts", "gaming"]),
                "provider": provider_label,
            }
        except Exception as exc:
            logger.error(f"{provider_label} API error: {exc}")
            raise
