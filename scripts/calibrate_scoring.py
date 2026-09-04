#!/usr/bin/env python3
"""
scripts/calibrate_scoring.py — Referans-Set Kalibrasyon Script'i

Bilinen viral kliplerin listesini (reference_set.json) kullanarak pipeline'ı çalıştırır
ve sistemin bu anları doğru puanlayıp puanlamadığını raporlar.

Kendi trafik/izlenme verimiz olmadan kalibrasyon imkânı sağlar.

Kullanım:
    python scripts/calibrate_scoring.py [--ref reference_set.json] [--output report.json]

Gereksinimler:
    - GEMINI_API_KEY ortam değişkeni
    - reference_set.json dolu olmalı (REPLACE_ME URL'ler değiştirilmeli)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

# Proje kökünü Python path'ine ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from core.audio_dsp import AudioDSPAnalyzer
from core.candidate_ranker import CandidateRanker
from core.llm_engine import GeminiHighlightEngine, score_to_band
from core.transcript import TranscriptManager
from core.extractor import YouTubeExtractor
import numpy as np


def run_single_ref(ref: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    """Tek bir referans klip için pipeline'ı çalıştırır."""
    video_url = ref["video_url"]
    known_start = float(ref["known_start_sec"])
    known_end = float(ref["known_end_sec"])
    expected_cat = ref.get("expected_category", "EPIC_MOMENT")
    expected_score_min = int(ref.get("expected_score_min", 60))
    label = ref.get("label", ref["id"])

    logger.info("▶️  Kalibrasyon başlatılıyor: {} ({})", label, video_url)
    result: Dict[str, Any] = {
        "id": ref["id"],
        "label": label,
        "video_url": video_url,
        "known_start_sec": known_start,
        "known_end_sec": known_end,
        "expected_category": expected_cat,
        "expected_score_min": expected_score_min,
        "status": "error",
        "matched_candidate": None,
        "llm_score": None,
        "llm_category": None,
        "llm_band": None,
        "llm_rationale": None,
        "passed_score": False,
        "passed_category": False,
        "overlap_sec": 0.0,
        "error": None,
    }

    try:
        # 1. Video metadata
        video_data = YouTubeExtractor.get_video_data(video_url)
        video_id = video_data.get("id", "ref")
        video_title = video_data.get("title", "Referans Video")
        duration = int(video_data.get("duration", 600))

        # 2. Audio DSP
        try:
            times, audio_energy = AudioDSPAnalyzer.extract_audio_energy(video_url, duration_sec=duration)
            signals = AudioDSPAnalyzer.detect_signals(times, audio_energy)
        except Exception as e:
            logger.warning("Audio DSP skipped for {}: {}", label, e)
            times, audio_energy = np.array([]), np.array([])
            signals = {"times": np.array([]), "audio_spikes": np.array([]), "silence_bursts": np.array([])}

        # 3. Transcript
        transcripts = []
        try:
            transcripts = TranscriptManager.get_transcript(video_id)
        except Exception as e:
            logger.debug("Transcript failed for {}: {}", label, e)

        # 4. Candidate Ranking
        ranker = CandidateRanker(top_n=15)
        candidates = ranker.fuse_signals_and_generate_candidates(
            times=signals.get("times", np.array([])),
            audio_spikes=signals.get("audio_spikes", np.array([])),
            silence_bursts=signals.get("silence_bursts", np.array([])),
            heatmap=[],
            transcript=transcripts,
            total_duration=duration,
            video_id=video_id,
        )

        # Referans penceresiyle örtüşen adayı bul
        best_candidate = None
        best_overlap = 0.0
        for cand in candidates:
            cs = cand["start_time"]
            ce = cand["end_time"]
            overlap = max(0.0, min(ce, known_end) - max(cs, known_start))
            if overlap > best_overlap:
                best_overlap = overlap
                best_candidate = cand

        result["overlap_sec"] = round(best_overlap, 1)

        if best_candidate is None or best_overlap < 5.0:
            result["status"] = "no_match"
            result["error"] = f"Referans penceresiyle örtüşen aday bulunamadı (en iyi örtüşme: {best_overlap:.1f}s)"
            logger.warning("❌ {} — Aday bulunamadı (örtüşme: {:.1f}s)", label, best_overlap)
            return result

        logger.info("✅ Aday eşleşti: #{} ({:.0f}s-{:.0f}s, örtüşme: {:.1f}s)",
                    best_candidate["candidate_id"],
                    best_candidate["start_time"],
                    best_candidate["end_time"],
                    best_overlap)

        result["matched_candidate"] = {
            "candidate_id": best_candidate["candidate_id"],
            "start_time": best_candidate["start_time"],
            "end_time": best_candidate["end_time"],
            "fusion_score": best_candidate["fusion_score"],
        }

        # 5. LLM Scoring
        llm_results = GeminiHighlightEngine.batch_judge_gaming_candidates(
            candidates=[best_candidate],
            video_title=video_title,
            total_duration=duration,
            target_clips=1,
            api_key=api_key,
        )

        if not llm_results:
            result["status"] = "llm_failed"
            result["error"] = "LLM sonuç döndürmedi."
            return result

        clip_res = llm_results[0]
        llm_score = clip_res["score"]
        llm_cat = clip_res["category"]

        result["llm_score"] = llm_score
        result["llm_category"] = llm_cat
        result["llm_band"] = score_to_band(llm_score)
        result["llm_rationale"] = clip_res.get("rationale", "")
        result["passed_score"] = llm_score >= expected_score_min
        result["passed_category"] = llm_cat.upper() == expected_cat.upper()
        result["status"] = "ok"

        status_icon = "✅" if result["passed_score"] else "❌"
        cat_icon = "✅" if result["passed_category"] else "⚠️"
        logger.info(
            "{} Skor: {} (bant: {}) {} Kategori: {} (beklenen: {})",
            status_icon, llm_score, result["llm_band"],
            cat_icon, llm_cat, expected_cat
        )

    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        logger.error("❌ {} hata: {}", label, exc)

    return result


