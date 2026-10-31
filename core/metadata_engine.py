"""
core/metadata_engine.py — İnsansı Başlık, Açıklama ve Canlı Trend Etiket Motoru
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any

from loguru import logger


class YouTubeTagMiner:
    """Mines real-time trending search queries from YouTube Autocomplete API."""

    @staticmethod
    def get_live_youtube_suggestions(query: str, max_results: int = 10) -> list[str]:
        encoded_query = urllib.parse.quote(query)
        url = f"https://suggestqueries.google.com/complete/search?client=youtube&ds=yt&q={encoded_query}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as response:
                content = response.read().decode("utf-8", errors="ignore")
                match = re.search(r"\[.*\]", content)
                if match:
                    data = json.loads(match.group(0))
                    if len(data) > 1 and isinstance(data[1], list):
                        suggestions = [item[0] for item in data[1] if isinstance(item, list) and item]
                        return suggestions[:max_results]
        except Exception as exc:
            logger.debug("YouTube autocomplete fetch failed for '{}': {}", query, exc)

        return []

    @classmethod
    def mine_popular_tags(
        cls, streamer_name: str, game_name: str | None = None, clip_topic: str | None = None, max_tags: int = 15
    ) -> dict[str, Any]:
        queries_to_try = [
            f"{streamer_name} {game_name}" if game_name else streamer_name,
            f"{streamer_name} komik anlar",
            f"{streamer_name} klip",
        ]
        if game_name:
            queries_to_try.append(f"{game_name} türkçe")
        if clip_topic:
            queries_to_try.append(f"{streamer_name} {clip_topic}")

        raw_suggestions = set()
        for q in queries_to_try:
            results = cls.get_live_youtube_suggestions(q, max_results=5)
            for r in results:
                raw_suggestions.add(r.strip())

        cleaned_tags: list[str] = []
        for s in raw_suggestions:
            if s and len(s) > 2 and s.lower() not in [t.lower() for t in cleaned_tags]:
                cleaned_tags.append(s)

        base_tags = [
            streamer_name.lower().replace(" ", ""),
            f"{streamer_name.lower().replace(' ', '')}klip",
            "shorts",
            "keşfet",
            "gaming",
        ]
        if game_name:
            base_tags.append(game_name.lower().replace(" ", ""))

        for bt in base_tags:
            if bt not in [t.lower() for t in cleaned_tags]:
                cleaned_tags.insert(0, bt)

        final_tags = cleaned_tags[:max_tags]

        hashtags = []
        for t in final_tags[:6]:
            tag_clean = re.sub(r"[^a-zA-Z0-9çğıöşüÇĞİÖŞÜ]", "", t)
            if tag_clean and len(tag_clean) > 2:
                hashtags.append(f"#{tag_clean.lower()}")

        return {"tags": final_tags, "hashtags": hashtags[:5], "tags_comma_separated": ", ".join(final_tags)}


class HumanMetadataEngine:
    """
    Generates 100% human-like, high-CTR titles, 3-second hook captions,
    and engagement-focused descriptions using DeepSeek-V3 (with Gemini fallback).
    """

    SYSTEM_PROMPT = """Sen YouTube Shorts, TikTok ve Instagram Reels için viral içerikler üreten usta bir Türk video editörüsün.
GÖREVİN: Verilen video klibi, transkripti ve yayıncı bilgisine göre izleyicinin kaydırmadan durup izleyeceği EN İNSANSI ve SAMİMİ başlık, açıklama ve kancaları üretmek.

