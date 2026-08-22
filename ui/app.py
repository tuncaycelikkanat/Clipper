import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

load_dotenv(os.path.join(root_dir, ".env"))

st.set_page_config(
    page_title="Clipper Studio",
    page_icon=":material/movie_filter:",
    layout="wide",
    initial_sidebar_state="expanded",
)

pages = [
    st.Page("app_pages/analyze.py", title="Analiz & Edit", icon=":material/auto_awesome:", default=True),
    st.Page("app_pages/clips.py", title="Klip Kütüphanesi", icon=":material/video_library:"),
    st.Page("app_pages/export.py", title="Dışa Aktar & Yayınla", icon=":material/upload:"),
    st.Page("app_pages/autopilot.py", title="Otonom Bot (AutoPilot)", icon=":material/smart_toy:"),
    st.Page("app_pages/settings.py", title="Sistem & Ayarlar", icon=":material/settings:"),
]


nav = st.navigation(pages, position="sidebar")
nav.run()
