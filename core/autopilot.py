"""
core/autopilot.py — Otonom Kanal Takip, Klip Stoklama & Planlı Otomatik Yayınlama Sistemi

Kullanıcının belirlediği YouTube kanallarını düzenli olarak takip eder, yeni video geldiğinde:
1. Videoyu işler (Audio DSP + Multimodal Ranker + Gemini LLM).
2. Yalnızca viral potansiyeli yüksek (Viral Skoru >= 90) olan klipleri stoklar.
3. Klibi otomatik renderlar, kapak resmi ve insansı YouTube Shorts başlık/açıklamasını üretir.
4. Türkiye gaming prime-time saatlerine (13:00, 18:00, 22:00) göre sıradaki boş zaman slotuna
   YouTube API 'publishAt' (zamanlanmış yayın) ile otomatik yükler.
"""

from __future__ import annotations

import datetime
import os
import re
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple


from loguru import logger

from core.feed import ChannelFeed
from core.instagram_uploader import InstagramUploader
from core.cutter import VideoCutter
from core.database import DatabaseManager
from core.deepseek_engine import DeepSeekEngine
from core.notifier import Notifier
from core.pipeline import ClipperPipeline
from core.thumbnail import ThumbnailGenerator
from core.tiktok_uploader import TikTokUploader
from core.uploader import YouTubeUploader


