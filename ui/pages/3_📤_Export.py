"""
ui/pages/3_📤_Export.py — Upload to YouTube, webhook settings
"""
import os
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import streamlit as st
from core.uploader import YouTubeUploader
from core.notifier import Notifier

st.set_page_config(page_title="Export - Gaming AI Clipper", page_icon="📤", layout="wide")

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
<div class="main-header">📤 Export & Notifications</div>
<p style="color: #888888;">Upload rendered clips to YouTube Shorts and manage Discord/Telegram webhook settings.</p>
""", unsafe_allow_html=True)

st.header("📺 YouTube Shorts Upload")
uploader = YouTubeUploader()

if uploader.is_authenticated():
    st.success("✅ YouTube Account Authenticated")
    
    with st.expander("Upload a Rendered Clip"):
        video_path = st.text_input("Path to rendered .mp4 file")
        title = st.text_input("Shorts Title", max_chars=100)
        desc = st.text_area("Description")
        tags = st.text_input("Tags (comma separated)", value="shorts,gaming")
        
        if st.button("Upload to YouTube", type="primary"):
            if os.path.exists(video_path):
                with st.spinner("Uploading..."):
                    try:
                        res = uploader.upload_short(
                            video_path=video_path,
                            title=title,
                            description=desc,
                            tags=[t.strip() for t in tags.split(",")]
                        )
                        st.success(f"Uploaded! Video URL: {res['url']}")
                    except Exception as e:
                        st.error(f"Upload failed: {e}")
            else:
                st.error("File not found.")
else:
    st.warning("⚠️ YouTube Authentication Required")
    if st.button("Authenticate with YouTube"):
        try:
            uploader.authenticate()
            st.rerun()
        except Exception as e:
            st.error(f"Authentication error: {e}")


st.divider()

st.header("🔔 Notification Settings")
discord_url = st.text_input("Discord Webhook URL", value=os.environ.get("DISCORD_WEBHOOK_URL", ""), type="password")
telegram_token = st.text_input("Telegram Bot Token", value=os.environ.get("TELEGRAM_BOT_TOKEN", ""), type="password")
telegram_chat = st.text_input("Telegram Chat ID", value=os.environ.get("TELEGRAM_CHAT_ID", ""))

if st.button("Test Notifications"):
    notifier = Notifier(webhook_url=discord_url, telegram_token=telegram_token, telegram_chat_id=telegram_chat)
    dummy_clip = {
        "title": "Test Clip",
        "category": "TEST",
        "score": 99,
        "duration_formatted": "15s",
        "start_formatted": "00:00",
        "end_formatted": "00:15",
        "rank": 1
    }
    with st.spinner("Sending..."):
        notifier.notify_clip_ready(dummy_clip, "test_render.mp4")
    st.success("Test notification triggered. Check your Discord/Telegram if configured, otherwise check logs.")
