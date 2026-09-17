"""
core/deepseek_engine.py — DeepSeek V3 / R1 engine powering:
1. Top-N Batch Candidate Clip Judgment (Layer 4)
2. Quality & Viral Action Density Evaluation (Layer 5)
3. Viral Social Metadata, Hooks, and Titles (Export)
"""

from __future__ import annotations

import json
import os
from typing import Any

from loguru import logger
from openai import OpenAI


class DeepSeekEngine:
    """Uses DeepSeek V3 / R1 via OpenRouter or direct OpenAI-compatible endpoint."""

    @classmethod
    def get_client_and_model(cls, api_key: str | None = None) -> tuple[OpenAI, str, str]:
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
    def is_available(cls, api_key: str | None = None) -> bool:
        """Check if OpenRouter or direct DeepSeek API is configured."""
        or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        ds_key = (api_key or os.environ.get("DEEPSEEK_API_KEY", "")).strip()
        return bool(or_key or ds_key)

    @classmethod
    def batch_judge_candidates(
        cls,
        candidates_summary: list[dict[str, Any]],
        video_title: str,
        total_duration: int,
        target_clips: int = 3,
        api_key: str | None = None,
    ) -> dict[str, Any]:
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
        clip: dict[str, Any],
        video_title: str,
        dur: float,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate clip quality and action density using DeepSeek V3."""
        client, model, provider_label = cls.get_client_and_model(api_key)

        system_prompt = (
            "Sen YouTube Shorts ve TikTok için milyonlar izlenen Gaming ve Yayın içerikleri üreten Baş Editörsün. "
            "Verilen klibi izleyici tutma, aksiyon, kanca ve vuruş gücüne göre değerlendirip JSON formatında yanıt ver."
        )

        user_prompt = f"""
