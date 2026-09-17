from typing import TYPE_CHECKING, Any, Optional

import numpy as np
from loguru import logger

from core.extractor import YouTubeExtractor

if TYPE_CHECKING:
    from core.database import DatabaseManager


def _zscore_normalize(arr: np.ndarray) -> np.ndarray:
    """Z-score normalize et, ardından 0-1 aralığına clip et.

    Video-bazında normalizasyon: her sinyali kendi dağılımına göre ölçekler.
    Heatmap sinyali gibi dışarıdan gelen mutlak sayıların ağırlığını dengeler.
    """
    if len(arr) == 0:
        return arr
    median = np.median(arr)
    std = np.std(arr) + 1e-9
    normalized = (arr - median) / std
    # 0-1 sıkıştır: negatif → 0, z≥3 → 1.0
    return np.clip(normalized / 3.0, 0.0, 1.0)


class CandidateRanker:
    """Combines multimodal signals (Audio Spikes, Silence-Burst, Transcripts, Visual, Pitch) into Top-N Candidates."""

    def __init__(
        self,
        candidate_window_sec: int = 35,
        merge_threshold_sec: int = 8,
        top_n: int = 15,
        db: Optional["DatabaseManager"] = None,
        min_diversity_ratio: float = 0.02,
        dynamic_window: bool = False,
        min_window_sec: float = 8.0,
        max_window_sec: float = 60.0,
    ):
        self.candidate_window_sec = candidate_window_sec
        self.merge_threshold_sec = merge_threshold_sec
        self.top_n = top_n
        self._db = db
        # Çeşitlilik kısıtı: iki aday arasında video süresine göre dengeli mesafe (varsayılan %2)
        self.min_diversity_ratio = min_diversity_ratio
        # Dinamik pencere: sabit 35sn yerine sinyal eğrisine göre pencere belirle
        self.dynamic_window = dynamic_window
        self.min_window_sec = min_window_sec
        self.max_window_sec = max_window_sec

    def fuse_signals_and_generate_candidates(
        self,
        times: np.ndarray,
        audio_spikes: np.ndarray,
        silence_bursts: np.ndarray,
        heatmap: list[dict[str, float]],  # ARTIK KULLANILMIYOR — parametre uyum için tutuldu
        transcript: list[dict[str, Any]],
        total_duration: int,
        video_id: str | None = None,
        view_count: int = 0,
        comments: list[Any] | None = None,
        pitch_variance: np.ndarray | None = None,
        frame_diff: np.ndarray | None = None,
        vocal_spikes: np.ndarray | None = None,
    ) -> list[dict[str, Any]]:
        """
        Tüm sinyalleri tek bir bileşik skora kaynaştırır ve Top-N aday klip üretir.

        Değişiklikler (v2):
        - Heatmap sinyali füzyondan çıkarıldı (yeni videolarda veri yok).
        - Her sinyal video-bazında z-score ile normalize edilir.
        - Pitch variance (ZCR tabanlı) ve frame-diff sinyalleri eklendi.
        - Konuşma hızı ivmesi (speech_rate_accel) eklendi.
        - Aday havuzuna çeşitlilik kısıtı eklendi.
        - Dinamik pencere: sinyal baseline'a dönüş noktasına göre pencere belirlenir.
        """

        if len(times) == 0:
            return []

        n_points = len(times)

        # ----------------------------------------------------------------
        # 1. Yorumları İşle
        # ----------------------------------------------------------------
        comment_curve = np.zeros(n_points)
        comment_clusters: list[dict[str, Any]] = []
        has_comments = False
        if comments:
            try:
                from core.comment_miner import CommentMiner

                miner = CommentMiner()
                comment_res = miner.process_comments(
                    comments=comments,
                    total_duration=float(total_duration),
                    timeline_times=times,
                )
                comment_curve = comment_res.get("comment_signal", np.zeros(n_points))
                comment_clusters = comment_res.get("timestamp_clusters", [])
                has_comments = len(comment_clusters) > 0
            except Exception as e:
                logger.debug("Comment mining failed, using zero signal: {}", e)
                comment_curve = np.zeros(n_points)

        # ----------------------------------------------------------------
        # 2. Transkript Yoğunluğu + Konuşma Hızı İvmesi
        # ----------------------------------------------------------------
        transcript_curve = np.zeros(n_points)
        speech_rate_curve = np.zeros(n_points)
        has_transcript_density = False
        if transcript:
            try:
                from core.transcript_density import TranscriptDensityAnalyzer

                t_analyzer = TranscriptDensityAnalyzer()
                transcript_curve = t_analyzer.compute_density_curve(
                    transcript_segments=transcript,
                    timeline_times=times,
                    total_duration=float(total_duration),
                )
                has_transcript_density = bool(np.any(transcript_curve > 0.05))

                speech_rate_curve = t_analyzer.compute_speech_rate_acceleration(
                    transcript_segments=transcript,
                    timeline_times=times,
                    total_duration=float(total_duration),
                )
            except Exception as e:
                logger.debug("Transcript/speech-rate analysis failed, using zero signal: {}", e)
                transcript_curve = np.zeros(n_points)
                speech_rate_curve = np.zeros(n_points)

        # ----------------------------------------------------------------
        # 3. Heatmap
        # ----------------------------------------------------------------
        # Gizli viral tespit ve tahmin DB'ye bağımlı metadata
        hidden_viral_peaks: list = []
        heatmap_source = "disabled"
        predicted_confidence = 0.0
        heatmap_curve = np.zeros(n_points)
        has_heatmap_signal = False
        
        from core.scoring_config import HEATMAP_FUSION_ENABLED, HEATMAP_FUSION_WEIGHT
        
        if len(heatmap) > 0 and HEATMAP_FUSION_ENABLED:
            heatmap_source = "real"
            has_heatmap_signal = True
            # Heatmap verisini times dizisine interpolate et
            hm_times = []
            hm_vals = []
            for h in heatmap:
                t_mid = (float(h.get("start_time", 0.0)) + float(h.get("end_time", 0.0))) / 2.0
                hm_times.append(t_mid)
                hm_vals.append(float(h.get("value", 0.0)))
            if hm_times:
                heatmap_curve = np.interp(times, hm_times, hm_vals, left=0.0, right=0.0)
            
        if self._db is not None and view_count > 0:
            try:
                from core.heatmap_predictor import HeatmapPredictor
                predictor = HeatmapPredictor(self._db)
                if len(heatmap) > 0:
                    hidden_viral_peaks = predictor.detect_hidden_viral_from_real(heatmap, view_count)
                else:
                    pred_res = predictor.predict(
                        audio_times=times,
                        audio_spikes=audio_spikes,
                        silence_bursts=silence_bursts,
                        total_duration=int(total_duration),
                        video_id=video_id,
                        view_count=view_count,
                    )
                    if pred_res and pred_res.get("heatmap"):
                        heatmap_source = "predicted"
                        predicted_confidence = float(pred_res.get("confidence", 0.0))
            except Exception as e:
                logger.debug("Heatmap prediction/hidden-viral skipped: {}", e)

        # ----------------------------------------------------------------
        # 4. Pitch Variance & Frame-Diff — timeline'a interpolate et
        # ----------------------------------------------------------------
        pitch_curve = np.zeros(n_points)
        if pitch_variance is not None and len(pitch_variance) > 0:
            if len(pitch_variance) == n_points:
                pitch_curve = pitch_variance
            else:
                # Farklı uzunluktaysa lineer interpolasyon
                pv_times = np.linspace(float(times[0]), float(times[-1]), len(pitch_variance))
                pitch_curve = np.interp(times, pv_times, pitch_variance, left=0.0, right=0.0)

        frame_diff_curve = np.zeros(n_points)
        if frame_diff is not None and len(frame_diff) > 0:
            if len(frame_diff) == n_points:
                frame_diff_curve = frame_diff
            else:
                fd_times = np.linspace(float(times[0]), float(times[-1]), len(frame_diff))
                frame_diff_curve = np.interp(times, fd_times, frame_diff, left=0.0, right=0.0)

        has_pitch = bool(np.any(pitch_curve > 0.05))
        has_frame_diff = bool(np.any(frame_diff_curve > 0.05))
        has_vocal = bool(vocal_spikes is not None and len(vocal_spikes) > 0 and np.any(vocal_spikes > 0.05))

        # ----------------------------------------------------------------
        # 5. Video-bazında Z-score normalizasyon (her sinyal kendi dağılımına göre)
        # ----------------------------------------------------------------
        audio_norm = _zscore_normalize(audio_spikes)
        silence_norm = _zscore_normalize(silence_bursts)
        transcript_norm = _zscore_normalize(transcript_curve) if has_transcript_density else transcript_curve
        comment_norm = _zscore_normalize(comment_curve) if has_comments else comment_curve
        speech_norm = _zscore_normalize(speech_rate_curve) if np.any(speech_rate_curve > 0) else speech_rate_curve
        pitch_norm = _zscore_normalize(pitch_curve) if has_pitch else pitch_curve
        fdiff_norm = _zscore_normalize(frame_diff_curve) if has_frame_diff else frame_diff_curve
        vocal_norm = _zscore_normalize(vocal_spikes) if (has_vocal and vocal_spikes is not None) else np.zeros(n_points)
        heatmap_norm = _zscore_normalize(heatmap_curve) if has_heatmap_signal else heatmap_curve

        # ----------------------------------------------------------------
        # 6. Adaptif Ağırlık Füzyonu (Yorum & Vokal & Sinyal Entegrasyonu)
        # ----------------------------------------------------------------
        # Sinyal varlığına göre ağırlıklar dinamik olarak ayarlanır.
        # Temel ağırlık: audio %20, silence %15
        # Yorum sinyali: izleyici ilgisinin doğrudan kanıtı (%35 ağırlık)
        # Vokal/konuşma sinyali: %20 ağırlık alarak oyun içi gürültüleri filtreler.

        base_audio_w = 0.20
        base_silence_w = 0.15
        optional_signals = []
        if has_comments:
            optional_signals.append(("comment", comment_norm, 0.35))
        if has_heatmap_signal:
            optional_signals.append(("heatmap", heatmap_norm, float(HEATMAP_FUSION_WEIGHT)))
        if has_vocal:
            optional_signals.append(("vocal", vocal_norm, 0.20))
        if has_transcript_density:
            optional_signals.append(("transcript", transcript_norm, 0.12))
        if np.any(speech_rate_curve > 0):
            optional_signals.append(("speech_rate", speech_norm, 0.08))
        if has_pitch:
            optional_signals.append(("pitch", pitch_norm, 0.08))
        if has_frame_diff:
            optional_signals.append(("frame_diff", fdiff_norm, 0.07))

        opt_total_w = sum(w for _, _, w in optional_signals)
        remaining = 1.0 - (base_audio_w + base_silence_w)
        if opt_total_w > 0:
            scale = min(1.0, remaining / opt_total_w)
        else:
            scale = 1.0
            base_audio_w += remaining * 0.55
            base_silence_w += remaining * 0.45

        composite_score = (audio_norm * base_audio_w) + (silence_norm * base_silence_w)
        for _, arr, w in optional_signals:
            composite_score = composite_score + arr * (w * scale)

        # ----------------------------------------------------------------
        # 7. Peak Bulma & Cluster Birleştirme
        # ----------------------------------------------------------------
        candidate_indices = np.where(composite_score > 0.18)[0]
        if len(candidate_indices) < self.top_n:
            fallback_indices = np.argsort(composite_score)[::-1][: self.top_n]
            candidate_indices = np.unique(np.concatenate([candidate_indices, fallback_indices]))

        clusters: list[dict[str, Any]] = []
        for idx in candidate_indices:
            t = times[idx]
            score = float(composite_score[idx])
            merged = False
            for c in clusters:
                if abs(t - c["peak_time"]) <= self.merge_threshold_sec:
                    if score > c["score"]:
                        c["peak_time"] = t
                        c["score"] = score
                    c["indices"].append(idx)
                    merged = True
                    break
            if not merged:
                clusters.append({"peak_time": t, "score": score, "indices": [idx], "is_vip": False})

        # --- VIP Yorum Tohumlaması (Comment VIP Injection) ---
        # İzleyicilerin yorumlarda bizzat güldüğü/dikkat çektiği anlar (örn. 5:13)
        # doğrudan VIP adayı olarak havuza en yüksek öncelikle enjekte edilir.
        if comment_clusters:
            for comm_cl in comment_clusters:
                comm_t = float(comm_cl["time"])
                idx_comm = int(np.argmin(np.abs(times - comm_t)))
                base_c_score = float(composite_score[idx_comm]) if idx_comm < len(composite_score) else 0.5
                vip_score = max(0.96, min(1.0, base_c_score + 0.50))

                found = False
                for c in clusters:
                    if abs(c["peak_time"] - comm_t) <= self.merge_threshold_sec:
                        c["score"] = max(c["score"], vip_score)
                        c["is_vip"] = True
                        c["comment_info"] = comm_cl
                        found = True
                        break
                if not found:
                    clusters.append(
                        {
                            "peak_time": comm_t,
                            "score": vip_score,
                            "indices": [idx_comm],
                            "is_vip": True,
                            "comment_info": comm_cl,
                        }
                    )

        # ----------------------------------------------------------------
        # 8. Çeşitlilik Kısıtı — art arda aşırı yakın anları dengele (Makul 20-30s aralık)
        # ----------------------------------------------------------------
        # VIP yorum adayları önceliklidir
        clusters.sort(key=lambda x: (1 if x.get("is_vip") else 0, x["score"]), reverse=True)
        min_gap_sec = max(float(self.merge_threshold_sec), min(30.0, float(total_duration) * self.min_diversity_ratio))

        diverse_clusters: list[dict[str, Any]] = []
        for clu in clusters:
            too_close = any(
                abs(clu["peak_time"] - accepted["peak_time"]) < min_gap_sec for accepted in diverse_clusters
            )
            # VIP adaylar veya yeterli mesafedeki adaylar kabul edilir
            if not too_close or clu.get("is_vip"):
                diverse_clusters.append(clu)
            if len(diverse_clusters) >= self.top_n:
                break

        selected_clusters = diverse_clusters

        # ----------------------------------------------------------------
        # 9. Aday nesneleri oluştur (Dinamik Pencere dahil)
        # ----------------------------------------------------------------
        candidates = []
        half_win_default = self.candidate_window_sec / 2.0

        for cand_id, clus in enumerate(selected_clusters, start=1):
            peak_t = clus["peak_time"]

            # --- Dinamik Pencere: sinyal baseline'a dönüş noktasını bul ---
            if self.dynamic_window and len(times) >= 10 and (times[-1] - times[0]) >= 30.0:
                idx_peak = int(np.argmin(np.abs(times - peak_t)))
                baseline = float(np.median(composite_score))

                # Başlangıç: geriye git, sinyal baseline altına düşene kadar
                win_start_idx = idx_peak
                for j in range(idx_peak - 1, -1, -1):
                    if composite_score[j] <= baseline:
                        win_start_idx = j
                        break

                # Bitiş: ileriye git, sinyal baseline altına düşene kadar
                win_end_idx = idx_peak
                for j in range(idx_peak + 1, len(times)):
                    if composite_score[j] <= baseline:
                        win_end_idx = j
                        break

                dyn_start = float(times[win_start_idx])
                dyn_end = float(times[win_end_idx])
                dyn_half = (dyn_end - dyn_start) / 2.0

                # Min/max sınırları uygula
                dyn_half = np.clip(dyn_half, self.min_window_sec / 2.0, self.max_window_sec / 2.0)
                half_win = float(dyn_half)
            else:
                half_win = half_win_default

            start_t = max(0.0, peak_t - half_win)
            end_t = min(float(total_duration), peak_t + half_win)

            # Minimum klip süresi garantisi
            if (end_t - start_t) < self.min_window_sec:
                extra = (self.min_window_sec - (end_t - start_t)) / 2.0
                start_t = max(0.0, start_t - extra)
                end_t = min(float(total_duration), end_t + extra)

            # --- Semantik Setup & Punchline Genişletmesi ---
            # Eğer diyalog/espri başlamışsa cümlenin başını ve vurucu sonunu içine al
            if transcript:
                matching_segs = [
                    seg
                    for seg in transcript
                    if float(seg.get("end", float(seg.get("start", 0)) + float(seg.get("duration", 0)))) >= start_t
                    and float(seg.get("start", 0)) <= end_t
                ]
                if matching_segs:
                    first_seg_start = float(matching_segs[0].get("start", start_t))
                    last_seg_end = float(
                        matching_segs[-1].get(
                            "end",
                            float(matching_segs[-1].get("start", 0)) + float(matching_segs[-1].get("duration", 0)),
                        )
                    )
                    if 0 < (start_t - first_seg_start) <= 3.0:
                        start_t = max(0.0, first_seg_start)
                    if 0 < (last_seg_end - end_t) <= 3.0:
                        end_t = min(float(total_duration), last_seg_end)

            # Transkript metni
            matching_text = []
            if transcript:
                for seg in transcript:
                    seg_start = float(seg.get("start", 0.0))
                    seg_end = float(seg.get("end", seg_start + float(seg.get("duration", 0.0))))
                    if seg_end >= start_t and seg_start <= end_t:
                        matching_text.append(seg.get("text", ""))
            transcript_snippet = " ".join(matching_text).strip()

            idx_near = int(np.argmin(np.abs(times - peak_t)))

            # Yorum kümesi eşleştir
            matched_comment_cl = clus.get("comment_info")
            if not matched_comment_cl:
                for cl in comment_clusters:
                    if abs(cl["time"] - peak_t) <= half_win:
                        matched_comment_cl = cl
                        break

            is_vip_candidate = bool(
                clus.get("is_vip") or (matched_comment_cl and matched_comment_cl.get("count", 0) >= 1)
            )

            # Heatmap kontrolü
            matching_hm = [
                float(h.get("value", 0.0))
                for h in (heatmap or [])
                if float(h.get("start_time", 0.0)) <= peak_t <= float(h.get("end_time", 0.0))
            ]
            hm_val = (
                float(max(matching_hm))
                if matching_hm
                else (float(heatmap[0].get("value", 0.0)) if (heatmap and len(heatmap) > 0) else 0.0)
            )
            has_hm = bool(
                heatmap_source == "real"
                or (heatmap and len(heatmap) > 0 and (hm_val > 0.0 or heatmap[0].get("value", 0) > 0))
            )

            candidates.append(
                {
                    "candidate_id": cand_id,
                    "peak_time": round(float(peak_t), 1),
                    "peak_formatted": YouTubeExtractor.format_seconds(peak_t),
                    "start_time": round(float(start_t), 1),
                    "start_formatted": YouTubeExtractor.format_seconds(start_t),
                    "end_time": round(float(end_t), 1),
                    "end_formatted": YouTubeExtractor.format_seconds(end_t),
                    "duration": round(float(end_t - start_t), 1),
                    "fusion_score": int(clus["score"] * 100),
                    "is_vip": is_vip_candidate,
                    "from_comment": bool(matched_comment_cl is not None or clus.get("is_vip")),
                    "signals": {
                        "audio_spike": round(float(audio_spikes[idx_near]), 2),
                        "silence_burst": round(float(silence_bursts[idx_near]), 2),
                        "vocal_spike": round(float(vocal_spikes[idx_near]), 2) if (has_vocal and vocal_spikes is not None) else 0.0,
                        "has_heatmap": has_hm,
                        "heatmap_val": round(hm_val, 2),
                        "heatmap_source": heatmap_source
                        if heatmap_source != "disabled"
                        else ("real" if has_hm else "disabled"),
                        "predicted_confidence": predicted_confidence,
                        "comment_density": round(float(comment_curve[idx_near]), 2) if has_comments else 0.0,
                        "comment_reaction": matched_comment_cl.get("dominant_reaction") if matched_comment_cl else None,
                        "comment_count": matched_comment_cl.get("count", 0) if matched_comment_cl else 0,
                        "transcript_density": round(float(transcript_curve[idx_near]), 2)
                        if has_transcript_density
                        else 0.0,
                        "speech_rate_accel": round(float(speech_rate_curve[idx_near]), 2),
                        "pitch_variance": round(float(pitch_curve[idx_near]), 2),
                        "frame_diff": round(float(frame_diff_curve[idx_near]), 2),
                    },
                    "hidden_viral": any(abs(hvp["time"] - peak_t) <= half_win for hvp in hidden_viral_peaks),
                    "comment_samples": matched_comment_cl.get("samples", []) if matched_comment_cl else [],
                    "transcript_snippet": transcript_snippet or "Ses/Tepki ağırlıklı an (Konuşma transkripti yok)",
                }
            )

        # Kronolojik sırayla döndür
        candidates.sort(key=lambda x: x["start_time"])
        return candidates
