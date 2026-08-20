import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from core.extractor import YouTubeExtractor
from core.transcript import TranscriptManager

# Load .env file
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

class GeminiBatchClipVerdict(BaseModel):
    candidate_id: int = Field(description="Değerlendirilen adayın ID'si")
    verdict: str = Field(description="'KEEP' (seçildi) veya 'DROP' (elendi)")
    category: str = Field(description="Kategori: CLUTCH, FAIL/FUNNY, RAGE/REACTION, VICTORY, JUMPSCARE, EPIC_MOMENT, STORY")
    title: str = Field(description="Shorts/TikTok için dikkat çekici Türkçe başlık")
    hook_caption: str = Field(description="İlk 3 saniyede izleyiciyi yakalayacak kanca başlığı/yazısı")
    why_viral: str = Field(description="Neden viral olacağının analizi")
    viral_confidence: int = Field(description="Viral olma olasılığı puanı (1-100)")
    suggested_start: float = Field(description="Önerilen tam başlangıç saniyesi")
    suggested_end: float = Field(description="Önerilen tam bitiş saniyesi")

class GeminiGamingBatchResult(BaseModel):
    selected_clips: List[GeminiBatchClipVerdict] = Field(description="Seçilen ve değerlendirilen klipler")

class GeminiHighlightEngine:
    """Uses Google Gemini Flash to batch-judge Top-N gaming candidate clips in 1 structured call."""

    MODELS_TO_TRY = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]

    @classmethod
    def batch_judge_gaming_candidates(
        cls,
        candidates: List[Dict[str, Any]],
        video_title: str,
        total_duration: int,
        target_clips: int = 3,
        api_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Takes Top-15 DSP candidates and evaluates them in a single batch Gemini call.
        """
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError("Gemini API Key bulunamadı.")

        client = genai.Client(api_key=key)

        # Prepare compact JSON payload for Gemini
        candidates_summary = []
        for c in candidates:
            candidates_summary.append({
                "candidate_id": c["candidate_id"],
                "time_window": f"{c['start_formatted']} - {c['end_formatted']} (Zirve: {c['peak_formatted']})",
                "raw_start_sec": c["start_time"],
                "raw_end_sec": c["end_time"],
                "signals": c["signals"],
                "fusion_score": c["fusion_score"],
                "transcript": c["transcript_snippet"]
            })

        system_instruction = (
            "Sen YouTube Shorts, TikTok ve Instagram Reels için milyonlar izlenen Gaming / Yayın klipleri seçen "
            "profesyonel bir video editörüsün. Sana sinyal işleme (ses patlamaları, sessizlikten çığlığa geçiş, "
            "izleyici tekrar yoğunluğu) ile tespit edilmiş aday klip havuzu verilecek.\n"
            "GÖREVİN:\n"
            "1. Tüm adayları bağlamsal olarak incele, sahte alarmları (sadece gürültü olan boş anları) ele ('DROP').\n"
            "2. Gerçekten viral olabilecek en iyi anları ('KEEP') olarak işaretle ve en yüksek puandan sırala.\n"
            "3. Her klip için aksiyonun başladığı ve bittiği en doğru başlangıç/bitiş saniyelerini öner.\n"
            "4. Dikkat çekici bir başlık, ilk 3 saniye kanca yazısı (Hook) ve kategori belirle."
        )

        prompt = f"""
Video Başlığı: {video_title}
Toplam Süre: {YouTubeExtractor.format_seconds(total_duration)} ({total_duration}s)
İstenen En İyi Klip Sayısı: {target_clips}

ADAY HAVUZU (TOP-{len(candidates)} Sinyal Verisi):
{json.dumps(candidates_summary, indent=2, ensure_ascii=False)}

Lütfen bu adayları tek tek yargıla ve en iyi {target_clips} klibi 'KEEP' olarak seçip detaylandır.
"""

        last_error = None
        data = None

        for model_name in cls.MODELS_TO_TRY:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=GeminiGamingBatchResult,
                        temperature=0.3
                    ),
                )
                data = json.loads(response.text)
                break
            except Exception as e:
                last_error = e
                continue

        if not data:
            raise RuntimeError(f"Gemini Batch API hatası: {str(last_error)}")

        verdicts = data.get("selected_clips", [])
        
        # Filter KEEP verdicts and sort by confidence
        keep_clips = [v for v in verdicts if v.get("verdict", "").upper() == "KEEP"]
        if not keep_clips:
            # Fallback if all marked drop
            keep_clips = verdicts[:target_clips]

        keep_clips.sort(key=lambda x: x.get("viral_confidence", 0), reverse=True)
        top_selected = keep_clips[:target_clips]

        # Build standardized clip objects
        final_clips = []
        for rank, clip in enumerate(top_selected, start=1):
            s_time = max(0.0, float(clip.get("suggested_start", 0.0)))
            e_time = min(float(total_duration), float(clip.get("suggested_end", s_time + 30.0)))
            
            # Ensure valid duration
            if e_time <= s_time or (e_time - s_time) < 10.0:
                e_time = min(float(total_duration), s_time + 35.0)

            dur = round(e_time - s_time, 1)

            # Match original candidate
            cand_match = next((c for c in candidates if c["candidate_id"] == clip.get("candidate_id")), None)
            snippet = cand_match["transcript_snippet"] if cand_match else ""

            final_clips.append({
                "rank": rank,
                "candidate_id": clip.get("candidate_id"),
                "title": clip.get("title", f"Gaming Klip #{rank}"),
                "category": clip.get("category", "EPIC_MOMENT"),
                "score": int(clip.get("viral_confidence", 90)),
                "intensity": int(clip.get("viral_confidence", 90)),
                "hook_caption": clip.get("hook_caption", ""),
                "reason": f"🎮 [{clip.get('category', 'EPIC')}] {clip.get('hook_caption', '')} — {clip.get('why_viral', '')}",
                "peak_time": round((s_time + e_time) / 2.0, 1),
                "peak_formatted": YouTubeExtractor.format_seconds((s_time + e_time) / 2.0),
                "start_time": round(s_time, 1),
                "start_formatted": YouTubeExtractor.format_seconds(s_time),
                "end_time": round(e_time, 1),
                "end_formatted": YouTubeExtractor.format_seconds(e_time),
                "duration": dur,
                "duration_formatted": f"{int(dur)} sn",
                "text": snippet
            })

        final_clips.sort(key=lambda x: x["start_time"])
        return final_clips

    @classmethod
    def generate_shorts_metadata(
        cls,
        clip_title: str,
        hook_caption: str,
        category: str,
        video_title: str = "",
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate high-CTR title, SEO description, and tags for YouTube Shorts."""
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            # Clean heuristic fallback
            clean_title = f"{clip_title} 🔥 #Shorts #Gaming"
            clean_desc = f"🎯 {hook_caption}\n\nOrijinal Video: {video_title}\n\n#Shorts #Gaming #Viral #Highlights"
            clean_tags = ["shorts", "gaming", "viral", "highlights", "komik anlar", "türkçe gaming"]
            return {"title": clean_title, "description": clean_desc, "tags": clean_tags}

        client = genai.Client(api_key=key)

        prompt = f"""
Sen YouTube Shorts, TikTok ve SEO algoritmalarını mükemmel bilen uzman bir Gaming içerik yöneticisisin.
Aşağıdaki oyun klibi için ASLA jenerik/kopya olmayan, doğrudan bu oyuna, olaya ve klibe özel başlık, açıklama ve etiketler üret:

Orijinal Video Başlığı / Kanal: {video_title}
Klip Başlığı: {clip_title}
Kategori: {category}
Klipteki Kanca Cümle / Olay: "{hook_caption}"

GÖREVLER:
1. Başlık: İzleyicinin kaydırmasını (scroll) anında durduracak, merak veya kahkaha uyandıran, BÜYÜK HARF vurgulu, 2 emoji içeren ve sonunda '#Shorts' etiketi olan maksimum 90 karakterlik Türkçe başlık.
2. Açıklama: İlk satırda güçlü bir hook, ikinci paragrafta klibin heyecanını anlatan kısa özet, oyun adı ve 5 adet spesifik hashtag (#OyunAdi #Shorts #Gaming vb.).
3. Etiketler (Tags): Kesinlikle sadece 'gaming, shorts' gibi genel kelimelerle kalma! Oyunun tam adını, klibin konusunu, oynanış mekaniğini, Türkçe oyun terimlerini ve niş arama terimlerini içeren 10-14 adet spesifik etiket listesi üret. (Örn BeamNG ise: 'beamng drive', 'beamng türkçe', 'araba ön kaldırma', 'araba kazaları', 'komik oyun anları', 'beamng rekor').
"""
        class GeminiShortsMeta(BaseModel):
            title: str = Field(description="Maks 90 karakterlik dikkat çekici YouTube Shorts başlığı")
            description: str = Field(description="Kanca ve hashtag içeren açıklama")
            tags: List[str] = Field(description="Oyun ve klibe özel 10-14 adet arama etiketi")

        for model_name in cls.MODELS_TO_TRY:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=GeminiShortsMeta,
                        temperature=0.6
                    ),
                )
                res_dict = json.loads(response.text)
                return {
                    "title": res_dict.get("title", f"{clip_title} #Shorts"),
                    "description": res_dict.get("description", f"{hook_caption}\n\n#Shorts"),
                    "tags": res_dict.get("tags", [video_title.lower(), clip_title.lower(), "shorts", "gaming"])
                }
            except Exception:
                continue

        return {
            "title": f"{clip_title} 🔥 #Shorts",
            "description": f"🎯 {hook_caption}\n\n#Shorts #Gaming",
            "tags": ["shorts", "gaming", "viral"]
        }