Video: {video_title}
Klip Başlığı: {clip.get("title", "")}
Kategori: {clip.get("category", "ACTION")}
Klip Süresi: {dur:.1f} sn
Kanca (Hook): "{clip.get("hook_caption", "")}"
Diyalog/Transkript: "{clip.get("text", "")}"

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
        hook_caption: str = "",
        category: str = "GAMING",
        video_title: str = "",
        channel_name: str = "",
        youtube_username: str = "",
        instagram_username: str = "",
        original_tags: list[str] | None = None,
        api_key: str | None = None,
        raise_on_error: bool = False,
    ) -> dict[str, Any]:
        """Generate high-CTR organic, human-like Turkish title, interactive description, and tags using DeepSeek."""
        client, model, provider_label = cls.get_client_and_model(api_key)

        yt_credit = f"@{youtube_username}" if youtube_username else (f"@{channel_name}" if channel_name else "yayıncı")
        ig_credit = f"@{instagram_username}" if instagram_username else ""

        system_prompt = (
            "Sen Türkiye'nin en popüler Twitch ve YouTube Gaming klip kanallarını yöneten kıdemli bir Shorts/TikTok editörüsün.\n\n"
            "GÖREVİN:\n"
            "Verilen oyun klibi için ASLA robotik, yapay zeka kokan ('İnanılmaz An!', 'Şok Etti!', 'Tarihi An!', 'Bunu Kimse Beklemiyordu', "
            "'Gaming Highlight', 'Epic Moment') klişeler KULLANMADAN; tamamen gerçek bir oyun/yayın izleyicisinin ağzından samimi, "
            "dikkat çekici, merak uyandıran veya güldüren organik başlık, açıklama ve etiketler üretmek.\n\n"
            "İNSANSI BAŞLIK REHBERİ (Aşağıdaki tarzlardan duruma en uygun olanını seç):\n"
            "1. Transkriptten direkt replik alıntısı: 'burada ölürsem oyunu silerim dedi ve...', 'abi arkanda arkandaaaa! 💀'\n"
            "2. Doğal Reaksiyon / Durum: 'Hiç beklemediğim yerden çıktı ahahah', 'Son saniyede gelen o panik'\n"
            "3. Merak / Olay Örgüsü: 'O pozisyonda ne yapmaya çalıştı acaba?', '1 canla kurtulduğu o an'\n"
            "4. İzleyiciye Soru / Tartışma: 'Sizce burada şans mı var bilek mi?', 'Bu pozisyonda ne yapardınız?'\n"
            "5. Format Kuralı: Maksimum 80-90 karakter, doğal konuşma dili, 1-2 samimi emoji (😂, 💀, 🤦‍♂️, 🔥, 🎯, 😭) ve sonunda '#Shorts'. "
            "ASLA BÜTÜN KELİMELERİ BÜYÜK HARFLE YAZMA. ASLA 'Gaming Highlight', 'Epic', 'Amazing', 'Incredible' gibi İngilizce klişe kullanma.\n\n"
            "İNSANSI AÇIKLAMA REHBERİ (YouTube Shorts için):\n"
            "- Asla 'Category: GAMING' veya robotik kalıplar kullanma!\n"
            "- 1-2 cümlelik samimi ve eğlenceli olay özeti + izleyiciye yorum sorusu.\n"
            f"- Yayıncı kredisi: '🎮 {yt_credit}' şeklinde gerçek @kullanıcıadı kullan.\n"
            "- AÇIKLAMANIN İÇİNE ORİJİNAL VİDEO LİNKİNİ ASLA EKLEME.\n"
            "- 4-6 adet temiz ve ilgili hashtag (#oyunadi #gaming #shorts #kesitler #oyun vb.).\n\n"
            "ETİKETLER (tags — YouTube için):\n"
            "- Oyunun tam adı, yayıncının adı, klipteki olayın terimleri (örn: ['valorant', 'clutch', 'ace', 'twitch türkiye']).\n"
            "- Eğer Orijinal Video Etiketleri verilmişse, oyunu ve konuyu onlardan çıkar.\n\n"
            "INSTAGRAM CAPTION (Instagram Reels için ayrı alan):\n"
            "- İlk satır: Klipten çekici 1-2 cümle (başlık görevi görür) — #Shorts EKLEME.\n"
            "- Yoruma teşvik eden kısa bir soru.\n"
            f"- {'📌 ' + ig_credit + chr(10) if ig_credit else ''}"
            "- En az 20 hashtag: #reels #fyp #gaming #oyun #twitch #türkçeyayın #keşfet #viral ve oyuna/yayıncıya özel taglar.\n"
            "- Caption toplam 300-500 karakter arası olsun."
        )

        tags_hint = ""
        if original_tags:
            tags_hint = f"\nOrijinal Video Etiketleri (Oyun/Konu İpucu): {', '.join(original_tags[:15])}"

        user_prompt = f"""Klip Bilgileri:
- Orijinal Video / Kanal: {video_title}
- Yayıncı Adı: {channel_name or 'Bilinmiyor'}
- YouTube Kullanıcı Adı: {yt_credit}
- Instagram Kullanıcı Adı: {ig_credit or 'Yok'}
- Klip Başlığı: {clip_title}
- Kategori: {category}
- Kanca Cümle / Olay: "{hook_caption}"{tags_hint}

Lütfen samimi ve insansı bir üslupla şu JSON formatında yanıt ver:
{{
  "title": "Samimi, merak uyandıran veya güldüren doğal Türkçe başlık 😂 #Shorts",
  "description": "Arkadan geleni fark etmeyince olanlar oldu ahahah. Sizce bu pozisyonda ne yapmalıydı?\\n\\n🎮 {yt_credit}\\n\\n#oyun #shorts #gaming #kesitler #komik",
  "instagram_caption": "Gece 3'te ekiple bu pozisyona düştük 😭 Siz olsaydınız ne yapardınız?\\n\\n#reels #fyp #gaming #oyun #twitch #türkçeyayın #keşfet #viral #shorts #komik #highlight #twitch #youtube #gamingturkiye #oyunkesitleri #türkçeoyun #akıntı #clutch #türkiye #gamer",
  "tags": ["oyun_adi", "yayin_kesitleri", "gaming", "shorts", "turkce_oyun"]
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
                temperature=0.75,
                max_tokens=600,
            )
            raw_text = response.choices[0].message.content or "{}"
            data = json.loads(raw_text)
            logger.info(f"{provider_label} successfully generated Shorts copy for '{clip_title}'")
            return {
                "title": data.get("title", f"{clip_title} #Shorts"),
                "description": data.get("description", f"{hook_caption}\n\n\n#Shorts #Gaming"),
                "instagram_caption": data.get("instagram_caption", data.get("description", "")),
                "tags": data.get("tags", [video_title.lower(), "shorts", "gaming"]),
                "provider": provider_label,
            }
        except Exception as exc:
            logger.error(f"{provider_label} API error: {exc}")
            if raise_on_error:
                raise
            # İnsansı fallback — klip kategorisine göre farklı kalıplar
            category_up = category.upper()
            if any(k in category_up for k in ["CLUTCH", "EPIC"]):
                fallback_title = f"Son saniyede gelen o {clip_title.split()[0] if clip_title else 'pozisyon'} 🎯 #Shorts"
            elif any(k in category_up for k in ["FUNNY", "FAIL", "RAGE"]):
                fallback_title = f"Bunu beklemiyordu ahahah 😂 #Shorts"
            else:
                hook_words = hook_caption.split()[:4] if hook_caption else []
                fallback_title = (" ".join(hook_words) + "... #Shorts") if hook_words else f"{clip_title} 🎮 #Shorts"
            ig_fallback_caption = (
                f"{hook_caption or clip_title}\n\n"
                f"Siz olsaydınız ne yapardınız? 👇\n\n"
                f"{'📌 ' + ig_credit + chr(10) if ig_credit else ''}"
                "#reels #fyp #gaming #oyun #twitch #türkçeyayın #keşfet #viral #shorts "
                "#komik #highlight #gamingturkiye #oyunkesitleri #türkçeoyun #gamer #clutch #türkiye #twitch"
            )
            return {
                "title": fallback_title,
                "description": (
                    f"{hook_caption or clip_title}\n\n"
                    f"🎮 {yt_credit}\n\n"
                    "#Shorts #Gaming #OyunKesitleri"
                ),
                "instagram_caption": ig_fallback_caption,
                "tags": [category.lower(), "shorts", "gaming", "oyun"],
                "provider": "Heuristic Fallback",
            }
