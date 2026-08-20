"""
ui/app_pages/export.py — Upload to YouTube, webhook settings
"""

import os
from pathlib import Path
import streamlit as st
from core.uploader import YouTubeUploader
from core.notifier import Notifier

st.header("Dışa Aktar & Bildirimler", anchor=False)
st.caption("Renderlanan klipleri doğrudan YouTube Shorts'a yükleyin veya Discord / Telegram kanallarına otomatik fırlatın.")

tab_yt, tab_hook = st.tabs(["YouTube Shorts Yükleme", "Webhook & Bildirimler"])

with tab_yt:
    with st.container(border=True):
        uploader = YouTubeUploader()
        
        if uploader.is_authenticated():
            st.success("YouTube Hesabı Bağlandı ve Yetkilendirildi", icon=":material/check_circle:")
            
            with st.form("upload_form"):
                video_path = st.text_input("Klip Dosya Yolu (.mp4)", placeholder="outputs/clips/Kanal_Adi/clip_1.mp4")
                title = st.text_input("Shorts Başlığı", max_chars=100, placeholder="En İyi An! #shorts #gaming")
                desc = st.text_area("Açıklama", placeholder="Orijinal video linki ve etiketler...")
                tags = st.text_input("Etiketler (Virgülle ayırın)", value="shorts, gaming, highlights")
                
                submitted = st.form_submit_button("YouTube'a Yükle", type="primary", icon=":material/upload:")
                if submitted:
                    if os.path.exists(video_path):
                        with st.spinner("Video YouTube sunucularına yükleniyor..."):
                            try:
                                res = uploader.upload_short(
                                    video_path=video_path,
                                    title=title,
                                    description=desc,
                                    tags=[t.strip() for t in tags.split(",") if t.strip()]
                                )
                                st.success(f"Yükleme Başarılı! Video URL: {res['url']}", icon=":material/verified:")
                            except Exception as e:
                                st.error(f"Yükleme başarısız: {e}")
                    else:
                        st.error("Dosya bulunamadı. Lütfen yolu kontrol edin.")
        else:
            st.warning("YouTube Hesabı Doğrulaması Gerekiyor (OAuth2)", icon=":material/lock:")
            st.caption("credentials.json dosyasını proje kök dizinine yerleştirdikten sonra aşağıdaki butona tıklayın.")
            if st.button("YouTube ile Giriş Yap", icon=":material/login:"):
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
