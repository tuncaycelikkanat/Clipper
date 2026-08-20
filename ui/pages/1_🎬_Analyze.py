"""
ui/pages/1_🎬_Analyze.py — Main analysis page.

This is the original analysis pipeline from ui/app.py, now organised as a
Streamlit multipage page. All five pipeline layers run here.
"""

import os
import sys
import re
from pathlib import Path
from dotenv import load_dotenv

# Ensure project root is on sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

load_dotenv(os.path.join(root_dir, ".env"))

import streamlit as st
import plotly.graph_objects as go
import numpy as np

from core.extractor import YouTubeExtractor
from core.audio_dsp import AudioDSPAnalyzer
from core.candidate_ranker import CandidateRanker
from core.transcript import TranscriptManager
from core.llm_engine import GeminiHighlightEngine
from core.aligner import AlignmentEngine
from core.quality_evaluator import QualityEvaluator
from core.cutter import VideoCutter
from core.database import DatabaseManager

db = DatabaseManager()
db.init_db()

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #FF0055, #7928CA, #0070F3);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #888888;
        margin-bottom: 1.5rem;
    }
    .gaming-badge {
        display: inline-block;
        background: linear-gradient(135deg, #FF0055, #7928CA);
        color: white;
        padding: 4px 12px;
        border-radius: 14px;
        font-weight: bold;
        font-size: 0.85rem;
        margin-right: 8px;
    }
    .hook-badge {
        background-color: rgba(255, 0, 85, 0.15);
        border-left: 4px solid #FF0055;
        padding: 8px 12px;
        border-radius: 4px;
        font-weight: 600;
        color: #FF77A9;
        margin-top: 6px;
        margin-bottom: 6px;
    }
</style>
""", unsafe_allow_html=True)

# Session state initialisation
for key, default in [
    ("video_data", None),
    ("signals", None),
    ("candidates", None),
    ("clips", None),
    ("transcript", None),
    ("quality_reports", {}),
    ("generated_clips", {}),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/e/ef/Youtube_logo.png", width=140)
    st.title("🎮 Gaming AI Edit Studio")

    st.subheader("🔑 Gemini Flash API")
    env_key = os.environ.get("GEMINI_API_KEY", "")
    gemini_api_key = st.text_input(
        "Gemini API Key",
        value=env_key,
        type="password",
        help="Google Gemini API anahtarınız .env dosyasından otomatik yüklendi.",
    )
    active_key = gemini_api_key or env_key
    if active_key:
        st.success("✅ Gemini Flash & Judge Aktif!")
    else:
        st.warning("⚠️ API anahtarı giriniz.")

    st.divider()
    st.subheader("🎬 Programatik Edit Efektleri")
    enable_subtitles = st.toggle("🎤 Dinamik & Renkli Altyazı Ekle", value=True,
        help="Konuşmayla senkronize kalın sarı vurgulu altyazı yakar.")
    enable_hook_card = st.toggle("🎯 İlk 3 Sn Kanca Başlığı Kartı", value=True,
        help="Videonun başında dikkat çeken kanca yazısını gösterir.")
    enable_color_grade = st.toggle("🎨 Canlı Renk İyileştirme (+%20)", value=True,
        help="Mobil ekranlarda renkleri ve kontrastı canlandırır.")
    use_whisper = st.toggle(
        "🎙️ Whisper Kelime Zamanlama (Daha İyi Senkron)",
        value=False,
        help="faster-whisper ile gerçek kelime zaman damgası. İlk kullanımda model indirilir (~150MB).",
    )

    st.divider()
    st.subheader("📱 Çıktı / En-Boy Oranı")
    format_choice = st.selectbox(
        "Render Formatı",
        options=[
            "⬛ 1:1 Kare Shorts (Siyah Arka Plan)",
            "📱 9:16 Shorts (Bulanık Arka Plan)",
            "⬛ 9:16 Shorts (Siyah Arka Plan)",
            "📺 Orijinal 16:9 Yatay",
        ],
        index=0,
    )
    mode_mapping = {
        "⬛ 1:1 Kare Shorts (Siyah Arka Plan)": "square_1x1_black",
        "📱 9:16 Shorts (Bulanık Arka Plan)": "shorts_9x16_blur",
        "⬛ 9:16 Shorts (Siyah Arka Plan)": "shorts_9x16_black",
        "📺 Orijinal 16:9 Yatay": "original",
    }
    selected_render_mode = mode_mapping[format_choice]

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="main-header">🎮 Gaming Vertical — Otonom Klip & Video Edit Stüdyosu</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-header">5 Katmanlı Mimari + Dinamik Altyazı + İlk 3 Sn Kanca Kartı + Canlı Renk Düzenlemesi</div>',
    unsafe_allow_html=True,
)

# ── URL input ─────────────────────────────────────────────────────────────────
col_url, col_btn = st.columns([5, 1])
with col_url:
    url_input = st.text_input(
        "YouTube Gaming / Yayın VOD Linki",
        placeholder="https://www.youtube.com/watch?v=...",
        label_visibility="collapsed",
    )
    force_reanalyze = st.checkbox("Önbelleği Yoksay (Yeniden Analiz Et)", value=False)
with col_btn:
    analyze_btn = st.button("🚀 Otonom Analiz & Edit", type="primary", use_container_width=True)

# Quick sample buttons
st.caption("Hızlı test örnekleri:")
sample_col1, sample_col2, sample_col3, _ = st.columns([2.5, 2.5, 2.5, 1.5])
with sample_col1:
    if st.button("🎙️ Steve Jobs (Transkript)", use_container_width=True):
        url_input = "https://www.youtube.com/watch?v=UF8uR6Z6KLc"
        analyze_btn = True
with sample_col2:
    if st.button("📱 MKBHD Review (Hibrit)", use_container_width=True):
        url_input = "https://www.youtube.com/watch?v=34d7Kj7f-yQ"
        analyze_btn = True
with sample_col3:
    if st.button("🎵 Rick Astley (Heatmap)", use_container_width=True):
        url_input = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        analyze_btn = True

# ── 5-Layer Pipeline ──────────────────────────────────────────────────────────
if analyze_btn and url_input:
    progress_bar = st.progress(0, text="Katman 1: Video bilgileri alınıyor...")
    try:
        video_data = YouTubeExtractor.get_video_data(url_input)
        cached_clips = None
        
        # Check cache early
        if not force_reanalyze and db.video_exists(video_data["id"]):
            cached_clips = db.get_clips_for_video(video_data["id"])
            if cached_clips:
                # Format string'leri geri oluştur
                for c in cached_clips:
                    c["start_formatted"] = YouTubeExtractor.format_seconds(c["start_time"])
                    c["end_formatted"] = YouTubeExtractor.format_seconds(c["end_time"])
                    c["duration_formatted"] = f"{int(c['duration'])} sn"

                st.session_state.video_data = video_data
                st.session_state.clips = cached_clips
                st.session_state.transcript = TranscriptManager.get_transcript(video_data["id"])
                
                # Mock signals & reports to prevent KeyError down the line
                st.session_state.signals = {"times": [], "rms": [], "audio_spikes": [], "silence_bursts": []}
                st.session_state.candidates = []
                st.session_state.quality_reports = {}
                st.session_state.generated_clips = {}
                
                progress_bar.progress(100, text="Önbellekten Yüklendi! ✅")
                st.success(f"Video daha önce analiz edilmiş. {len(cached_clips)} klip önbellekten hızlıca getirildi.")
            else:
                cached_clips = None
                
        if force_reanalyze or not db.video_exists(video_data["id"]) or not cached_clips:
            st.session_state.video_data = video_data
            transcript = TranscriptManager.get_transcript(video_data["id"])
            st.session_state.transcript = transcript
    
            progress_bar.progress(20, text="Katman 1: Ses Enerji Patlamaları & Sessizlik-Şok Analizi yapılıyor...")
            times, rms = AudioDSPAnalyzer.extract_audio_energy(
                video_data["url"], duration_sec=video_data["duration"]
            )
            dsp_signals = AudioDSPAnalyzer.detect_signals(times, rms)
            st.session_state.signals = dsp_signals
    
            progress_bar.progress(40, text="Katman 2: Skorlar birleştirilip Top-N aday havuzu oluşturuluyor...")
            ranker = CandidateRanker(candidate_window_sec=35, merge_threshold_sec=8, top_n=12)
            candidates = ranker.fuse_signals_and_generate_candidates(
                times=dsp_signals["times"],
                audio_spikes=dsp_signals["audio_spikes"],
                silence_bursts=dsp_signals["silence_bursts"],
                heatmap=video_data["heatmap"],
                transcript=transcript,
                total_duration=video_data["duration"],
            )
            st.session_state.candidates = candidates

            progress_bar.progress(65, text="Katman 3: Gemini Flash tek batch çağrıda tüm adayları yargılıyor...")
            if active_key:
                judged_clips = GeminiHighlightEngine.batch_judge_gaming_candidates(
                    candidates=candidates,
                    video_title=video_data["title"],
                    total_duration=video_data["duration"],
                    target_clips=3,
                    api_key=active_key,
                )
            else:
                judged_clips = []
                for rank, c in enumerate(candidates[:3], start=1):
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
    
            progress_bar.progress(80, text="Katman 4: Sınırlar ses sessizlik noktalarına hizalanıyor...")
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
    
            progress_bar.progress(90, text="Kalite Değerlendirmesi: Her klip için detaylı karne çıkarılıyor...")
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
                st.error(f"Analiz sonuçları veritabanına yazılamadı: {e}")
    
            st.session_state.clips = final_clips
            st.session_state.quality_reports = quality_reports
        if force_reanalyze or not db.video_exists(video_data["id"]) or not cached_clips:
            st.session_state.generated_clips = {}
            progress_bar.progress(100, text="Tamamlandı!")
            st.success(
                f"Analiz & Kalite Denetimi tamamlandı! {len(st.session_state.clips)} nihai viral klip seçildi."
            )

    except Exception as e:
        progress_bar.empty()
        st.error(f"İşlem hatası: {str(e)}")

# ── Results ───────────────────────────────────────────────────────────────────
if st.session_state.video_data and st.session_state.clips:
    vdata = st.session_state.video_data
    clips = st.session_state.clips
    signals = st.session_state.signals
    candidates = st.session_state.candidates
    reports = st.session_state.quality_reports
    transcript = st.session_state.transcript

    st.divider()

    # Video info header
    info_col1, info_col2 = st.columns([1, 3])
    with info_col1:
        if vdata.get("thumbnail"):
            st.image(vdata["thumbnail"], use_container_width=True)
    with info_col2:
        st.subheader(vdata["title"])
        st.markdown(
            f"**Kanal:** {vdata['uploader']} | **Süre:** {vdata['duration_formatted']} | "
            f"**İzlenme:** {vdata.get('view_count', 0):,}"
        )
        st.info(
            f"✨ **Otomatik Edit Aktif:** Altyazı: {'Açık' if enable_subtitles else 'Kapalı'} | "
            f"Kanca Kartı: {'Açık' if enable_hook_card else 'Kapalı'} | "
            f"Canlı Renk: {'Açık' if enable_color_grade else 'Kapalı'}"
        )

    # Multi-signal timeline chart
    if signals and len(signals["times"]) > 0:
        st.markdown("### 📊 Katman 1 & 2: Çoklu Sinyal Zaman Çizelgesi (Audio RMS + Shock + Heatmap)")
        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=signals["times"],
            y=signals["rms"],
            mode="lines",
            name="Ses Enerjisi (RMS)",
            line=dict(color="#00D2FF", width=1.5),
            hovertemplate="Zaman: %{x:.1f}s<br>Ses RMS: %{y:.2f}<extra></extra>",
        ))

        shock_indices = np.where(signals["silence_bursts"] > 0.4)[0]
        if len(shock_indices) > 0:
            fig.add_trace(go.Scatter(
                x=signals["times"][shock_indices],
                y=signals["silence_bursts"][shock_indices],
                mode="markers",
                name="⚡ Şok / Sessizlik➔Çığlık İmzası",
                marker=dict(color="#FF0055", size=8, symbol="diamond"),
                hovertemplate="Zaman: %{x:.1f}s<br>Şok Skoru: %{y:.2f}<extra></extra>",
            ))

        colors = [
            "rgba(255, 0, 85, 0.35)",
            "rgba(121, 40, 202, 0.35)",
            "rgba(0, 112, 243, 0.35)",
            "rgba(0, 210, 255, 0.35)",
        ]
        for idx, clip in enumerate(clips):
            c_color = colors[idx % len(colors)]
            fig.add_vrect(
                x0=clip["start_time"],
                x1=clip["end_time"],
                fillcolor=c_color,
                layer="below",
                line_width=1.5,
                line_color="#FFFFFF",
                annotation_text=f"Klip #{clip['rank']} ({clip.get('category', 'CLIP')})",
                annotation_position="top left",
            )

        fig.update_layout(
            xaxis_title="Video Zamanı (Saniye)",
            yaxis_title="Normalize Sinyal Şiddeti",
            margin=dict(l=20, r=20, t=30, b=20),
            height=320,
            hovermode="x unified",
            template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)

    # Top-N candidate inspector
    with st.expander(
        f"🔍 Katman 2: Gemini'ye Gönderilen Top-{len(candidates)} Aday Havuzunu İncele"
    ):
        for c in candidates:
            st.markdown(
                f"- **Aday #{c['candidate_id']}** (`{c['start_formatted']} - {c['end_formatted']}`) "
                f"— Skor: `{c['fusion_score']}/100` | Ses Patlaması: `{c['signals']['audio_spike']}` "
                f"| Şok Skoru: `{c['signals']['silence_burst']}`"
            )

    # Final clips with quality reports
    st.markdown(f"### 🏆 Katman 3 & 4: Gemini Flash Tarafından Seçilen En İyi {len(clips)} Klip")
    safe_uploader = re.sub(r'[^a-zA-Z0-9_\-]', '_', vdata.get("uploader", "Kanal")).strip("_")
    channel_out_dir = os.path.join("outputs", "clips", safe_uploader)
    os.makedirs(channel_out_dir, exist_ok=True)
    cutter = VideoCutter(output_dir=channel_out_dir)

    for idx, clip in enumerate(clips):
        rank = clip["rank"]
        clip_key = (
            f"clip_{idx}_{rank}_{clip['start_time']}_{clip['end_time']}_"
            f"{selected_render_mode}_{enable_subtitles}_{enable_hook_card}_{enable_color_grade}"
        )
        q_report = reports.get(rank, {})

        with st.container():
            col_header1, col_header2 = st.columns([3, 1])
            with col_header1:
                st.markdown(
                    f'<span class="gaming-badge">{clip.get("category", "GAMING")}</span>'
                    f'<span style="font-size: 1.25rem; font-weight: bold;">{clip["title"]}</span>'
                    f' — Not: `{q_report.get("grade", "A")}` '
                    f'(%{q_report.get("composite_score", clip["score"])} Kalite)',
                    unsafe_allow_html=True,
                )
                if clip.get("hook_caption"):
                    st.markdown(
                        f'<div class="hook-badge">🎯 Hook (İlk 3 Sn): "{clip["hook_caption"]}"</div>',
                        unsafe_allow_html=True,
                    )
                st.markdown(
                    f"⏱️ **Aralık:** `{clip['start_formatted']}` — `{clip['end_formatted']}` "
                    f"({clip['duration_formatted']})"
                )
                if clip.get("reason"):
                    st.caption(f"{clip['reason']}")

            col_slider, col_actions = st.columns([3, 2])

            with col_slider:
                time_range = st.slider(
                    f"Klip #{rank} Sınırlarını İnce Ayarla (Saniye)",
                    min_value=0.0,
                    max_value=float(vdata["duration"]),
                    value=(float(clip["start_time"]), float(clip["end_time"])),
                    step=0.5,
                    key=f"slider_{clip_key}",
                )
                start_sel, end_sel = time_range
                dur_sel = round(end_sel - start_sel, 1)
                st.caption(
                    f"Seçilen Aralık: **{YouTubeExtractor.format_seconds(start_sel)} - "
                    f"{YouTubeExtractor.format_seconds(end_sel)}** ({dur_sel} sn)"
                )

            with col_actions:
                st.write("")
                btn_label = f"🎬 Klip #{rank}'i Editli Render Et ({format_choice.split()[1]})"
                generate_btn = st.button(
                    btn_label, key=f"btn_{clip_key}", type="primary", use_container_width=True
                )

                if generate_btn:
                    with st.spinner(
                        f"Klip #{rank} kesiliyor, altyazı & kanca kartı ekleniyor, renkleri canlandırılıyor..."
                    ):
                        try:
                            clip_path = cutter.cut_clip(
                                url=vdata["url"],
                                start_time=start_sel,
                                end_time=end_sel,
                                clip_id=f"{rank}",
                                video_title=vdata["title"],
                                hook_caption=clip.get("hook_caption", ""),
                                transcript_segments=transcript,
                                render_mode=selected_render_mode,
                                add_subtitles=enable_subtitles,
                                add_hook_card=enable_hook_card,
                                enhance_colors=enable_color_grade,
                            )
                            st.session_state.generated_clips[clip_key] = clip_path
                            try:
                                db.save_video(vdata)
                                db.save_clips(vdata["id"], [clip])
                            except Exception as e:
                                st.warning(f"DB Kayıt Hatası (Render Öncesi): {e}")
                                pass
                            
                            try:
                                db.save_render(clip.get("id", f"{vdata['id']}_clip_{rank}"), selected_render_mode, clip_path)
                                st.success("Klip başarıyla editlendi ve hazır!")
                            except Exception as e:
                                st.error(f"Render Veritabanına Yazılamadı: {e}")
                        except Exception as e:
                            st.error(f"Klip editlenirken hata: {str(e)}")
                            
                thumb_btn = st.button(f"🖼️ Thumbnail Üret", key=f"thumb_btn_{clip_key}", use_container_width=True)
                if thumb_btn:
                    with st.spinner("Thumbnail üretiliyor..."):
                        try:
                            from core.thumbnail import ThumbnailGenerator
                            thumb_dir = os.path.join("outputs", "thumbnails", safe_uploader)
                            thumb_path = os.path.join(thumb_dir, f"{vdata['id']}_clip_{rank}_thumb.jpg")
                            ThumbnailGenerator.batch_generate_thumbnails(
                                clips=[clip],
                                video_path_or_url=vdata["url"],
                                output_dir=thumb_dir
                            )
                            st.success("Thumbnail üretildi!")
                        except Exception as e:
                            st.error(f"Thumbnail hatası: {str(e)}")

            # Video player + download
            if clip_key in st.session_state.generated_clips:
                path = st.session_state.generated_clips[clip_key]
                if os.path.exists(path):
                    col_v1, col_v2 = st.columns([3, 2])
                    with col_v1:
                        st.video(path)
                    with col_v2:
                        with open(path, "rb") as f:
                            video_bytes = f.read()
                        st.download_button(
                            label=f"⬇️ Editlenmiş Klip #{rank}'i İndir (.mp4)",
                            data=video_bytes,
                            file_name=os.path.basename(path),
                            mime="video/mp4",
                            use_container_width=True,
                        )
                        
                        thumb_dir = os.path.join("outputs", "thumbnails", safe_uploader)
                        thumb_path = os.path.join(thumb_dir, f"{vdata['id']}_clip_{rank}_thumb.jpg")
                        if os.path.exists(thumb_path):
                            st.image(thumb_path, caption=f"Klip #{rank} Thumbnail", use_container_width=True)

            # Quality report expander
            if q_report:
                with st.expander(
                    f"🧪 Klip #{rank} Kalite & Viralite Raporu (Karnesi: {q_report.get('grade', 'A')})"
                ):
                    qc1, qc2, qc3, qc4 = st.columns(4)
                    qc1.metric("🎯 Hook Gücü", f"%{q_report.get('hook_score', 85)}")
                    qc2.metric("⚡ Eğlence & Hype", f"%{q_report.get('context_score', 88)}")
                    qc3.metric("💥 Aksiyon / Payoff", f"%{q_report.get('payoff_score', 85)}")
                    qc4.metric("✂️ Teknik Ritim", f"%{q_report.get('technical_score', 95)}")
                    st.markdown(f"**📝 Baş Editör Yorumu:** {q_report.get('editor_feedback', '')}")
                    if q_report.get("viral_tips"):
                        st.markdown(
                            f"**💡 Viral Büyüme Tavsiyesi:** `{q_report.get('viral_tips', '')}`"
                        )
                        
                    st.markdown("---")
                    # Feedback buttons
                    fb_col1, fb_col2 = st.columns(2)
                    with fb_col1:
                        if st.button('👍 İyi Klip', key=f'fb_good_{clip_key}'):
                            st.session_state[f'feedback_{clip_key}'] = 'good'
                            st.success('Geri bildirim kaydedildi!')
                    with fb_col2:
                        if st.button('👎 Kötü Klip', key=f'fb_bad_{clip_key}'):
                            st.session_state[f'feedback_{clip_key}'] = 'bad'
                            st.warning('Geri bildirim kaydedildi.')

            st.divider()
