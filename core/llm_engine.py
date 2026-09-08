"""
core/llm_engine.py — Gemini Flash tabanlı Viral Skorlama Motoru

Pipeline katmanları:
    CandidateRanker (sinyal füzyonu) → GeminiHighlightEngine (LLM yargılaması) → AlignmentEngine

DEĞİŞİKLİK GEÇMİŞİ:
    v2 (2026-09-04):
        - Ağırlıklar scoring_config.py'a taşındı (madde 4)
        - MUNDANE/NONE kategori fallback eklendi (madde 5)
        - Kısa gerekçe alanı (rationale) eklendi (madde 8)
        - Sinyal doğrulama faktörü genişletildi: pitch_variance + frame_diff dahil (madde 7)
        - Bant etiketleme yardımcı fonksiyonu eklendi (madde 2)
        - Ensemble/medyan skorlama modu eklendi (madde 3)
        - Skor tutarlılık testi altyapısı eklendi (madde 1)
"""

import json
import os
import statistics
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field

import core.scoring_config as SC
from core.extractor import YouTubeExtractor

# Load .env file
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


# ---------------------------------------------------------------------------
# Pydantic Şemaları
# ---------------------------------------------------------------------------


class GeminiBatchClipVerdict(BaseModel):
    candidate_id: int = Field(description="Değerlendirilen adayın ID'si")
    verdict: str = Field(description="'KEEP' (seçildi) veya 'DROP' (elendi)")
    category: str = Field(
        description=(
            "Kategori: CLUTCH, FAIL/FUNNY, RAGE/REACTION, JUMPSCARE, EPIC_MOMENT, STORY "
            "veya viral potansiyeli olmayan sıradan anlar için MUNDANE"
        )
    )
    title: str = Field(description="Shorts/TikTok için dikkat çekici Türkçe başlık")
    hook_caption: str = Field(description="İlk 3 saniyede izleyiciyi yakalayacak kanca başlığı/yazısı")
    rationale: str = Field(
        description="Neden bu skoru verdiğini açıklayan 1-2 cümlelik kısa gerekçe (spesifik olay veya sinyal referansı ile)"
    )
    why_viral: str = Field(description="Neden viral olacağının analizi")
    viral_confidence: int = Field(description="Viral olma olasılığı puanı (1-100)")
    suggested_start: float = Field(description="Önerilen tam başlangıç saniyesi")
    suggested_end: float = Field(description="Önerilen tam bitiş saniyesi")


class GeminiGamingBatchResult(BaseModel):
    selected_clips: list[GeminiBatchClipVerdict] = Field(description="Seçilen ve değerlendirilen klipler")


# ---------------------------------------------------------------------------
# Yardımcı Fonksiyonlar
# ---------------------------------------------------------------------------


def score_to_band(score: int) -> str:
    """
    Ham 0-100 viral skorunu konfigüre edilmiş bant etiketine çevirir.

    scoring_config.BAND_LABELS_ENABLED kapalıysa "—" döner.
    Varyans testi sonucuna göre açılıp kapatılabilir.

    Args:
        score: Gemini'den gelen viral_confidence (0-100).

    Returns:
        "Yüksek" / "Orta-Yüksek" / "Orta" / "Düşük" veya "—".
    """
    if not SC.BAND_LABELS_ENABLED:
        return "—"
    for band in SC.SCORE_BANDS:
        b_min = int(float(str(band.get("min", 0))))
        b_max = int(float(str(band.get("max", 100))))
        if b_min <= score <= b_max:
            return str(band.get("label", "Düşük"))
    return "Düşük"


