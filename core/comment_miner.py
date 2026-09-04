"""
core/comment_miner.py — YouTube Yorum Patlaması & Timestamp Analizcisi (Comment Mining)

YouTube video yorumlarından:
1. Zaman damgalarını (5:32, 05:32, 1:24:10, 5m32s vb.) regex ile ayıklar.
2. Timestamp frekanslarını video zaman çizelgesi üzerinde yoğunluk eğrisine (comment signal) dönüştürür.
3. Timestamp içeren yorumlardaki emojiler ve anahtar kelimelerle reaksiyon duygu tespiti yapar (FUNNY, EPIC, JUMPSCARE, RAGE, FAIL, WTF).
4. candidate_ranker.py için füzyon sinyali sağlar.

Kullanım::

    miner = CommentMiner()
    result = miner.mine_comments(comments_data, total_duration=600)
    # result["comment_curve"]       -> zaman noktalarına göre sinyal
    # result["timestamp_clusters"]  -> [{time, count, dominant_reaction, samples}]
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from core.logger import logger

# ---------------------------------------------------------------------------
# Timestamp Regex Patterns
# ---------------------------------------------------------------------------
# Desteklenen formatlar:
# 05:32, 5:32, 5.32, 05.32, 1:05:32, 1.05.32, @05:32, (05:32), (5.13), 5m32s, 1h20m10s, 5m 32s, 5 dk 13 sn, 5dk, t=332
_TS_HHMMSS = re.compile(r'(?:@|\b)?(?:\()?(\d{1,2})[:.](\d{2})[:.](\d{2})(?:\))?')
_TS_MMSS = re.compile(r'(?:@|\b)?(?:\()?(\d{1,2})[:.](\d{2})(?:\))?')
_TS_LETTER = re.compile(r'(?:@|\b)?(?:(\d{1,2})\s*(?:saat|sa|h)\s*)?(?:(\d{1,3})\s*(?:dakika|dak|dk|d|m)\s*)?(?:(\d{1,2})\s*(?:saniye|san|sn|s))\b', re.IGNORECASE)
_TS_MINUTES_ONLY = re.compile(r'(?:@|\b)?(\d{1,3})\s*(?:dakika|dak|dk)\b', re.IGNORECASE)

# ---------------------------------------------------------------------------
# Reaksiyon / Duygu Sözlükleri
# ---------------------------------------------------------------------------
_REACTION_KEYWORDS: Dict[str, List[str]] = {
    "FUNNY": [
        "😂", "🤣", "xd", "koptum", "gümledim", "yarıldım", "hahaha", "asdf",
        "komik", "lmao", "lol", "patladım", "ahahaha", "sjsj", "kahkaha",
        "öldüm", "yarıl", "güldüm", "ağladım gülmekten", "hoca", "jshs", "sksk"
    ],
    "EPIC": [
        "🔥", "goat", "efsane", "mükemmel", "harika", "god mode", "kral",
        "epic", "inanılmaz", "vuruş", "clutch", "headshot", "rekor", "şov",
        "helal", "pro", "carry", "akıyor"
    ],
    "JUMPSCARE": [
        "😱", "korktum", "altıma", "jumpscare", "kalbim", "yüreğim", "ağzıma",
        "scary", "korku", "çığlık", "titredim", "zıplattı"
    ],
    "RAGE": [
        "🤬", "rage", "çıldırdı", "delirdi", "sinir", "masayı", "kırdı",
        "küfür", "tilt", "çıldırtan", "kansere", "çıldırma"
    ],
    "FAIL": [
        "💀", "fail", "yazık", "rezil", "olamaz", "öldü", "patladı", "gg",
        "rip", "beceremedi", "fiyasko", "hata", "yazık kafana"
    ],
    "WTF": [
        "🤨", "😳", "wtf", "noldu", "nasıl", "ne alaka", "oha", "yuh",
        "çüş", "ne yaptı", "mantıksız", "bu ne"
    ]
}


class CommentMiner:
    """YouTube yorumlarını madenleyerek timestamp yoğunluğu ve reaksiyon tespiti yapar."""

    def __init__(self, cluster_window_sec: float = 10.0) -> None:
        self.cluster_window_sec = cluster_window_sec

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_timestamps_from_text(self, text: str) -> List[float]:
        """Bir yorum metnindeki tüm timestamp'leri saniye cinsinden döner."""
        if not text:
            return []

        seconds_list: List[float] = []

        # 1. HH:MM:SS veya HH.MM.SS (Örn: 01:05:32 veya 1.05.32)
        for match in _TS_HHMMSS.finditer(text):
            h, m, s = match.groups()
            min_val, sec_val = int(m), int(s)
            if min_val < 60 and sec_val < 60:
                sec = int(h) * 3600 + min_val * 60 + sec_val
                seconds_list.append(float(sec))

        # 2. MM:SS veya MM.SS (Örn: 5:13, 5.13, 05.13)
        # HH:MM:SS bulunan konumları maskeleyerek MM:SS ara
        masked_text = _TS_HHMMSS.sub("XX:XX:XX", text)
        for match in _TS_MMSS.finditer(masked_text):
            m, s = match.groups()
            min_val, sec_val = int(m), int(s)
            # Saniye 0-59 arasında olmalı (rastgele ondalık sayıları engellemek için, örn. 3.85 elenir)
            if sec_val < 60 and min_val < 300:
                sec = min_val * 60 + sec_val
                seconds_list.append(float(sec))

        # 3. Metinsel Türkçe/İngilizce formatlar: 1h20m10s, 5m32s, 5 dk 13 sn, 5d 13s
        for match in _TS_LETTER.finditer(text):
            h, m, s = match.groups()
            hours = int(h) if h else 0
            minutes = int(m) if m else 0
            secs = int(s) if s else 0
            if hours == 0 and minutes == 0 and secs == 0:
                continue
            total = hours * 3600 + minutes * 60 + secs
            seconds_list.append(float(total))

        # 4. Sadece dakika belirten formatlar: "5 dk", "12 dakika"
        for match in _TS_MINUTES_ONLY.finditer(text):
            m = match.group(1)
            if m:
                min_val = int(m)
                if 0 < min_val < 300:
                    seconds_list.append(float(min_val * 60))

        return sorted(list(set(seconds_list)))

    def detect_comment_reaction(self, text: str) -> str:
        """Yorum metnindeki baskın reaksiyonu / duyguyu tespit eder."""
        if not text:
            return "GENERAL"

        lower_text = text.lower()
        reaction_scores: Dict[str, int] = {k: 0 for k in _REACTION_KEYWORDS}

        for reaction, keywords in _REACTION_KEYWORDS.items():
            for kw in keywords:
                if kw in lower_text:
                    reaction_scores[reaction] += 1

        best_reaction = max(reaction_scores, key=lambda k: reaction_scores[k])
        if reaction_scores[best_reaction] > 0:
            return best_reaction
        return "HIGHLIGHT"

    def process_comments(
        self,
        comments: List[Dict[str, Any]],
        total_duration: float,
        timeline_times: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Ham yorum listesini işler:
        - Timestamp içeren yorumları gruplar
        - Zaman çizelgesi üzerinde normalize yoğunluk eğrisi (0-1) oluşturur
        - Timestamp kümelerini (clusters) reaksiyonlarıyla birlikte döner

        Args:
            comments: [{'text': str, 'like_count': int, ...}] veya [str, ...]
            total_duration: Video toplam süresi (saniye)
            timeline_times: Sinyalin interpolasyon yapılacağı zaman ekseni (opsiyonel)

        Returns:
            dict:
                - timestamp_clusters (list[dict]): [{time, count, weighted_score, dominant_reaction, samples}]
                - comment_signal (np.ndarray): timeline_times üzerinde 0-1 yoğunluk eğrisi
                - total_timestamps_found (int): Bulunan toplam timestamp sayısı
        """
        if not comments or total_duration <= 0:
            n_pts = len(timeline_times) if timeline_times is not None else 0
            return {
                "timestamp_clusters": [],
                "comment_signal": np.zeros(n_pts),
                "total_timestamps_found": 0,
            }

        extracted_events: List[Dict[str, Any]] = []

        for c in comments:
            if isinstance(c, dict):
                text = c.get("text", "") or c.get("textDisplay", "") or ""
                likes = int(c.get("like_count", 0) or c.get("likeCount", 0) or 0)
            else:
                text = str(c)
                likes = 0

            ts_list = self.extract_timestamps_from_text(text)
            if not ts_list:
                continue

            reaction = self.detect_comment_reaction(text)
            # Beğeni ağırlığı: 1 + log1p(likes)
            weight = 1.0 + float(np.log1p(max(0, likes)))

            for ts in ts_list:
                if 0 <= ts <= total_duration:
                    extracted_events.append({
                        "time": ts,
                        "weight": weight,
                        "reaction": reaction,
                        "text": text.strip()[:120],
                    })

        if not extracted_events:
            n_pts = len(timeline_times) if timeline_times is not None else 0
            return {
                "timestamp_clusters": [],
                "comment_signal": np.zeros(n_pts),
                "total_timestamps_found": 0,
            }

        # Kümeleri oluştur (Cluster nearby timestamps)
        clusters = self._cluster_timestamp_events(extracted_events)

        # Zaman çizelgesi üzerinde yoğunluk eğrisi üret
        if timeline_times is not None and len(timeline_times) > 0:
            comment_signal = self._generate_density_curve(clusters, timeline_times, total_duration)
        else:
            comment_signal = np.array([])

        logger.info(
            "CommentMiner: {} yorumdan {} timestamp ayıklandı, {} küme oluşturuldu.",
            len(comments), len(extracted_events), len(clusters)
        )

        return {
            "timestamp_clusters": clusters,
            "comment_signal": comment_signal,
            "total_timestamps_found": len(extracted_events),
        }

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _cluster_timestamp_events(
        self, events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Zaman olarak yakın timestamp olaylarını birleştirir."""
        events.sort(key=lambda x: x["time"])
        clusters: List[Dict[str, Any]] = []

        for ev in events:
            t = ev["time"]
            w = ev["weight"]
            r = ev["reaction"]
            txt = ev["text"]

            merged = False
            for cl in clusters:
                if abs(t - cl["time"]) <= self.cluster_window_sec:
                    # Ağırlıklı ortalama zaman hesabı
                    new_weight = cl["weight"] + w
                    cl["time"] = (cl["time"] * cl["weight"] + t * w) / new_weight
                    cl["weight"] = new_weight
                    cl["count"] += 1
                    cl["reactions"][r] = cl["reactions"].get(r, 0) + 1
                    if len(cl["samples"]) < 3 and txt not in cl["samples"]:
                        cl["samples"].append(txt)
                    merged = True
                    break

            if not merged:
                clusters.append({
                    "time": t,
                    "weight": w,
                    "count": 1,
                    "reactions": {r: 1},
                    "samples": [txt],
                })

        # Baskın reaksiyonu ve nihai skorları hesapla
        for cl in clusters:
            cl["time"] = round(float(cl["time"]), 1)
            cl["dominant_reaction"] = max(cl["reactions"], key=lambda k: cl["reactions"][k])

        # Ağırlığa göre sırala
        clusters.sort(key=lambda x: x["weight"], reverse=True)
        return clusters

    def _generate_density_curve(
        self,
        clusters: List[Dict[str, Any]],
        timeline_times: np.ndarray,
        total_duration: float,
        sigma: float = 8.0,
    ) -> np.ndarray:
        """Kümelerden Gauss kernel yoğunluk tahmini (KDE) ile 0-1 normalize eğri üretir."""
        if not clusters or len(timeline_times) == 0:
            return np.zeros(len(timeline_times))

        signal = np.zeros(len(timeline_times))
        for cl in clusters:
            mu = cl["time"]
            weight = cl["weight"]
            # Gaussian bell curve around peak
            diff = timeline_times - mu
            gauss = np.exp(-0.5 * (diff / sigma) ** 2)
            signal += weight * gauss

        mx = signal.max()
        if mx > 1e-9:
            signal = signal / mx

        return signal
