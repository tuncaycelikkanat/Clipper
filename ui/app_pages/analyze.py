"""
ui/app_pages/analyze.py — Main autonomous analysis & editing studio
"""

import os
import re
from pathlib import Path
import streamlit as st
import plotly.graph_objects as go

from core.extractor import YouTubeExtractor
from core.audio_dsp import AudioDSPAnalyzer
from core.candidate_ranker import CandidateRanker
from core.transcript import TranscriptManager
from core.llm_engine import GeminiHighlightEngine
from core.aligner import AlignmentEngine
from core.quality_evaluator import QualityEvaluator
from core.cutter import VideoCutter
from core.thumbnail import ThumbnailGenerator
from core.database import DatabaseManager

db = DatabaseManager()
db.init_db()

# ── Session State Initialization ──────────────────────────────────────────────
if "video_data" not in st.session_state:
    st.session_state.video_data = None
if "signals" not in st.session_state:
    st.session_state.signals = None
if "candidates" not in st.session_state:
    st.session_state.candidates = None
if "clips" not in st.session_state:
    st.session_state.clips = None
if "transcript" not in st.session_state:
    st.session_state.transcript = None
if "quality_reports" not in st.session_state:
    st.session_state.quality_reports = {}
if "generated_clips" not in st.session_state:
    st.session_state.generated_clips = {}
if "sample_url" not in st.session_state:
    st.session_state.sample_url = ""

# ── Header ────────────────────────────────────────────────────────────────────
st.header("Otonom Klip Analizi & Edit", anchor=False)
st.caption("5 katmanlı sinyal işleme ve Gemini yapay zekası ile YouTube videolarından viral dikey klipler çıkarın.")

# ── Sidebar: Edit Config & Engine Settings ─────────────────────────────────────
with st.sidebar:
    st.subheader("Edit & Render Ayarları")
    
    target_clips = st.slider(
        "Hedef Klip Sayısı",
        min_value=1,
        max_value=20,
        value=3,
        help="Analiz sonrası üretilecek en iyi klip sayısı (1 - 20)"
    )

    selected_render_mode = st.segmented_control(
        "Klip Formatı",
        options=[
            "9:16 Akıllı Dikey (Facecam / Blur)",
            "9:16 Siyah Arkaplan",
            "1:1 Kare",
            "16:9 Orijinal"
        ],
        default="9:16 Akıllı Dikey (Facecam / Blur)",
        help="Çıktı video en-boy oranı ve arkaplan yerleşimi. Akıllı dikey modda Facecam varsa orantılı split, yoksa dikey ortalı sinematik blur uygulanır."
    )
    
    render_mode_map = {
        "9:16 Akıllı Dikey (Facecam / Blur)": "shorts_9x16_blur",
        "9:16 Siyah Arkaplan": "shorts_9x16_black",
        "1:1 Kare": "square_1x1_black",
        "16:9 Orijinal": "original_16x9",
    }
    render_mode_val = render_mode_map.get(selected_render_mode, "shorts_9x16_blur")

    st.markdown("---")
    st.subheader("Efektler & Filtreler")
    enable_subtitles = st.toggle("Karaoke Altyazı (ASS)", value=False, help="Açıkken kelime vurgulu dinamik altyazı ekler.")
    enable_hook_card = st.toggle("Kanca Başlık Kartı (İlk 3 Sn)", value=False, help="İlk 3 saniye animasyonlu dikkat çekici başlık ekler.")
    enable_color_grade = st.toggle("Renk İyileştirme (+Vibrance)", value=True, help="FFmpeg canlı renk & kontrast filtresi")
    use_whisper = st.toggle("Whisper Kelime Senkronu", value=True, help="faster-whisper ile milisaniyelik kelime zamanlaması")
    
    st.markdown("---")
    active_key = os.environ.get("GEMINI_API_KEY", "")
    if active_key:
        st.success("Gemini API Bağlı", icon=":material/check_circle:")
    else:
        st.warning("GEMINI_API_KEY eksik. Heuristic mod aktif.", icon=":material/warning:")

