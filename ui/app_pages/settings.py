"""
ui/app_pages/settings.py — System settings, scheduler, and cache
"""

import os
import shutil
from pathlib import Path
import streamlit as st
from core.database import DatabaseManager
from core.cache_manager import CacheManager
from core.scheduler_manager import SchedulerManager

root_dir = Path(__file__).resolve().parent.parent.parent

st.header("Sistem & Ayarlar", anchor=False)
st.caption("API yapılandırmaları, zamanlanmış kanal botları ve disk önbellek yönetimi.")

# Section 1: API Status
with st.container(border=True):
    st.subheader("API Yapılandırması", anchor=False)
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    masked_key = gemini_key[:6] + "..." + gemini_key[-4:] if gemini_key else "Tanımlanmamış"
    
    col_k1, col_k2 = st.columns([3, 1], vertical_alignment="center")
    with col_k1:
        st.text_input("GEMINI_API_KEY", value=masked_key, disabled=True, help=".env dosyasından okunur")
    with col_k2:
        if gemini_key:
            st.success("Aktif", icon=":material/check:")
        else:
            st.error("Eksik", icon=":material/close:")

# Section 2: Disk & Cache Management
with st.container(border=True):
    st.subheader("Önbellek & Disk Yönetimi", anchor=False)
    cache_mgr = CacheManager(output_dir="outputs/clips")
    disk_info = cache_mgr.get_disk_usage()
    size_mb = disk_info["total_bytes"] / (1024 * 1024)

    m1, m2, m3 = st.columns(3)
    m1.metric("Klip Boyutu", f"{size_mb:.1f} MB")
    m2.metric("Üretilen MP4 Sayısı", disk_info["clip_count"])
    
    try:
        db = DatabaseManager()
        with db._connect() as conn:
            clip_count = conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
        m3.metric("Veritabanı Klip Kaydı", clip_count)
    except Exception:
        m3.metric("Veritabanı Klip Kaydı", "-")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("Geçici Dosyaları Temizle (.ass & raw)", icon=":material/cleaning_services:", width="stretch"):
            cache_mgr.clear_temp_files()
            st.toast("Geçici dosyalar silindi.", icon="🧹")
    with col_btn2:
        if st.button("Tüm Çıktıları Sıfırla (Outputs)", icon=":material/delete_sweep:", type="primary", width="stretch"):
            cache_mgr.cleanup(max_age_days=0)
            st.toast("Tüm klip önbelleği temizlendi.", icon="🗑️")
            st.rerun()

# Section 3: Background Channel Scheduler
with st.container(border=True):
    st.subheader("Otonom Kanal Takipçisi (Scheduler)", anchor=False)
    st.caption("Belirli YouTube kanallarını periyodik olarak tarayıp yeni video yüklendiğinde otomatik klip üretir.")

    with st.form("add_channel_form"):
        col_c1, col_c2 = st.columns([3, 1])
        with col_c1:
            chan_url = st.text_input("Kanal URL", placeholder="https://www.youtube.com/@KanalAdi")
        with col_c2:
            interval_h = st.number_input("Kontrol Aralığı (Saat)", min_value=1, value=12)
        
        add_job = st.form_submit_button("Kanal Takibini Başlat", icon=":material/add_task:", type="primary")
        if add_job:
            if chan_url:
                st.success(f"**{chan_url}** takibe alındı (Her {interval_h} saatte bir kontrol edilecek).", icon=":material/check_circle:")
            else:
                st.error("Lütfen geçerli bir kanal linki girin.")
