"""
ui/app_pages/detail.py — Detaylı Görünüm (Videolar / Kanallar / Clipler)

Tüm videolar, takip edilen kanallar ve üretilen klipler hakkında derinlemesine
ve filtrelenebilir bir bakış sunar. Her kayıt genişletilebilir (expander) kartlar
ile ilişkili alt verileri (klip -> video, video -> klipler & heatmap) gösterir.
"""

import os
import json
from datetime import datetime, timezone

import streamlit as st
import pandas as pd

from core.database import DatabaseManager

db = DatabaseManager()
db.init_db()

st.header("🔬 Detaylı Görünüm", anchor=False)
st.caption(
    "Tüm videolar, takip edilen kanallar ve üretilen klipler hakkında derinlemesine, "
    "ilişkisel ve filtrelenebilir bir bakış."
)

# ------------------------------------------------------------------
# Yardımcı sorgular
# ------------------------------------------------------------------

def _local_tz(dt_str, offset_hours=3):
    """UTC ISO zamanı Türkiye yerel saatine (UTC+3) çevirir, yoksa olduğu gibi döner."""
    if not dt_str:
        return "—"
    try:
        s = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc) + pd.Timedelta(hours=offset_hours)
        return dt.strftime("%d %b %Y %H:%M")
    except Exception:
        return str(dt_str)


def _load_all():
    """Tüm ilgili tabloları ve ilişkisel istatistikleri belleğe yükler."""
    with db._connect() as conn:
        videos_df = pd.read_sql_query(
            "SELECT * FROM videos ORDER BY processed_at DESC;", conn
        )
        clips_df = pd.read_sql_query(
            "SELECT * FROM clips ORDER BY created_at DESC;", conn
        )
        renders_df = pd.read_sql_query("SELECT * FROM renders;", conn)
        channels_df = pd.read_sql_query(
            "SELECT * FROM tracked_channels ORDER BY created_at DESC;", conn
        )
        queue_df = pd.read_sql_query(
            "SELECT * FROM autopilot_queue ORDER BY created_at DESC;", conn
        )
        processed_df = pd.read_sql_query(
            "SELECT channel_url, video_id FROM channel_processed_videos;", conn
        )
        heat_df = pd.read_sql_query(
            "SELECT * FROM heatmap_patterns;", conn
        )

    # Kanal başına işlenmiş video sayısı
    if not processed_df.empty:
        processed_counts = (
            processed_df.groupby("channel_url").size().reset_index(name="processed_count")
        )
    else:
        processed_counts = pd.DataFrame(columns=["channel_url", "processed_count"])

    # Kanal başına kuyruk istatistikleri
    if not queue_df.empty:
        queue_stats = queue_df.groupby("channel_url").agg(
            queued_total=("id", "count"),
            queued_scheduled=("status", lambda s: (s == "SCHEDULED").sum()),
            queued_published=("status", lambda s: (s == "PUBLISHED").sum()),
            queued_stock=("status", lambda s: (s == "QUEUED").sum()),
        ).reset_index()
    else:
        queue_stats = pd.DataFrame(columns=[
            "channel_url", "queued_total", "queued_scheduled",
            "queued_published", "queued_stock",
        ])

    # Video başına klip & render sayısı
    if not clips_df.empty:
        clip_counts = clips_df.groupby("video_id").size().reset_index(name="clip_count")
        # Toplam klip skoru ortalaması
        clip_scores = clips_df.groupby("video_id")["score"].mean().reset_index(name="avg_clip_score")
    else:
        clip_counts = pd.DataFrame(columns=["video_id", "clip_count"])
        clip_scores = pd.DataFrame(columns=["video_id", "avg_clip_score"])

    if not renders_df.empty:
        render_counts = renders_df.groupby("clip_id").size().reset_index(name="render_count")
    else:
        render_counts = pd.DataFrame(columns=["clip_id", "render_count"])

    return {
        "videos": videos_df,
        "clips": clips_df,
        "renders": renders_df,
        "channels": channels_df,
        "queue": queue_df,
        "processed_counts": processed_counts,
        "queue_stats": queue_stats,
        "clip_counts": clip_counts,
        "clip_scores": clip_scores,
        "render_counts": render_counts,
        "heat": heat_df,
    }


