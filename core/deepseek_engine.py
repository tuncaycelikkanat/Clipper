"""
core/deepseek_engine.py — DeepSeek V3 / R1 engine powering:
1. Top-N Batch Candidate Clip Judgment (Layer 4)
2. Quality & Viral Action Density Evaluation (Layer 5)
3. Viral Social Metadata, Hooks, and Titles (Export)
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
    def batch_judge_candidates(
        cls,
        candidates_summary: List[Dict[str, Any]],
        video_title: str,
        total_duration: int,
        target_clips: int = 3,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Judge Top-15 candidates in a single batch call using DeepSeek V3."""
        client, model, provider_label = cls.get_client_and_model(api_key)

        system_prompt = (
            "Sen YouTube Shorts, TikTok ve Instagram Reels için milyonlar izlenen Gaming / Yayın klipleri seçen "
            "profesyonel bir video editörüsün. Sana sinyal işleme (ses patlamaları, sessizlikten çığlığa geçiş, "
            "izleyici tekrar yoğunluğu) ile tespit edilmiş aday klip havuzu verilecek.\n"
            "GÖREVİN:\n"
            "1. Tüm adayları bağlamsal olarak incele, sahte alarmları (sadece gürültü olan boş anları) ele ('DROP').\n"
            "2. Gerçekten viral olabilecek en iyi anları ('KEEP') olarak işaretle ve en yüksek puandan sırala.\n"
            "3. Her klip için aksiyonun başladığı ve bittiği en doğru başlangıç/bitiş saniyelerini öner.\n"
            "4. Dikkat çekici bir başlık, ilk 3 saniye kanca yazısı (Hook) ve kategori belirle.\n"
            "Yanıtı kesinlikle saf JSON formatında döndür."
        )

        user_prompt = f"""
Video Başlığı: {video_title}
Toplam Süre: {total_duration} saniye
İstenen En İyi Klip Sayısı: {target_clips}

ADAY HAVUZU (TOP-{len(candidates_summary)} Sinyal Verisi):
{json.dumps(candidates_summary, indent=2, ensure_ascii=False)}

Lütfen şu JSON formatında yanıt ver:
{{
  "selected_clips": [
    {{
      "candidate_id": 1,
      "verdict": "KEEP",
      "category": "CLUTCH / FAIL_FUNNY / RAGE_REACTION / EPIC_MOMENT",
      "title": "Shorts/TikTok için dikkat çekici Türkçe başlık",
      "hook_caption": "İlk 3 saniyede izleyiciyi yakalayacak kanca başlığı/yazısı",
      "why_viral": "Neden viral olacağının analizi",
      "viral_confidence": 92,
      "suggested_start": 120.0,
      "suggested_end": 155.0
    }}
  ]
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
                temperature=0.3,
                max_tokens=2000,
            )
            raw_text = response.choices[0].message.content or "{}"
            data = json.loads(raw_text)
            logger.info(f"{provider_label} successfully judged candidates")
            return data
        except Exception as exc:
            logger.error(f"{provider_label} batch judgment error: {exc}")
            raise

    @classmethod
    def evaluate_quality(
        cls,
        clip: Dict[str, Any],
        video_title: str,
        dur: float,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evaluate clip quality and action density using DeepSeek V3."""
        client, model, provider_label = cls.get_client_and_model(api_key)

        system_prompt = (
            "Sen YouTube Shorts ve TikTok için milyonlar izlenen Gaming ve Yayın içerikleri üreten Baş Editörsün. "
            "Verilen klibi izleyici tutma, aksiyon, kanca ve vuruş gücüne göre değerlendirip JSON formatında yanıt ver."
        )

        user_prompt = f"""
Video: {video_title}
Klip Başlığı: {clip.get('title', '')}
Kategori: {clip.get('category', 'ACTION')}
Klip Süresi: {dur:.1f} sn
Kanca (Hook): "{clip.get('hook_caption', '')}"
Diyalog/Transkript: "{clip.get('text', '')}"

Lütfen şu JSON formatında yanıt ver:
{{
  "hook_score": 90,
  "entertainment_score": 92,
  "payoff_score": 88,
  "grade": "A+",
  "editor_feedback": "Klibin güçlü ve zayıf yönlerine dair Türkçe editör yorumu",
  "viral_tips": "Shorts/TikTok'ta etkileşimi artırmak için pratik tavsiye"
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
                temperature=0.3,
                max_tokens=800,
            )
            raw_text = response.choices[0].message.content or "{}"
            data = json.loads(raw_text)
            logger.info(f"{provider_label} successfully evaluated clip quality")
            return data
        except Exception as exc:
            logger.error(f"{provider_label} quality evaluation error: {exc}")
            raise

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
            "Görevin: Verilen oyun klibi için ASLA robotik 'AI slop' olmayan, "
            "tamamen Türk internet jargonuna, mizahına ve oyunun dinamiklerine uygun "
            "viral başlık, açıklama ve etiketler üretmek. Yanıtı saf JSON olarak döndür.\n\n"
            "KRİTİK KURALLAR:\n"
            "1. Başlık Kesinlikle Dilbilgisel Olarak Tam Olmalıdır: Asla yarım kalmış veya devrik saçma meme cümleleri kurma. Akıcı, merak veya kahkaha uyandıran tam bir Türkçe cümle yaz.\n"
            "2. Başlık Formatı: En fazla 90 karakter, dikkat çekici kelimelerde BÜYÜK HARF vurgusu, 2 ilgili emoji ve sonunda '#Shorts' etiketi olmalıdır.\n"
            "3. Açıklama: İlk satırda samimi kanca, ikinci paragrafta klibin heyecanını anlatan özet, kanal adı ve 5 spesifik hashtag (#OyunAdi #Shorts #Gaming vb.).\n"
            "4. Etiketler (Tags): Oyunun tam adını, klibin konusunu, oyun mekaniğini ve Türkçe oyun terimlerini içeren 10-14 adet spesifik etiket."
        )

        user_prompt = f"""
Klip Bilgileri:
- Orijinal Video / Kanal: {video_title}
- Klip Başlığı: {clip_title}
- Kategori: {category}
- Kanca Cümle / Olay: "{hook_caption}"

Lütfen şu JSON formatında yanıt ver:
{{
  "title": "AKICI, MERAK UYANDIRAN TAM TÜRKÇE CÜMLE! 🚗💥 #Shorts",
  "description": "İlk satır kanca, özet paragrafı ve hashtagler",
  "tags": ["oyunun_tam_adi", "klipteki_olay", "turkce_oyun_terimleri", "nis_etiketler"]
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