# ── Top Section: Video Input ──────────────────────────────────────────────────
with st.container(border=True):
    col_input, col_action = st.columns([4, 1], vertical_alignment="bottom")
    
    with col_input:
        default_url = st.session_state.sample_url or ""
        url_input = st.text_input(
            "YouTube Video Linki",
            value=default_url,
            placeholder="https://www.youtube.com/watch?v=...",
            help="Herhangi bir YouTube Gaming videosu veya canlı yayın kaydı URL'si girin."
        )
    
    with col_action:
        analyze_btn = st.button("Analizi Başlat", type="primary", icon=":material/play_arrow:", width="stretch")

    col_quick, col_opts = st.columns([3, 2], vertical_alignment="center")
    with col_quick:
        sample_choice = st.pills(
            "Hızlı Örnekler",
            options=["Steve Jobs (Transkript)", "MKBHD (Hibrit)", "Rick Astley (Heatmap)"],
            selection_mode="single",
            label_visibility="collapsed"
        )
        if sample_choice == "Steve Jobs (Transkript)":
            st.session_state.sample_url = "https://www.youtube.com/watch?v=UF8uR6Z6KLc"
            st.rerun()
        elif sample_choice == "MKBHD (Hibrit)":
            st.session_state.sample_url = "https://www.youtube.com/watch?v=34d7Kj7f-yQ"
            st.rerun()
        elif sample_choice == "Rick Astley (Heatmap)":
            st.session_state.sample_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            st.rerun()

    with col_opts:
        force_reanalyze = st.checkbox("Önbelleği Yoksay (Sıfırdan Analiz)", value=False)

