"""
ui/pages/2_📁_Clips.py — Browse & manage existing clips from DB
"""
import os
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import streamlit as st
import pandas as pd
from core.database import DatabaseManager

st.set_page_config(page_title="Clips - Gaming AI Clipper", page_icon="📁", layout="wide")

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
</style>
<div class="main-header">📁 Clips Library</div>
<p style="color: #888888;">Browse and manage all previously generated clips from the database.</p>
""", unsafe_allow_html=True)

try:
    db = DatabaseManager()
    db.init_db()

    with db._connect() as conn:
        videos_df = pd.read_sql_query("SELECT * FROM videos", conn)
        clips_df = pd.read_sql_query("SELECT * FROM clips", conn)

    if videos_df.empty:
        st.info("No videos found in the database. Go to the Analyze page to process some videos.")
    else:
        st.sidebar.header("Filters")
        selected_video = st.sidebar.selectbox("Filter by Video", ["All"] + videos_df['title'].tolist())
        
        categories = clips_df['category'].unique().tolist() if not clips_df.empty else []
        selected_category = st.sidebar.selectbox("Filter by Category", ["All"] + categories)

        if not clips_df.empty:
            filtered_clips = clips_df
            
            if selected_video != "All":
                video_id = videos_df[videos_df['title'] == selected_video]['id'].values[0]
                filtered_clips = filtered_clips[filtered_clips['video_id'] == video_id]
                
            if selected_category != "All":
                filtered_clips = filtered_clips[filtered_clips['category'] == selected_category]
                
            st.write(f"Found {len(filtered_clips)} clips.")
            
            for _, clip in filtered_clips.iterrows():
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.subheader(f"🎬 {clip['title']}")
                        st.markdown(f"**Category:** {clip['category']} | **Score:** {clip['score']} | **Duration:** {clip['duration']}s")
                        if pd.notna(clip.get('hook_caption')) and clip['hook_caption']:
                            st.caption(f"🎯 Hook: {clip['hook_caption']}")
                    with col2:
                        st.button("📥 Download", key=f"dl_{clip['id']}")
                        if st.button("🔁 Re-render", key=f"rr_{clip['id']}"):
                            st.success(f"Re-rendering {clip['title']}...")
                        
                        col_up, col_down = st.columns(2)
                        with col_up:
                            st.button("👍", key=f"up_{clip['id']}")
                        with col_down:
                            st.button("👎", key=f"down_{clip['id']}")
                    st.divider()
        else:
            st.info("No clips generated yet.")

except Exception as e:
    st.error(f"Error connecting to database: {str(e)}")