class AutoPilotManager:
    """Otonom kanal takip, klip stoklama ve akıllı zamanlanmış yayın yöneticisi."""

    DEFAULT_DAILY_SLOTS = ["13:00", "18:00", "22:00"]  # Türkiye Saati (UTC+3)

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        daily_slots: Optional[List[str]] = None,
        timezone_offset_hours: int = 3,  # Turkey UTC+3
    ) -> None:
        self.db = db or DatabaseManager()
        self.db.init_db()
        self.daily_slots = daily_slots or list(self.DEFAULT_DAILY_SLOTS)
        self.tz_offset = timezone_offset_hours
        self.feed = ChannelFeed()
        self.uploader = YouTubeUploader()
        self.instagram = InstagramUploader()
        self.tiktok = TikTokUploader()
        self.notifier = Notifier()


    # ------------------------------------------------------------------
    # Channel Management
    # ------------------------------------------------------------------

    def add_channel(
        self,
        url: str,
        name: str,
        min_score: int = 90,
        target_playlist: Optional[str] = None,
        auto_upload: bool = True,
    ) -> str:
        """Kanalı otomatik takip listesine ekler."""
        clean_url = url.strip()
        clean_name = name.strip() or clean_url.split("/")[-1]
        return self.db.add_tracked_channel(
            url=clean_url,
            name=clean_name,
            min_score=min_score,
            target_playlist=target_playlist,
            auto_upload=1 if auto_upload else 0,
        )

    def get_tracked_channels(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Takip edilen kanalları listeler."""
        return self.db.get_tracked_channels(active_only=active_only)

    def remove_channel(self, channel_id_or_url: str) -> None:
        """Kanalı takipten çıkarır."""
        self.db.remove_tracked_channel(channel_id_or_url)

    # ------------------------------------------------------------------
    # Smart Slot Allocator (Akıllı Slot Dağıtıcısı)
    # ------------------------------------------------------------------

    def compute_next_available_slot(
        self,
        reference_time_utc: Optional[datetime.datetime] = None,
        latest_scheduled_iso: Optional[str] = None,
    ) -> Tuple[datetime.datetime, str]:
        """
        Sıradaki en erken boş yayın zamanını hesaplar.

        Args:
            reference_time_utc:   Hesaplama için baz zaman (None ise şu anki UTC)
            latest_scheduled_iso: Kuyrukta daha önce planlanmış en son videonun ISO zamanı

        Returns:
            Tuple of (scheduled_utc_datetime, scheduled_utc_iso_string)
        """
        now_utc = reference_time_utc or datetime.datetime.now(datetime.timezone.utc)
        if now_utc.tzinfo is not None:
            now_utc = now_utc.astimezone(datetime.timezone.utc).replace(tzinfo=None)

        tz_delta = datetime.timedelta(hours=self.tz_offset)

        # Eğer daha önce planlanmış bir slot varsa ve gelecekteyse, onun sonrasına bak
        if latest_scheduled_iso:
            try:
                latest_utc = datetime.datetime.fromisoformat(
                    latest_scheduled_iso.replace("Z", "+00:00")
                ).astimezone(datetime.timezone.utc).replace(tzinfo=None)
                if latest_utc > now_utc:
                    now_utc = latest_utc + datetime.timedelta(minutes=15)
            except Exception as e:
                logger.warning("Could not parse latest_scheduled_iso '{}': {}", latest_scheduled_iso, e)

        # Yerel zamana dönüştür (Türkiye saati)
        local_now = now_utc + tz_delta
        today = local_now.date()

        # Slot saatlerini parse et (örn: 13:00 -> time(13, 0))
        parsed_slots = []
        for s in sorted(self.daily_slots):
            parts = s.strip().split(":")
            h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
            parsed_slots.append(datetime.time(h, m))

        # Bugün için gelecekte kalan slotları kontrol et
        candidate_local: Optional[datetime.datetime] = None
        for slot_time in parsed_slots:
            slot_dt = datetime.datetime.combine(today, slot_time)
            # En az 15 dakika sonrasına planla
            if slot_dt > (local_now + datetime.timedelta(minutes=15)):
                candidate_local = slot_dt
                break

        # Bugün slot kalmadıysa yarından başla
        if not candidate_local:
            days_ahead = 1
            while not candidate_local:
                next_day = today + datetime.timedelta(days=days_ahead)
                for slot_time in parsed_slots:
                    candidate_local = datetime.datetime.combine(next_day, slot_time)
                    break
                days_ahead += 1

        # Yerel zamandan tekrar UTC'ye dönüştür
        candidate_utc_naive = candidate_local - tz_delta
        candidate_utc = candidate_utc_naive.replace(tzinfo=datetime.timezone.utc)
        # YouTube ISO formatı: YYYY-MM-DDTHH:MM:SS.000Z
        iso_str = candidate_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        return candidate_utc, iso_str

    # ------------------------------------------------------------------
    # Gap Refill (Akıllı Boşluk Doldurma)
    # ------------------------------------------------------------------

    def remove_and_refill_gap(self, queue_id: str) -> Dict[str, Any]:
        """
        Kuyruktan bir videoyu siler ve arkasındaki tüm videoları 1 slot öne kaydırarak
        takvimde boşluk kalmasını engeller (Akıllı Boşluk Doldurma).
        """
        active_items = self.db.get_all_active_scheduled_queue()
        target_idx = None
        for i, item in enumerate(active_items):
            if item["id"] == queue_id:
                target_idx = i
                break

        if target_idx is None:
            return {"success": False, "error": "Klip bulunamadı", "shifted_count": 0}

        deleted_item = active_items[target_idx]
        self.db.delete_from_autopilot_queue(queue_id)

        # Sonraki elemanları 1 önceki slot zamanına kaydır
        target_slot_time = deleted_item["scheduled_at"]
        shifted = []
        for i in range(target_idx + 1, len(active_items)):
            curr_item = active_items[i]
            curr_scheduled_time = curr_item["scheduled_at"]
            # DB güncelle
            self.db.update_autopilot_queue_scheduled_time(curr_item["id"], target_slot_time)
            shifted.append({
                "id": curr_item["id"],
                "title": curr_item["title"],
                "new_time": target_slot_time
            })
            # Bir sonraki eleman için hedef zaman bu elemanın eski zamanı olur
            target_slot_time = curr_scheduled_time

        logger.info("Removed queue item '{}' and shifted {} items forward to fill gap.", deleted_item["title"], len(shifted))

        return {
            "success": True,
            "deleted_title": deleted_item["title"],
            "shifted_count": len(shifted),
            "shifted_items": shifted,
        }

    def get_calendar_days_data(self, days_ahead: int = 14) -> List[Dict[str, Any]]:
        """
        Gelecek N gün için tarih bazında planlanmış videoları ve slot durumlarını gruplar.
        """
        now_local = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=self.tz_offset)
        today = now_local.date()

        queue = self.db.get_all_active_scheduled_queue()

        # Parse items by local date
        items_by_date: Dict[str, List[Dict[str, Any]]] = {}
        for item in queue:
            sched = item.get("scheduled_at", "")
            try:
                dt_utc = datetime.datetime.fromisoformat(sched.replace("Z", "+00:00"))
                dt_local = dt_utc + datetime.timedelta(hours=self.tz_offset)
                date_key = dt_local.date().isoformat()
                time_str = dt_local.strftime("%H:%M")
                item_copy = dict(item)
                item_copy["local_time"] = time_str
                item_copy["local_dt"] = dt_local
                items_by_date.setdefault(date_key, []).append(item_copy)
            except Exception:
                continue

        days_data = []
        for d in range(days_ahead):
            current_date = today + datetime.timedelta(days=d)
            date_str = current_date.isoformat()
            day_items = items_by_date.get(date_str, [])

            # Label
            if d == 0:
                day_label = f"Bugün ({current_date.strftime('%d %b')})"
            elif d == 1:
                day_label = f"Yarın ({current_date.strftime('%d %b')})"
            else:
                day_label = current_date.strftime("%d %b %a")

            days_data.append({
                "date": current_date,
                "date_str": date_str,
                "label": day_label,
                "item_count": len(day_items),
                "items": day_items,
            })

        return days_data



    # ------------------------------------------------------------------
    # AutoPilot Cycle Execution
    # ------------------------------------------------------------------

    def run_cycle(
        self,
        api_key: Optional[str] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Tüm aktif kanalları tarar, yeni videoları işler, >= 90 skorlu klipleri
        stoklar ve ileri tarihli olarak YouTube'a planlar.

        Returns:
            Dict with summary metrics.
        """
        cb = progress_callback or (lambda msg: None)
        channels = self.get_tracked_channels(active_only=True)
        cb(f"🤖 [AutoPilot] {len(channels)} aktif kanal taranıyor…")

        summary = {
            "channels_checked": len(channels),
            "new_videos_found": 0,
            "clips_stockpiled": 0,
            "clips_scheduled": 0,
            "errors": [],
        }

        if not channels:
            cb("ℹ️ Takip listesinde aktif kanal bulunamadı.")
            return summary

        for ch in channels:
            ch_url = ch["url"]
            ch_name = ch["name"]
            min_score = ch.get("min_score", 90)
            target_pl = ch.get("target_playlist")
            auto_upload = bool(ch.get("auto_upload", 1))

            cb(f"🔍 '{ch_name}' kanalı taranıyor…")
            try:
                # 1. Kanaldaki son videoları al
                recent_videos = self.feed.get_channel_videos(ch_url, max_count=5)
                # 2. Daha önce işlenmiş videoları filtrele
                new_videos = [v for v in recent_videos if not self.db.video_exists(v["id"])]

                if not new_videos:
                    cb(f"   ✓ '{ch_name}' için yeni video yok.")
                    self.db.update_tracked_channel_checked(ch_url)
                    continue

                summary["new_videos_found"] += len(new_videos)
                cb(f"   ⚡ {len(new_videos)} yeni video bulundu!")

                for vid in new_videos:
                    vid_url = vid["url"]
                    vid_title = vid.get("title", "Video")
                    if not self.db.video_exists(vid["id"]):
                        self.db.save_video({"id": vid["id"], "url": vid_url, "title": vid_title})

                    # Pipeline'ı çalıştır
                    pipeline = ClipperPipeline(db=self.db)

                    results = pipeline.run(
                        url=vid_url,
                        target_clips=3,
                        render_mode="shorts_9x16_black",
                        add_subtitles=True,
                        add_hook_card=True,
                        api_key=api_key,
                        db=self.db,
                    )

                    # Üretilen kliplerden viral skoru >= min_score olanları seç
                    for clip in results:
                        score = int(clip.get("viral_confidence") or clip.get("score") or 0)
                        if score < min_score:
                            logger.info(f"Klip skoru ({score}) eşiğin ({min_score}) altında, elendi.")
                            continue

                        render_path = clip.get("render_path", "")
                        if not render_path or not os.path.exists(render_path):
                            continue

                        summary["clips_stockpiled"] += 1
                        clip_title = clip.get("title", "Gaming Highlight")
                        hook = clip.get("hook_caption", "")
                        category = clip.get("category", "GAMING")

                        # DeepSeek ile insansı başlık ve açıklama üret
                        try:
                            copy_res = DeepSeekEngine.generate_shorts_copy(
                                clip_title=clip_title,
                                hook_caption=hook,
                                category=category,
                                video_title=vid_title,
                            )
                            final_title = copy_res.get("title", f"{clip_title} #Shorts")
                            final_desc = copy_res.get("description", "")
                            final_tags = copy_res.get("tags", ["shorts", "gaming"])
                        except Exception as e:
                            logger.warning(f"DeepSeek copywriting fallback: {e}")
                            final_title = f"{clip_title} #Shorts"
                            final_desc = YouTubeUploader.generate_description(clip, vid_title)
                            final_tags = ["shorts", "gaming", "oyun"]

                        # Thumbnail üret
                        thumb_path = None
                        try:
                            thumbs = ThumbnailGenerator.batch_generate_thumbnails(
                                clips=[clip],
                                video_path_or_url=render_path,
                                output_dir="outputs/thumbnails",
                            )
                            if thumbs and os.path.exists(thumbs[0]):
                                thumb_path = thumbs[0]
                        except Exception as e:
                            logger.warning(f"Thumbnail generation error: {e}")

                        # Sıradaki boş yayın zamanını hesapla
                        latest_sched = self.db.get_latest_scheduled_time()
                        _, sched_iso = self.compute_next_available_slot(
                            latest_scheduled_iso=latest_sched
                        )

                        # YouTube'a Planlı Yükle (Eğer OAuth aktif ve auto_upload açıksa)
                        yt_url = None
                        queue_status = "QUEUED"
                        error_msg = None

                        if auto_upload and self.uploader.is_authenticated():
                            try:
                                cb(f"   📤 YouTube'a zamanlanıyor (@ {sched_iso})…")
                                up_res = self.uploader.upload_short(
                                    video_path=render_path,
                                    title=final_title,
                                    description=final_desc,
                                    tags=final_tags,
                                    thumbnail_path=thumb_path,
                                    playlist_id=target_pl,
                                    publish_at=sched_iso,
                                    language="tr",
                                    location_description="Istanbul, Turkey",
                                )
                                yt_url = up_res.get("url")
                                queue_status = "SCHEDULED"
                                summary["clips_scheduled"] += 1
                                cb(f"   ✅ YouTube Shorts zamanlandı: {yt_url}")
                            except Exception as up_err:
                                logger.error(f"Auto-upload YouTube failed: {up_err}")
                                error_msg = str(up_err)
                                queue_status = "QUEUED"  # Stokta kalsın

                        # Instagram Reels'a Planlı Yükle (Eğer Meta Graph API aktifse)
                        if auto_upload and self.instagram.is_authenticated():
                            try:
                                cb(f"   📸 Instagram Reels (@{self.instagram.account_id}) planlanıyor…")
                                ig_caption = InstagramUploader.generate_caption(
                                    {"title": final_title, "hook_caption": hook},
                                    vid.get("title", "")
                                )
                                # Unix timestamp hesapla
                                sched_dt = datetime.datetime.fromisoformat(sched_iso.replace("Z", "+00:00"))
                                sched_unix = int(sched_dt.timestamp())

                                ig_res = self.instagram.upload_reel(
                                    video_path=render_path,
                                    caption=ig_caption,
                                    share_to_feed=True,
                                    scheduled_publish_time=sched_unix,
                                )
                                cb(f"   ✅ Instagram Reels zamanlandı: {ig_res.get('url')}")
                            except Exception as ig_err:
                                logger.error(f"Auto-upload Instagram failed: {ig_err}")

                        # TikTok'a Yükle (Eğer TikTok API aktifse)
                        if auto_upload and self.tiktok.is_authenticated():
                            try:
                                cb("   🎵 TikTok videosu gönderiliyor…")
                                tt_title = TikTokUploader.generate_caption(
                                    {"title": final_title, "hook_caption": hook},
                                    vid.get("title", "")
                                )
                                tt_res = self.tiktok.upload_video(
                                    video_path=render_path,
                                    title=tt_title,
                                )
                                cb(f"   ✅ TikTok videosu yüklendi! Publish ID: {tt_res.get('publish_id')}")
                            except Exception as tt_err:
                                logger.error(f"Auto-upload TikTok failed: {tt_err}")


                        # Veritabanı kuyruğuna kaydet
                        self.db.add_to_autopilot_queue(
                            video_id=vid["id"],
                            clip_id=clip.get("clip_id"),
                            channel_url=ch_url,
                            title=final_title,
                            render_path=render_path,
                            thumbnail_path=thumb_path,
                            viral_score=score,
                            scheduled_at=sched_iso,
                            status=queue_status,
                            youtube_url=yt_url,
                        )

                        # Discord / Telegram Bildirimi gönder
                        try:
                            self.notifier.notify_clip_ready(
                                clip={
                                    "title": final_title,
                                    "category": category,
                                    "score": score,
                                    "duration_formatted": f"{int(clip.get('duration', 30))} sn",
                                    "hook_caption": hook,
                                    "scheduled_at": sched_iso,
                                },
                                render_path=render_path,
                            )
                        except Exception:
                            pass

                self.db.update_tracked_channel_checked(ch_url)

            except Exception as exc:
                logger.error(f"Error checking channel {ch_name}: {exc}")
                summary["errors"].append(f"{ch_name}: {str(exc)}")

        cb(f"🎉 [AutoPilot Döngüsü Bitti] {summary['clips_stockpiled']} klip stoklandı, {summary['clips_scheduled']} klip zamanlandı.")
        return summary


    def sync_queue_to_socials(
        self,
        progress_callback: Optional[Callable[[str], None]] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        Iterates through all queued/scheduled clips in the database and pushes them to Instagram Reels and TikTok.
        - If scheduled_at is in the future (> 15 mins), schedules it for that exact timestamp on Instagram Reels.
        - If scheduled_at is past or immediate, publishes immediately.
        - Uploads to TikTok.
        """
        cb = progress_callback or (lambda msg: None)
        queue_items = self.db.get_autopilot_queue()
        summary = {"processed": 0, "instagram_success": 0, "tiktok_success": 0, "errors": []}

        if not queue_items:
            cb("Kuyrukta yayınlanacak klip bulunamadı.")
            return summary

        cb(f"🚀 Toplam {len(queue_items)} adet klip Instagram ve TikTok'a senkronlanıyor…")
        cutter = VideoCutter()
        now_utc = datetime.datetime.now(datetime.timezone.utc)

        for idx, item in enumerate(queue_items[:limit], 1):
            title = item.get("title", "Klip")
            render_path = item.get("render_path")
            video_id = item.get("video_id")
            sched_iso = item.get("scheduled_at")
            cb(f"\n[{idx}/{len(queue_items)}] {title}")

            # 1. Video dosyasını doğrula, yoksa kes
            if not render_path or not os.path.exists(render_path):
                cb("   ⏳ Video render dosyası hazırlanıyor…")
                clip_id = item.get("clip_id")
                clip_row = None
                with self.db._connect() as conn:
                    if clip_id:
                        clip_row = conn.execute(
                            "SELECT start_time, end_time, hook_caption, title FROM clips WHERE id=?",
                            (clip_id,)
                        ).fetchone()
                    if not clip_row:
                        clip_row = conn.execute(
                            "SELECT start_time, end_time, hook_caption, title FROM clips WHERE video_id=? ORDER BY score DESC LIMIT 1",
                            (video_id,)
                        ).fetchone()


                if clip_row:
                    s_time, e_time, hook, clip_title = clip_row
                    try:
                        render_path = cutter.cut_clip(
                            url=f"https://www.youtube.com/watch?v={video_id}",
                            start_time=float(s_time),
                            end_time=float(e_time),
                            clip_id=f"sync_{video_id}_{idx}",
                            video_title=clip_title or title,
                            hook_caption=hook or "",
                            render_mode="shorts_9x16_black",
                            add_subtitles=True,
                            add_hook_card=True,
                            enhance_colors=True,
                            use_whisper=True,
                            progress_callback=cb,
                        )
                        item["render_path"] = render_path
                    except Exception as cut_err:
                        logger.error(f"Render failed for {video_id}: {cut_err}")
                        summary["errors"].append(f"{title} render hatası: {cut_err}")
                        continue
                else:
                    cb("   ⚠️ Klip zamanlaması veritabanında bulunamadı, atlanıyor.")
                    continue

            if not render_path or not os.path.exists(render_path):
                continue

            summary["processed"] += 1

            # 2. Zamanlama Hesabı (Meta Graph API: 15 dk - 75 gün)
            sched_unix = None
            if sched_iso:
                try:
                    sched_dt = datetime.datetime.fromisoformat(sched_iso.replace("Z", "+00:00"))
                    diff_sec = (sched_dt - now_utc).total_seconds()
                    if 900 <= diff_sec <= 6480000:
                        sched_unix = int(sched_dt.timestamp())
                except Exception:
                    sched_unix = None

            # 3. Instagram Reels Yükle / Planla
            if self.instagram.is_authenticated():
                try:
                    ig_caption = InstagramUploader.generate_caption(
                        {"title": title, "hook_caption": item.get("hook_caption", "")},
                        video_title=title
                    )
                    if sched_unix:
                        cb(f"   📸 Instagram Reels zamanlanıyor (@ {sched_iso})…")
                    else:
                        cb("   📸 Instagram Reels hemen yayına alınıyor…")

                    ig_res = self.instagram.upload_reel(
                        video_path=render_path,
                        caption=ig_caption,
                        share_to_feed=True,
                        scheduled_publish_time=sched_unix,
                    )
                    summary["instagram_success"] += 1
                    cb(f"   ✅ Instagram Reels başarılı: {ig_res.get('url')}")
                except Exception as ig_err:
                    logger.error(f"Instagram upload error for {title}: {ig_err}")
                    summary["errors"].append(f"Instagram ({title}): {ig_err}")

            # 4. TikTok Yükle
            if self.tiktok.is_authenticated():
                try:
                    cb("   🎵 TikTok videosu yükleniyor…")
                    tt_title = TikTokUploader.generate_caption(
                        {"title": title, "hook_caption": item.get("hook_caption", "")}
                    )
                    tt_res = self.tiktok.upload_video(
                        video_path=render_path,
                        title=tt_title,
                    )
                    summary["tiktok_success"] += 1
                    cb(f"   ✅ TikTok videosu yüklendi! ID: {tt_res.get('publish_id')}")
                except Exception as tt_err:
                    logger.error(f"TikTok upload error for {title}: {tt_err}")
                    summary["errors"].append(f"TikTok ({title}): {tt_err}")

        cb(f"\n🎉 Eşzamanlama tamamlandı! ({summary['instagram_success']} Instagram, {summary['tiktok_success']} TikTok)")
        return summary

    def sync_from_youtube_channel(self, max_results: int = 50) -> int:
        """
        YouTube kanalında daha önce yüklenmiş / planlanmış Shorts videolarını çeker
        ve yayın takvimi veritabanına aktarır.
        """
        if not self.uploader.is_authenticated():
            raise RuntimeError("YouTube kimlik bilgileri eksik veya doğrulanmamış.")

        from googleapiclient.discovery import build
        creds = self.uploader._get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

        ch_res = youtube.channels().list(mine=True, part="contentDetails").execute()
        if not ch_res.get("items"):
            return 0
        uploads_playlist_id = ch_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

        pl_res = youtube.playlistItems().list(
            playlistId=uploads_playlist_id,
            part="snippet,contentDetails",
            maxResults=max_results,
        ).execute()

        video_ids = [item["contentDetails"]["videoId"] for item in pl_res.get("items", [])]
        if not video_ids:
            return 0

        v_res = youtube.videos().list(
            id=",".join(video_ids),
            part="snippet,status,contentDetails"
        ).execute()

        from difflib import SequenceMatcher

        synced_count = 0
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db._connect() as conn:
            # Mevcut gerçek klipleri hafızaya al
            existing_clips = conn.execute(
                "SELECT id, video_id, title, start_time, end_time FROM clips WHERE id NOT LIKE 'clip_%';"
            ).fetchall()

            for v in v_res.get("items", []):
                st = v.get("status", {})
                sn = v.get("snippet", {})
                v_id = v["id"]
                title = sn.get("title", "Shorts")
                pub_at = st.get("publishAt")
                privacy = st.get("privacyStatus")

                # Başlığa göre en uygun orijinal klibi bul
                clean_q = re.sub(r'[^\w\s]', '', title.lower().replace('#shorts', '')).strip()
                matched_clip_id = None
                matched_video_id = v_id
                best_score = 0.0

                for c_id, c_vid, c_title, s, e in existing_clips:
                    clean_c = re.sub(r'[^\w\s]', '', (c_title or "").lower()).strip()
                    ratio = SequenceMatcher(None, clean_q, clean_c).ratio()
                    if ratio > best_score and ratio >= 0.35:
                        best_score = ratio
                        matched_clip_id = c_id
                        matched_video_id = c_vid

                # Eğer eşleşen klip bulunamadıysa varsayılan kayıt oluştur
                if not matched_clip_id:
                    matched_clip_id = f"clip_{v_id}"
                    conn.execute("""
                        INSERT INTO videos (id, url, title, uploader, duration, view_count, status, processed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                        ON CONFLICT(id) DO UPDATE SET title=excluded.title;
                    """, (v_id, f"https://youtube.com/watch?v={v_id}", title, "YouTube Channel", 60, 0, "PROCESSED"))

                    conn.execute("""
                        INSERT INTO clips (id, video_id, rank, title, start_time, end_time, duration, score, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                        ON CONFLICT(id) DO UPDATE SET title=excluded.title;
                    """, (matched_clip_id, v_id, 1, title, 0.0, 59.0, 59.0, 95))

                if pub_at:
                    sched_time = pub_at
                    status = "SCHEDULED"
                elif privacy == "public":
                    sched_time = sn.get("publishedAt", now_iso)
                    status = "PUBLISHED"
                else:
                    sched_time = now_iso
                    status = "QUEUED"

                yt_url = f"https://youtube.com/shorts/{v_id}"
                # Mükerrer kayıt kontrolü
                exists = conn.execute(
                    "SELECT id FROM autopilot_queue WHERE youtube_url=? OR (title=? AND scheduled_at=?);",
                    (yt_url, title, sched_time)
                ).fetchone()

                if exists:
                    continue

                thumb = sn.get("thumbnails", {}).get("high", {}).get("url", "")
                q_id = str(uuid.uuid4())
                conn.execute("""
                    INSERT INTO autopilot_queue 
                    (id, video_id, clip_id, channel_url, title, render_path, thumbnail_path, viral_score, scheduled_at, status, youtube_url, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'));
                """, (
                    q_id, matched_video_id, matched_clip_id, "https://youtube.com", title, "", thumb, 95, sched_time, status, yt_url
                ))
                synced_count += 1


            conn.commit()
        return synced_count




    # ------------------------------------------------------------------
    # 7/24 Arka Plan Nöbetçisi (Background Daemon)
    # ------------------------------------------------------------------

    _worker_scheduler: Optional[Any] = None
    _worker_info: Dict[str, Any] = {
        "running": False,
        "interval_hours": 2.0,
        "last_run": None,
        "next_run": None,
    }

    @classmethod
    def start_background_worker(
        cls,
        interval_hours: float = 2.0,
        api_key: Optional[str] = None,
        db: Optional[DatabaseManager] = None,
    ) -> bool:
        """7/24 arka plan nöbetçisini başlatır. Belirtilen aralıkla kanalları otomatik tarar."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.interval import IntervalTrigger
        except ImportError:
            logger.error("APScheduler bulunamadı.")
            return False

        if cls._worker_scheduler and cls._worker_scheduler.running:
            logger.info("Background AutoPilot worker zaten çalışıyor.")
            return True

        manager = cls(db=db)

        def _cycle_job():
            logger.info("🤖 [AutoPilot Nöbetçi] Otomatik periyodik kontrol başladı…")
            cls._worker_info["last_run"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            try:
                manager.run_cycle(api_key=api_key)
            except Exception as e:
                logger.error("Background AutoPilot cycle error: {}", e)

        scheduler = BackgroundScheduler(job_defaults={"coalesce": True, "max_instances": 1})
        trigger = IntervalTrigger(hours=interval_hours)
        scheduler.add_job(_cycle_job, trigger=trigger, id="autopilot_periodic_check", replace_existing=True)
        scheduler.start()

        cls._worker_scheduler = scheduler
        cls._worker_info["running"] = True
        cls._worker_info["interval_hours"] = interval_hours
        logger.info("Background AutoPilot worker başlatıldı (Aralık: {} saat).", interval_hours)
        return True

    @classmethod
    def stop_background_worker(cls) -> bool:
        """Arka plan nöbetçisini durdurur."""
        if cls._worker_scheduler and cls._worker_scheduler.running:
            cls._worker_scheduler.shutdown(wait=False)
            cls._worker_scheduler = None
            cls._worker_info["running"] = False
            logger.info("Background AutoPilot worker durduruldu.")
            return True
        return False

    @classmethod
    def is_background_worker_running(cls) -> bool:
        """Arka plan nöbetçisinin aktif olup olmadığını döner."""
        return bool(cls._worker_scheduler and cls._worker_scheduler.running)

    @classmethod
    def get_background_worker_info(cls) -> Dict[str, Any]:
        """Nöbetçi durum bilgilerini döner."""
        info = dict(cls._worker_info)
        info["running"] = cls.is_background_worker_running()
        if cls._worker_scheduler and cls._worker_scheduler.running:
            job = cls._worker_scheduler.get_job("autopilot_periodic_check")
            if job and getattr(job, "next_run_time", None):
                info["next_run"] = str(job.next_run_time)
        return info

