"""
ui/app_pages/export.py — Multi-Platform Publishing (YouTube Shorts, Instagram Reels, TikTok)
"""

import os
import glob
from pathlib import Path
import streamlit as st
import pandas as pd

from core.uploader import YouTubeUploader
from core.instagram_uploader import InstagramUploader
from core.tiktok_uploader import TikTokUploader
from core.multi_publisher import MultiPublisher
from core.notifier import Notifier
from core.database import DatabaseManager
from core.llm_engine import GeminiHighlightEngine
from core.deepseek_engine import DeepSeekEngine

db = DatabaseManager()
db.init_db()

multi_pub = MultiPublisher()
uploader = multi_pub.youtube
ig_uploader = multi_pub.instagram
tt_uploader = multi_pub.tiktok

st.header("Dışa Aktar & Yayınla", anchor=False)
st.caption("Klipleri YouTube Shorts, Instagram Reels ve TikTok platformlarına tek tıkla veya ayrı ayrı yayınlayın.")

# Platform Bağlantı Rozetleri
auth_status = multi_pub.get_auth_status()
col_a1, col_a2, col_a3 = st.columns(3)
with col_a1:
    if auth_status["youtube"]:
        st.success("YouTube: Bağlandı", icon=":material/check_circle:")
    else:
        st.warning("YouTube: Giriş Bekleniyor", icon=":material/lock:")
with col_a2:
    if auth_status["instagram"]:
        st.success("Instagram Reels: Aktif", icon=":material/check_circle:")
    else:
        st.info("Instagram: Token Gerekli", icon=":material/info:")
with col_a3:
    if auth_status["tiktok"]:
        st.success("TikTok: Aktif", icon=":material/check_circle:")
    else:
        st.info("TikTok: Token Gerekli", icon=":material/info:")

st.divider()

# Tablar
tab_multi, tab_yt, tab_ig, tab_tt, tab_hook = st.tabs([
    "🌐 Çoklu Yayınla (Omnichannel)",
    "📺 YouTube Shorts",
    "📸 Instagram Reels",
    "🎵 TikTok",
    "🔔 Webhook & Bildirimler"
])

# Klipleri listele
rendered_files = glob.glob("outputs/clips/**/*.mp4", recursive=True)
rendered_files = [f for f in rendered_files if not os.path.basename(f).startswith("raw_cut_")]

# ------------------------------------------------------------------
# TAB 1: ÇOKLU YAYINLA (OMNICHANNEL)
# ------------------------------------------------------------------
with tab_multi:
    with st.container(border=True):
        st.subheader("Tek Tıkla Tüm Platformlara Dağıt", anchor=False)
        st.caption("Aynı klibi YouTube Shorts, Instagram Reels ve TikTok platformlarına aynı anda yükleyin.")

        if not rendered_files:
            st.info("Henüz renderlanmış klip bulunamadı. Önce 'Analiz & Edit' sayfasından klip üretin.")
        else:
            selected_file = st.selectbox(
                "Yayınlanacak Klibi Seçin",
                options=rendered_files,
                key="multi_clip_select",
                format_func=lambda x: f"🎬 {os.path.basename(x)} ({os.path.dirname(x).split('/')[-1]})"
            )

            # Metadata bul
            clip_info = {}
            try:
                with db._connect() as conn:
                    res = conn.execute("SELECT * FROM renders WHERE file_path = ?;", (selected_file,)).fetchone()
                    if res:
                        crow = conn.execute("SELECT * FROM clips WHERE id = ?;", (res["clip_id"],)).fetchone()
                        if crow:
                            clip_info = dict(crow)
            except Exception:
                pass

            parent_dir = os.path.basename(os.path.dirname(selected_file))
            potential_thumbs = [
                f"outputs/thumbnails/{parent_dir}/clip_1_thumb.jpg",
                f"outputs/thumbnails/{parent_dir}/clip_2_thumb.jpg",
                f"outputs/thumbnails/{parent_dir}/clip_3_thumb.jpg",
            ]
            default_thumb = next((pt for pt in potential_thumbs if os.path.exists(pt)), "")

            col_p1, col_p2, col_p3 = st.columns(3)
            with col_p1:
                post_yt = st.checkbox("YouTube Shorts", value=auth_status["youtube"], disabled=not auth_status["youtube"])
            with col_p2:
                post_ig = st.checkbox("Instagram Reels", value=auth_status["instagram"], disabled=not auth_status["instagram"])
            with col_p3:
                post_tt = st.checkbox("TikTok", value=auth_status["tiktok"], disabled=not auth_status["tiktok"])

            chosen_platforms = []
            if post_yt: chosen_platforms.append("youtube")
            if post_ig: chosen_platforms.append("instagram")
            if post_tt: chosen_platforms.append("tiktok")

            if st.button("🚀 Seçilen Platformlara Gönder", type="primary", disabled=len(chosen_platforms) == 0, width="stretch"):
                with st.spinner(f"Klip {', '.join(chosen_platforms).upper()} platformlarına dağıtılıyor…"):
                    try:
                        results = multi_pub.publish_clip(
                            clip=clip_info or {"title": os.path.basename(selected_file).replace(".mp4", "")},
                            render_path=selected_file,
                            thumbnail_path=default_thumb if os.path.exists(default_thumb) else None,
                            platforms=chosen_platforms,
                            video_title=parent_dir.replace("_", " "),
                        )
                        for plat, res in results.items():
                            if res.get("status") == "success":
                                st.success(f"✅ **{plat.upper()}**: Başarıyla Yüklendi! ({res.get('url', '')})")
                            elif res.get("status") == "failed":
                                st.error(f"❌ **{plat.upper()}**: Hata ({res.get('error')})")
                    except Exception as exc:
                        st.error(f"Dağıtım hatası: {exc}")