def print_summary(results: List[Dict[str, Any]]) -> None:
    """Kalibrasyon özetini konsola yazar."""
    total = len(results)
    ok = sum(1 for r in results if r["status"] == "ok")
    passed_score = sum(1 for r in results if r.get("passed_score"))
    passed_cat = sum(1 for r in results if r.get("passed_category"))

    print("\n" + "="*60)
    print("📊 KALİBRASYON SONUÇLARI")
    print("="*60)
    print(f"Toplam referans: {total}")
    print(f"Başarılı çalışma: {ok}/{total}")
    print(f"Skor eşiği geçen: {passed_score}/{ok}")
    print(f"Doğru kategori: {passed_cat}/{ok}")
    print()

    for r in results:
        s = r["status"]
        if s == "ok":
            score_flag = "✅" if r["passed_score"] else "❌"
            cat_flag = "✅" if r["passed_category"] else "⚠️"
            print(f"  {score_flag} [{r['id']}] {r['label']}")
            print(f"      Skor: {r['llm_score']} (bant: {r['llm_band']}, beklenen min: {r['expected_score_min']}) {score_flag}")
            print(f"      Kategori: {r['llm_category']} (beklenen: {r['expected_category']}) {cat_flag}")
            print(f"      Örtüşme: {r['overlap_sec']}s | Gerekçe: {r['llm_rationale'][:80]}...")
        else:
            print(f"  ❌ [{r['id']}] {r['label']} → {s}: {r.get('error', '')}")
        print()

    print("="*60)

    # Öneriler
    if ok > 0:
        avg_score = sum(r["llm_score"] for r in results if r.get("llm_score") is not None) / max(ok, 1)
        print(f"Ortalama viral skor: {avg_score:.1f}")
        if passed_score / max(ok, 1) < 0.7:
            print("⚠️  Uyarı: Referans kliplerin %70'inden azı beklenen skor eşiğini geçti.")
            print("   Öneri: HOOK_STRENGTH_WEIGHT veya SIGNAL_VALIDATION_WEIGHT'i artırın.")
        else:
            print("✅ Sistem referans seti üzerinde iyi performans gösteriyor.")


def main():
    parser = argparse.ArgumentParser(
        description="Clipper Scoring Kalibrasyon Script'i"
    )
    parser.add_argument(
        "--ref",
        default="reference_set.json",
        help="Referans set JSON dosyası (varsayılan: reference_set.json)"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Sonuçların kaydedileceği JSON dosyası (opsiyonel)"
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Gemini API anahtarı (yoksa GEMINI_API_KEY env değişkeni kullanılır)"
    )
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY bulunamadı. --api-key veya ortam değişkeni gerekli.")
        sys.exit(1)

    # Referans set yükle
    ref_path = args.ref
    if not os.path.isabs(ref_path):
        ref_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ref_path)

    if not os.path.exists(ref_path):
        print(f"❌ Referans set dosyası bulunamadı: {ref_path}")
        sys.exit(1)

    with open(ref_path, "r", encoding="utf-8") as f:
        ref_data = json.load(f)

    ref_clips = ref_data.get("clips", [])
    if not ref_clips:
        print("❌ Referans set boş. reference_set.json dosyasını doldurun.")
        sys.exit(1)

    # REPLACE_ME URL'leri filtrele
    valid_clips = [r for r in ref_clips if "REPLACE_ME" not in r.get("video_url", "")]
    if not valid_clips:
        print("❌ Hiç geçerli referans klip yok. reference_set.json'daki video_url değerlerini doldurun.")
        sys.exit(1)

    print(f"\n🚀 Kalibrasyon başlatılıyor — {len(valid_clips)} referans klip")
    print(f"   Referans dosyası: {ref_path}\n")

    results = []
    for ref in valid_clips:
        result = run_single_ref(ref, api_key)
        results.append(result)
        time.sleep(1)  # Rate limit

    print_summary(results)

    # Rapor kaydet
    output_path = args.output
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            f"calibration_report_{ts}.json"
        )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "ref_file": ref_path,
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n📄 Detaylı rapor kaydedildi: {output_path}")


if __name__ == "__main__":
    main()