def _build_signal_validation_section(signals: dict[str, Any]) -> str:
    """
    Sinyal doğrulama faktörü için prompt metnini oluşturur.
    Hem eski sinyalleri (audio_spike, silence_burst) hem yeni sinyalleri
    (pitch_variance, frame_diff, speech_rate_accel) içerir.
    """
    parts = []

    if signals.get("audio_spike", 0) > 0.3:
        parts.append(f"ses dalgalanması={signals['audio_spike']:.2f}")
    if signals.get("silence_burst", 0) > 0.2:
        parts.append(f"sessizlik-patlama={signals['silence_burst']:.2f}")
    if signals.get("vocal_spike", 0) > 0.2:
        parts.append(f"vokal_baskınlığı={signals['vocal_spike']:.2f} (insan sesi/konuşma)")
    if signals.get("pitch_variance", 0) > 0.2:
        parts.append(f"pitch_varyans={signals['pitch_variance']:.2f} (kahkaha/coşku tespiti)")
    if signals.get("frame_diff", 0) > 0.2:
        parts.append(f"görsel-değişim={signals['frame_diff']:.2f} (sahne kesimi tespiti)")
    if signals.get("speech_rate_accel", 0) > 0.2:
        parts.append(f"konuşma_ivmesi={signals['speech_rate_accel']:.2f}")
    if signals.get("transcript_density", 0) > 0.3:
        parts.append(f"transkript_yoğunluğu={signals['transcript_density']:.2f}")
    if signals.get("comment_density", 0) > 0.1 or signals.get("comment_count", 0) > 0:
        c_count = signals.get("comment_count", 0)
        c_react = signals.get("comment_reaction", "HIGHLIGHT")
        parts.append(f"⭐ İZLEYİCİ YORUMU ÖNE ÇIKAN (VIP) [{c_count} yorum, tepki={c_react}]")

    if not parts:
        return "sinyal doğrulama: zayıf/yetersiz"
    return "aktif sinyaller: " + ", ".join(parts)


def _gemini_single_call(
    client: genai.Client,
    models_to_try: list[str],
    prompt: str,
    system_instruction: str,
) -> dict[str, Any] | None:
    """Tek bir Gemini çağrısı yapar, model fallback uygular."""
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=GeminiGamingBatchResult,
                    temperature=0.3,
                ),
            )
            if response and response.text:
                return json.loads(response.text)
            return None
        except Exception as e:
            logger.debug("Model {} failed: {}", model_name, e)
            continue
    return None


# ---------------------------------------------------------------------------
# Ana Motor
# ---------------------------------------------------------------------------