# ------------------------------------------------------------------
# TAB 2: YOUTUBE SHORTS
# ------------------------------------------------------------------
with tab_yt:
    with st.container(border=True):
        if uploader.is_authenticated():
            st.success("YouTube Hesabı Bağlandı", icon=":material/check_circle:")
            if rendered_files:
                sel_yt = st.selectbox("Shorts Olarak Yüklenecek Video", rendered_files, key="yt_only_select")
                yt_title = st.text_input("Shorts Başlığı", value=f"{os.path.basename(sel_yt).replace('.mp4', '')[:80]} #Shorts")
                yt_desc = st.text_area("Açıklama", value="En efsane oyun anları! Abone olmayı unutmayın 👇\n\n#Shorts #Gaming")
                
                if st.button("YouTube Shorts'a Yükle", type="primary", key="btn_yt_upload"):
                    with st.spinner("YouTube'a yükleniyor…"):
                        try:
                            res = uploader.upload_short(video_path=sel_yt, title=yt_title, description=yt_desc)
                            st.success(f"✅ Yüklendi: {res['url']}")
                        except Exception as e:
                            st.error(f"Hata: {e}")
        else:
            st.warning("YouTube Hesabı Doğrulaması Gerekiyor (credentials.json)")
            if st.button("YouTube ile Giriş Yap", type="primary", key="btn_yt_auth"):
                uploader.authenticate()
                st.rerun()

# ------------------------------------------------------------------
# TAB 3: INSTAGRAM REELS
# ------------------------------------------------------------------
with tab_ig:
    with st.container(border=True):
        st.subheader("Instagram Reels Yayınlama (Meta Graph API)", anchor=False)
        if ig_uploader.is_authenticated():
            st.success(f"Instagram Bağlı (Hesap ID: {ig_uploader.account_id})", icon=":material/check_circle:")
            if rendered_files:
                sel_ig = st.selectbox("Reels Olarak Yüklenecek Video", rendered_files, key="ig_only_select")
                ig_cap = st.text_area("Reels Açıklaması & Hashtagler", value=InstagramUploader.generate_caption({"title": os.path.basename(sel_ig)}))
                if st.button("Instagram Reels Olarak Yayınla", type="primary", key="btn_ig_upload"):
                    with st.spinner("Meta Graph API ile Instagram Reels yükleniyor…"):
                        try:
                            res = ig_uploader.upload_reel(video_path=sel_ig, caption=ig_cap)
                            st.success(f"✅ Instagram Reels Yayınlandı! Media ID: {res['media_id']}")
                        except Exception as e:
                            st.error(f"Hata: {e}")
        else:
            st.info("""
            **Instagram Reels Kurulumu (Meta Graph API):**
            1. [Meta for Developers](https://developers.facebook.com/) panelinde bir App açın.
            2. Instagram Business/Creator hesabınızı Facebook Sayfanıza bağlayın.
            3. `INSTAGRAM_ACCESS_TOKEN` ve `INSTAGRAM_ACCOUNT_ID` değerlerini `.env` dosyasına ekleyin.
            """)

# ------------------------------------------------------------------
# TAB 4: TIKTOK
# ------------------------------------------------------------------
with tab_tt:
    with st.container(border=True):
        st.subheader("TikTok Video Yayınlama (Direct Post API v2)", anchor=False)
        if tt_uploader.is_authenticated():
            st.success("TikTok API Bağlı", icon=":material/check_circle:")
            if rendered_files:
                sel_tt = st.selectbox("TikTok Olarak Yüklenecek Video", rendered_files, key="tt_only_select")
                tt_title = st.text_input("TikTok Başlığı & Etiketler (Max 150 Karakter)", value=TikTokUploader.generate_caption({"title": os.path.basename(sel_tt)}))
                if st.button("TikTok'a Gönder", type="primary", key="btn_tt_upload"):
                    with st.spinner("TikTok Direct Post API ile yükleniyor…"):
                        try:
                            res = tt_uploader.upload_video(video_path=sel_tt, title=tt_title)
                            st.success(f"✅ TikTok'a Gönderildi! Publish ID: {res['publish_id']}")
                        except Exception as e:
                            st.error(f"Hata: {e}")
        else:
            st.info("""
            **TikTok Direct Post API Kurulumu:**
            1. [TikTok for Developers](https://developers.tiktok.com/) portalından bir App oluşturun.
            2. Content Posting API iznini (`video.publish`) etkinleştirin.
            3. `TIKTOK_ACCESS_TOKEN` değerini `.env` dosyasına kaydedin.
            """)

# ------------------------------------------------------------------
# TAB 5: WEBHOOK & BİLDİRİMLER
# ------------------------------------------------------------------
with tab_hook:
    with st.container(border=True):
        st.subheader("Otomasyon Webhook Ayarları", anchor=False)
        discord_url = st.text_input("Discord Webhook URL", value=os.environ.get("DISCORD_WEBHOOK_URL", ""), type="password")
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
                "hook_caption": "Bu bir test kancasıdır!"
            }
            with st.spinner("Bildirim fırlatılıyor..."):
                notifier.notify_clip_ready(dummy_clip, "outputs/test.mp4")
            st.success("Test bildirimi başarıyla tetiklendi!", icon=":material/send:")