data = _load_all()
videos_df = data["videos"]
clips_df = data["clips"]
renders_df = data["renders"]
channels_df = data["channels"]
queue_df = data["queue"]
heat_df = data["heat"]

# ------------------------------------------------------------------
# Üst Metrikler
# ------------------------------------------------------------------
total_videos = len(videos_df)
total_clips = len(clips_df)
total_channels = len(channels_df)
total_processed = int(data["processed_counts"]["processed_count"].sum()) if not data["processed_counts"].empty else 0
total_renders = len(renders_df)
published = int((queue_df["status"] == "PUBLISHED").sum()) if not queue_df.empty else 0

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Toplam Video", f"{total_videos}")
m2.metric("İşlenmiş (Anchor)", f"{total_processed}")
m3.metric("Toplam Klip", f"{total_clips}")
m4.metric("Render", f"{total_renders}")
m5.metric("Takip Kanalı", f"{total_channels}")
m6.metric("Yayında (Shorts)", f"{published}")

st.divider()

# ------------------------------------------------------------------
# TABLAR
# ------------------------------------------------------------------
tab_channels, tab_videos, tab_clips = st.tabs([
    "📺 Kanallar (Detay)",
    "🎬 Videolar (Detay)",
    "✂️ Clipler (Detay)",
])

