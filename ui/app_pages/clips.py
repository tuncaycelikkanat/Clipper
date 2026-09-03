"""
ui/app_pages/clips.py — Browse & manage existing clips from DB
"""

import os
import re
from pathlib import Path
import streamlit as st
import pandas as pd
from core.database import DatabaseManager
from core.cutter import VideoCutter
from core.transcript import TranscriptManager

db = DatabaseManager()
db.init_db()

st.header("Klip Kütüphanesi", anchor=False)
st.caption("Daha önce üretilen ve analiz edilen tüm videolar ve viral klipler.")

try:
    with db._connect() as conn:
        videos_df = pd.read_sql_query("SELECT * FROM videos ORDER BY processed_at DESC", conn)
        clips_df = pd.read_sql_query("SELECT * FROM clips ORDER BY created_at DESC", conn)
        renders_df = pd.read_sql_query("SELECT * FROM renders", conn)
        queue_df = pd.read_sql_query("SELECT * FROM autopilot_queue", conn)

    if videos_df.empty:
        st.info("Veritabanında henüz kayıtlı video yok. 'Analiz & Edit' sayfasından yeni bir video ekleyin.", icon=":material/info:")
    else:
        # Filter controls in a clean container
        with st.container(border=True):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                video_options = ["Tüm Videolar"] + videos_df["title"].tolist()
                selected_video = st.selectbox("Videoya Göre Filtrele", video_options)
            with col_f2:
                categories = ["Tümü"] + (clips_df["category"].dropna().unique().tolist() if not clips_df.empty else [])
                selected_category = st.selectbox("Kategoriye Göre Filtrele", categories)

        if not clips_df.empty:
            filtered_clips = clips_df.copy()
            
            if selected_video != "Tüm Videolar":
                vid_id = videos_df[videos_df["title"] == selected_video]["id"].values[0]
                filtered_clips = filtered_clips[filtered_clips["video_id"] == vid_id]
                
            if selected_category != "Tümü":
                filtered_clips = filtered_clips[filtered_clips["category"] == selected_category]

            st.caption(f"Toplam **{len(filtered_clips)}** klip listeleniyor.")

            for _, clip in filtered_clips.iterrows():
                # Find parent video
                parent_vid = videos_df[videos_df["id"] == clip["video_id"]]
                video_url = parent_vid.iloc[0]["url"] if not parent_vid.empty else ""
                video_uploader = parent_vid.iloc[0]["uploader"] if not parent_vid.empty else "Kanal"
                video_title = parent_vid.iloc[0]["title"] if not parent_vid.empty else ""

                with st.container(border=True):
                    col_info, col_actions = st.columns([3, 2], vertical_alignment="center")
                    
                    with col_info:
                        category = clip.get("category", "HIGHLIGHT")
                        st.markdown(f":violet-background[**{category}**] **{clip['title']}**")
                        st.caption(f"Kanal: **{video_uploader}** | Süre: **{clip['duration']} sn** | Skor: **%{clip['score']}**")
                        
                        if pd.notna(clip.get("hook_caption")) and clip["hook_caption"]:
                            st.info(f"**Kanca:** \"{clip['hook_caption']}\"", icon=":material/campaign:")

                        # Platform Scores
                        try:
                            from core.platform_scorer import PlatformScorer
                            p_scorer = PlatformScorer()
                            p_res = p_scorer.score_clip(dict(clip))
                            st.markdown(
                                f"🎯 **Shorts:** %{p_res['shorts']} · "
                                f"🎵 **TikTok:** %{p_res['tiktok']} · "
                                f"📸 **Reels:** %{p_res['reels']} · "
                                f"🐦 **X:** %{p_res['twitter']}"
                            )
                        except Exception as e:
                            st.info(f"Platform skorları hesaplanamadı: {e}")
                        # Check if a render exists on disk
                        clip_renders = renders_df[renders_df["clip_id"] == clip["id"]] if not renders_df.empty else pd.DataFrame()
                        existing_file = None
                        if not clip_renders.empty:
                            last_path = clip_renders.iloc[-1]["file_path"]
                            if os.path.exists(last_path):
                                existing_file = last_path

                        if existing_file:
                            st.video(existing_file)
                            with open(existing_file, "rb") as f:
                                st.download_button(
                                    "Klibi İndir (MP4)",
                                    data=f,
                                    file_name=os.path.basename(existing_file),
                                    mime="video/mp4",
                                    icon=":material/download:",
                                    width="stretch",
                                    key=f"lib_dl_{clip['id']}"
                                )
                        
                        # ADD TO QUEUE BUTTON
                        if existing_file:
                            is_queued = False
                            if not queue_df.empty:
                                is_queued = not queue_df[(queue_df["clip_id"] == clip["id"]) & (queue_df["status"] == "QUEUED")].empty
                                
                            if is_queued:
                                st.button("✅ Zaten Kuyrukta Bekliyor", key=f"q_dis_{clip['id']}", disabled=True, use_container_width=True)
                            else:
                                if st.button("🚀 Nöbetçi Bot'a (Sıraya) Ekle", key=f"q_{clip['id']}", type="primary", use_container_width=True):
                                    try:
                                        from core.autopilot import AutoPilotManager
                                        ap = AutoPilotManager(db=db)
                                        import uuid
                                        import datetime
                                        
                                        latest_iso = None
                                        with db._connect() as conn:
                                            res = conn.execute("SELECT scheduled_at FROM autopilot_queue ORDER BY scheduled_at DESC LIMIT 1").fetchone()
                                            if res:
                                                latest_iso = res[0]
                                                
                                        next_slot = ap.compute_next_available_slot(latest_scheduled_iso=latest_iso)[1]
                                        q_id = str(uuid.uuid4())
                                        
                                        # Thumbnail Uret (Manuel Ekleme Icin)
                                        thumb_path = ""
                                        try:
                                            from core.thumbnail import ThumbnailGenerator
                                            thumbs = ThumbnailGenerator.batch_generate_thumbnails(
                                                clips=[dict(clip)],
                                                video_path_or_url=existing_file,
                                                output_dir="outputs/thumbnails"
                                            )
                                            if thumbs:
                                                thumb_path = thumbs[0]
                                        except Exception as e:
                                            print(f"Thumbnail error: {e}")
                                            
                                        with db._connect() as conn:
                                            conn.execute("""
                                                INSERT INTO autopilot_queue 
                                                (id, video_id, clip_id, channel_url, title, render_path, thumbnail_path, viral_score, scheduled_at, status, created_at)
                                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', ?)
                                            """, (
                                                q_id, clip["video_id"], clip["id"], video_url, clip["title"],
                                                existing_file, thumb_path, clip["score"], next_slot, datetime.datetime.utcnow().isoformat()
                                            ))
                                            conn.commit()
                                        st.success(f"Klip başarıyla sıraya alındı! Yayın Tarihi: {next_slot[:16].replace('T', ' ')}")
                                    except Exception as e:
                                        st.error(f"Hata: {e}")
                                    
                        # Re-render button
                        render_btn_label = "Yeniden Renderla" if existing_file else "Klibi Renderla"
                        if st.button(render_btn_label, icon=":material/refresh:", width="stretch", key=f"re_ren_{clip['id']}"):
                            if not video_url:
                                st.error("Orijinal video linki bulunamadı.")
                            else:
                                with st.spinner(f"Klip #{clip['rank']} renderlanıyor..."):
                                    try:
                                        safe_uploader = re.sub(r'[^a-zA-Z0-9_\-]', '_', video_uploader).strip("_")
                                        channel_out_dir = os.path.join("outputs", "clips", safe_uploader)
                                        os.makedirs(channel_out_dir, exist_ok=True)
                                        
                                        cutter = VideoCutter(output_dir=channel_out_dir)
                                        transcript = TranscriptManager.get_transcript(clip["video_id"])

                                        clip_path = cutter.cut_clip(
                                            url=video_url,
                                            start_time=float(clip["start_time"]),
                                            end_time=float(clip["end_time"]),
                                            clip_id=f"{clip['rank']}",
                                            video_title=video_title,
                                            hook_caption=clip.get("hook_caption", ""),
                                            transcript_segments=transcript,
                                            render_mode="shorts_9x16_blur",
                                            add_subtitles=False,
                                            add_hook_card=False,
                                            enhance_colors=True,
                                            use_whisper=True
                                        )
                                        db.save_render(clip["id"], "shorts_9x16_blur", clip_path)
                                        
                                        # Auto-generate thumbnail
                                        try:
                                            thumb_dir = os.path.join("outputs", "thumbnails", safe_uploader)
                                            from core.thumbnail import ThumbnailGenerator
                                            ThumbnailGenerator.batch_generate_thumbnails(
                                                clips=[{**dict(clip), "start_time": 0.0, "end_time": float(clip["duration"])}],
                                                video_path_or_url=clip_path,
                                                output_dir=thumb_dir
                                            )
                                        except Exception as e:
                                            st.warning(f"Thumbnail üretimi başarısız oldu: {e}")

                                        st.toast("Klip ve thumbnail başarıyla hazırlandı!", icon="🎉")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Render hatası: {str(e)}")
        else:
            st.info("Kayıtlı klip bulunamadı.", icon=":material/video_library:")

except Exception as e:
    st.error(f"Veritabanı bağlantı hatası: {str(e)}")
