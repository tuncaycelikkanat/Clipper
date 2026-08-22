"""
ui/app_pages/autopilot.py — Otonom Bot Kontrol Merkezi (AutoPilot)

Takip edilen YouTube kanallarını listeler, yeni video geldiğinde viral skoru >= 90
olan anları otomatik stoklar ve Türkiye gaming saatlerine (13:00, 18:00, 22:00)
göre YouTube Shorts'a zamanlanmış olarak yükler.
"""

import datetime
import os
from pathlib import Path
import streamlit as st
import pandas as pd

from core.database import DatabaseManager
from core.autopilot import AutoPilotManager
from core.uploader import YouTubeUploader

db = DatabaseManager()
db.init_db()
autopilot = AutoPilotManager(db=db)
uploader = YouTubeUploader()

st.header("🤖 Otonom Bot (AutoPilot)", anchor=False)
st.caption("Kanalları arka planda takip eder, $\\ge 90$ viral skorlu klipleri stoklar ve otomatik zamanlayarak YouTube Shorts'a yükler.")

# ------------------------------------------------------------------
# Üst Metrikler
# ------------------------------------------------------------------
tracked_channels = autopilot.get_tracked_channels(active_only=True)
queue_items = db.get_autopilot_queue(limit=100)

stock_count = sum(1 for q in queue_items if q.get("status") == "QUEUED")
scheduled_count = sum(1 for q in queue_items if q.get("status") == "SCHEDULED")
published_count = sum(1 for q in queue_items if q.get("status") == "PUBLISHED")
latest_slot = db.get_latest_scheduled_time()

col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1:
    st.metric("Takip Edilen Kanallar", f"{len(tracked_channels)} Kanal")
with col_m2:
    st.metric("Stoktaki Klipler (\\ge 90)", f"{stock_count} Klip")
with col_m3:
    st.metric("Planlanan Shorts", f"{scheduled_count} Video")
with col_m4:
    if latest_slot:
        try:
            slot_dt = datetime.datetime.fromisoformat(latest_slot.replace("Z", "+00:00"))
            # Display in Turkey local time (+3h)
            local_slot = slot_dt + datetime.timedelta(hours=3)
            slot_str = local_slot.strftime("%d %b %H:%M")
        except Exception:
            slot_str = latest_slot
    else:
        slot_str = "Boşta"
    st.metric("Sıradaki Son Slot", slot_str)

st.divider()

# ------------------------------------------------------------------
# Tablar: Kanallar, Kuyruk, Ayarlar
# ------------------------------------------------------------------
tab_channels, tab_queue, tab_settings = st.tabs([
    "📺 Takip Edilen Kanallar",
    "📦 Zamanlanmış Kuyruk & Stok",
    "⚙️ Yayın Saatleri & Ayarlar"
])

# ------------------------------------------------------------------
# TAB 1: TAKİP EDİLEN KANALLAR
# ------------------------------------------------------------------
with tab_channels:
    st.subheader("Yeni Kanal Ekle", anchor=False)
    
    # Playlist seçeneklerini al
    playlists = []
    if uploader.is_authenticated():
        try:
            playlists = uploader.get_playlists()
        except Exception:
            pass
    
    pl_options = ["(Yok)"] + [f"{p['title']} ({p['id']})" for p in playlists]

    with st.form("add_channel_form", clear_on_submit=True):
        col_c1, col_c2 = st.columns([3, 2])
        with col_c1:
            ch_url = st.text_input(
                "YouTube Kanal veya Oynatma Listesi URL'si",
                placeholder="https://www.youtube.com/@Mithrain veya /videos URL",
            )
            ch_name = st.text_input("Kanal İsmi / Etiket", placeholder="Mithrain")
        with col_c2:
            min_score = st.slider("Minimum Viral Skor Eşiği", min_value=80, max_value=98, value=90, step=1,
                                  help="Sadece bu puanın üzerindeki efsane anlar otomatik stoklanır.")
            selected_pl_str = st.selectbox("Hedef Oynatma Listesi", pl_options)
            auto_up = st.toggle("Otomatik YouTube Shorts Zamanlama", value=True,
                                help="Açıksa sıradaki boş slota publishAt ile otomatik yüklenir.")

        submitted = st.form_submit_button("➕ Kanalı Takibe Al", type="primary", use_container_width=True)
        if submitted:
            if not ch_url:
                st.error("Lütfen geçerli bir YouTube kanal URL'si girin.")
            else:
                pl_id = None
                if selected_pl_str != "(Yok)":
                    pl_id = selected_pl_str.split("(")[-1].replace(")", "").strip()
                
                ch_id = autopilot.add_channel(
                    url=ch_url,
                    name=ch_name or ch_url.split("/")[-1],
                    min_score=min_score,
                    target_playlist=pl_id,
                    auto_upload=auto_up,
                )
                st.success(f"✅ '{ch_name or ch_url}' başarıyla takip listesine eklendi!")
                st.rerun()

    st.subheader("Mevcut Takip Listesi", anchor=False)
    if not tracked_channels:
        st.info("Henüz takip edilen kanal yok. Yukarıdaki formdan bir yayıncı/oyun kanalı ekleyin.")
    else:
        for ch in tracked_channels:
            with st.container(border=True):
                col_i, col_act = st.columns([4, 1], vertical_alignment="center")
                with col_i:
                    st.markdown(f"🎮 **{ch['name']}** — `{ch['url']}`")
                    pl_text = f" | Playlist: **{ch.get('target_playlist')}**" if ch.get('target_playlist') else ""
                    last_chk = ch.get("last_checked") or "Henüz taranmadı"
                    st.caption(f"Min Skor: **{ch['min_score']}** | Otomatik Yükleme: **{'Açık' if ch['auto_upload'] else 'Kapalı'}** | Son Kontrol: **{last_chk}**{pl_text}")
                with col_act:
                    if st.button("🗑️ Sil", key=f"del_ch_{ch['id']}", use_container_width=True):
                        autopilot.remove_channel(ch["id"])
                        st.success(f"'{ch['name']}' silindi.")
                        st.rerun()