═══════════════════════════════════════
KESİN KURALLAR — ROBOTİK VE YAPAY OLMAKTAN KAÇIN
═══════════════════════════════════════
1. ASLA "Şok Edici An!", "İnanılmaz!", "Tarihi An!", "Herkesi Büyüledi!" gibi AI klişeleri KULLANMA.
2. 3 FARKLI İNSANSI BAŞLIK VARYANTI ÜRET:
   - 'quote_based': Klipten geçen en komik / vurucu 1 repliği doğrudan alıntıla (Örn: "burada ölürsem oyunu silerim dedi ve...", "abi arkanda arkandaaaa! 💀").
   - 'pov_reaction': Gen-Z / POV izleyici tepkisi formatında yaz (Örn: "kanka 1 canla attığı clutcha bak amk", "gece 3'te ekiple gelen o delirme anı 😂").
   - 'streamer_tone': Yayıncının kendi konuşma tarzı ve mizahıyla yaz (Örn: "böyle bir şans olamaz ahahaha", "oyunu bırakıyorum beyler").
3. İLK 3 SANİYE KANCASI ('hook_caption'): Ekranda büyük puntolarla belirecek 2-4 kelimelik çok kısa ve merak uyandırıcı bir metin olsun (Örn: "BUNU BEKLEMİYORDU!", "KİMSE İNANMADI!", "İMKANSIZ CLUTCH!").
4. AÇIKLAMA ('description'):
   - 1. Satır: İzleyiciyi yorum yapmaya kışkırtan samimi bir soru (Örn: "Sizce burada suç kimdeydi? Yorumlarda buluşalım 👇😂").
   - 2. Satır: Yayıncı ve Oyun kredisi (Örn: "🎮 Yayıncı: @{streamer} | 🕹️ Oyun: {game}").
   - 3. Satır: 3-4 odaklı hashtag.

ÇIKTIYI YALNIZCA GEÇERLİ BİR JSON OBJESİ OLARAK DÖNDÜR. Başka hiçbir açıklama metni ekleme."""

    @classmethod
    def generate_metadata(
        cls,
        transcript_snippet: str = "",
        streamer_name: str = "Yayıncı",
        video_title: str = "",
        game_name: str | None = None,
        duration_sec: float = 30.0,
        youtube_username: str = "",
        instagram_username: str = "",
    ) -> dict[str, Any]:
        tag_data = YouTubeTagMiner.mine_popular_tags(
            streamer_name=streamer_name, game_name=game_name, clip_topic=video_title
        )

        yt_credit = f"@{youtube_username}" if youtube_username else f"@{streamer_name.replace(' ', '')}"
        ig_credit = f"@{instagram_username}" if instagram_username else ""

        user_prompt = f"""
Klip Bilgileri:
- Yayıncı / Kanal: {streamer_name}
- YouTube Kullanıcı Adı: {yt_credit}
- Instagram Kullanıcı Adı: {ig_credit or 'Belirtilmemiş'}
- Oyun / Kategori: {game_name or "Bilinmiyor / Genel"}
- Video Başlığı: {video_title}
- Klip Süresi: {duration_sec:.1f} saniye
- Klipte Konuşulanlar (Transkript):
\"\"\"{transcript_snippet}\"\"\"

