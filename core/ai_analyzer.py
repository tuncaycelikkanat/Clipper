from typing import List, Dict, Any, Optional
import re
from core.extractor import YouTubeExtractor
from core.transcript import TranscriptManager

class AIHighlightAnalyzer:
    """Detects viral/interesting highlights from transcript when heatmap is unavailable or as an AI enhancer."""

    def __init__(
        self,
        min_clip_duration: int = 30,
        max_clip_duration: int = 60,
        target_clips: int = 3,
        min_distance_sec: int = 60
    ):
        self.min_clip_duration = min_clip_duration
        self.max_clip_duration = max_clip_duration
        self.target_clips = target_clips
        self.min_distance_sec = min_distance_sec

    def create_chunks(self, transcript: List[Dict[str, Any]], total_duration: int, step_sec: int = 15) -> List[Dict[str, Any]]:
        """Creates sliding time windows over the transcript."""
        if not transcript:
            return []

        chunks = []
        cur_start = 0.0
        
        while cur_start + self.min_clip_duration <= total_duration:
            cur_end = min(cur_start + self.max_clip_duration, float(total_duration))
            
            # Gather text in this window
            seg_texts = []
            for seg in transcript:
                if seg["end"] >= cur_start and seg["start"] <= cur_end:
                    seg_texts.append(seg["text"])
            
            chunk_text = " ".join(seg_texts).strip()
            if len(chunk_text) > 30:
                chunks.append({
                    "start_time": cur_start,
                    "end_time": cur_end,
                    "duration": cur_end - cur_start,
                    "text": chunk_text
                })
            
            cur_start += step_sec

        return chunks

    def score_chunk(self, text: str) -> Dict[str, Any]:
        """
        Heuristic NLP scoring for viral potential based on hook keywords, question starters,
        emotional emphasis, and narrative structure.
        """
        text_lower = text.lower()
        
        # 1. Hook Score (Question words, intriguing openers)
        hook_indicators = [
            r'\b(neden|nasıl|niçin|kim|nerede|ne zaman|kaç|what|why|how|when|who)\b',
            r'\b(aslında|gerçekten|hiç|asla|sakın|en büyük|en önemli|sır|taktik|hata|secret|mistake|never|always)\b',
            r'\b(bunu biliyor muydunuz|did you know|bakın|dinleyin|listen|look)\b',
            r'\?'
        ]
        hook_score = 0
        for pattern in hook_indicators:
            if re.search(pattern, text_lower):
                hook_score += 25
        hook_score = min(100, max(20, hook_score))

        # 2. Emotional / Contrast & Insight Score
        insight_indicators = [
            r'\b(çünkü|fakat|ama|ancak|oysa|bunun yerine|sonuç olarak|ve sonra|because|but|however|therefore)\b',
            r'\b(inanılmaz|harika|korkunç|şok|şaşırtıcı|crazy|insane|amazing|unbelievable)\b',
            r'\b(para|başarı|hayat|kariyer|zaman|hedef|money|success|life|career|time)\b',
            r'!'
        ]
        insight_score = 0
        for pattern in insight_indicators:
            if re.search(pattern, text_lower):
                insight_score += 20
        insight_score = min(100, max(20, insight_score))

        # 3. Density & Word Count Score
        words = text.split()
        word_count = len(words)
        # Optimal speech density is around 2-3 words per second (60-120 words for 30s)
        density_score = 80 if 40 <= word_count <= 140 else 50

        # Composite score
        total_score = int((hook_score * 0.45) + (insight_score * 0.35) + (density_score * 0.20))
        
        # Reason tag
        reasons = []
        if hook_score >= 60:
            reasons.append("🔥 Güçlü Hook / Soru")
        if insight_score >= 60:
            reasons.append("💡 Çarpıcı Bilgi / Karşıtlık")
        if not reasons:
            reasons.append("📌 Akıcı Anlatım")

        return {
            "score": total_score,
            "hook_score": hook_score,
            "insight_score": insight_score,
            "reason": " • ".join(reasons)
        }

    def analyze(self, transcript: List[Dict[str, Any]], total_duration: int) -> List[Dict[str, Any]]:
        """Analyzes transcript and returns the top AI-recommended highlight clips."""
        if not transcript:
            return []

        chunks = self.create_chunks(transcript, total_duration)
        if not chunks:
            return []

        # Score all chunks
        scored_chunks = []
        for c in chunks:
            sc = self.score_chunk(c["text"])
            scored_chunks.append({
                **c,
                "score": sc["score"],
                "reason": sc["reason"]
            })

        # Sort descending by score
        scored_chunks.sort(key=lambda x: x["score"], reverse=True)

        # Select top candidates respecting minimum distance
        selected = []
        for cand in scored_chunks:
            if all(abs(cand["start_time"] - s["start_time"]) >= self.min_distance_sec for s in selected):
                selected.append(cand)
            if len(selected) >= self.target_clips:
                break

        # Snap to exact sentence boundaries
        clips = []
        for rank, cand in enumerate(selected, start=1):
            snapped_start, snapped_end, text_snapped = TranscriptManager.snap_boundaries(
                cand["start_time"],
                cand["end_time"],
                transcript
            )
            duration = round(snapped_end - snapped_start, 1)

            clips.append({
                "rank": rank,
                "score": cand["score"],
                "intensity": cand["score"], # compatibility
                "reason": cand["reason"],
                "peak_time": round((snapped_start + snapped_end) / 2.0, 1),
                "peak_formatted": YouTubeExtractor.format_seconds((snapped_start + snapped_end) / 2.0),
                "start_time": snapped_start,
                "start_formatted": YouTubeExtractor.format_seconds(snapped_start),
                "end_time": snapped_end,
                "end_formatted": YouTubeExtractor.format_seconds(snapped_end),
                "duration": duration,
                "duration_formatted": f"{int(duration)} sn",
                "text": text_snapped or cand["text"]
            })

        # Sort chronologically for display
        clips.sort(key=lambda c: c["start_time"])
        return clips