# ── Analysis Execution ─────────────────────────────────────────────────────────
if analyze_btn and url_input:
    with st.status("Video analiz ediliyor...", expanded=True) as status:
        try:
            st.write("🔍 [Katman 1/5] Video bilgileri ve transkript çekiliyor...")
            video_data = YouTubeExtractor.get_video_data(url_input)
            cached_clips = None

            if not force_reanalyze and db.video_exists(video_data["id"]):
                cached_clips = db.get_clips_for_video(video_data["id"])
                if cached_clips:
                    for c in cached_clips:
                        c["start_formatted"] = YouTubeExtractor.format_seconds(c["start_time"])
                        c["end_formatted"] = YouTubeExtractor.format_seconds(c["end_time"])
                        c["duration_formatted"] = f"{int(c['duration'])} sn"

                    st.session_state.video_data = video_data
                    st.session_state.clips = cached_clips
                    st.session_state.transcript = TranscriptManager.get_transcript(video_data["id"])
                    st.session_state.signals = {"times": [], "rms": [], "audio_spikes": [], "silence_bursts": []}
                    st.session_state.candidates = []
                    st.session_state.quality_reports = {}
                    st.session_state.generated_clips = {}
                    status.update(label="Önbellekten başarıyla yüklendi!", state="complete", expanded=False)
                    st.toast("Sonuçlar önbellekten saniyeler içinde getirildi! ⚡", icon="⚡")

            if force_reanalyze or not db.video_exists(video_data["id"]) or not cached_clips:
                st.session_state.video_data = video_data
                transcript = TranscriptManager.get_transcript(video_data["id"])
                st.session_state.transcript = transcript

                st.write("🔊 [Katman 2/5] Paralel ses DSP: Enerji patlamaları ve sessizlik şokları taranıyor...")
                times, rms = AudioDSPAnalyzer.extract_audio_energy(
                    video_data["url"], duration_sec=video_data["duration"]
                )
                dsp_signals = AudioDSPAnalyzer.detect_signals(times, rms)
                st.session_state.signals = dsp_signals

                pool_size = max(target_clips * 3, 15)
                st.write(f"🎯 [Katman 3/5] Çoklu sinyal füzyonu ile Top-{pool_size} aday havuzu oluşturuluyor...")
                ranker = CandidateRanker(candidate_window_sec=35, merge_threshold_sec=8, top_n=pool_size)
                candidates = ranker.fuse_signals_and_generate_candidates(
                    times=dsp_signals["times"],
                    audio_spikes=dsp_signals["audio_spikes"],
                    silence_bursts=dsp_signals["silence_bursts"],
                    heatmap=video_data["heatmap"],
                    transcript=transcript,
                    total_duration=video_data["duration"],
                )
                st.session_state.candidates = candidates

                st.write(f"🤖 [Katman 4/5] Gemini yapay zekası viral potansiyeli en yüksek {target_clips} klibi seçiyor...")
                if active_key:
                    judged_clips = GeminiHighlightEngine.batch_judge_gaming_candidates(
                        candidates=candidates,
                        video_title=video_data["title"],
                        total_duration=video_data["duration"],
                        target_clips=target_clips,
                        api_key=active_key,
                    )
                else:
                    judged_clips = []
                    for rank, c in enumerate(candidates[:target_clips], start=1):
                        judged_clips.append({
                            "rank": rank,
                            "title": f"Highlight #{rank}",
                            "category": "ACTION",
                            "score": c["fusion_score"],
                            "hook_caption": "İşte o an!",
                            "reason": "Sinyal işleme zirve noktası",
                            "start_time": c["start_time"],
                            "start_formatted": c["start_formatted"],
                            "end_time": c["end_time"],
                            "end_formatted": c["end_formatted"],
                            "duration": c["duration"],
                            "duration_formatted": f"{int(c['duration'])} sn",
                            "text": c["transcript_snippet"],
                        })

                st.write("✂️ [Katman 5/5] Kesim noktaları sessizlik sınırlarına hizalanıyor...")
                final_clips = []
                for c in judged_clips:
                    ref_start, ref_end = AlignmentEngine.refine_cut_points(
                        c["start_time"],
                        c["end_time"],
                        times=dsp_signals["times"],
                        rms=dsp_signals["rms"],
                        transcript=transcript,
                    )
                    c["start_time"] = ref_start
                    c["start_formatted"] = YouTubeExtractor.format_seconds(ref_start)
                    c["end_time"] = ref_end
                    c["end_formatted"] = YouTubeExtractor.format_seconds(ref_end)
                    c["duration"] = round(ref_end - ref_start, 1)
                    c["duration_formatted"] = f"{int(c['duration'])} sn"
                    final_clips.append(c)

                st.write("📊 Kalite denetimi ve karne puanlaması yapılıyor...")
                quality_reports: dict = {}
                for c in final_clips:
                    report = QualityEvaluator.evaluate_clip(
                        clip=c,
                        video_title=video_data["title"],
                        times=dsp_signals["times"],
                        rms=dsp_signals["rms"],
                        transcript=transcript,
                        api_key=active_key,
                    )
                    quality_reports[c["rank"]] = report

                try:
                    db.save_video(video_data)
                    db.save_clips(video_data["id"], final_clips)
                except Exception as e:
                    st.error(f"Veritabanı kayıt hatası: {e}")

                # Auto-generate thumbnails for all selected clips
                st.write("🖼️ Kapak resimleri (thumbnails) otomatik üretiliyor...")
                try:
                    safe_uploader_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', video_data.get("uploader", "Kanal")).strip("_")
                    thumb_dir = os.path.join("outputs", "thumbnails", safe_uploader_name)
                    ThumbnailGenerator.batch_generate_thumbnails(
                        clips=final_clips,
                        video_path_or_url=video_data["url"],
                        output_dir=thumb_dir
                    )
                except Exception as e:
                    st.warning(f"Thumbnail üretimi başarısız oldu: {e}")
                st.session_state.quality_reports = quality_reports
                st.session_state.generated_clips = {}
                status.update(label=f"Analiz tamamlandı! {len(final_clips)} klip ve thumbnail hazır.", state="complete", expanded=False)
                st.toast("Analiz ve kapak resimleri başarıyla tamamlandı!", icon="🎉")

        except Exception as e:
            status.update(label=f"Hata oluştu: {str(e)}", state="error")
            st.error(f"İşlem sırasında bir hata oluştu: {str(e)}")