# ==================================================================
# TAB 1: KANALLAR
# ==================================================================
with tab_channels:
    if channels_df.empty:
        st.info("Henüz takip edilen kanal yok.", icon=":material/info:")
    else:
        for _, ch in channels_df.iterrows():
            ch_url = ch["url"]
            pc = data["processed_counts"]
            qs = data["queue_stats"]
            processed_n = int(pc[pc["channel_url"] == ch_url]["processed_count"].sum()) if not pc.empty else 0
            qrow = qs[qs["channel_url"] == ch_url]
            q_total = int(qrow["queued_total"].sum()) if not qrow.empty else 0
            q_sched = int(qrow["queued_scheduled"].sum()) if not qrow.empty else 0
            q_pub = int(qrow["queued_published"].sum()) if not qrow.empty else 0
            q_stock = int(qrow["queued_stock"].sum()) if not qrow.empty else 0

            active = bool(ch.get("active", 1))
            status_badge = "🟢 Aktif" if active else "🔴 Pasif"

            with st.expander(f"🎮 **{ch['name']}**  ·  {status_badge}  ·  {processed_n} işlenmiş video", expanded=False):
                col_a, col_b = st.columns([2, 2])
                with col_a:
                    st.markdown("**Genel**")
                    st.markdown(f"- URL: `{ch_url}`")
                    st.markdown(f"- Min. Viral Skor: **{ch.get('min_score', 90)}**")
                    st.markdown(f"- Otomatik Yükleme: **{'Açık' if ch.get('auto_upload') else 'Kapalı'}**")
                    st.markdown(f"- Hedef Playlist: `{ch.get('target_playlist') or 'Yok'}`")
                    st.markdown(f"- Oluşturulma: {_local_tz(ch.get('created_at'))}")
                    st.markdown(f"- Son Kontrol: {_local_tz(ch.get('last_checked'))}")
                with col_b:
                    st.markdown("**İstatistikler**")
                    st.markdown(f"- İşlenmiş Video (anchor): **{processed_n}**")
                    st.markdown(f"- Kuyruktaki Toplam Klip: **{q_total}**")
                    st.markdown(f"  - 📦 Stokta: **{q_stock}**")
                    st.markdown(f"  - ⏰ Zamanlanmış: **{q_sched}**")
                    st.markdown(f"  - ✅ Yayında: **{q_pub}**")

                # Bu kanalda işlenmiş videoların listesi
                with db._connect() as conn:
                    ch_vids = pd.read_sql_query(
                        "SELECT video_id, title, processed_at FROM channel_processed_videos "
                        "WHERE channel_url = ? ORDER BY processed_at DESC;",
                        conn, params=(ch_url,),
                    )
                if not ch_vids.empty:
                    st.markdown("**Bu Kanalda İşlenmiş Videolar**")
                    st.dataframe(
                        ch_vids.assign(
                            processed_at=ch_vids["processed_at"].map(_local_tz)
                        ).rename(columns={
                            "video_id": "Video ID",
                            "title": "Başlık",
                            "processed_at": "İşlenme Zamanı",
                        }),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.caption("Bu kanal için henüz anchor kaydı yok.")

# ==================================================================
# TAB 2: VIDEOLAR
# ==================================================================
with tab_videos:
    if videos_df.empty:
        st.info("Veritabanında henüz kayıtlı video yok.", icon=":material/info:")
    else:
        # Filtreler
        with st.container(border=True):
            fcol1, fcol2, fcol3 = st.columns(3)
            with fcol1:
                search = st.text_input("Başlık / Uploader Ara", placeholder="örn: Mithrain", key="vid_search")
            with fcol2:
                status_opts = ["Tümü"] + sorted(videos_df["status"].dropna().unique().tolist())
                status_filter = st.selectbox("Duruma Göre Filtrele", status_opts)
            with fcol3:
                uploaders = ["Tümü"] + sorted(videos_df["uploader"].dropna().unique().tolist())
                uploader_filter = st.selectbox("Kanala (Uploader) Göre", uploaders)

        vdf = videos_df.copy()
        if search:
            mask = vdf["title"].astype(str).str.contains(search, case=False, na=False) | \
                   vdf["uploader"].astype(str).str.contains(search, case=False, na=False)
            vdf = vdf[mask]
        if status_filter != "Tümü":
            vdf = vdf[vdf["status"] == status_filter]
        if uploader_filter != "Tümü":
            vdf = vdf[vdf["uploader"] == uploader_filter]

        st.caption(f"**{len(vdf)}** video listeleniyor.")

        # Genel özet tablo
        vdf = vdf.merge(data["clip_counts"], left_on="id", right_on="video_id", how="left")
        vdf = vdf.merge(data["clip_scores"], left_on="id", right_on="video_id", how="left")
        vdf["clip_count"] = vdf["clip_count"].fillna(0).astype(int)
        vdf["avg_clip_score"] = vdf["avg_clip_score"].round(1)

        summary = vdf[[
            "title", "uploader", "duration", "view_count", "status",
            "has_heatmap", "clip_count", "avg_clip_score", "processed_at",
        ]].rename(columns={
            "title": "Başlık", "uploader": "Kanal", "duration": "Süre (sn)",
            "view_count": "İzlenme", "status": "Durum", "has_heatmap": "Heatmap?",
            "clip_count": "# Klip", "avg_clip_score": "Ort. Klip Skoru",
            "processed_at": "İşlenme",
        })
        summary["İşlenme"] = summary["İşlenme"].map(_local_tz)
        summary["Heatmap?"] = summary["Heatmap?"].map(lambda x: "✅" if x else "❌")
        st.dataframe(summary, use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("### Video Detayları (Genişletilebilir)")
        for _, vid in vdf.iterrows():
            vid_id = vid["id"]
            with st.expander(f"🎬 **{vid.get('title', 'Başlıksız')}**  ·  {vid.get('uploader', '?')}  ·  {int(vid.get('clip_count', 0))} klip", expanded=False):
                col_v1, col_v2 = st.columns([2, 2])
                with col_v1:
                    st.markdown("**Metadata**")
                    st.markdown(f"- ID: `{vid_id}`")
                    st.markdown(f"- URL: {vid.get('url', '—')}")
                    st.markdown(f"- Süre: **{vid.get('duration', 0)} sn**")
                    st.markdown(f"- İzlenme: **{vid.get('view_count', 0)}**")
                    st.markdown(f"- Durum: **{vid.get('status', '?')}**")
                    st.markdown(f"- Heatmap: **{'Var' if vid.get('has_heatmap') else 'Yok'}**")
                    st.markdown(f"- İşlenme: {_local_tz(vid.get('processed_at'))}")
                with col_v2:
                    st.markdown("**Açıklama & Etiketler**")
                    desc = vid.get("description") or "—"
                    if len(str(desc)) > 400:
                        desc = str(desc)[:400] + "…"
                    st.caption(desc)
                    tags = vid.get("tags")
                    if tags and str(tags).startswith("["):
                        try:
                            tag_list = json.loads(tags)
                            st.markdown("Etiketler: " + " ".join(f"`{t}`" for t in tag_list))
                        except Exception:
                            pass

                # Bu videonun klipleri
                vclips = clips_df[clips_df["video_id"] == vid_id]
                if not vclips.empty:
                    st.markdown(f"**Bu Videodan Üretilen Klipler ({len(vclips)})**")
                    clip_tbl = vclips[[
                        "rank", "title", "category", "start_time", "end_time",
                        "duration", "score", "viral_confidence", "render_path",
                    ]].copy()
                    clip_tbl["render?"] = clip_tbl["render_path"].apply(
                        lambda p: "✅" if p and os.path.exists(p) else "❌"
                    )
                    clip_tbl = clip_tbl.rename(columns={
                        "rank": "#", "title": "Başlık", "category": "Kategori",
                        "start_time": "Başl.", "end_time": "Bitiş", "duration": "Süre",
                        "score": "Skor", "viral_confidence": "Viral", "render?": "Render?",
                    })
                    st.dataframe(clip_tbl, use_container_width=True, hide_index=True)
                else:
                    st.caption("Bu video için henüz klip üretilmemiş.")

                # Heatmap deseni
                vheat = heat_df[heat_df["video_id"] == vid_id]
                if not vheat.empty:
                    h = vheat.iloc[0]
                    st.markdown("**Heatmap Deseni (Ses→Heatmap Korelasyonu)**")
                    st.markdown(
                        f"- 🔊 Spike Korelasyonu: **{h.get('spike_heatmap_corr', 0):.3f}**"
                    )
                    st.markdown(
                        f"- 🤫 Sessizlik Korelasyonu: **{h.get('silence_heatmap_corr', 0):.3f}**"
                    )
                    st.markdown(f"- 📈 Peak Oranı: **{h.get('peak_ratio', 0):.3f}**")
                    meta = h.get("heatmap_meta_json")
                    if meta:
                        try:
                            m = json.loads(meta)
                            if m:
                                st.json(m)
                        except Exception:
                            pass

# ==================================================================
# TAB 3: CLIPLER
# ==================================================================
with tab_clips:
    if clips_df.empty:
        st.info("Veritabanında henüz kayıtlı klip yok.", icon=":material/info:")
    else:
        with st.container(border=True):
            ccol1, ccol2 = st.columns(2)
            with ccol1:
                csearch = st.text_input("Klip Başlığı Ara", placeholder="örn: clutch", key="clip_search")
            with ccol2:
                cat_opts = ["Tümü"] + sorted(clips_df["category"].dropna().unique().tolist())
                cat_filter = st.selectbox("Kategoriye Göre", cat_opts)

        cdf = clips_df.copy()
        if csearch:
            cdf = cdf[cdf["title"].astype(str).str.contains(csearch, case=False, na=False)]
        if cat_filter != "Tümü":
            cdf = cdf[cdf["category"] == cat_filter]

        # Video başlıklarını ekle
        if not videos_df.empty:
            title_map = dict(zip(videos_df["id"], videos_df["title"]))
            uploader_map = dict(zip(videos_df["id"], videos_df["uploader"]))
            cdf["video_title"] = cdf["video_id"].map(title_map).fillna("(bilinmeyen video)")
            cdf["video_uploader"] = cdf["video_id"].map(uploader_map).fillna("?")
        else:
            cdf["video_title"] = "(bilinmeyen video)"
            cdf["video_uploader"] = "?"

        # Render var mı?
        cdf = cdf.merge(data["render_counts"], left_on="id", right_on="clip_id", how="left")
        cdf["render_count"] = cdf["render_count"].fillna(0).astype(int)

        st.caption(f"**{len(cdf)}** klip listeleniyor.")

        overview = cdf[[
            "title", "category", "video_uploader", "video_title", "score",
            "viral_confidence", "duration", "render_count",
        ]].rename(columns={
            "title": "Klip", "category": "Kategori", "video_uploader": "Kanal",
            "video_title": "Kaynak Video", "score": "Skor",
            "viral_confidence": "Viral", "duration": "Süre",
            "render_count": "# Render",
        })
        st.dataframe(overview, use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("### Klip Detayları (Genişletilebilir)")

        try:
            from core.platform_scorer import PlatformScorer
            scorer = PlatformScorer()
            have_scorer = True
        except Exception:
            have_scorer = False

        for _, clip in cdf.iterrows():
            clip_id = clip["id"]
            with st.expander(
                f"✂️ **{clip.get('title', 'Klip')}**  ·  {clip.get('category', '?')}  ·  Skor %{clip.get('score', 0)}",
                expanded=False,
            ):
                col_c1, col_c2 = st.columns([2, 2])
                with col_c1:
                    st.markdown("**Klip Bilgisi**")
                    st.markdown(f"- ID: `{clip_id}`")
                    st.markdown(f"- Kategori: **{clip.get('category', '?')}**")
                    st.markdown(f"- Skor: **%{clip.get('score', 0)}** · Viral: **%{clip.get('viral_confidence', 0)}**")
                    st.markdown(f"- Zaman: **{clip.get('start_time', 0)}s – {clip.get('end_time', 0)}s** (Süre: {clip.get('duration', 0)}sn)")
                    st.markdown(f"- Kaynak Video: {clip.get('video_title', '?')} (`{clip.get('video_id', '')}`)")
                    st.markdown(f"- Kanal: **{clip.get('video_uploader', '?')}**")

                    if clip.get("hook_caption"):
                        st.info(f"**Kanca:** \"{clip['hook_caption']}\"", icon=":material/campaign:")

                with col_c2:
                    st.markdown("**Platform Uygunluğu**")
                    if have_scorer:
                        try:
                            p = scorer.score_clip(dict(clip))
                            st.markdown(
                                f"🎯 Shorts: **%{p['shorts']}** · "
                                f"🎵 TikTok: **%{p['tiktok']}** · "
                                f"📸 Reels: **%{p['reels']}** · "
                                f"🐦 X: **%{p['twitter']}**"
                            )
                        except Exception as e:
                            st.caption(f"Skor hesaplanamadı: {e}")
                    else:
                        st.caption("Platform skorer mevcut değil.")

                    # Render dosyası
                    clip_renders = renders_df[renders_df["clip_id"] == clip_id] if not renders_df.empty else pd.DataFrame()
                    if not clip_renders.empty:
                        last_path = clip_renders.iloc[-1]["file_path"]
                        st.markdown(f"- Render Boyutu: **{clip_renders.iloc[-1].get('file_size', 0)} bayt**")
                        st.markdown(f"- Render Modu: `{clip_renders.iloc[-1].get('render_mode', '?')}`")
                        if os.path.exists(last_path):
                            st.video(last_path)
                            with open(last_path, "rb") as f:
                                st.download_button(
                                    "Klibi İndir (MP4)",
                                    data=f,
                                    file_name=os.path.basename(last_path),
                                    mime="video/mp4",
                                    icon=":material/download:",
                                    key=f"detail_dl_{clip_id}",
                                )
                        else:
                            st.warning("Render dosyası diskte bulunamadı.")
                    elif clip.get("render_path") and os.path.exists(clip["render_path"]):
                        st.video(clip["render_path"])
                    else:
                        st.caption("Bu klip için render dosyası yok.")
