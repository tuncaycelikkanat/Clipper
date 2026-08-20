import re
from typing import List, Dict, Any, Optional, Tuple
from youtube_transcript_api import YouTubeTranscriptApi

class TranscriptManager:
    """Fetches YouTube transcripts and performs advanced Turkish/Multilingual sentence completion snapping."""

    # Incomplete sentence connector words (sentence cannot end with these)
    INCOMPLETE_ENDINGS = {
        've', 'veya', 'ile', 'ama', 'fakat', 'ancak', 'çünkü', 'oysa', 'oysaki',
        'diye', 'için', 'ki', 'ise', 'de', 'da', 'gibi', 'kadar', 'bu', 'şu', 'o',
        'bir', 'en', 'çok', 'daha', 'hem', 'ya', 'ne', 'yani', 'dolayısıyla',
        'nasıl', 'neden', 'niçin', 'kim', 'nerede', 'neye', 'kime',
        'mı', 'mi', 'mu', 'mü', 'yapmayı', 'etmeyi', 'olmayı', 'gitmeyi',
        'and', 'or', 'but', 'because', 'so', 'if', 'that', 'with', 'to', 'for', 'at', 'in', 'on', 'the', 'a', 'an'
    }

    # Turkish verb tense/person suffixes indicating a complete predicate
    VERB_SUFFIX_PATTERNS = [
        r'(dı|di|du|dü|tı|ti|tu|tü)$',                    # görülen geçmiş zaman (gitti, oldu, yaptı)
        r'(mış|miş|muş|müş)$',                            # duyulan geçmiş zaman (gelmiş, bitmiş)
        r'(yor|ıyor|iyor|uyor|üyor)$',                    # şimdiki zaman (gidiyor, yapıyor)
        r'(acak|ecek)$',                                  # gelecek zaman (olacak, bitecek)
        r'(ır|ir|ur|ür|ar|er|maz|mez)$',                  # geniş zaman (yapar, olmaz, gider)
        r'(malı|meli|sa|se|sın|sin|sun|sün|yız|yiz|yım|yim)$', # kipler & şahıs ekleri
        r'(dır|dir|dur|dür|tır|tir|tur|tür)$',            # ek eylem (vardır, güzeldir)
        r'(var|yok|değil|tamam|evet|hayır|bitti|oldu)$'   # isim cümleleri ve onaylar
    ]

    @staticmethod
    def get_transcript(video_id: str, preferred_languages: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Fetches transcript snippets from YouTube.
        Returns a list of standardized dicts: [{'text': str, 'start': float, 'end': float, 'duration': float}, ...]
        """
        if preferred_languages is None:
            preferred_languages = ['tr', 'en']

        ytt = YouTubeTranscriptApi()
        try:
            transcript_list = ytt.list(video_id)
        except Exception:
            return []

        selected_transcript = None
        for lang in preferred_languages:
            for t in transcript_list:
                if t.language_code.lower().startswith(lang.lower()):
                    selected_transcript = t
                    break
            if selected_transcript:
                break

        if not selected_transcript:
            for t in transcript_list:
                selected_transcript = t
                break

        if not selected_transcript:
            return []

        try:
            raw_snippets = selected_transcript.fetch()
        except Exception:
            return []

        clean_segments = []
        for s in raw_snippets:
            text = s.text.replace("\n", " ").strip() if hasattr(s, 'text') else str(s.get('text', '')).replace("\n", " ").strip()
            start = float(s.start if hasattr(s, 'start') else s.get('start', 0.0))
            dur = float(s.duration if hasattr(s, 'duration') else s.get('duration', 0.0))
            end = round(start + dur, 2)
            if text:
                clean_segments.append({
                    "text": text,
                    "start": round(start, 2),
                    "end": end,
                    "duration": round(dur, 2)
                })

        return clean_segments

    @classmethod
    def is_sentence_complete(cls, text: str) -> bool:
        """Determines if a text snippet represents a complete sentence or complete thought."""
        text = text.strip()
        if not text:
            return False

        # 1. Check punctuation
        if any(text.endswith(p) for p in ['.', '?', '!', '...', '."', '?"', '!"']):
            return True

        # 2. Check last word
        words = re.findall(r'\b\w+\b', text.lower())
        if not words:
            return False

        last_word = words[-1]

        # Incomplete connectors check
        if last_word in cls.INCOMPLETE_ENDINGS:
            return False

        # Check Turkish verb patterns
        for pattern in cls.VERB_SUFFIX_PATTERNS:
            if re.search(pattern, last_word):
                return True

        return False

    @classmethod
    def snap_boundaries(
        cls,
        candidate_start: float,
        candidate_end: float,
        transcript_segments: List[Dict[str, Any]],
        max_snap_sec: float = 6.0
    ) -> Tuple[float, float, str]:
        """
        Guarantees that:
        1. Start begins cleanly at the first word of a sentence / thought.
        2. End extends forward until a complete verb, punctuation, or natural pause (>0.6s) is reached.
        """
        if not transcript_segments:
            return candidate_start, candidate_end, ""

        # 1. Snap Start Time (Clean opener)
        best_start = candidate_start
        min_start_diff = float("inf")

        for idx, seg in enumerate(transcript_segments):
            s_time = seg["start"]
            diff = abs(s_time - candidate_start)
            
            prev_end = transcript_segments[idx-1]["end"] if idx > 0 else 0
            is_after_pause = (s_time - prev_end) >= 0.5

            if diff <= max_snap_sec:
                score_weight = 0.6 if is_after_pause else 1.0
                weighted_diff = diff * score_weight
                if weighted_diff < min_start_diff:
                    min_start_diff = weighted_diff
                    best_start = s_time

        # 2. Snap End Time with Verb & Completion Verification
        target_idx = None
        for idx, seg in enumerate(transcript_segments):
            if seg["start"] <= candidate_end <= seg["end"] + 1.2:
                target_idx = idx
                break
        
        if target_idx is None:
            target_idx = min(range(len(transcript_segments)), key=lambda i: abs(transcript_segments[i]["end"] - candidate_end))

        best_end = transcript_segments[target_idx]["end"]
        
        # Look forward up to 4 segments to complete the thought/verb
        accumulated_text = ""
        for forward_offset in range(5):
            curr_idx = target_idx + forward_offset
            if curr_idx >= len(transcript_segments):
                break
            
            curr_seg = transcript_segments[curr_idx]
            accumulated_text += " " + curr_seg["text"].strip()
            
            # Check pause after this segment
            next_start = transcript_segments[curr_idx+1]["start"] if curr_idx + 1 < len(transcript_segments) else curr_seg["end"] + 5.0
            has_pause = (next_start - curr_seg["end"]) >= 0.6
            
            is_complete = cls.is_sentence_complete(accumulated_text)
            best_end = curr_seg["end"]

            # If thought is complete or has clear natural pause after a complete thought, stop here!
            if is_complete or has_pause:
                break

        # Add 0.35s audio breathing room
        best_end = round(best_end + 0.35, 2)
        best_start = round(best_start, 2)

        if best_end <= best_start or (best_end - best_start) < 10.0:
            best_start = candidate_start
            best_end = candidate_end

        # Gather included texts
        included_texts = []
        for seg in transcript_segments:
            if seg["end"] >= best_start - 0.1 and seg["start"] <= best_end + 0.1:
                included_texts.append(seg["text"])

        snippet_text = " ".join(included_texts)
        return best_start, best_end, snippet_text
