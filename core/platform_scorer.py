"""
core/platform_scorer.py — Platform Uyum Skoru (Clip-to-Platform Matrix)

Kırpılan veya değerlendirilen her klip için 4 ana kısa video platformuna uyum skoru (0-100) üretir:
1. TikTok: Hook gücü, hızlı tempo, reaksiyon/komedi kategorisi, 15-35s süre.
2. YouTube Shorts: Hikaye tamlığı, 20-55s süre (<60s kuralı), SEO & yüksek kalite.
3. Instagram Reels: Görsel dinamizm, estetik ve clutch/epic anlar, 15-40s süre.
4. Twitter / X: Hızlı punchline (<30s), ilk 10 saniyede başlayan şok/aksiyon, rage/fail anları.

Kullanım::

    scorer = PlatformScorer()
    scores = scorer.score_clip(clip_data)
    # scores["tiktok"]        -> 88
    # scores["shorts"]        -> 94
    # scores["reels"]         -> 82
    # scores["twitter"]       -> 65
    # scores["best_platform"] -> "YouTube Shorts"
"""

from __future__ import annotations

from typing import Any


class PlatformScorer:
    """Klipleri TikTok, YouTube Shorts, Instagram Reels ve Twitter için puanlar."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score_clip(self, clip: dict[str, Any]) -> dict[str, Any]:
        """
        Bir klip sözlüğünü (ClipData) 4 platform için puanlar.

        Args:
            clip: {
                'duration': float,
                'category': str,
                'hook_caption': str,
                'score': int,
                'viral_confidence': int,
                'signals': dict, (opsiyonel)
                'text': str, (opsiyonel)
            }

        Returns:
            dict: {
                'tiktok': int (0-100),
                'shorts': int (0-100),
                'reels': int (0-100),
                'twitter': int (0-100),
                'best_platform': str,
                'platform_badges': list[dict],
                'recommendation': str,
            }
        """
        duration = float(clip.get("duration") or 30.0)
        category = str(clip.get("category") or "GAMING").upper()
        hook = str(clip.get("hook_caption") or "")
        quality_score = float(clip.get("score") or clip.get("viral_confidence") or 70.0)
        signals = clip.get("signals") or {}

        # 1. TikTok Skoru (0-100)
        tiktok_score = self._score_tiktok(duration, category, hook, quality_score, signals)

        # 2. YouTube Shorts Skoru (0-100)
        shorts_score = self._score_shorts(duration, category, hook, quality_score, signals)

        # 3. Instagram Reels Skoru (0-100)
        reels_score = self._score_reels(duration, category, hook, quality_score, signals)

        # 4. Twitter / X Skoru (0-100)
        twitter_score = self._score_twitter(duration, category, hook, quality_score, signals)

        # En iyi platformu belirle
        platform_map = {
            "YouTube Shorts": shorts_score,
            "TikTok": tiktok_score,
            "Instagram Reels": reels_score,
            "Twitter / X": twitter_score,
        }
        best_plat = max(platform_map, key=lambda k: platform_map[k])

        # Rozetler
        badges = []
        for name, score in sorted(platform_map.items(), key=lambda x: x[1], reverse=True):
            if score >= 85:
                status = "MÜKEMMEL" if name == best_plat else "ÇOK İYİ"
            elif score >= 70:
                status = "İYİ"
            elif score >= 50:
                status = "ORTA"
            else:
                status = "UYGUN DEĞİL"

            badges.append(
                {
                    "platform": name,
                    "score": score,
                    "status": status,
                }
            )

        rec = (
            f"Bu klip {int(duration)} saniyelik süresi ve [{category}] yapısıyla en çok "
            f"**{best_plat}** (%{platform_map[best_plat]}) için optimize edilmiştir."
        )

        return {
            "tiktok": tiktok_score,
            "shorts": shorts_score,
            "reels": reels_score,
            "twitter": twitter_score,
            "best_platform": best_plat,
            "platform_badges": badges,
            "recommendation": rec,
        }

    # ------------------------------------------------------------------
    # Platform Specific Scoring
    # ------------------------------------------------------------------

    def _score_tiktok(
        self,
        duration: float,
        category: str,
        hook: str,
        quality_score: float,
        signals: dict[str, Any],
    ) -> int:
        score = 0.0

        # Hook gücü (Maks 30): İlk 3 saniyede izleyiciyi tutma
        if hook and len(hook) >= 5:
            score += 30.0
        elif hook:
            score += 15.0
        else:
            score += 5.0

        # Süre uyumu (Maks 25): 15-32s TikTok için altın oran
        if 15.0 <= duration <= 32.0:
            score += 25.0
        elif 10.0 <= duration < 15.0 or 32.0 < duration <= 45.0:
            score += 15.0
        elif duration <= 60.0:
            score += 5.0
        else:
            score -= 10.0  # >60s ceza

        # Kategori uyumu (Maks 25): Komedi, şok, rage, jumpscare çok viral
        if any(c in category for c in ["FUNNY", "RAGE", "JUMPSCARE", "FAIL", "WTF"]):
            score += 25.0
        elif any(c in category for c in ["CLUTCH", "EPIC"]):
            score += 18.0
        else:
            score += 12.0

        # Dinamizm / Sinyal (Maks 20)
        spike = float(signals.get("audio_spike") or 0.5)
        silence = float(signals.get("silence_burst") or 0.5)
        score += (spike * 10.0) + (silence * 10.0)

        return int(min(100, max(0, round(score))))

    def _score_shorts(
        self,
        duration: float,
        category: str,
        hook: str,
        quality_score: float,
        signals: dict[str, Any],
    ) -> int:
        score = 0.0

        # Süre uyumu (Maks 30): YouTube Shorts <60s zorunlu, 20-50s ideal
        if 20.0 <= duration <= 50.0:
            score += 30.0
        elif 12.0 <= duration < 20.0 or 50.0 < duration <= 58.0:
            score += 20.0
        elif duration <= 60.0:
            score += 10.0
        else:
            score = 0.0  # 60 saniyeden uzun Shorts olamaz
            return int(score)

        # Kalite & Hikaye puanı (Maks 25)
        score += (quality_score / 100.0) * 25.0

        # Kategori & İçerik derinliği (Maks 25): Gaming, Clutch, Story, Epic
        if any(c in category for c in ["CLUTCH", "EPIC", "STORY", "GAMING", "VICTORY"]):
            score += 25.0
        elif any(c in category for c in ["FUNNY", "FAIL"]):
            score += 20.0
        else:
            score += 15.0

        # Heatmap / İzleyici tekrar değeri (Maks 20)
        heatmap_val = float(signals.get("heatmap_val") or 0.0)
        if heatmap_val > 0.60:
            score += 20.0
        elif heatmap_val > 0.30:
            score += 12.0
        elif hook:
            score += 10.0
        else:
            score += 5.0

        return int(min(100, max(0, round(score))))

    def _score_reels(
        self,
        duration: float,
        category: str,
        hook: str,
        quality_score: float,
        signals: dict[str, Any],
    ) -> int:
        score = 0.0

        # Süre uyumu (Maks 25): 15-40s Reels için ideal
        if 15.0 <= duration <= 40.0:
            score += 25.0
        elif 10.0 <= duration < 15.0 or 40.0 < duration <= 60.0:
            score += 18.0
        elif duration <= 90.0:
            score += 10.0
        else:
            score += 0.0

        # Kalite & Estetik skoru (Maks 30)
        score += (quality_score / 100.0) * 30.0

        # Kategori uyumu (Maks 25): Epic, Clutch, Funny, Aesthetic
        if any(c in category for c in ["EPIC", "CLUTCH", "FUNNY", "VICTORY", "SHOW"]):
            score += 25.0
        elif any(c in category for c in ["FAIL", "WTF", "GAMING"]):
            score += 18.0
        else:
            score += 12.0

        # Hook & Başlık (Maks 20)
        if hook:
            score += 20.0
        else:
            score += 8.0

        return int(min(100, max(0, round(score))))

    def _score_twitter(
        self,
        duration: float,
        category: str,
        hook: str,
        quality_score: float,
        signals: dict[str, Any],
    ) -> int:
        score = 0.0

        # Süre uyumu (Maks 40): Twitter'da dikkat süresi çok kısa, <25s altın oran
        if duration <= 22.0:
            score += 40.0
        elif duration <= 32.0:
            score += 28.0
        elif duration <= 45.0:
            score += 15.0
        else:
            score += 0.0  # >45s Twitter için çok uzun

        # Kategori (Maks 35): Rage, Fail, Meme, WTF, Shock Twitter'da anında retweet alır
        if any(c in category for c in ["RAGE", "FAIL", "WTF", "MEME", "JUMPSCARE"]):
            score += 35.0
        elif any(c in category for c in ["FUNNY", "CLUTCH"]):
            score += 24.0
        else:
            score += 14.0

        # Hızlı aksiyon / Şok (Maks 25)
        spike = float(signals.get("audio_spike") or 0.5)
        score += spike * 25.0

        return int(min(100, max(0, round(score))))