# ── Results & Clip Studio Display ─────────────────────────────────────────────
if st.session_state.video_data and st.session_state.clips:
    vdata = st.session_state.video_data
    clips = st.session_state.clips
    signals = st.session_state.signals or {}
    reports = st.session_state.quality_reports or {}

    # Video Overview Card
    with st.container(border=True):
        col_thumb, col_meta = st.columns([1, 2], vertical_alignment="center")
        with col_thumb:
            if vdata.get("thumbnail"):
                st.image(vdata["thumbnail"], width="stretch")
        with col_meta:
            st.subheader(vdata["title"], anchor=False)
            st.caption(f"Kanal: **{vdata['uploader']}** | Süre: **{vdata['duration_formatted']}**")
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("İzlenme", f"{vdata.get('view_count', 0):,}")
            m2.metric("Isı Haritası", "Mevcut" if vdata.get("has_heatmap") else "Yok")
            m3.metric("Seçilen Klip", len(clips))
            m4.metric("Format", selected_render_mode)

    # Signal waveform chart expander (if signals available)
    if signals and len(signals.get("times", [])) > 0:
        with st.expander("Sinyal Füzyonu & Dalga Formu Grafiği", icon=":material/show_chart:"):
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=signals["times"], y=signals["rms"],
                mode="lines", name="Ses RMS Enerjisi",
                line=dict(color="#61afef", width=1.5)
            ))
            for clip in clips:
                fig.add_vrect(
                    x0=clip["start_time"], x1=clip["end_time"],
                    fillcolor="rgba(97, 175, 239, 0.2)",
                    layer="below", line_width=1, line_color="#98c379",
                    annotation_text=f"Klip #{clip['rank']}",
                    annotation_position="top left"
                )
            fig.update_layout(
                xaxis_title="Zaman (Saniye)",
                yaxis_title="Normalize Sinyal",
                margin=dict(l=10, r=10, t=20, b=10),
                height=260,
                template="plotly_dark"
            )
            st.plotly_chart(fig, width="stretch")

    # Final Clips Studio
    st.subheader(f"Seçilen Klipler ({len(clips)})", anchor=False)
    
    safe_uploader = re.sub(r'[^a-zA-Z0-9_\-]', '_', vdata.get("uploader", "Kanal")).strip("_")
    channel_out_dir = os.path.join("outputs", "clips", safe_uploader)
    os.makedirs(channel_out_dir, exist_ok=True)
    cutter = VideoCutter(output_dir=channel_out_dir)

    for idx, clip in enumerate(clips):
        rank = clip["rank"]
        clip_key = f"clip_{idx}_{rank}_{clip['start_time']}_{clip['end_time']}_{render_mode_val}_{enable_subtitles}_{enable_hook_card}_{enable_color_grade}"
        q_report = reports.get(rank, {})
        category = clip.get("category", "HIGHLIGHT")

        with st.container(border=True):
            # Clip header with clean badges
            col_h1, col_h2 = st.columns([3, 1], vertical_alignment="center")
            with col_h1:
                st.markdown(
                    f":violet-background[**{category}**] **{clip['title']}** "
                    f"| :green-background[Not: {q_report.get('grade', 'A')} (%{q_report.get('composite_score', clip.get('score', 90))})]"
                )
                if clip.get("hook_caption"):
                    st.info(f"**Kanca (İlk 3 Sn):** \"{clip['hook_caption']}\"", icon=":material/campaign:")
            with col_h2:
                st.metric("Viral Potansiyeli", f"%{clip.get('score', 90)}")

            # Controls and Player layout
            col_ctrl, col_preview = st.columns([3, 2], gap="medium")

            with col_ctrl:
                time_range = st.slider(
                    f"Klip #{rank} Sınır Ayarı (Saniye)",
                    min_value=0.0,
                    max_value=float(vdata["duration"]),
                    value=(float(clip["start_time"]), float(clip["end_time"])),
                    step=0.5,
                    key=f"slider_{clip_key}"
                )
                start_sel, end_sel = time_range
                dur_sel = round(end_sel - start_sel, 1)
                st.caption(f"⏱️ Seçilen Aralık: **{YouTubeExtractor.format_seconds(start_sel)} - {YouTubeExtractor.format_seconds(end_sel)}** ({dur_sel} sn)")

                if clip.get("reason"):
                    st.caption(f"💡 {clip['reason']}")

                # Render & Thumbnail buttons
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    render_click = st.button("Bu Klibi Edit & İndir", key=f"btn_render_{clip_key}", icon=":material/movie_edit:", type="primary", width="stretch")
                with col_b2:
                    thumb_click = st.button("Thumbnail Üret", key=f"btn_thumb_{clip_key}", icon=":material/image:", width="stretch")

                # Feedback loop using native st.feedback
                st.caption("Klip Kalite Geri Bildirimi:")
                fb = st.feedback("thumbs", key=f"fb_{clip_key}")
                if fb is not None:
                    st.toast("Geri bildiriminiz kaydedildi!", icon="👍")

                if render_click:
                    with st.spinner("Video FFmpeg ile kesiliyor ve işleniyor..."):
                        try:
                            clip_path = cutter.cut_clip(
                                url=vdata["url"],
                                start_time=start_sel,
                                end_time=end_sel,
                                clip_id=f"{rank}",
                                video_title=vdata["title"],
                                hook_caption=clip.get("hook_caption", ""),
                                transcript_segments=st.session_state.transcript,
                                render_mode=render_mode_val,
                                add_subtitles=enable_subtitles,
                                add_hook_card=enable_hook_card,
                                enhance_colors=enable_color_grade,
                                use_whisper=use_whisper
                            )
                            st.session_state.generated_clips[clip_key] = clip_path
                            try:
                                db.save_video(vdata)
                                db.save_clips(vdata["id"], [clip])
                            except Exception as e:
                                st.warning(f"Veritabanı kayıt hatası: {e}")
                            db.save_render(clip.get("id", f"{vdata['id']}_clip_{rank}"), render_mode_val, clip_path)
                            
                            # Automatically generate thumbnail from newly rendered clip
                            try:
                                thumb_dir = os.path.join("outputs", "thumbnails", safe_uploader)
                                ThumbnailGenerator.batch_generate_thumbnails(
                                    clips=[{**clip, "start_time": 0.0, "end_time": dur_sel}],
                                    video_path_or_url=clip_path,
                                    output_dir=thumb_dir
                                )
                            except Exception as e:
                                st.warning(f"Thumbnail üretimi başarısız oldu: {e}")

                            st.success("Klip ve thumbnail başarıyla editlendi ve hazır!", icon=":material/check:")
                        except Exception as e:
                            st.error(f"Klip render hatası: {str(e)}")

                if thumb_click:
                    with st.spinner("3 farklı kritik kareden kapak resimleri yakalanıyor..."):
                        try:
                            thumb_dir = os.path.join("outputs", "thumbnails", safe_uploader)
                            source_media = vdata["url"]
                            clip_start_arg = start_sel
                            if clip_key in st.session_state.generated_clips and os.path.exists(st.session_state.generated_clips[clip_key]):
                                source_media = st.session_state.generated_clips[clip_key]
                                clip_start_arg = 0.0

                            gen_paths = ThumbnailGenerator.extract_candidates(
                                clip={**clip, "start_time": clip_start_arg, "end_time": clip_start_arg + dur_sel},
                                video_path_or_url=source_media,
                                output_dir=thumb_dir
                            )
                            if gen_paths:
                                st.toast("3 farklı kapak karesi başarıyla üretildi!", icon="🖼️")
                                st.rerun()
                            else:
                                st.error("Thumbnail oluşturulamadı.")
                        except Exception as e:
                            st.error(f"Thumbnail hatası: {str(e)}")

            with col_preview:
                thumb_dir = os.path.join("outputs", "thumbnails", safe_uploader)
                main_thumb = os.path.join(thumb_dir, f"clip_{rank}_thumb.jpg")
                hook_thumb = os.path.join(thumb_dir, f"clip_{rank}_thumb_hook.jpg")
                action_thumb = os.path.join(thumb_dir, f"clip_{rank}_thumb_action.jpg")
                
                if clip_key in st.session_state.generated_clips:
                    rendered_file = st.session_state.generated_clips[clip_key]
                    if os.path.exists(rendered_file):
                        st.video(rendered_file)
                        with open(rendered_file, "rb") as f:
                            st.download_button(
                                label="MP4 Olarak İndir",
                                data=f,
                                file_name=os.path.basename(rendered_file),
                                mime="video/mp4",
                                icon=":material/download:",
                                width="stretch"
                            )
                elif os.path.exists(main_thumb):
                    frame_options = {"💥 Zirve Şok": main_thumb}
                    if os.path.exists(hook_thumb):
                        frame_options["🎯 Giriş Kancası"] = hook_thumb
                    if os.path.exists(action_thumb):
                        frame_options["🔥 Aksiyon Anı"] = action_thumb

                    if len(frame_options) > 1:
                        sel_frame = st.segmented_control(
                            "Kapak Karesi Seç",
                            options=list(frame_options.keys()),
                            default="💥 Zirve Şok",
                            key=f"thumb_choice_{clip_key}"
                        )
                        active_thumb = frame_options.get(sel_frame, main_thumb)
                    else:
                        active_thumb = main_thumb

                    st.image(active_thumb, caption=f"Klip #{rank} Kapak Resmi", width="stretch")
                    with open(active_thumb, "rb") as f:
                        st.download_button(
                            label="Thumbnail İndir (JPG)",
                            data=f,
                            file_name=os.path.basename(active_thumb),
                            mime="image/jpeg",
                            icon=":material/image:",
                            width="stretch",
                            key=f"dl_thumb_{clip_key}"
                        )
                else:
                    st.info("Klibi izlemek için 'Edit & İndir'e, kapak resmi yakalamak için 'Thumbnail Üret'e basın.", icon=":material/play_circle:")