Lütfen yukarıdaki kurallara uygun olarak aşağıdaki JSON şablonunda çıktı üret.
Açıklamada yayıncı kredisi için MUTLAKA "{yt_credit}" kullanıcı adını kullan (Örn: "🎮 {yt_credit} | 🕹️ {game_name or 'Gaming'}").
{{
  "titles": {{
    "quote_based": "Transkriptten replik başlığı",
    "pov_reaction": "POV / İzleyici reaksiyon başlığı",
    "streamer_tone": "Yayıncı mizahı / tarzı başlığı"
  }},
  "recommended_title": "En yüksek CTR alacak 1 tanesi",
  "hook_caption": "2-4 kelimelik büyük ekran kancası",
  "engagement_question": "Yoruma teşvik eden soru cümlesi",
  "description": "Shorts açıklaması (Soru + Kredi + Hashtagler)"
}}
"""

        result_json = None
        # 1. DeepSeek-V3 Call
        if not getattr(cls, "_DEEPSEEK_CREDIT_EXHAUSTED", False):
            try:
                from core.deepseek_engine import DeepSeekEngine

                if DeepSeekEngine.is_available():
                    client, model_name, _ = DeepSeekEngine.get_client_and_model()
                    messages_payload: list[Any] = [
                        {"role": "system", "content": cls.SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ]
                    kwargs: dict[str, Any] = {
                        "model": model_name,
                        "messages": messages_payload,
                        "temperature": 0.7,
                        "max_tokens": 800,
                    }
                    if "deepseek" in model_name:
                        kwargs["response_format"] = {"type": "json_object"}
                    response = client.chat.completions.create(**kwargs)
                    if response and getattr(response, "choices", None) and len(response.choices) > 0:
                        msg = response.choices[0].message
                        raw_text = getattr(msg, "content", "") or ""
                        clean_json = re.search(r"\{.*\}", raw_text, re.DOTALL)
                        if clean_json:
                            result_json = json.loads(clean_json.group(0))
            except Exception as exc:
                err_str = str(exc)
                if "402" in err_str or "credit" in err_str.lower():
                    cls._DEEPSEEK_CREDIT_EXHAUSTED = True
                    logger.info("OpenRouter bakiyesi tükendi (402). Meta veri motoru doğrudan Gemini yedeğine geçirildi.")
                else:
                    logger.debug("DeepSeek metadata generation failed: {}", exc)

        # 2. Gemini Fallback
        if not result_json:
            try:
                from google import genai
                from google.genai import types

                api_key = os.getenv("GEMINI_API_KEY")
                if not api_key:
                    try:
                        from dotenv import load_dotenv

                        load_dotenv(".env")
                        api_key = os.getenv("GEMINI_API_KEY")
                    except Exception:
                        pass
                if api_key:
                    g_client = genai.Client(api_key=api_key)
                    gemini_models = [
                        "gemini-3.8-flash",
                        "gemini-3.5-flash-lite",
                        "gemini-flash-lite-latest",
                        "gemini-3.6-flash",
                        "gemini-3.7-flash",
                        "gemini-3.5-flash",
                        "gemini-flash-latest",
                    ]
                    for m in gemini_models:
                        try:
                            resp = g_client.models.generate_content(
                                model=m,
                                contents=f"{cls.SYSTEM_PROMPT}\n\n{user_prompt}",
                                config=types.GenerateContentConfig(response_mime_type="application/json"),
                            )
                            if resp and resp.text:
                                clean_json = re.search(r"\{.*\}", resp.text, re.DOTALL)
                                if clean_json:
                                    result_json = json.loads(clean_json.group(0))
                                    break
                        except Exception as m_err:
                            logger.debug("Gemini model {} failed for metadata: {}", m, m_err)
                            continue
            except Exception as exc:
                logger.debug("Gemini fallback metadata generation failed: {}", exc)

        # 3. Rule-based Fallback
        if not result_json:
            snippet_part = transcript_snippet[:40] if transcript_snippet else video_title[:40]
            result_json = {
                "titles": {
                    "quote_based": f'"{snippet_part}..." dedi ve...',
                    "pov_reaction": f"kanka {streamer_name}'in bu pozisyona bak amk 😂",
                    "streamer_tone": f"oyun bitti beyler 😭 #Shorts",
                },
                "recommended_title": f"kanka {streamer_name}'in bu pozisyona bak 😂 #Shorts",
                "hook_caption": "BEKLENMEDIK AN!",
                "engagement_question": "Sizce burada ne yapılmalıydı? Yorumlara yazın 👇",
                "description": (
                    f"Sizce burada ne yapılmalıydı? Yorumlara yazın 👇\n\n"
                    f"🎮 {yt_credit} | 🕹️ {game_name or 'Gaming'}\n\n"
                    f"{' '.join(tag_data['hashtags'])}"
                ),
            }

        result_json["tags"] = tag_data["tags"]
        result_json["hashtags"] = tag_data["hashtags"]
        result_json["tags_comma_separated"] = tag_data["tags_comma_separated"]
        return result_json

