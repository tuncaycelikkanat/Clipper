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
from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger

from core.database import DatabaseManager
from core.deepseek_engine import DeepSeekEngine
from core.feed import ChannelFeed
from core.notifier import Notifier
from core.pipeline import ClipperPipeline
from core.thumbnail import ThumbnailGenerator
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
                                logger.error(f"Auto-upload failed: {up_err}")
                                error_msg = str(up_err)
                                queue_status = "QUEUED"  # Stokta kalsın

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
