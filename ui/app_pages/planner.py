"""
ui/app_pages/planner.py — İnteraktif Görsel Slot Takvimi & Kütüphane Yönetim Masası
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

st.header("📅 İnteraktif Yayın Takvimi & Slot Masası", anchor=False)
st.caption("Günlük 4 yayın slotunu yönetin, klipleri sürükleyip taşıyın, havuza çekin veya kanalları akıllıca karıştırın.")

# ------------------------------------------------------------------
# Gelecek 14 Günlük Takvim Verisi
# ------------------------------------------------------------------
days_data = autopilot.get_calendar_days_data(days_ahead=14)
pool_clips = db.get_pool_clips()

total_scheduled = sum(d["item_count"] for d in days_data)
active_days_count = sum(1 for d in days_data if d["item_count"] > 0)

col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1:
    st.metric("Toplam Planlanan Shorts", f"{total_scheduled} Video")
with col_m2:
    st.metric("Dolu Gün Sayısı", f"{active_days_count} / 14 Gün")
with col_m3:
    st.metric("Günlük Paylaşım Slotları", "11:30 / 15:30 / 19:00 / 22:30")
with col_m4:
    st.metric("Havuzdaki Yedek Klipler", f"{len(pool_clips)} Klip")

# ------------------------------------------------------------------
# Üst Araç Çubuğu: Nöbetçi + Shuffle (Karıştır)
# ------------------------------------------------------------------
worker_info = AutoPilotManager.get_background_worker_info()
is_worker_running = worker_info.get("running", False)

tool_box = st.container(border=True)
with tool_box:
    t_col1, t_col2, t_col3 = st.columns([2.5, 1.2, 1.3], vertical_alignment="center")
    with t_col1:
        st.markdown(
            f"**⏰ 7/24 Sosyal Medya Nöbetçisi:** "
            f"{'🟢 **Aktif (Her 5 dk kontrol)**' if is_worker_running else '⚪ **Durduruldu**'}"
        )
        st.caption("Slot saatleri (11:30 / 15:30 / 19:00 / 22:30) geldiğinde klipleri otomatik YouTube & Instagram'a yükler.")
    
    with t_col2:
        if is_worker_running:
            if st.button("⏹️ Nöbetçiyi Durdur", type="secondary", use_container_width=True):
                AutoPilotManager.stop_background_worker()
                st.toast("Zamanlayıcı durduruldu.", icon="⏸️")
                st.rerun()
        else:
            if st.button("▶️ Nöbetçiyi Başlat", type="primary", use_container_width=True):
                AutoPilotManager.start_background_worker(interval_hours=0.083, db=db)
                st.toast("7/24 Otomatik zamanlayıcı başlatıldı!", icon="🚀")
                st.rerun()
                
    with t_col3:
        with st.popover("🎲 Akıllı Karıştır (Shuffle)", use_container_width=True):
            st.markdown("#### 🎲 Anti-Monotony Shuffle")
            st.caption("Aynı kanalın videolarının peş peşe gelmesini engeller, günleri eşit ve karışık olarak çeşitlendirir.")
            
            all_date_strs = [d["date_str"] for d in days_data if d["item_count"] > 0]
            selected_shuffle_dates = st.multiselect(
                "Karıştırılacak Günler",
                options=[d["date_str"] for d in days_data],
                default=all_date_strs,
                format_func=lambda x: next((d["label"] for d in days_data if d["date_str"] == x), x),
            )
            
            if st.button("🎲 Seçili Günleri Karıştır", type="primary", use_container_width=True, disabled=not selected_shuffle_dates):
                with st.spinner("Klipler akıllıca çeşitlendirilerek karıştırılıyor…"):
                    s_res = autopilot.diversified_shuffle(selected_shuffle_dates)
                    st.toast(s_res.get("message", "Karıştırıldı!"), icon="🎲")
                    st.rerun()

st.divider()

# ------------------------------------------------------------------
# 1. Yatay Kaydırılabilir Gün Seçim Barı
# ------------------------------------------------------------------
st.subheader("🗓️ Gün Seçimi", anchor=False)

pill_options = list(range(len(days_data)))
def format_pill(idx: int) -> str:
    d = days_data[idx]
    badge = f"({d['item_count']}/4)" if d['item_count'] > 0 else "(Boş)"
    return f"{d['label']}  {badge}"

# Session state date
if "selected_day_idx" not in st.session_state:
    st.session_state.selected_day_idx = 0

selected_idx = st.pills(
    "Takvim Günleri",
    options=pill_options,
    default=st.session_state.selected_day_idx,
    format_func=format_pill,
    label_visibility="collapsed",
)

if selected_idx is None:
    selected_idx = 0
st.session_state.selected_day_idx = selected_idx

selected_day = days_data[selected_idx]
cur_date_str = selected_day["date_str"]

# ------------------------------------------------------------------
# 2. Seçili Günün 4 Görsel Slot Kartı (Dikdörtgen Grid)
# ------------------------------------------------------------------
st.subheader(f"📌 {selected_day['label']} — Yayın Slotları ({selected_day['item_count']}/4 Dolu)", anchor=False)

day_grid = autopilot.get_day_slots_grid(cur_date_str)
slot_cols = st.columns(4)

for col_idx, (slot_time, item) in enumerate(day_grid.items()):
    with slot_cols[col_idx]:
        slot_container = st.container(border=True)
        with slot_container:
            st.markdown(f"### ⏰ {slot_time}")
            
            if item:
                # Dolu Slot
                thumb = item.get("thumbnail_path")
                if thumb and os.path.exists(thumb):
                    st.image(thumb, use_container_width=True)
                else:
                    st.image("https://via.placeholder.com/320x180.png?text=Shorts+Klip", use_container_width=True)
                
                st.markdown(f"**{item.get('title', 'Klip Başlığı')}**")
                
                score = item.get("viral_score", 90)
                status = item.get("status", "QUEUED")
                
                if status == "SCHEDULED":
                    st.success("🟢 YouTube'da Planlandı", icon=":material/schedule:")
                elif status == "PUBLISHED":
                    st.info("🔵 Yayında", icon=":material/check_circle:")
                else:
                    st.warning(f"🟡 Sırada (Skor: %{score})", icon=":material/inventory_2:")
                
                render_path = item.get("render_path")
                if render_path and os.path.exists(render_path):
                    with st.popover("🎬 Önizle", use_container_width=True):
                        st.video(render_path)
                
                # Aksiyonlar: Havuza Çek veya Başka Slota Taşı
                btn_c1, btn_c2 = st.columns(2)
                with btn_c1:
                    if st.button("⬇️ Havuza", key=f"unassign_{item['id']}", help="Bu klibi slottan çıkarıp yedek havuzuna çeker", use_container_width=True):
                        db.unassign_clip_to_pool(item["id"])
                        st.toast("Klip yedek havuzuna çekildi!", icon="⬇️")
                        st.rerun()
                
                with btn_c2:
                    with st.popover("🔄 Taşı", use_container_width=True):
                        st.markdown("##### 🔄 Klibi Başka Slota Taşı")
                        st.caption("Hedef gün ve slot seçin:")
                        
                        target_day_str = st.selectbox(
                            "Hedef Gün",
                            options=[d["date_str"] for d in days_data],
                            format_func=lambda x: next((d["label"] for d in days_data if d["date_str"] == x), x),
                            key=f"target_day_{item['id']}"
                        )
                        target_slot_str = st.selectbox(
                            "Hedef Slot",
                            options=["11:30", "15:30", "19:00", "22:30"],
                            key=f"target_slot_{item['id']}"
                        )
                        
                        if st.button("Onayla & Taşı", key=f"confirm_move_{item['id']}", type="primary", use_container_width=True):
                            autopilot.assign_clip_to_date_slot(item["id"], target_day_str, target_slot_str)
                            st.toast("Klip yeni slotuna başarıyla taşındı!", icon="✅")
                            st.rerun()
                            
            else:
                # Boş Slot
                st.info("📭 Bu slot boş!", icon=":material/inbox:")
                st.caption("Aşağıdaki havuzdan bir klip yerleştirebilirsiniz.")
                
                if pool_clips:
                    with st.popover("➕ Klip Ata", use_container_width=True):
                        st.markdown("##### ➕ Bu Slota Klip Yerleştir")
                        clip_opts = {c["id"]: f"{c.get('title', 'Klip')} (%{c.get('viral_score', 90)})" for c in pool_clips}
                        chosen_c_id = st.selectbox("Havuzdaki Klip", options=list(clip_opts.keys()), format_func=lambda x: clip_opts[x], key=f"assign_slot_{cur_date_str}_{slot_time}")
                        
                        if st.button("Slota Yerleştir", key=f"btn_assign_{cur_date_str}_{slot_time}", type="primary", use_container_width=True):
                            autopilot.assign_clip_to_date_slot(chosen_c_id, cur_date_str, slot_time)
                            st.toast(f"Klip {slot_time} slotuna yerleştirildi!", icon="🚀")
                            st.rerun()
                else:
                    st.caption("💡 Havuzda bekleyen yedek klip yok.")

st.divider()

# ------------------------------------------------------------------
# 3. Hazır Klipler Havuzu (Stok Kütüphanesi)
# ------------------------------------------------------------------
st.subheader(f"📦 Hazır Klipler Havuzu & Kütüphane ({len(pool_clips)} Yedek Klip)", anchor=False)
st.caption("Yayın takviminden boşa çıkarılan veya henüz bir slota atanmamış hazır klipler. Buradaki klipleri dilediğiniz günün boş slotuna yerleştirebilirsiniz.")

if not pool_clips:
    st.success("Tüm hazır klipler slotlara yerleştirildi, havuzda yedek klip yok. Slottan '⬇️ Havuza' diyerek bir klibi buraya alabilirsiniz.", icon=":material/task_alt:")
else:
    pool_cols = st.columns(3)
    for p_idx, p_clip in enumerate(pool_clips):
        with pool_cols[p_idx % 3]:
            with st.container(border=True):
                p_thumb = p_clip.get("thumbnail_path")
                if p_thumb and os.path.exists(p_thumb):
                    st.image(p_thumb, use_container_width=True)
                else:
                    st.image("https://via.placeholder.com/320x180.png?text=Havuz+Klibi", use_container_width=True)
                
                st.markdown(f"**{p_clip.get('title', 'Klip')}**")
                st.caption(f"🎯 Viral Skoru: **%{p_clip.get('viral_score', 90)}**")
                
                with st.popover("🎯 Bir Slota Yerleştir", use_container_width=True):
                    st.markdown("##### 🎯 Klibi Hedef Slota Ata")
                    target_d = st.selectbox(
                        "Gün",
                        options=[d["date_str"] for d in days_data],
                        format_func=lambda x: next((d["label"] for d in days_data if d["date_str"] == x), x),
                        key=f"pool_target_day_{p_clip['id']}"
                    )
                    target_s = st.selectbox(
                        "Slot Saati",
                        options=["11:30", "15:30", "19:00", "22:30"],
                        key=f"pool_target_slot_{p_clip['id']}"
                    )
                    
                    if st.button("Bu Slota Ata", key=f"btn_pool_assign_{p_clip['id']}", type="primary", use_container_width=True):
                        autopilot.assign_clip_to_date_slot(p_clip["id"], target_d, target_s)
                        st.toast(f"Klip {target_d} {target_s} slotuna atandı!", icon="🚀")
                        st.rerun()
                
                if st.button("🗑️ Havuzdan Tamamen Sil", key=f"del_pool_{p_clip['id']}", type="secondary", use_container_width=True):
                    with db._connect() as conn:
                        conn.execute("DELETE FROM autopilot_queue WHERE id = ?", (p_clip["id"],))
                        conn.commit()
                    st.toast("Klip havuzdan silindi.", icon="🗑️")
                    st.rerun()

