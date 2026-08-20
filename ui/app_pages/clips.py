"""
ui/app_pages/clips.py — Browse & manage existing clips from DB
"""

import os
from pathlib import Path
import streamlit as st
import pandas as pd
from core.database import DatabaseManager

db = DatabaseManager()
db.init_db()

st.header("Klip Kütüphanesi", anchor=False)
st.caption("Daha önce üretilen ve analiz edilen tüm videolar ve viral klipler.")

try:
    with db._connect() as conn:
        videos_df = pd.read_sql_query("SELECT * FROM videos ORDER BY processed_at DESC", conn)
        clips_df = pd.read_sql_query("SELECT * FROM clips ORDER BY created_at DESC", conn)
        renders_df = pd.read_sql_query("SELECT * FROM renders", conn)

    if videos_df.empty:
        st.info("Veritabanında henüz kayıtlı video yok. 'Analiz & Edit' sayfasından yeni bir video ekleyin.", icon=":material/info:")
    else:
        # Filter controls in a clean container
        with st.container(border=True):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                video_options = ["Tüm Videolar"] + videos_df["title"].tolist()
                selected_video = st.selectbox("Videoya Göre Filtrele", video_options, icon=":material/movie:")
            with col_f2:
                categories = ["Tümü"] + (clips_df["category"].dropna().unique().tolist() if not clips_df.empty else [])
                selected_category = st.selectbox("Kategoriye Göre Filtrele", categories, icon=":material/category:")

        if not clips_df.empty:
            filtered_clips = clips_df.copy()
            
            if selected_video != "Tüm Videolar":
                vid_id = videos_df[videos_df["title"] == selected_video]["id"].values[0]
                filtered_clips = filtered_clips[filtered_clips["video_id"] == vid_id]
                
            if selected_category != "Tümü":
                filtered_clips = filtered_clips[filtered_clips["category"] == selected_category]

            st.caption(f"Toplam **{len(filtered_clips)}** klip listeleniyor.")

            for _, clip in filtered_clips.iterrows():
                with st.container(border=True):
                    col_info, col_actions = st.columns([3, 1], vertical_alignment="center")
                    
                    with col_info:
                        category = clip.get("category", "HIGHLIGHT")
                        st.markdown(f":violet-background[**{category}**] **{clip['title']}**")
                        st.caption(f"Süre: **{clip['duration']} sn** | Viral Skor: **%{clip['score']}** | Oluşturulma: **{clip['created_at'][:16]}**")
                        
                        if pd.notna(clip.get("hook_caption")) and clip["hook_caption"]:
                            st.info(f"**Kanca:** \"{clip['hook_caption']}\"", icon=":material/campaign:")

                    with col_actions:
                        # Check if a render exists
                        clip_renders = renders_df[renders_df["clip_id"] == clip["id"]] if not renders_df.empty else pd.DataFrame()
                        if not clip_renders.empty:
                            file_path = clip_renders.iloc[-1]["file_path"]
                            if os.path.exists(file_path):
                                with open(file_path, "rb") as f:
                                    st.download_button(
                                        "İndir (MP4)",
                                        data=f,
                                        file_name=os.path.basename(file_path),
                                        mime="video/mp4",
                                        icon=":material/download:",
                                        width="stretch",
                                        key=f"lib_dl_{clip['id']}"
                                    )
                            else:
                                st.button("Tekrar Renderla", icon=":material/refresh:", width="stretch", key=f"re_ren_{clip['id']}")
                        else:
                            st.caption("Henüz renderlanmadı.")
        else:
            st.info("Kayıtlı klip bulunamadı.", icon=":material/video_library:")

except Exception as e:
    st.error(f"Veritabanı bağlantı hatası: {str(e)}")