# ------------------------------------------------------------------
# TAB 2: ZAMANLANMIŞ KUYRUK & STOK
# ------------------------------------------------------------------
with tab_queue:
    st.subheader("Otomatik Klip Kuyruğu", anchor=False)

    col_btn, col_help = st.columns([2, 3], vertical_alignment="center")
    with col_btn:
        if st.button("⚡ Tüm Kanalları Şimdi Tara ve İşle", type="primary", use_container_width=True):
            with st.status("AutoPilot döngüsü çalışıyor…", expanded=True) as status:
                def ui_progress(msg: str):
                    st.write(msg)
                
                res = autopilot.run_cycle(progress_callback=ui_progress)
                status.update(label=f"Döngü tamamlandı! {res['clips_stockpiled']} klip stoklandı, {res['clips_scheduled']} yüklendi.", state="complete")
            st.rerun()

    with col_help:
        st.caption("Bot tüm kanallardaki yeni videoları kontrol eder, $\\ge 90$ puanlı anları kesip planlar.")

    if not queue_items:
        st.info("Kuyrukta henüz klip yok. Kanallar tarandıkça burası otomatik dolacaktır.")
    else:
        for item in queue_items:
            with st.container(border=True):
                col_q_thumb, col_q_info, col_q_status = st.columns([2, 4, 2], vertical_alignment="center")
                
                with col_q_thumb:
                    thumb = item.get("thumbnail_path")
                    if thumb and os.path.exists(thumb):
                        st.image(thumb, width="stretch")
                    else:
                        st.image("https://via.placeholder.com/320x180.png?text=Shorts+Klip", width="stretch")


                with col_q_info:
                    st.markdown(f"**{item['title']}**")
                    sched = item.get("scheduled_at", "")
                    try:
                        dt = datetime.datetime.fromisoformat(sched.replace("Z", "+00:00")) + datetime.timedelta(hours=3)
                        sched_formatted = dt.strftime("%d %B %Y - %H:%M")
                    except Exception:
                        sched_formatted = sched
                    st.caption(f"🎯 Viral Skor: **%{item['viral_score']}** | Planlanan Saat: **{sched_formatted}**")
                    if item.get("youtube_url"):
                        st.markdown(f"[🔗 YouTube Shorts'ta Görüntüle]({item['youtube_url']})")

                with col_q_status:
                    stt = item.get("status", "QUEUED")
                    if stt == "SCHEDULED":
                        st.success("⏰ Zamanlandı", icon=":material/schedule:")
                    elif stt == "PUBLISHED":
                        st.info("✅ Yayında", icon=":material/check_circle:")
                    elif stt == "FAILED":
                        st.error("❌ Hata", icon=":material/error:")
                    else:
                        st.warning("📦 Stokta", icon=":material/inventory_2:")

# ------------------------------------------------------------------
# TAB 3: YAYIN SAATLERİ & AYARLAR
# ------------------------------------------------------------------
with tab_settings:
    st.subheader("Günlük Shorts Yayın Saatleri (Slotlar)", anchor=False)
    st.markdown("""
    YouTube algoritmasında en yüksek etkileşimi almak için Türkiye gaming saatleri:
    - **1. Slot: 13:00** (Öğle molası)
    - **2. Slot: 18:00** (Okul/İş çıkışı)
    - **3. Slot: 22:00** (Gaming prime-time)
    """)

    current_slots = ", ".join(autopilot.daily_slots)
    st.info(f"Aktif Paylaşım Saatleri: **{current_slots}** (Türkiye Saati UTC+3)", icon=":material/alarm:")

    st.subheader("Sistem Dayanıklılığı", anchor=False)
    st.markdown("""
    - **Deduplication:** Aynı YouTube videosu asla 2 kez indirilmez veya işlenmez.
    - **Kalite Eşiği:** Sadece $\\ge 90$ viral skorlu anlar kesilir.
    - **Otomatik Zaman Öteleme:** Bugünün saatleri dolduysa sıradaki klipler ertesi güne aktarılır.
    """)