class GeminiHighlightEngine:
    """Uses Google Gemini Flash to batch-judge Top-N gaming candidate clips in 1 structured call."""

    MODELS_TO_TRY = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
    ]

    @classmethod
    def _build_prompt_and_system(
        cls,
        candidates: list[dict[str, Any]],
        video_title: str,
        total_duration: int,
        target_clips: int,
        channel_dna: dict[str, Any] | None = None,
    ):
        """Prompt ve system_instruction metnini oluşturur — test/ensemble için tekrar kullanılabilir."""
        candidates_summary = []
        for c in candidates:
            sig = c.get("signals", {})
            c_summary = {
                "candidate_id": c["candidate_id"],
                "time_window": f"{c['start_formatted']} - {c['end_formatted']} (Zirve: {c['peak_formatted']})",
                "raw_start_sec": c["start_time"],
                "raw_end_sec": c["end_time"],
                "fusion_score": c["fusion_score"],
                "is_vip": c.get("is_vip", False),
                "signal_summary": _build_signal_validation_section(sig),
                "transcript": c["transcript_snippet"],
            }
            if c.get("comment_samples"):
                c_summary["viewer_comments"] = c["comment_samples"]
            candidates_summary.append(c_summary)

        categories_str = ", ".join(SC.CATEGORIES)

        # Ağırlıklar artık scoring_config'den geliyor
        # NOT: Bu ağırlıklar sezgisel/doğrulanmamıştır — referans-set kalibrasyonuyla güncellenmeli.
        weight_guide = (
            f"Hook Gücü %{SC.HOOK_STRENGTH_WEIGHT} + "
            f"Duygu/Kategori Şiddeti %{SC.EMOTION_WEIGHT} + "
            f"Hikaye Bütünlüğü %{SC.STORY_COMPLETENESS_WEIGHT} + "
            f"Sinyal Doğrulama %{SC.SIGNAL_VALIDATION_WEIGHT}"
        )

        system_instruction = (
            "Sen YouTube Shorts, TikTok ve Instagram Reels için milyonlar izlenen Gaming / Yayın kesitleri seçen "
            "profesyonel bir video editörüsün. Sana sinyal işleme ile tespit edilmiş aday klip havuzu verilecek.\n\n"
            "GÖREVİN:\n"
            "1. Boş gürültüleri ele ('DROP'), sadece izleyicinin durup izleyeceği veya güleceği anları ('KEEP') seç.\n"
            "2. Başlık ve Kanca (Hook) için ASLA robotik 'İnanılmaz!', 'Şok etti!', 'Tarihi an!' gibi AI klişeleri KULLANMA!\n"
            "3. Tamamen samimi bir oyuncunun/izleyicinin ağzından doğal Türkçe başlıklar yaz "
            "(Örn: 'Burada ölürsem oyunu silerim dedi ve...', '1v4 pozisyonda gelen o panik', 'Gülmekten öldüğüm o an 😂').\n"
            "4. İlk 3 saniye kancasını ekranda büyük puntolu dikkat çekici bir cümle olarak hazırla.\n"
            f"5. viral_confidence puanı için şu ağırlıkları kullan: {weight_guide}\n"
            f"6. Kategori için şunlardan birini seç: {categories_str}\n"
            "   ÖNEMLI: Eğer an gerçekten sıradan ve viral potansiyeli yoksa MUNDANE seç — "
            "zorla kategori atama! MUNDANE seçersen viral_confidence en fazla 30 olabilir.\n"
            "7. rationale alanına: tam olarak hangi sesi/hareketi/sinyali görerek bu puanı verdiğini "
            "1-2 cümleyle yaz. 'İyi bir an' gibi genel cümleler kullanma.\n"
            "8. İZLEYİCİ YORUMU İLE VURGULANAN (VIP) ADAYLAR: Eğer bir adayda 'viewer_comments' veya 'is_vip' varsa, "
            "bu an izleyicilerin bizzat saniye verip güldüğü/reaksiyon verdiği organik andır. Bu anlar insan doğrulamalı en güçlü "
            "viral adaylarıdır! Bu anları KESİNLİKLE 'KEEP' olarak seç ve yüksek viral puanı (88-98 bandı) vererek ilk sıralara yerleştir.\n"
            "9. HİKAYE VE DİYALOG BÜTÜNLÜĞÜ (SETUP & PUNCHLINE): Bir esprinin veya olayın anlaşılması için giriş cümlesini (setup) "
            "ve vurucu sonucunu (punchline/kahkaha) klipte mutlaka koru. Eksik, yarım kalan veya cümlenin ortasından başlayan kesitleri 'suggested_start' ve 'suggested_end' değerleriyle tam hikayeyi kapsayacak şekilde genişlet."
        )

        dna_section = ""
        if channel_dna:
            try:
                from core.channel_dna import ChannelDNAManager

                dna_section = ChannelDNAManager().format_prompt_context(channel_dna)
            except Exception:
                pass

        prompt = f"""
Video Başlığı: {video_title}
Toplam Süre: {YouTubeExtractor.format_seconds(total_duration)} ({total_duration}s)
İstenen En İyi Klip Sayısı: {target_clips}
{dna_section}
ADAY HAVUZU (TOP-{len(candidates)} Sinyal Verisi):
{json.dumps(candidates_summary, indent=2, ensure_ascii=False)}

Lütfen bu adayları tek tek yargıla ve en iyi {target_clips} klibi 'KEEP' olarak seçip detaylandır.
MUNDANE değil, gerçekten viral potansiyeli olan anları seç.
"""
        return prompt, system_instruction

    @classmethod
    def batch_judge_gaming_candidates(
        cls,
        candidates: list[dict[str, Any]],
        video_title: str,
        total_duration: int,
        target_clips: int = 3,
        api_key: str | None = None,
        channel_dna: dict[str, Any] | None = None,
        ensemble_runs: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Top-N adayı Gemini Flash ile yargılar, viral skor hesaplar.

        Args:
            ensemble_runs: Kaç kez tekrar çalıştırıp medyan alınacak.
                           None ise scoring_config.ENSEMBLE_RUNS kullanılır.
                           1 = tekil çalışma (varsayılan).
        """
        n_runs = ensemble_runs if ensemble_runs is not None else SC.ENSEMBLE_RUNS

        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY bulunamadı.")

        client = genai.Client(api_key=key)
        prompt, system_instruction = cls._build_prompt_and_system(
            candidates, video_title, total_duration, target_clips, channel_dna
        )

        if n_runs <= 1:
            # Tekil çalışma (standart davranış)
            data = _gemini_single_call(client, cls.MODELS_TO_TRY, prompt, system_instruction)
            if not data:
                raise RuntimeError("Gemini Batch Analiz hatası: tüm modeller başarısız.")
            return cls._build_final_clips(data, candidates, total_duration, target_clips)

        # Ensemble modu: N kez çağır, her aday için medyan skor al
        logger.info("Ensemble modu: {} çalışma yapılıyor...", n_runs)
        all_runs: list[list[dict]] = []
        for run_idx in range(n_runs):
            run_data = _gemini_single_call(client, cls.MODELS_TO_TRY, prompt, system_instruction)
            if run_data:
                all_runs.append(run_data.get("selected_clips", []))
                logger.debug("Ensemble run {}/{} tamamlandı", run_idx + 1, n_runs)

        if not all_runs:
            raise RuntimeError("Ensemble: tüm çalışmalar başarısız.")

        # Her aday_id için tüm run'lardaki viral_confidence medyanını hesapla
        score_by_cid: dict[int, list[int]] = {}
        representative: dict[int, dict] = {}
        for run_verdicts in all_runs:
            for v in run_verdicts:
                cid = v.get("candidate_id")
                if cid is None:
                    continue
                score_by_cid.setdefault(cid, []).append(int(v.get("viral_confidence", 0)))
                representative.setdefault(cid, v)

        # Medyan skoru uygula
        for cid, scores in score_by_cid.items():
            median_score = int(statistics.median(scores))
            representative[cid]["viral_confidence"] = median_score
            representative[cid]["rationale"] = (
                representative[cid].get("rationale", "") + f" [Ensemble medyan: {median_score}, runs={scores}]"
            )

        ensemble_data = {"selected_clips": list(representative.values())}
        return cls._build_final_clips(ensemble_data, candidates, total_duration, target_clips)

    @classmethod
    def _build_final_clips(
        cls,
        data: dict[str, Any],
        candidates: list[dict[str, Any]],
        total_duration: int,
        target_clips: int,
    ) -> list[dict[str, Any]]:
        """Ham Gemini çıktısını standart klip listesine dönüştürür."""
        verdicts = data.get("selected_clips", [])

        # MUNDANE kırpma: MUNDANE kategorisindeki adayların skoru kap ile sınırla
        for v in verdicts:
            if str(v.get("category", "")).upper() == "MUNDANE":
                orig = int(v.get("viral_confidence", 0))
                v["viral_confidence"] = min(orig, SC.MUNDANE_SCORE_CAP)
                if v.get("verdict", "").upper() == "KEEP":
                    v["verdict"] = "DROP"  # MUNDANE olanları zorla KEEP yapma
                    logger.debug(
                        "MUNDANE aday {} DROP'a çevrildi (skor kırpıldı: {} → {})",
                        v.get("candidate_id"),
                        orig,
                        v["viral_confidence"],
                    )

        # VIP İzleyici Yorumu Puan Takviyesi: İzleyici yorumu olan anları ilk sıralara yükselt
        for v in verdicts:
            cid = v.get("candidate_id")
            cand_match = next((c for c in candidates if c["candidate_id"] == cid), None)
            if cand_match and (
                cand_match.get("is_vip")
                or cand_match.get("from_comment")
                or cand_match.get("signals", {}).get("comment_count", 0) > 0
            ):
                orig_score = int(v.get("viral_confidence", 80))
                # İzleyici teyitli anlara taban puan (min 88) ve bonus puan ekle (+15)
                boosted_score = max(SC.VIP_COMMENT_MIN_SCORE, min(98, orig_score + SC.COMMENT_BOOST_POINTS))
                v["viral_confidence"] = boosted_score
                if str(v.get("category", "")).upper() != "MUNDANE":
                    v["verdict"] = "KEEP"

                # Rationale'a izleyici teyidini açıkça ekle
                c_count = cand_match.get("signals", {}).get("comment_count", 1)
                c_react = cand_match.get("signals", {}).get("comment_reaction") or "HIGHLIGHT"
                curr_rationale = str(v.get("rationale", "")).strip()
                if "İzleyici Yorumu" not in curr_rationale:
                    v["rationale"] = (
                        f"⭐ [İzleyici Yorumu VIP Teyidi ({c_count} yorum, {c_react})] {curr_rationale}".strip()
                    )

        keep_clips = [v for v in verdicts if v.get("verdict", "").upper() == "KEEP"]
        if not keep_clips:
            # Fallback: MUNDANE olmayanlardan en iyileri al
            non_mundane = [v for v in verdicts if str(v.get("category", "")).upper() != "MUNDANE"]
            keep_clips = non_mundane[:target_clips] if non_mundane else verdicts[:target_clips]

        keep_clips.sort(key=lambda x: x.get("viral_confidence", 0), reverse=True)
        top_selected = keep_clips[:target_clips]

        final_clips = []
        for rank, clip in enumerate(top_selected, start=1):
            s_time = max(0.0, float(clip.get("suggested_start", 0.0)))
            e_time = min(float(total_duration), float(clip.get("suggested_end", s_time + 30.0)))

            if e_time <= s_time or (e_time - s_time) < 10.0:
                e_time = min(float(total_duration), s_time + 35.0)

            dur = round(e_time - s_time, 1)

            cand_match = next((c for c in candidates if c["candidate_id"] == clip.get("candidate_id")), None)
            snippet = cand_match["transcript_snippet"] if cand_match else ""

            raw_score = int(clip.get("viral_confidence", 90))
            category = clip.get("category", "EPIC_MOMENT")
            rationale = clip.get("rationale", "")
            why_viral = clip.get("why_viral", "")

            final_clips.append(
                {
                    "rank": rank,
                    "candidate_id": clip.get("candidate_id"),
                    "title": clip.get("title", f"Gaming Klip #{rank}"),
                    "category": category,
                    "score": raw_score,
                    "score_band": score_to_band(raw_score),  # Bant etiketi (madde 2)
                    "intensity": raw_score,
                    "rationale": rationale,  # Kısa gerekçe (madde 8)
                    "hook_caption": clip.get("hook_caption", ""),
                    "reason": f"🎮 [{category}] {clip.get('hook_caption', '')} — {why_viral}",
                    "peak_time": round((s_time + e_time) / 2.0, 1),
                    "peak_formatted": YouTubeExtractor.format_seconds((s_time + e_time) / 2.0),
                    "start_time": round(s_time, 1),
                    "start_formatted": YouTubeExtractor.format_seconds(s_time),
                    "end_time": round(e_time, 1),
                    "end_formatted": YouTubeExtractor.format_seconds(e_time),
                    "duration": dur,
                    "duration_formatted": f"{int(dur)} sn",
                    "text": snippet,
                }
            )

        final_clips.sort(key=lambda x: x["start_time"])
        return final_clips

    # -----------------------------------------------------------------------
    # Skor Tutarlılık Testi (Madde 1)
    # -----------------------------------------------------------------------
    @classmethod
    def score_consistency_test(
        cls,
        candidates: list[dict[str, Any]],
        video_title: str,
        total_duration: int,
        api_key: str | None = None,
        runs: int | None = None,
    ) -> dict[str, Any]:
        """
        Aynı aday listesini N kez bağımsız olarak skorlatır ve varyansı raporlar.

        Amaç: mevcut sistemin run-to-run kararlılığını ölçmek.
        Yüksek varyans → ensemble modu veya bant sistemi devreye alınmalı.

        Args:
            candidates:    Puanlanacak klip adayları (CandidateRanker çıktısı).
            video_title:   Gemini'ye gönderilecek video başlığı.
            total_duration: Video süresi (saniye).
            api_key:       Gemini API anahtarı.
            runs:          Tekrar sayısı. None ise scoring_config.CONSISTENCY_TEST_RUNS.

        Returns:
            {
              "run_results": [...],        # Her run'daki ham sonuçlar
              "per_candidate": {           # Her aday için istatistikler
                  <candidate_id>: {
                      "scores": [...],
                      "mean": float,
                      "std": float,
                      "range": int,        # max - min
                      "verdict": "STABLE" | "UNSTABLE"
                  }
              },
              "summary": {
                  "mean_std": float,       # Tüm adayların ortalama std'si
                  "max_range": int,
                  "recommendation": str
              }
            }
        """
        n_runs = runs if runs is not None else SC.CONSISTENCY_TEST_RUNS
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY bulunamadı.")

        client = genai.Client(api_key=key)
        prompt, system_instruction = cls._build_prompt_and_system(
            candidates, video_title, total_duration, target_clips=len(candidates)
        )

        run_results = []
        for i in range(n_runs):
            data = _gemini_single_call(client, cls.MODELS_TO_TRY, prompt, system_instruction)
            run_results.append(data or {})
            logger.info("Tutarlılık testi run {}/{} tamamlandı", i + 1, n_runs)

        # Her aday için skor dizisi oluştur
        per_candidate: dict[int, dict] = {}
        for run_data in run_results:
            for v in run_data.get("selected_clips", []):
                cid = v.get("candidate_id")
                if cid is None:
                    continue
                per_candidate.setdefault(cid, {"scores": [], "categories": []})
                per_candidate[cid]["scores"].append(int(v.get("viral_confidence", 0)))
                per_candidate[cid]["categories"].append(v.get("category", "?"))

        # İstatistikler
        all_stds = []
        all_ranges = []
        for _cid, info in per_candidate.items():
            scores = info["scores"]
            if len(scores) < 2:
                info["std"] = 0.0
                info["mean"] = float(scores[0]) if scores else 0.0
                info["range"] = 0
                info["verdict"] = "STABLE"
                continue
            mean = statistics.mean(scores)
            std = statistics.stdev(scores)
            rng = max(scores) - min(scores)
            info["mean"] = round(mean, 1)
            info["std"] = round(std, 1)
            info["range"] = rng
            info["verdict"] = "STABLE" if rng <= 15 else "UNSTABLE"
            all_stds.append(std)
            all_ranges.append(rng)

        mean_std = round(statistics.mean(all_stds), 1) if all_stds else 0.0
        max_range = max(all_ranges) if all_ranges else 0

        if max_range > 25:
            recommendation = (
                "⚠️ Yüksek varyans tespit edildi. scoring_config.ENSEMBLE_RUNS=3 ve BAND_LABELS_ENABLED=True önerilir."
            )
        elif max_range > 15:
            recommendation = (
                "ℹ️ Orta varyans. Bant etiketleme açılabilir (BAND_LABELS_ENABLED=True). Ensemble opsiyonel."
            )
        else:
            recommendation = "✅ Sistem kararlı. Mevcut tekil çalışma yeterli."

        logger.info(
            "Tutarlılık Testi Sonucu — Ortalama STD: {}, Max Aralık: {}\n{}", mean_std, max_range, recommendation
        )

        return {
            "run_results": run_results,
            "per_candidate": per_candidate,
            "summary": {
                "mean_std": mean_std,
                "max_range": max_range,
                "recommendation": recommendation,
            },
        }

    # -----------------------------------------------------------------------
    # Metadata (değişmedi)
    # -----------------------------------------------------------------------
    @classmethod
    def generate_shorts_metadata(
        cls, clip_title: str, hook_caption: str, category: str, video_title: str = "", api_key: str | None = None
    ) -> dict[str, Any]:
        """Generate high-CTR title, SEO description, and tags for YouTube Shorts."""
        # 1. Try DeepSeek V3/R1 first if configured (Dream Team Creative Lead)
        try:
            from core.deepseek_engine import DeepSeekEngine

            if DeepSeekEngine.is_available():
                res = DeepSeekEngine.generate_shorts_copy(
                    clip_title=clip_title, hook_caption=hook_caption, category=category, video_title=video_title
                )
                res["provider"] = "DeepSeek V3 (Kreatif Motor)"
                return res
        except Exception as e:
            logger.debug("DeepSeek metadata generation failed, falling back to Gemini: {}", e)

        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            clean_title = f"{clip_title} 🔥 #Shorts #Gaming"
            clean_desc = f"🎯 {hook_caption}\n\n#Shorts #Gaming #Viral #Highlights"
            clean_tags = ["shorts", "gaming", "viral", "highlights", "komik anlar", "türkçe gaming"]
            return {"title": clean_title, "description": clean_desc, "tags": clean_tags, "provider": "Heuristic"}

        client = genai.Client(api_key=key)

        prompt = f"""
Sen YouTube Shorts, TikTok ve Instagram Reels için çalışan profesyonel bir Gaming Klip / Kesit kanalı yöneticisisin.
Aşağıdaki oyun klibi için ASLA robotik 'AI slop' olmayan, doğrudan bu oyuna, olaya ve klibe özel başlık, kısa açıklama ve etiketler üret:

Orijinal Video Başlığı / Kanal: {video_title}
Klip Başlığı: {clip_title}
Kategori: {category}
Klipteki Kanca Cümle / Olay: "{hook_caption}"

GÖREVLER:
1. Başlık: İzleyicinin kaydırmasını (scroll) anında durduracak, merak veya kahkaha uyandıran, dilbilgisi tam, BÜYÜK HARF vurgulu, 2 emoji içeren ve sonunda '#Shorts' etiketi olan maksimum 90 karakterlik Türkçe başlık.
2. Açıklama: PERSPEKTİFE DİKKAT ET (Sen videodaki yayıncı değilsin, klip kanalısın!). Asla 'ben yaptım/oynadım' deme. 3. şahıs olarak olayı özetleyen maksimum 2 KISA CÜMLE + 5 trend hashtag (#OyunAdi #Shorts #Gaming vb.). Asla 'Orijinal Video:' vb. metin ekleme.
3. Etiketler (Tags): Oyunun tam adını, klibin konusunu, oynanış mekaniğini ve Türkçe oyun terimlerini içeren 10-14 adet spesifik etiket listesi üret.
"""

        class GeminiShortsMeta(BaseModel):
            title: str = Field(description="Maks 90 karakterlik dikkat çekici YouTube Shorts başlığı")
            description: str = Field(description="Kanca ve hashtag içeren açıklama")
            tags: list[str] = Field(description="Oyun ve klibe özel 10-14 adet arama etiketi")

        for model_name in cls.MODELS_TO_TRY:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json", response_schema=GeminiShortsMeta, temperature=0.6
                    ),
                )
                res_dict = json.loads(response.text) if (response and response.text) else {}
                return {
                    "title": res_dict.get("title", f"{clip_title} #Shorts"),
                    "description": res_dict.get("description", f"{hook_caption}\n\n#Shorts"),
                    "tags": res_dict.get("tags", [video_title.lower(), clip_title.lower(), "shorts", "gaming"]),
                    "provider": f"Google Gemini ({model_name})",
                }
            except Exception as e:
                logger.debug("Gemini metadata model {} failed: {}", model_name, e)
                continue

        return {
            "title": f"{clip_title} 🔥 #Shorts",
            "description": f"🎯 {hook_caption}\n\n#Shorts #Gaming",
            "tags": ["shorts", "gaming", "viral"],
            "provider": "Google Gemini (Fallback)",
        }
