"""
core/transcript_density.py — Transkript Yoğunluk & Konuşma Enerji Eğrisi

YouTube veya Whisper transkripti üzerinden:
1. Zaman ekseninde konuşma temposunu (Words Per Second / Kelime Hızı) hesaplar.
2. Türkçe gaming ve reaksiyon sözlüğündeki yüksek enerjili kelimeleri, tekrarları ("dur dur dur", "hayır hayır")
   ve ünlem/soru kalıplarını tespit edip konuşma enerji eğrisi oluşturur.
3. 0-1 normalize edilmiş yoğunluk sinyali üretir.
4. candidate_ranker.py için multimodal füzyon sinyali sağlar.

Kullanım::

    analyzer = TranscriptDensityAnalyzer()
    curve = analyzer.compute_density_curve(
        transcript_segments=transcript,
        timeline_times=times,
        total_duration=duration,
    )
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

import numpy as np

from core.logger import logger

# ---------------------------------------------------------------------------
# Türkçe Gaming & Reaksiyon Yüksek Enerji Sözlüğü
# ---------------------------------------------------------------------------
_HIGH_ENERGY_KEYWORDS: Set[str] = {
    # Panik & Kaçış
    "dur", "durun", "kaç", "kaçın", "geliyor", "arkanda", "pusmuş", "öldüm",
    "öldü", "ölme", "canım", "bitti", "bittik", "yardım", "help", "kurtar",
    "bas", "bastım", "patladı", "patladık", "bomba", "at", "attım", "tut",
    
    # Şok & Nida
    "lan", "lanet", "oha", "çüş", "yuh", "yok", "imkansız", "inanılmaz",
    "nasıl", "ne", "noldu", "yalan", "vallahi", "billahi", "hadi", "haydi",
    "lütfen", "nolur", "allahım", "tövbe", "aga", "abi", "kanka", "bro",
    
    # Başarı & Reaksiyon
    "vurdum", "headshot", "aldım", "aldık", "temiz", "ez", "kolaydı", "efsane",
    "mükemmel", "harika", "god", "clutch", "ace", "gg", "helal", "kral",
    "yürü", "koydum", "çaktım", "kazandık", "win", "şov", "show",
    
    # Kahkaha & İroni
    "hahaha", "ahahaha", "koptum", "gümledim", "yarıldım", "komik", "rezil",
}

_WORD_SPLIT_REGEX = re.compile(r"[\s,.;:!?\"'()\[\]{}—–-]+")
_PUNCTUATION_BOOST_REGEX = re.compile(r"[!?]{1,}")


class TranscriptDensityAnalyzer:
    """Transkriptten konuşma temposu ve reaksiyon kelime yoğunluğu eğrisi çıkarır."""

    def __init__(
        self,
        window_size_sec: float = 6.0,
        keyword_weight: float = 2.5,
        repetition_weight: float = 2.0,
        punctuation_weight: float = 1.5,
    ) -> None:
        self.window_size_sec = window_size_sec
        self.keyword_weight = keyword_weight
        self.repetition_weight = repetition_weight
        self.punctuation_weight = punctuation_weight

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_density_curve(
        self,
        transcript_segments: List[Dict[str, Any]],
        timeline_times: np.ndarray,
        total_duration: float,
    ) -> np.ndarray:
        """
        Transkript parçalarını zaman ekseninde konuşma enerji eğrisine dönüştürür.

        Args:
            transcript_segments: [{'text': str, 'start': float, 'duration': float, ...}]
            timeline_times: Sinyalin üretileceği numpy zaman ekseni (saniye)
            total_duration: Video toplam süresi (saniye)

        Returns:
            np.ndarray: 0.0 - 1.0 aralığında normalize konuşma yoğunluğu eğrisi
        """
        n_pts = len(timeline_times)
        if n_pts == 0 or not transcript_segments or total_duration <= 0:
            return np.zeros(n_pts)

        # 1. Her transkript segmenti için enerji puanı hesapla
        scored_events: List[Dict[str, float]] = []
        for seg in transcript_segments:
            text = seg.get("text", "") or ""
            start = float(seg.get("start", 0.0))
            dur = float(seg.get("duration", 2.0))
            mid = start + (dur / 2.0)

            score = self.score_segment_text(text, dur)
            if score > 0 and 0 <= mid <= total_duration:
                scored_events.append({
                    "start": start,
                    "end": start + dur,
                    "mid": mid,
                    "score": score,
                })

        if not scored_events:
            return np.zeros(n_pts)

        # 2. Timeline üzerinde sliding box / Gaussian ile enerji biriktir
        density = np.zeros(n_pts)
        half_win = self.window_size_sec / 2.0

        for ev in scored_events:
            mid = ev["mid"]
            score = ev["score"]

            # Etkilenen zaman penceresindeki noktalar
            mask = np.abs(timeline_times - mid) <= half_win
            if np.any(mask):
                # Merkeze yakınlığına göre yumuşatma (cosine bell)
                dist = np.abs(timeline_times[mask] - mid) / half_win
                weights = 0.5 * (1.0 + np.cos(np.pi * dist))
                density[mask] += score * weights

        # 3. 0-1 aralığına normalize et
        mx = density.max()
        if mx > 1e-9:
            density = density / mx

        return density

    def score_segment_text(self, text: str, duration_sec: float) -> float:
        """
        Tek bir konuşma segmentinin enerji puanını hesaplar:
        - Kelime hızı (WPS: Words Per Second)
        - Yüksek enerjili oyun kelimeleri
        - Tekrarlanan kelimeler (dur dur dur / hayır hayır)
        - Ünlem ve soru işaretleri
        """
        if not text:
            return 0.0

        raw_words = [w.strip() for w in _WORD_SPLIT_REGEX.split(text) if w.strip()]
        if not raw_words:
            return 0.0

        dur = max(0.5, float(duration_sec))
        wps = len(raw_words) / dur  # Kelime / saniye

        # Temel skor: WPS (ortalama konuşma hızı ~2.5 WPS)
        score = float(np.clip(wps / 2.5, 0.5, 3.0))

        # Yüksek enerjili kelime sayısı
        def _norm(w: str) -> str:
            return (
                w.lower()
                .replace("ı", "i")
                .replace("i̇", "i")
                .replace("ğ", "g")
                .replace("ü", "u")
                .replace("ş", "s")
                .replace("ö", "o")
                .replace("ç", "c")
            )

        norm_keywords = {_norm(k) for k in _HIGH_ENERGY_KEYWORDS}
        lower_words = [w.lower() for w in raw_words]
        keyword_hits = sum(1 for w in raw_words if _norm(w) in norm_keywords)
        if keyword_hits > 0:
            score += keyword_hits * self.keyword_weight


        # Tekrarlanan kelimeler (örn: "dur dur", "kaç kaç kaç")
        repetition_count = self._count_consecutive_repetitions(lower_words)
        if repetition_count > 0:
            score += repetition_count * self.repetition_weight

        # Ünlem ve soru işareti yoğunluğu
        punct_matches = len(_PUNCTUATION_BOOST_REGEX.findall(text))
        if punct_matches > 0:
            score += min(punct_matches, 3) * self.punctuation_weight

        # Büyük harf bağırma oranı (Caps Lock)
        caps_letters = sum(1 for ch in text if ch.isupper())
        total_letters = sum(1 for ch in text if ch.isalpha())
        if total_letters >= 4 and (caps_letters / total_letters) > 0.50:
            score *= 1.40

        return float(score)

    def extract_hotspots(
        self,
        transcript_segments: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Transkriptten en yüksek enerjili / en hararetli N segmenti ayıklar.
        """
        scored = []
        for seg in transcript_segments:
            text = seg.get("text", "") or ""
            start = float(seg.get("start", 0.0))
            dur = float(seg.get("duration", 2.0))
            score = self.score_segment_text(text, dur)
            if score > 1.0:
                scored.append({
                    "start": start,
                    "end": start + dur,
                    "duration": dur,
                    "text": text,
                    "energy_score": round(score, 2),
                })

        scored.sort(key=lambda x: x["energy_score"], reverse=True)
        return scored[:top_k]

    def compute_speech_rate_acceleration(
        self,
        transcript_segments: List[Dict[str, Any]],
        timeline_times: np.ndarray,
        total_duration: float,
        accel_window_sec: float = 10.0,
    ) -> np.ndarray:
        """
        Mevcut transkriptten konuşma hızı ivmesi sinyali çıkarır.
        Ek API çağrısı gerekmez — compute_density_curve ile aynı transkript kullanılır.

        Algoritma:
        1. Her segment için kelime/saniye (WPS) hesapla.
        2. Zaman ekseninde kayan pencerede WPS'in türevini (değişim hızını) hesapla.
        3. Pozitif ivme (hızlanma) → heyecan sinyali. 0-1 normalize et.

        Args:
            transcript_segments: [{'text': str, 'start': float, 'duration': float}]
            timeline_times:      Hedef zaman ekseni (audio_spikes ile aynı grid).
            total_duration:      Video süresi (saniye).
            accel_window_sec:    WPS değişimi hesaplanacak pencere genişliği.

        Returns:
            np.ndarray: 0-1 normalize konuşma hızı ivmesi eğrisi.
        """
        n_pts = len(timeline_times)
        if n_pts == 0 or not transcript_segments or total_duration <= 0:
            return np.zeros(n_pts)

        # 1. Her segment için WPS hesapla
        wps_events: List[Dict[str, float]] = []
        for seg in transcript_segments:
            text = seg.get("text", "") or ""
            start = float(seg.get("start", 0.0))
            dur = float(seg.get("duration", 2.0))
            if dur < 0.1:
                continue
            words = [w for w in _WORD_SPLIT_REGEX.split(text) if w.strip()]
            wps = len(words) / max(dur, 0.5)
            mid = start + dur / 2.0
            if 0 <= mid <= total_duration:
                wps_events.append({"mid": mid, "wps": wps})

        if len(wps_events) < 2:
            return np.zeros(n_pts)

        # 2. Timeline üzerinde WPS interpolasyonu
        ev_times = np.array([e["mid"] for e in wps_events], dtype=np.float64)
        ev_wps = np.array([e["wps"] for e in wps_events], dtype=np.float64)
        wps_timeline = np.interp(timeline_times, ev_times, ev_wps, left=ev_wps[0], right=ev_wps[-1])

        # 3. Kayan pencerede WPS türevi (ivme) — pozitif ivme heyecan = ani konuşma hızlanması
        hop = float(timeline_times[1] - timeline_times[0]) if len(timeline_times) > 1 else 0.5
        win_pts = max(2, int(accel_window_sec / hop))
        accel = np.zeros(n_pts, dtype=np.float64)
        for i in range(win_pts, n_pts):
            prev = np.mean(wps_timeline[i - win_pts: i - win_pts // 2])
            curr = np.mean(wps_timeline[i - win_pts // 2: i])
            accel[i] = max(0.0, curr - prev)  # Sadece pozitif ivme

        # 4. 0-1 normalize
        mx = accel.max()
        if mx > 1e-9:
            accel = accel / mx

        return accel.astype(np.float32)

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _count_consecutive_repetitions(words: List[str]) -> int:
        """Art arda tekrarlanan kelime sayısını bulur (örn: 'dur dur' -> 1, 'hayır hayır hayır' -> 2)."""
        reps = 0
        for i in range(len(words) - 1):
            if words[i] == words[i + 1] and len(words[i]) >= 2:
                reps += 1
        return reps
