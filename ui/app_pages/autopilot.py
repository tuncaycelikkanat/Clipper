"""
ui/app_pages/autopilot.py — Otonom Bot Kontrol Merkezi (AutoPilot)

Takip edilen YouTube kanallarını listeler, yeni video geldiğinde viral skoru >= 90
olan anları otomatik stoklar ve Türkiye gaming saatlerine (11:30, 15:30, 19:00, 22:30)
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
# 7/24 Arka Plan Nöbetçisi (Daemon) Kontrolü
# ------------------------------------------------------------------
with st.container(border=True):
    col_w1, col_w2, col_w3 = st.columns([4, 2, 2], vertical_alignment="center")
    worker_info = AutoPilotManager.get_background_worker_info()
    is_running = worker_info.get("running", False)

    with col_w1:
        st.markdown("### 🤖 7/24 Otonom Arka Plan Nöbetçisi")
        if is_running:
            st.caption(f"🟢 **Aktif:** Bot arka planda {worker_info.get('interval_hours', 2)} saatte bir kanalları otomatik tarayıp yeni videoları işliyor.")
        else:
            st.caption("🔴 **Durduruldu:** Otomatik arka plan taraması kapalı. Başlatırsanız yeni videolar otomatik işlenir.")

    with col_w2:
        interval_choice = st.selectbox(
            "Kontrol Sıklığı",
            options=[1.0, 2.0, 4.0, 6.0, 12.0],
            index=1,
            format_func=lambda x: f"Her {int(x)} Saatte Bir",
            disabled=is_running,
            label_visibility="collapsed",
        )

    with col_w3:
        if not is_running:
            if st.button("▶️ Nöbetçiyi Başlat", type="primary", use_container_width=True):
                AutoPilotManager.start_background_worker(interval_hours=interval_choice, db=db)
                st.success("7/24 Nöbetçi başlatıldı!")
                st.rerun()
        else:
            if st.button("⏸️ Nöbetçiyi Durdur", type="secondary", use_container_width=True):
                AutoPilotManager.stop_background_worker()
                st.warning("Nöbetçi durduruldu.")
                st.rerun()

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
                col_i, col_tog, col_act = st.columns([3.5, 1.2, 0.8], vertical_alignment="center")
                with col_i:
                    st.markdown(f"🎮 **{ch['name']}** — `{ch['url']}`")
                    pl_text = f" | Playlist: **{ch.get('target_playlist')}**" if ch.get('target_playlist') else ""
                    last_chk = ch.get("last_checked") or "Henüz taranmadı"
                    st.caption(f"Min Skor: **{ch['min_score']}** | Son Kontrol: **{last_chk}**{pl_text}")
                with col_tog:
                    is_act = bool(ch.get("active", 1))
                    new_act = st.toggle("Aktif", value=is_act, key=f"tog_ch_{ch['id']}", help="Bu kanalın otomatik taranmasını aç/kapat")
                    if new_act != is_act:
                        with db._connect() as conn:
                            conn.execute("UPDATE tracked_channels SET active=? WHERE id=?", (1 if new_act else 0, ch["id"]))
                            conn.commit()
                        st.toast(f"'{ch['name']}' {'Aktif edildi' if new_act else 'Devre dışı bırakıldı'}")
                        st.rerun()
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
    
    # Bekleyen Videoları Göster & Yönet
    with db._connect() as conn:
        pending_rows = conn.execute("SELECT id, title, url FROM videos WHERE status='pending'").fetchall()
    if pending_rows:
        st.info(f"⏳ Fabrika (Render) için bekleyen **{len(pending_rows)} adet** taze video var! Hemen işleyebilir veya istemediklerini listeden silebilirsin.")
        with st.expander("👀 Bekleyen Videoları Gör & Yönet", expanded=False):
            for p_id, p_title, p_url in pending_rows:
                p_col1, p_col2, p_col3 = st.columns([3.8, 1.4, 0.8], vertical_alignment="center")
                with p_col1:
                    st.markdown(f"🎬 **{p_title}**")
                with p_col2:
                    video_link = p_url or f"https://www.youtube.com/watch?v={p_id}"
                    st.markdown(f"[🔗 YouTube'da Aç]({video_link})")
                with p_col3:
                    if st.button("🗑️ Sil", key=f"del_pending_{p_id}", use_container_width=True, help="Bu videoyu bekleme listesinden çıkar"):
                        with db._connect() as conn:
                            conn.execute("DELETE FROM videos WHERE id=?", (p_id,))
                            conn.commit()
                        st.toast("Video bekleme listesinden silindi!", icon="🗑️")
                        st.rerun()
            st.divider()
            if st.button("🧹 Tüm Bekleyenleri Temizle", type="secondary", use_container_width=True):
                with db._connect() as conn:
                    conn.execute("DELETE FROM videos WHERE status='pending'")
                    conn.commit()
                st.toast("Tüm bekleyen videolar temizlendi!", icon="🧹")
                st.rerun()
    else:
        st.success("Tüm videolar işlendi, kuyrukta bekleyen yeni video yok. Önce tarama yapmalısın.")
    st.divider()


    col_limit, col_sub, col_btn1, col_btn2, col_help = st.columns([1.6, 1.3, 1.2, 1.3, 1.6], vertical_alignment="bottom")
    with col_limit:
        process_limit = st.slider(
            "İşlenecek Video Limiti",
            min_value=1,
            max_value=15,
            value=5,
            step=1,
            help="Tek seferde arka arkaya işlenecek (render edilecek) maksimum video adedi (1 - 15)."
        )
    with col_sub:
        add_subtitles = st.toggle(
            "💬 Altyazı Ekle",
            value=False,
            help="Kliplere otomatik kelime senkronlu karaoke altyazı ekler. Kapalıyken (varsayılan) temiz ve yazısız klip üretilir."
        )
    with col_btn1:
        if st.button("⚡ Kanalları Tara", type="primary", width="stretch", help="Sadece tarama yapar, yeni videoları 'Bekliyor' listesine ekler."):
            with st.status("Kanallar taranıyor…", expanded=True) as status:
                def ui_progress(msg: str):
                    st.write(msg)
                
                res = autopilot.run_cycle(progress_callback=ui_progress)
                status.update(label=f"Tarama tamamlandı! {res.get('new_videos_found', 0)} yeni video beklemeye alındı.", state="complete")
            st.rerun()

    with col_btn2:
        if st.button("⚙️ Bekleyenleri İşle", type="primary", width="stretch", help=f"Bekleyen en fazla {process_limit} videoyu alır ve renderlayarak takvime atar."):
            with st.status(f"Videolar işleniyor (Maks {process_limit} video, Altyazı: {'Açık' if add_subtitles else 'Kapalı'})…", expanded=True) as status:
                def ui_progress(msg: str):
                    st.write(msg)
                
                res = autopilot.process_pending_videos(max_videos=process_limit, add_subtitles=add_subtitles, progress_callback=ui_progress)
                status.update(label=f"İşlem tamamlandı! {res.get('processed', 0)} video kesildi.", state="complete")
            st.rerun()

    with col_help:
        st.caption(f"Seçili Limit: **{process_limit} video** | Altyazı: **{'Açık' if add_subtitles else 'Kapalı'}**")
        if st.button("🧱 Eski İşlenmiş Videoları Anchor'a Aktar", width="stretch",
                     help="Daha önce işlenmiş videoları kanal başına 'işlendi' tablosuna geriye dönük kaydeder; böylece bir sonraki taramada yalnızca gerçekten yeni videolar yakalanır."):
            with st.status("Eski videolar anchor tablosuna aktarılıyor…", expanded=True) as status:
                def bf_progress(msg: str):
                    st.write(msg)
                bf_res = autopilot.backfill_processed_videos(progress_callback=bf_progress)
                status.update(label=f"Anchor aktarımı bitti: {bf_res['recorded']} eski video işaretlendi.", state="complete")
            st.rerun()

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
    YouTube ve Instagram algoritmasında en yüksek etkileşimi almak için Türkiye gaming saatleri:
    - **1. Slot: 11:30** (Öğle öncesi / Kahve molası)
    - **2. Slot: 15:30** (Okul & İş çıkışı)
    - **3. Slot: 19:00** (Prime-time / Akşam zirvesi)
    - **4. Slot: 22:30** (Gece kuşları / Yatak öncesi scroll)
    """)

    current_slots = ", ".join(autopilot.daily_slots)
    st.info(f"Aktif Paylaşım Saatleri: **{current_slots}** (Türkiye Saati UTC+3)", icon=":material/alarm:")

    st.subheader("Sistem Dayanıklılığı", anchor=False)
    st.markdown("""
    - **Deduplication:** Aynı YouTube videosu asla 2 kez indirilmez veya işlenmez.
    - **Kalite Eşiği:** Sadece $\\ge 90$ viral skorlu anlar kesilir.
    - **Otomatik Zaman Öteleme:** Bugünün saatleri dolduysa sıradaki klipler ertesi güne aktarılır.
    """)

    st.subheader("🧹 Veritabanı Bakımı", anchor=False)
    st.warning(
        "Bu işlem **gelecekte planlı** kuyruk öğelerini ve ilişkili videolar/klipler/renderları "
        "korur; takip edilen kanallara dokunmaz. Geri kalan tüm videolar, klipler, renderlar ve "
        "heatmap desenleri silinir. YouTube'a yüklenmiş videolar ile korunan planlı videolar "
        "'işlenmiş' (anchor) listesine eklenir; böylece yeniden işlenmezler.",
        icon=":material/warning:",
    )
    confirm_cleanup = st.checkbox(
        "Yukarıdaki temizliği anladım ve gerçekleştirmek istiyorum.",
        key="confirm_cleanup",
    )
    if st.button("🧹 Planlı Olanları Koruyarak Temizle", type="primary", use_container_width=True, disabled=not confirm_cleanup):
        with st.status("Veritabanı temizleniyor…", expanded=True) as status:
            res = db.cleanup_keep_planned()
            status.update(
                label=f"Temizlendi! Korunan: {res['kept_queue']} kuyruk / {res['kept_videos']} video / "
                      f"{res['kept_clips']} klip · Anchor'a eklenen: {res['anchors_added']}",
                state="complete",
            )
        st.rerun()
