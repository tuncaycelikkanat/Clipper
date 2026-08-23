"""
ui/app_pages/planner.py — Yayın Takvimi & Akıllı Boşluk Doldurmalı Planlayıcı

Gün gün kaydırmalı takvim üzerinden planlanan YouTube Shorts videolarını gösterir.
Bir video silindiğinde arkasındaki tüm videolar takvimdeki boşluğu doldurmak için
otomatik olarak 1 slot öne kayar.
"""

import datetime
import os
from pathlib import Path
import streamlit as st

from core.autopilot import AutoPilotManager
from core.database import DatabaseManager

db = DatabaseManager()
db.init_db()
autopilot = AutoPilotManager(db=db)

st.header("📅 Yayın Takvimi & Planlayıcı", anchor=False)
st.caption("Gün gün planlanan Shorts videolarını görüntüleyin. Silinen videoların yerine sıradaki klipler otomatik kayarak boşlukları doldurur.")

# ------------------------------------------------------------------
# Gelecek 14 Günlük Takvim Verisi
# ------------------------------------------------------------------
days_data = autopilot.get_calendar_days_data(days_ahead=14)

total_scheduled = sum(d["item_count"] for d in days_data)
active_days_count = sum(1 for d in days_data if d["item_count"] > 0)

col_m1, col_m2, col_m3 = st.columns(3)
with col_m1:
    st.metric("Toplam Planlanan Shorts", f"{total_scheduled} Video")
with col_m2:
    st.metric("Dolu Gün Sayısı (14 Gün İçinde)", f"{active_days_count} Gün")
with col_m3:
    st.metric("Günlük Paylaşım Slotları", "13:00 / 18:00 / 22:00")

col_sync1, col_sync2 = st.columns([2.5, 1.5], vertical_alignment="center")
with col_sync1:
    st.info("💡 YouTube'a planlanmış klipleri **Instagram Reels (@tuncaysclips)** ve **TikTok** hesaplarına senkronlayabilirsiniz.")
with col_sync2:
    if st.button("📥 YouTube'dan Aktar", icon=":material/download:", width="stretch", help="YouTube kanalınızda zaten planlanmış olan tüm Shorts videolarını takvime çeker."):
        with st.spinner("YouTube kanalındaki videolar taranıyor…"):
            n = autopilot.sync_from_youtube_channel()
            st.success(f"{n} adet YouTube Shorts videosu takvime aktarıldı!")
            st.rerun()

# ------------------------------------------------------------------
# 7/24 Otomatik Zamanlayıcı & Nöbetçi Kartı
# ------------------------------------------------------------------

worker_info = AutoPilotManager.get_background_worker_info()
is_worker_running = worker_info.get("running", False)

sched_box = st.container(border=True)
with sched_box:
    s_col1, s_col2, s_col3 = st.columns([2.5, 1.2, 1.0], vertical_alignment="center")
    with s_col1:
        st.markdown(
            f"**⏰ 7/24 Sosyal Medya Zamanlayıcısı:** "
            f"{'🟢 **Aktif (Her 15 dk kontrol)**' if is_worker_running else '⚪ **Durduruldu**'}"
        )
        st.caption(
            "YouTube'da planlanan videonun günü ve saati (13:00 / 18:00 / 22:00) geldiğinde "
            "bu nöbetçi videoyu otomatik olarak **Instagram Reels**'e tam vaktinde yükler."
        )
    with s_col2:
        if is_worker_running:
            if st.button("⏹️ Nöbetçiyi Durdur", type="secondary", width="stretch"):
                AutoPilotManager.stop_background_worker()
                st.toast("Zamanlayıcı durduruldu.", icon="⏸️")
                st.rerun()
        else:
            if st.button("▶️ Nöbetçiyi Başlat", type="primary", width="stretch"):
                AutoPilotManager.start_background_worker(interval_hours=0.25, db=db)
                st.toast("7/24 Otomatik zamanlayıcı başlatıldı!", icon="🚀")
                st.rerun()
    with s_col3:
        if st.button("⚡ Şimdi Kontrol Et", help="Saati gelmiş videolar varsa hemen Instagram'a atar", width="stretch"):
            with st.spinner("Zamanı gelmiş videolar kontrol ediliyor…"):
                pub_cnt = autopilot.publish_due_socials()
                if pub_cnt > 0:
                    st.success(f"{pub_cnt} adet videonun saati gelmişti ve Instagram'a yüklendi!")
                else:
                    st.info("Şu an için saati gelmiş bekleyen video yok.")
                st.rerun()

