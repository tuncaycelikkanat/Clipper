"""
ui/app_pages/export.py — Upload to YouTube, webhook settings
"""

import os
import glob
from pathlib import Path
import streamlit as st
import pandas as pd
from core.uploader import YouTubeUploader
from core.notifier import Notifier
from core.database import DatabaseManager

db = DatabaseManager()
db.init_db()

st.header("Dışa Aktar & Yayınla", anchor=False)
st.caption("Renderlanan klipleri doğrudan YouTube Shorts'a yükleyin veya Discord / Telegram kanallarına otomatik fırlatın.")

tab_yt, tab_hook = st.tabs(["YouTube Shorts Yükleme", "Webhook & Bildirimler"])

with tab_yt:
    with st.container(border=True):
        uploader = YouTubeUploader()
        
        if uploader.is_authenticated():
            st.success("YouTube Hesabı Bağlandı ve Yetkilendirildi", icon=":material/check_circle:")
            
            # Find available rendered clips
            rendered_files = glob.glob("outputs/clips/**/*.mp4", recursive=True)
            rendered_files = [f for f in rendered_files if not os.path.basename(f).startswith("raw_cut_")]
            
            if rendered_files:
                selected_file = st.selectbox(
                    "Yüklenecek Klibi Seçin",
                    options=rendered_files,
                    format_func=lambda x: f"🎬 {os.path.basename(x)} ({os.path.dirname(x).split('/')[-1]})"
                )
                
                # Try to find matching thumbnail automatically
                base_name = os.path.basename(selected_file).replace(".mp4", "")
                parent_dir = os.path.basename(os.path.dirname(selected_file))
                
                # Check potential thumbnail paths
                potential_thumbs = [
                    f"outputs/thumbnails/{parent_dir}/clip_1_thumb.jpg",
                    f"outputs/thumbnails/{parent_dir}/clip_2_thumb.jpg",
                    f"outputs/thumbnails/{parent_dir}/clip_3_thumb.jpg",
                ]
                default_thumb = ""
                for pt in potential_thumbs:
                    if os.path.exists(pt):
                        default_thumb = pt
                        break

                with st.form("upload_form"):
                    col_f1, col_f2 = st.columns([3, 2])
                    with col_f1:
                        title_candidate = os.path.basename(selected_file).replace(".mp4", "").replace("_", " ")
                        title = st.text_input("Shorts Başlığı", value=title_candidate[:90] + " #shorts #gaming", max_chars=100)
                        tags = st.text_input("Etiketler (Virgülle ayırın)", value="shorts, gaming, funny, highlight, clips")
                        thumb_path = st.text_input("Özel Kapak Resmi Yolu (.jpg)", value=default_thumb, placeholder="outputs/thumbnails/.../clip_1_thumb.jpg")
                    with col_f2:
                        desc = st.text_area(
                            "Video Açıklaması",
                            value=f"Bu klip Gaming AI Clipper stüdyosu tarafından otonom olarak üretilmiştir.\n\n#Shorts #Gaming #Highlights",
                            height=150
                        )

                    submitted = st.form_submit_button("YouTube'a Yükle", type="primary", icon=":material/upload:", width="stretch")
                    if submitted:
                        with st.spinner("Video ve kapak resmi YouTube sunucularına yükleniyor..."):
                            try:
                                res = uploader.upload_short(
                                    video_path=selected_file,
                                    title=title,
                                    description=desc,
                                    tags=[t.strip() for t in tags.split(",") if t.strip()],
                                    thumbnail_path=thumb_path if thumb_path and os.path.exists(thumb_path) else None
                                )
                                st.success(f"Yükleme Başarılı! Video URL: {res['url']}", icon=":material/verified:")
                            except Exception as e:
                                st.error(f"Yükleme başarısız: {e}")
            else:
                st.info("Henüz renderlanmış klip bulunamadı. Önce 'Analiz & Edit' sayfasından bir klip oluşturun.", icon=":material/info:")

        else:
            st.warning("YouTube Hesabı Doğrulaması Gerekiyor (OAuth2)", icon=":material/lock:")
            st.markdown("""
            **Kurulum Adımları:**
            1. [Google Cloud Console](https://console.cloud.google.com/) adresine gidin.
            2. Bir proje açıp **YouTube Data API v3** servisini etkinleştirin.
            3. OAuth 2.0 Client ID oluşturun (Uygulama tipi: *Desktop App*).
            4. İndirdiğiniz JSON dosyasını proje kök dizinine **`credentials.json`** adıyla kaydedin.
            5. Aşağıdaki butona tıklayarak tarayıcıdan izin verin.
            """)
            if st.button("YouTube ile Giriş Yap", icon=":material/login:", type="primary"):
                try:
                    uploader.authenticate()
                    st.rerun()
                except Exception as e:
                    st.error(f"Giriş hatası: {e}")

with tab_hook:
    with st.container(border=True):
        st.subheader("Otomasyon Webhook Ayarları", anchor=False)
        st.caption("Her yeni klip renderlandığında otomatik bildirim gönderilecek adresleri tanımlayın.")
        
        discord_url = st.text_input("Discord Webhook URL", value=os.environ.get("DISCORD_WEBHOOK_URL", ""), type="password", help="Discord kanal entegrasyonu webhook linki")
        
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            telegram_token = st.text_input("Telegram Bot Token", value=os.environ.get("TELEGRAM_BOT_TOKEN", ""), type="password")
        with col_t2:
            telegram_chat = st.text_input("Telegram Chat ID", value=os.environ.get("TELEGRAM_CHAT_ID", ""))

        if st.button("Test Bildirimi Gönder", icon=":material/notifications_active:"):
            notifier = Notifier(webhook_url=discord_url, telegram_token=telegram_token, telegram_chat_id=telegram_chat)
            dummy_clip = {
                "title": "Test Highlight Klibi",
                "category": "TEST",
                "score": 98,
                "duration_formatted": "22 sn",
                "start_formatted": "01:10",
                "end_formatted": "01:32",
                "rank": 1,
                "hook_caption": "Bu bir test kancasıdır!"
            }
            with st.spinner("Bildirim fırlatılıyor..."):
                notifier.notify_clip_ready(dummy_clip, "outputs/test.mp4")
            st.success("Test bildirimi başarıyla tetiklendi!", icon=":material/send:")
