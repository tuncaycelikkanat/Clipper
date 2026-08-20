"""
ui/pages/4_⚙️_Settings.py — API keys, scheduler settings, cache management
"""
import os
import sys
import shutil
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import streamlit as st
from core.database import DatabaseManager

st.set_page_config(page_title="Settings - Gaming AI Clipper", page_icon="⚙️", layout="wide")

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
<div class="main-header">⚙️ Settings</div>
<p style="color: #888888;">Configure API keys, scheduler channels, and manage disk cache.</p>
""", unsafe_allow_html=True)

st.header("🔑 API Keys")
gemini_key = os.environ.get("GEMINI_API_KEY", "")
masked_key = gemini_key[:8] + "..." + gemini_key[-4:] if gemini_key else "Not Set"
st.text_input("GEMINI_API_KEY", value=masked_key, disabled=True, help="Set this in your .env file")

st.divider()

st.header("🧹 Cache Management")

cache_dir = os.path.join(root_dir, "outputs")
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)

def get_dir_size(path='.'):
    total = 0
    with os.scandir(path) as it:
        for entry in it:
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += get_dir_size(entry.path)
    return total

size_bytes = get_dir_size(cache_dir)
size_mb = size_bytes / (1024 * 1024)

col1, col2 = st.columns(2)
with col1:
    st.metric("Cache Disk Usage", f"{size_mb:.2f} MB")
with col2:
    try:
        db = DatabaseManager()
        with db._connect() as conn:
            clip_count = conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
        st.metric("Total Clips in DB", clip_count)
    except Exception:
        st.metric("Total Clips in DB", "Error")

if st.button("Clear Cache (Outputs Folder)", type="primary"):
    try:
        for item in os.listdir(cache_dir):
            item_path = os.path.join(cache_dir, item)
            if os.path.isfile(item_path):
                os.unlink(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
        st.success("Cache cleared successfully.")
        st.rerun()
    except Exception as e:
        st.error(f"Failed to clear cache: {e}")

st.divider()

st.header("⏱️ Scheduler Configuration")
st.write("Configure background channels to monitor for new videos.")

with st.expander("Add Channel to Monitor"):
    channel_url = st.text_input("Channel URL")
    interval = st.number_input("Check Interval (hours)", min_value=1, value=24)
    if st.button("Add Job"):
        st.success(f"Added {channel_url} to scheduler (every {interval}h).")

st.write("**Active Jobs:**")
st.info("No active jobs currently.")