st.divider()




# ------------------------------------------------------------------
# Üst Kısım: Gün Gün Kaydırmalı Seçici
# ------------------------------------------------------------------
st.subheader("🗓️ Gün Seçimi", anchor=False)

pill_options = list(range(len(days_data)))
def format_pill(idx: int) -> str:
    d = days_data[idx]
    badge = f"({d['item_count']} Video)" if d['item_count'] > 0 else "(Boş)"
    return f"{d['label']}  {badge}"

# Default to first day or first day with items
default_idx = 0
for i, d in enumerate(days_data):
    if d["item_count"] > 0:
        default_idx = i
        break

selected_idx = st.pills(
    "Takvim Günleri",
    options=pill_options,
    default=default_idx,
    format_func=format_pill,
    label_visibility="collapsed",
)

if selected_idx is None:
    selected_idx = 0

selected_day = days_data[selected_idx]
items = selected_day["items"]

st.divider()

# ------------------------------------------------------------------
# Alt Kısım: Seçilen Günün Detayları
# ------------------------------------------------------------------
st.subheader(f"📌 {selected_day['label']} Planlanan Yayınlar ({len(items)} Video)", anchor=False)

if not items:
    st.info(f"📭 **{selected_day['label']}** için henüz planlanmış video bulunmuyor. Otonom bot yeni klipler buldukça burayı sırayla dolduracaktır.", icon=":material/event_busy:")
else:
    for item in items:
        with st.container(border=True):
            col_thumb, col_details, col_actions = st.columns([2, 5, 2], vertical_alignment="center")

            # 1. Thumbnail
            with col_thumb:
                thumb = item.get("thumbnail_path")
                if thumb and os.path.exists(thumb):
                    st.image(thumb, width="stretch")
                else:
                    st.image("https://via.placeholder.com/320x180.png?text=Shorts+Klip", width="stretch")


            # 2. Video Detayları
            with col_details:
                st.markdown(f"### {item.get('title', 'Klip Başlığı')}")
                local_time = item.get("local_time", "Belirsiz")
                score = item.get("viral_score", 90)
                status = item.get("status", "QUEUED")
                yt_url = item.get("youtube_url")

                # Rozetler
                badge_str = f"⏰ **Saat: {local_time}** | 🔥 Viral Skoru: **%{score}**"
                if status == "SCHEDULED":
                    badge_str += " | 🟢 **YouTube'da Planlandı**"
                elif status == "PUBLISHED":
                    badge_str += " | 🔵 **Yayında**"
                else:
                    badge_str += " | 🟡 **Stokta Bekliyor**"

                st.markdown(badge_str)
                if yt_url:
                    st.markdown(f"[🔗 YouTube Shorts Bağlantısı]({yt_url})")

            # 3. Aksiyonlar & Akıllı Boşluk Doldurma
            with col_actions:
                st.write("")
                if st.button("🗑️ Sil & Boşluğu Doldur", key=f"del_plan_{item['id']}", type="secondary", use_container_width=True):
                    res = autopilot.remove_and_refill_gap(item["id"])
                    if res["success"]:
                        st.success(f"✅ '{res['deleted_title']}' silindi! Takvimdeki boşluğu kapatmak için sıradaki {res['shifted_count']} video 1 slot öne kaydırıldı.")
                        st.rerun()
                    else:
                        st.error(res.get("error", "Silme işlemi başarısız."))
