import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to sys.path so all pages can import core/
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from core.extractor import YouTubeExtractor
from core.audio_dsp import AudioDSPAnalyzer
from core.candidate_ranker import CandidateRanker
from core.transcript import TranscriptManager
from core.llm_engine import GeminiHighlightEngine
from core.aligner import AlignmentEngine
from core.quality_evaluator import QualityEvaluator
from core.cutter import VideoCutter
from core.thumbnail import ThumbnailGenerator

load_dotenv(os.path.join(root_dir, ".env"))

import streamlit as st

st.set_page_config(
    page_title="Gaming AI Clipper",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS (shared across pages via session_state injection)
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

# Home page content
st.markdown('<div class="main-header">🎮 Gaming AI Clipper</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Autonomous YouTube gaming clip extraction & editing studio</div>', unsafe_allow_html=True)

st.info("👈 Use the sidebar to navigate between pages.", icon="ℹ️")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("### 🎬 Analyze")
    st.write("Extract highlights from any YouTube video using the 5-layer AI pipeline.")

with col2:
    st.markdown("### 📁 Clips")
    st.write("Browse and manage all previously generated clips from the database.")

with col3:
    st.markdown("### 📤 Export")
    st.write("Upload rendered clips to YouTube Shorts or send Discord/Telegram notifications.")

with col4:
    st.markdown("### ⚙️ Settings")
    st.write("Configure API keys, scheduler channels, and manage disk cache.")
