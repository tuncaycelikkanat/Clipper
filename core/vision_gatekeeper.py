"""
core/vision_gatekeeper.py — Multimodal Vision-Based Clip Quality Gatekeeper.

Claude Architecture Blueprint:
1. LLM'den sayı yerine ikili/ordinal etiketler alır (hook: bool, facecam_reaction: none/subtle/strong, gameplay_event: bool).
2. Sadece en iyi 5-6 adaya vision uygular (maliyet optimizasyonu).
3. Aday anlardan 3 anahtar kare çeker: Hook (t_start+1s), Climax (t_peak), Payoff (t_end-1s).
4. İki katmanlı kapı: Mutlak minimum eşikler (olay veya mimik şart) + deterministik rubrik puanı.
5. Kalite eşiğini geçemeyen adayları eler; videoda kaliteli an yoksa 0 klip döner.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Any, Literal

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field

import core.scoring_config as SC


# ---------------------------------------------------------------------------
# Pydantic Yapılandırılmış Çıktı Modelleri
# ---------------------------------------------------------------------------


class CandidateVisualVerdict(BaseModel):
    """Tek bir klip adayı için görsel doğrulama sonucu (sayısal skor yok, sadece etiketler)."""

    candidate_id: int = Field(description="Değerlendirilen adayın benzersiz id'si")
    has_facecam: bool = Field(
        default=False,
        description="Videoda yayıncının gerçek bir webcami / facecam çerçevesi var mı? (Kamera yoksa false)",
    )
    hook_visual_punch: bool = Field(
        description="İlk karelerde/girişte izleyicinin kaydırmasını (scroll) durduracak görsel hareket, kanca, yaklaşan tehlike/kaza veya merak unsuru var mı?"
    )
    facecam_reaction: Literal["none", "subtle", "strong"] = Field(
        description="Yayıncının tepkisi. Eğer facecam varsa yüz mimikleri (none/subtle/strong); eğer facecam YOKSA mikrofondaki ses tonu, çığlığı veya konuşmadaki coşku/şaşkınlık seviyesi.",
    )
    gameplay_event_detected: bool = Field(
        description="Ekranda gerçek bir oyun olayı (kill, ölüm, clutch, kaza, patlama, fizik bug'ı, zafer/yenilgi) gerçekleşti mi?"
    )
    story_complete: bool = Field(
        description="Klip kendi içinde anlamlı bir başlangıç ve sonuç içeriyor mu, yoksa olay ortada/havada mı kalıyor?"
    )
    category: Literal[
        "CLUTCH", "FAIL/FUNNY", "RAGE/REACTION", "JUMPSCARE", "EPIC_MOMENT", "STORY", "MUNDANE"
    ] = Field(description="Klibin asıl içerik kategorisi")
    visual_summary: str = Field(description="Ekranda görsel olarak tam ne gerçekleştiğini anlatan 1 net cümle")
    title_suggestion: str = Field(description="Klip için doğal ve samimi Türkçe başlık önerisi")
    hook_caption_suggestion: str = Field(description="İlk saniyelerde ekranda belirecek vurucu kanca yazısı")


# ---------------------------------------------------------------------------
# Deterministik Rubrik & İki Katmanlı Kapı Formülasyonu
# ---------------------------------------------------------------------------


def compute_deterministic_score(
    verdict: CandidateVisualVerdict,
    fusion_score: int,
) -> tuple[int, bool, str]:
    """
    LLM'in verdiği ikili/ordinal etiketleri koddaki matematiksel rubrikle
    güvenilir bir 0-100 skoruna dönüştürür.

    Kamera Varsa:
    - Hook: %30, Facecam Mimik: %25, Oyun Olayı: %25, Hikaye: %20

    Kamera YOKSA (Kamerasız Oyun):
    - Yüz mimikleri aranmaz (haksız yere puan kırılmaz)!
    - Hook: %30, Ses/Tepki: %15, Oyun Olayı/Aksiyon: %40, Hikaye: %15

    Returns:
        (final_score, passed_gate, rationale)
    """
    if verdict.hook_visual_punch:
        hook_pts = 90
    elif verdict.gameplay_event_detected and verdict.facecam_reaction in ("subtle", "strong"):
        # Doğrulanmış büyük olay ve tepki varsa, ilk saniyeler kaza/aksiyon öncesi gerilim ve hazırlık kancasıdır
        hook_pts = 65
    else:
        hook_pts = 40

    if verdict.facecam_reaction == "strong":
        reaction_pts = 95
    elif verdict.facecam_reaction == "subtle":
        reaction_pts = 70
    else:
        reaction_pts = 40

    event_pts = 95 if verdict.gameplay_event_detected else 25
    story_pts = 90 if verdict.story_complete else 40

    if verdict.has_facecam:
        # Facecam VARSA: Yüz mimikleri önemli
        vision_rubric = round(
            (hook_pts * 0.30)
            + (reaction_pts * 0.25)
            + (event_pts * 0.25)
            + (story_pts * 0.20)
        )
        reaction_label = f"Facecam={reaction_pts} ({verdict.facecam_reaction})"
    else:
        # Facecam YOKSA: Yüz aranmaz; oyun içi aksiyona ve ses tonuna ağırlık verilir
        vision_rubric = round(
            (hook_pts * 0.30)
            + (reaction_pts * 0.15)
            + (event_pts * 0.40)
            + (story_pts * 0.15)
        )
        reaction_label = f"SesTepki={reaction_pts} ({verdict.facecam_reaction}) [Kamerasız Oyun]"

    # Hibrit Sentez: Vision %70 + DSP Sinyal Füzyonu %30
    final_score = round(vision_rubric * 0.70 + fusion_score * 0.30)
    final_score = max(0, min(100, final_score))

    # --- Mutlak Kapı Kontrolleri (Absolute Gate) ---
    passed_gate = True
    fail_reasons: list[str] = []

    # Kural 1: Ekranda ne bir oyun olayı ne de yayıncı tepkisi varsa elenir.
    if not verdict.gameplay_event_detected and verdict.facecam_reaction == "none":
        passed_gate = False
        fail_reasons.append("Ne oyun içi olay ne de yayıncı tepkisi tespit edilemedi")
        final_score = min(final_score, 35)

    # Kural 2: MUNDANE kategorisi
    if str(verdict.category).upper() == "MUNDANE":
        passed_gate = False
        fail_reasons.append("MUNDANE/Sıradan an olarak etiketlendi")
        final_score = min(final_score, SC.MUNDANE_SCORE_CAP)

    # Kural 3: Minimum Kalite Barajı
    min_thresh = getattr(SC, "VIRAL_SCORE_THRESHOLD", 70)
    if final_score < min_thresh:
        passed_gate = False
        fail_reasons.append(f"Skor ({final_score}) kalite barajının ({min_thresh}) altında")

    rationale = (
        f"[Vision: Hook={hook_pts}, {reaction_label}, "
        f"Olay={event_pts}, Hikaye={story_pts} -> Rubrik:{vision_rubric}] "
        f"Görsel: {verdict.visual_summary}"
    )
    if not passed_gate:
        rationale += f" [ELENDİ: {', '.join(fail_reasons)}]"

    return final_score, passed_gate, rationale


# ---------------------------------------------------------------------------
# Vision Gatekeeper Sınıfı
# ---------------------------------------------------------------------------


class VisionGatekeeper:
    """Multimodal video/kare incelemesi yapan kapı bekçisi."""

    MODELS_TO_TRY = [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-flash-latest",
    ]

    @staticmethod
    def extract_candidate_keyframes(
        source: str,
        start_time: float,
        peak_time: float,
        end_time: float,
        width: int = 480,
        height: int = 270,
    ) -> list[bytes]:
        """
        Aday penceresinden 3 anahtar kare çıkarır (Hook, Climax, Payoff).
        Düşük çözünürlük (480x270 / 360p) ile çıkarılır; token maliyeti ve gecikme minimumdur.
        """
        dur = end_time - start_time
        if dur <= 0:
            return []

        # 3 Örnekleme Noktası
        t1 = start_time + min(1.5, dur * 0.15)  # Hook
        t2 = peak_time                           # Climax
        t3 = max(start_time, end_time - min(2.0, dur * 0.15))  # Payoff

        target_times = [t1, t2, t3]
        frames_bytes: list[bytes] = []

        scale_filter = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"

        with tempfile.TemporaryDirectory() as tmp_dir:
            for idx, t in enumerate(target_times):
                out_path = os.path.join(tmp_dir, f"frame_{idx}.jpg")
                cmd = ["ffmpeg", "-y"]
                if source.startswith("http://") or source.startswith("https://"):
                    headers_str = "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n"
                    cmd.extend(["-headers", headers_str])
                cmd.extend([
                    "-reconnect",
                    "1",
                    "-reconnect_at_eof",
                    "1",
                    "-reconnect_streamed",
                    "1",
                    "-ss",
                    f"{t:.2f}",
                    "-i",
                    source,
                    "-vframes",
                    "1",
                    "-vf",
                    scale_filter,
                    "-q:v",
                    "5",
                    out_path,
                ])
                try:
                    subprocess.run(cmd, capture_output=True, timeout=25, check=True)
                    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                        with open(out_path, "rb") as f:
                            frames_bytes.append(f.read())
                except Exception as exc:
                    logger.debug("Vision frame extraction failed at t={:.2f}s: {}", t, exc)
                    continue

        return frames_bytes

    @classmethod
    def evaluate_candidate(
        cls,
        candidate: dict[str, Any],
        frames: list[bytes],
        video_title: str,
        api_key: str | None = None,
    ) -> CandidateVisualVerdict | None:
        """Tek bir adayı 3 anahtar karesiyle Gemini Vision'a değerlendirtir."""
        if not frames:
            return None

        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            return None

        client = genai.Client(api_key=key)

        cand_id = candidate.get("candidate_id", 1)
        transcript_snippet = candidate.get("transcript_snippet", "")
        time_str = f"{candidate.get('start_formatted', '')} - {candidate.get('end_formatted', '')}"

        prompt = f"""
Sen YouTube Shorts ve TikTok için viral oyun/yayın kesitleri seçen Baş Editörsün.
Aşağıda bir video kesitine ait kronolojik 3 kare (Kare 1: Giriş/Hook, Kare 2: Zirve/Olay, Kare 3: Kapanış/Payoff) ve konuşma transkripti verilmiştir.

Video: "{video_title}"
Zaman Penceresi: {time_str}
Transkript Parçası: "{transcript_snippet}"

GÖREVİN:
Görselleri ve transkripti incele; sayısal skor verme, yalnızca nesnel etiketleri belirle:
1. has_facecam: Videoda yayıncının gerçek bir webcami / facecam çerçevesi (odadan yayıncı görüntüsü) var mı? (Oyun içi 3D karakter veya araba facecam DEĞİLDİR, kamera yoksa kesinlikle false seç!)
2. hook_visual_punch: Giriş karesinde kaydırmayı durduracak bir aksiyon/kanca/merak unsuru veya yaklaşan tehlike/kaza/hız var mı?
3. facecam_reaction: Yayıncının tepkisi nasıldır?
   - Eğer facecam VARSA: Yayıncının yüz ifadesi ('none': tepkisiz/düz, 'subtle': hafif tebessüm/mimik, 'strong': çığlık, kahkaha, elini kafaya atma, panik).
   - Eğer facecam YOKSA (kamerasız oyun): Mikrofondaki ses tonu, çığlığı veya konuşmadaki coşku/şaşkınlık seviyesine göre belirle ('none': sakin/düz konuşma, 'subtle': hafif tebessüm/şaşırma, 'strong': bağırma/kahkaha/çığlık).
4. gameplay_event_detected: Ekranda gerçekten somut bir oyun olayı (kill, ölüm, kaza, patlama, zafer, ragdoll bug) gerçekleşiyor mu?
5. story_complete: Giriş ve sonuç bütünlüğü var mı?
6. category: Kategori seç. Eğer an sıradan ve boşsa KESİNLİKLE 'MUNDANE' seç!

Lütfen Pydantic JSON olarak yanıtla.
"""

        # Part listesi oluştur: 3 resim + metin
        contents_payload: list[Any] = []
        for f_bytes in frames:
            contents_payload.append(types.Part.from_bytes(data=f_bytes, mime_type="image/jpeg"))
        contents_payload.append(prompt)

        for model_name in cls.MODELS_TO_TRY:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents_payload,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=CandidateVisualVerdict,
                        temperature=0.2,
                    ),
                )
                if response and response.text:
                    parsed = json.loads(response.text)
                    parsed["candidate_id"] = cand_id
                    return CandidateVisualVerdict(**parsed)
            except Exception as e:
                logger.debug("Vision evaluation model {} failed: {}", model_name, e)
                continue

        return None

    @classmethod
    def filter_and_evaluate_candidates(
        cls,
        candidates: list[dict[str, Any]],
        video_source: str,
        video_title: str,
        total_duration: int,
        target_clips: int = 3,
        api_key: str | None = None,
        max_vision_candidates: int = 5,
        include_rejected: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Tüm pipeline için Vision Gatekeeper ana çağrısı:
        1. Adayları DSP fusion skoruyla sıralayıp en iyi `max_vision_candidates` (5) adayı seçer.
        2. Her aday için 3 kare çıkarıp Gemini Vision ile ordinal etiketler alır.
        3. Deterministik rubrik ile skoru hesaplar, mutlak kapıyı geçemeyenleri eler.
        4. Barajı geçen en iyi klipleri döner (include_rejected=True ise elenenleri de [ELENDİ] ile döner).
        """
        if not candidates:
            return []

        save_rejected = include_rejected or getattr(SC, "SAVE_REJECTED_CLIPS", False)

        # 1. Aşama: Ön Eleme (DSP + Transkript ile en iyi 5 adaya indir)
        sorted_cands = sorted(
            candidates,
            key=lambda c: (1 if c.get("is_vip") else 0, c.get("fusion_score", 0)),
            reverse=True,
        )
        preselected = sorted_cands[:max_vision_candidates]

        logger.info(
            "Vision Gatekeeper: {} aday arasından en iyi {} adaya görsel inceleme yapılıyor (Audit/Elenenleri Kaydet: {})...",
            len(candidates),
            len(preselected),
            save_rejected,
        )

        # Uzaktan YouTube URL ise video akışını bir kez çöz
        resolved_source = video_source
        if video_source.startswith("http://") or video_source.startswith("https://"):
            try:
                import yt_dlp

                ydl_opts = {
                    "format": "bestvideo[ext=mp4][height<=720]/bestvideo/best",
                    "quiet": True,
                    "no_warnings": True,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_source, download=False)
                    stream_url = info.get("url") or ""
                    if not stream_url:
                        for fmt in info.get("formats", []):
                            if fmt.get("vcodec") != "none" and fmt.get("url"):
                                stream_url = fmt["url"]
                                break
                    if stream_url:
                        resolved_source = stream_url
            except Exception as e:
                logger.debug("Vision stream URL resolution skipped: {}", e)

        qualified_clips: list[dict[str, Any]] = []
        total_frames_extracted = 0
        successful_api_evaluations = 0

        for cand in preselected:
            cid = cand.get("candidate_id", 0)
            s_time = float(cand.get("start_time", 0.0))
            p_time = float(cand.get("peak_time", s_time + 15.0))
            e_time = float(cand.get("end_time", s_time + 30.0))
            fusion_s = int(cand.get("fusion_score", 50))

            # Kareleri çek
            frames = cls.extract_candidate_keyframes(
                source=resolved_source,
                start_time=s_time,
                peak_time=p_time,
                end_time=e_time,
            )

            if not frames:
                logger.debug("Klip #{} için kare çıkarılamadı, görsel inceleme atlanıyor.", cid)
                continue

            total_frames_extracted += len(frames)

            # Gemini Vision ile analiz et
            verdict = cls.evaluate_candidate(
                candidate=cand,
                frames=frames,
                video_title=video_title,
                api_key=api_key,
            )

            if not verdict:
                logger.debug("Klip #{} için Vision analizi yanıt vermedi.", cid)
                continue

            successful_api_evaluations += 1
            final_score, passed_gate, rationale = compute_deterministic_score(verdict, fusion_s)

            if not passed_gate:
                logger.info(
                    "❌ Klip #{} Kapıdan Geçemedi (Skor: {}, Kategori: {}) -> {}",
                    cid,
                    final_score,
                    verdict.category,
                    rationale,
                )
                if not save_rejected:
                    continue
            else:
                logger.info(
                    "✅ Klip #{} Kapıdan Geçti! Skor: {}, Kategori: {} -> {}",
                    cid,
                    final_score,
                    verdict.category,
                    verdict.visual_summary,
                )

            from core.extractor import YouTubeExtractor

            dur = round(e_time - s_time, 1)
            raw_title = verdict.title_suggestion or cand.get("title", f"Gaming Klip #{cid}")
            display_title = raw_title if passed_gate else f"[ELENDİ] {raw_title}"

            qualified_clips.append(
                {
                    "rank": len(qualified_clips) + 1,
                    "candidate_id": cid,
                    "title": display_title,
                    "category": verdict.category,
                    "score": final_score,
                    "viral_confidence": final_score,
                    "intensity": final_score,
                    "rationale": rationale,
                    "is_passed": passed_gate,
                    "gate_status": "PASSED" if passed_gate else "REJECTED",
                    "hook_caption": verdict.hook_caption_suggestion or cand.get("hook_caption", ""),
                    "reason": f"{'🎮' if passed_gate else '❌ [ELENDİ]'} [{verdict.category}] {verdict.visual_summary}",
                    "peak_time": round(p_time, 1),
                    "peak_formatted": YouTubeExtractor.format_seconds(p_time),
                    "start_time": round(s_time, 1),
                    "start_formatted": YouTubeExtractor.format_seconds(s_time),
                    "end_time": round(e_time, 1),
                    "end_formatted": YouTubeExtractor.format_seconds(e_time),
                    "duration": dur,
                    "duration_formatted": f"{int(dur)} sn",
                    "text": cand.get("transcript_snippet", ""),
                    "visual_summary": verdict.visual_summary,
                }
            )

        if total_frames_extracted == 0:
            raise RuntimeError(
                f"Video kaynağından ({video_source}) hiçbir kare çıkarılamadı. "
                "Metin tabanlı LLM fallback devreye giriyor."
            )

        if successful_api_evaluations == 0:
            raise RuntimeError(
                "Gemini Vision API çağrıları yanıt vermedi (kota aşımı, rate limit veya ağ hatası). "
                "Metin tabanlı LLM fallback devreye giriyor."
            )

        # Geçenler önce (skora göre azalan), elenenler arkada (skora göre azalan)
        qualified_clips.sort(
            key=lambda x: (1 if x.get("is_passed", True) else 0, x["score"]),
            reverse=True,
        )

        top_selected = qualified_clips if save_rejected else qualified_clips[:target_clips]

        # Klip sıralarını (rank) güncelle
        for idx, cl in enumerate(top_selected, start=1):
            cl["rank"] = idx

        # Başlangıç saniyesine göre timeline sırasına diz
        top_selected.sort(key=lambda x: x["start_time"])

        passed_count = sum(1 for c in top_selected if c.get("is_passed", True))
        rejected_count = len(top_selected) - passed_count
        logger.info(
            "Vision Gatekeeper tamamlandı: Toplam {} aday incelendi, {} klip kapıyı geçti, {} klip elendi.",
            len(preselected),
            passed_count,
            rejected_count,
        )
        return top_selected
