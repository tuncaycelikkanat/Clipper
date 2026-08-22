"""
core/channel_dna.py — Kanal Parmak İzi & İzleyici Reaksiyon Profili (Channel DNA)

Kanalın geçmiş videoları, klip skorları ve heatmap verilerinden:
1. Kanalın izleyici DNA'sını çıkarır:
   - dominant_category: En çok viral olan kategori (FUNNY, RAGE, CLUTCH vb.)
   - avg_clip_duration: En iyi performans gösteren ideal klip süresi
   - category_distribution: Kategori bazlı ilgi dağılımı
   - shock_weight: Ani reaksiyon / sessizlik patlaması hassasiyeti
   - optimal_fusion_weights: Kanala özel optimize edilmiş sinyal ağırlıkları
2. Gemini / DeepSeek prompt'larına eklenebilecek bağlamsal DNA özeti üretir.
3. Çıkarılan DNA'yı SQLite `channels` tablosuna kaydeder ve günceller.

Kullanım::

    dna_mgr = ChannelDNAManager(db)
    dna = dna_mgr.get_or_compute_dna(channel_name="Efe Uygaç", uploader="Efe Uygaç")
    # dna["dominant_category"]       -> "FUNNY"
    # dna["avg_clip_duration"]       -> 28.5
    # dna["optimal_fusion_weights"]  -> {"audio": 0.45, "silence": 0.35, "heatmap": 0.20}
    # dna["dna_summary"]             -> "Bu kanalın izleyicisi komik ve ani reaksiyon anlarına %60 daha fazla ilgi gösteriyor..."
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import numpy as np

from core.logger import logger

if TYPE_CHECKING:
    from core.database import DatabaseManager


# ---------------------------------------------------------------------------
# Default General Gaming DNA (Yeterli geçmiş olmadığında kullanılır)
# ---------------------------------------------------------------------------
DEFAULT_CHANNEL_DNA: Dict[str, Any] = {
    "channel_name": "General",
    "dominant_category": "GAMING",
    "avg_clip_duration": 30.0,
    "total_clips_analyzed": 0,
    "shock_weight": 0.50,
    "category_distribution": {
        "GAMING": 0.40,
        "FUNNY": 0.30,
        "CLUTCH": 0.15,
        "RAGE": 0.15,
    },
    "optimal_fusion_weights": {
        "audio_spike": 0.40,
        "silence_burst": 0.30,
        "heatmap": 0.30,
    },
    "dna_summary": (
        "Genel oyun profili: Dengeli aksiyon, komedi ve reaksiyon odaklı içerik yapısı."
    ),
}


class ChannelDNAManager:
    """Kanal parmak izini (DNA) çıkarır, saklar ve sinyal/LLM optimizasyonuna sunar."""

    def __init__(self, db: Optional["DatabaseManager"] = None) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_dna_from_clips(
        self,
        channel_name: str,
        clips: List[Dict[str, Any]],
        heatmap_patterns: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Geçmiş klip ve heatmap verilerinden kanal DNA'sı hesaplar.

        Args:
            channel_name: Kanal adı / uploader adı
            clips: Geçmiş klip kayıtları [{category, duration, score, ...}]
            heatmap_patterns: Geçmiş heatmap korelasyonları

        Returns:
            Dict representing Channel DNA
        """
        if not clips:
            dna = dict(DEFAULT_CHANNEL_DNA)
            dna["channel_name"] = channel_name
            return dna

        total_clips = len(clips)
        categories: Dict[str, float] = {}
        durations: List[float] = []
        scores: List[float] = []

        for c in clips:
            cat = (c.get("category") or "GAMING").upper()
            dur = float(c.get("duration") or 30.0)
            score = float(c.get("score") or c.get("viral_confidence") or 50)

            durations.append(dur)
            scores.append(score)
            # Skor ağırlıklı kategori frekansı
            categories[cat] = categories.get(cat, 0.0) + (score / 100.0)

        # Ortalama süre ve baskın kategori
        avg_dur = round(float(np.mean(durations)), 1) if durations else 30.0
        tot_weight = sum(categories.values()) or 1.0
        cat_dist = {k: round(v / tot_weight, 2) for k, v in categories.items()}
        dominant_cat = max(categories, key=lambda k: categories[k]) if categories else "GAMING"

        # Şok ağırlığı (RAGE, JUMPSCARE veya FUNNY baskınsa şok sinyali daha değerlidir)
        shock_prone = cat_dist.get("RAGE", 0.0) + cat_dist.get("JUMPSCARE", 0.0) + cat_dist.get("FUNNY", 0.0)
        shock_weight = round(float(np.clip(0.35 + shock_prone * 0.40, 0.30, 0.85)), 2)

        # Kanala özel optimize edilmiş füzyon ağırlıkları
        if shock_weight > 0.60:
            optimal_weights = {
                "audio_spike": 0.45,
                "silence_burst": 0.35,
                "heatmap": 0.20,
            }
        else:
            optimal_weights = {
                "audio_spike": 0.40,
                "silence_burst": 0.30,
                "heatmap": 0.30,
            }

        # Doğal dilde DNA özeti (LLM prompt enjeksiyonu için)
        pct = int(cat_dist.get(dominant_cat, 0.3) * 100)
        dna_summary = (
            f"Kanal DNA'sı ({channel_name}): İzleyiciler ağırlıklı olarak %{pct} oranında "
            f"[{dominant_cat}] anlarına ilgi gösteriyor. İdeal viral klip süresi ~{int(avg_dur)} saniye. "
            f"Şok/reaksiyon duyarlılığı: {'Yüksek' if shock_weight > 0.55 else 'Normal'}."
        )

        dna = {
            "channel_name": channel_name,
            "dominant_category": dominant_cat,
            "avg_clip_duration": avg_dur,
            "total_clips_analyzed": total_clips,
            "shock_weight": shock_weight,
            "category_distribution": cat_dist,
            "optimal_fusion_weights": optimal_weights,
            "dna_summary": dna_summary,
        }

        logger.info(
            "ChannelDNAManager: DNA hesaplandı — channel='{}' clips={} dominant={} avg_dur={}s",
            channel_name, total_clips, dominant_cat, avg_dur
        )
        return dna

    def get_or_compute_dna(
        self,
        channel_name: str,
        uploader: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Kanalın DB'de kayıtlı DNA'sını döner; yoksa geçmiş klipleri toplayıp hesaplar ve kaydeder.
        """
        lookup_name = uploader or channel_name or "General"
        if not self.db:
            return self.compute_dna_from_clips(lookup_name, [])

        # 1. DB'de kayıtlı kanal var mı kontrol et
        try:
            channel_record = self.db.get_channel(lookup_name)
            if channel_record and channel_record.get("dna_json"):
                dna = json.loads(channel_record["dna_json"])
                if isinstance(dna, dict) and dna.get("dominant_category"):
                    return dna
        except Exception:
            pass

        # 2. Geçmiş klipleri çekip hesapla
        clips = []
        try:
            clips = self.db.get_channel_clips(lookup_name)
        except Exception:
            clips = []

        dna = self.compute_dna_from_clips(lookup_name, clips)

        # 3. Sonucu DB'ye kaydet
        try:
            self.db.save_channel({
                "id": lookup_name,
                "url": f"https://youtube.com/@{lookup_name.replace(' ', '')}",
                "name": lookup_name,
                "dna_json": dna,
            })
        except Exception as exc:
            logger.warning(f"Could not persist channel DNA: {exc}")

        return dna

    def format_prompt_context(self, channel_dna: Dict[str, Any]) -> str:
        """Gemini veya DeepSeek prompt'larına eklenecek DNA yönlendirme metnini döner."""
        if not channel_dna:
            return ""
        summary = channel_dna.get("dna_summary", "")
        dom = channel_dna.get("dominant_category", "")
        dur = channel_dna.get("avg_clip_duration", 30)

        return (
            f"\n[KANAL PARMAK İZİ / CHANNEL DNA]\n"
            f"- {summary}\n"
            f"- Bu kanalın izleyici kitlesi için öncelikli kategori: {dom}\n"
            f"- Hedeflenen ideal tempo/süre: ~{dur} saniye\n"
        )
