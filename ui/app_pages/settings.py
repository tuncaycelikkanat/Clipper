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

# Section 1: API Status (Dream Team)
with st.container(border=True):
    st.subheader("Yapay Zeka Motorları (Dream Team)", anchor=False)
    st.caption("Gemini Flash devasa video transkript analizini ve aday seçimini yapar; DeepSeek ise viral kanca ve başlıkları kurgular.")
    
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    masked_gemini = gemini_key[:6] + "..." + gemini_key[-4:] if gemini_key else "Tanımlanmamış"
    
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    masked_deepseek = deepseek_key[:6] + "..." + deepseek_key[-4:] if deepseek_key else "Tanımlanmamış (Gemini yedekte)"

    col_k1, col_k2 = st.columns([3, 1], vertical_alignment="center")
    with col_k1:
        st.text_input("GEMINI_API_KEY (Analiz Motoru)", value=masked_gemini, disabled=True)
    with col_k2:
        if gemini_key:
            st.success("Aktif", icon=":material/check:")
        else:
            st.error("Eksik", icon=":material/close:")

    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    masked_or = openrouter_key[:8] + "..." + openrouter_key[-4:] if openrouter_key else "Tanımlanmamış"

    col_or1, col_or2 = st.columns([3, 1], vertical_alignment="center")
    with col_or1:
        st.text_input("OPENROUTER_API_KEY (DeepSeek V3 Ücretsiz)", value=masked_or, disabled=True)
    with col_or2:
        if openrouter_key:
            st.success("Aktif (Öncelikli)", icon=":material/verified:")
        else:
            st.info("İsteğe Bağlı", icon=":material/info:")

# Section 1b: Social Media Integrations (Meta & TikTok)
with st.container(border=True):
    st.subheader("Sosyal Medya Yayınlama API'leri (Meta & TikTok)", anchor=False)
    st.caption("Meta Graph API (Instagram Reels) ve TikTok Content Posting API entegrasyon durumları.")

    ig_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
    ig_acc = os.environ.get("INSTAGRAM_ACCOUNT_ID", "")
    masked_ig = (ig_token[:8] + "..." + ig_token[-4:]) if ig_token else "Tanımlanmamış"

    col_ig1, col_ig2 = st.columns([3, 1], vertical_alignment="center")
    with col_ig1:
        st.text_input("INSTAGRAM_ACCESS_TOKEN (Meta Graph API)", value=masked_ig, disabled=True,
                      help="Instagram Business/Creator hesabı için kalıcı Graph API access token.")
    with col_ig2:
        if ig_token and ig_acc:
            st.success(f"Aktif (ID: {ig_acc})", icon=":material/check_circle:")
        elif ig_token:
            st.warning("Account ID Eksik", icon=":material/warning:")
        else:
            st.info("İsteğe Bağlı", icon=":material/info:")

    tt_token = os.environ.get("TIKTOK_ACCESS_TOKEN", "")
    tt_key = os.environ.get("TIKTOK_CLIENT_KEY", "")
    tt_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "")
    masked_tt = (tt_token[:8] + "..." + tt_token[-4:]) if tt_token else "Tanımlanmamış"

    col_tt1, col_tt2 = st.columns([3, 1], vertical_alignment="center")
    with col_tt1:
        st.text_input("TIKTOK_ACCESS_TOKEN (TikTok Direct Post API v2)", value=masked_tt, disabled=True,
                      help="TikTok Developer Direct Post API v2 Bearer token.")
    with col_tt2:
        if tt_token:
            st.success("Aktif", icon=":material/check_circle:")
        else:
            st.info("İsteğe Bağlı", icon=":material/info:")

    if tt_key and tt_secret and not tt_token:
        with st.expander("🔗 TikTok Hesabını Tek Tıkla Bağla (OAuth2)", expanded=True):
            st.caption("TikTok Developer Client Key & Secret kaydedildi. Aşağıdaki butona tıklayıp hesabına izin ver.")
            from core.tiktok_uploader import TikTokUploader
            auth_url = TikTokUploader.get_authorization_url(client_key=tt_key)
            st.link_button("🚀 TikTok İle Giriş Yap & Yetkilendir", auth_url, icon=":material/login:", type="primary")

            st.write("Yetkilendirmeden sonra yönlendirildiğin adres çubuğundaki linki (veya `code=...` kısmını) buraya yapıştır:")
            auth_code_input = st.text_input("Yönlendirme Linki veya Code", placeholder="https://tuncaycelikkanat.github.io/Clipper/?code=...")
            if st.button("Token'ı Al ve Kaydet", icon=":material/key:", key="btn_exchange_tt"):
                if auth_code_input:
                    # Extract code if full URL was pasted
                    code = auth_code_input.strip()
                    if "code=" in code:
                        code = code.split("code=")[1].split("&")[0]
                    try:
                        token_res = TikTokUploader.exchange_code_for_token(
                            code=code,
                            client_key=tt_key,
                            client_secret=tt_secret,
                        )
                        act = token_res["access_token"]
                        open_id = token_res.get("open_id", "")
                        # Save to .env
                        with open(".env", "a") as f:
                            f.write(f"\nTIKTOK_ACCESS_TOKEN={act}\nTIKTOK_OPEN_ID={open_id}\n")
                        os.environ["TIKTOK_ACCESS_TOKEN"] = act
                        os.environ["TIKTOK_OPEN_ID"] = open_id
                        st.success(f"🎉 TikTok Hesabı Başarıyla Bağlandı! (Open ID: {open_id})", icon=":material/verified:")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Token alınamadı: {e}", icon=":material/error:")



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
        if st.button("Tüm Çıktıları & Veritabanını Sıfırla", icon=":material/delete_sweep:", type="primary", width="stretch"):
            cache_mgr.clear_all()
            try:
                db = DatabaseManager()
                db.clear_database()
            except Exception:
                pass
            
            # Clear all session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
                
            st.toast("Tüm klip dosyaları, veritabanı kayıtları ve önbellek sıfırlandı!", icon="🗑️")
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
