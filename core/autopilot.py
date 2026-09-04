"""
core/autopilot.py — Otonom Kanal Takip, Klip Stoklama & Planlı Otomatik Yayınlama Sistemi
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
from core.notifier import Notifier
from core.pipeline import ClipperPipeline
from core.thumbnail import ThumbnailGenerator
from core.uploader import YouTubeUploader
from core.copywriter import CopywriterEngine
from core.slot_allocator import SlotAllocator


class AutoPilotManager:
    """Otonom kanal takip, klip stoklama ve akıllı zamanlanmış yayın yöneticisi."""

    _worker_scheduler: Optional[Any] = None
    _worker_info: Dict[str, Any] = {
        "running": False,
        "interval_hours": 2.0,
        "last_run": None,
        "next_run": None,
    }

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        daily_slots: Optional[List[str]] = None,
        timezone_offset_hours: int = 3,
        feed: Optional[ChannelFeed] = None,
        uploader: Optional[YouTubeUploader] = None,
        instagram: Optional[InstagramUploader] = None,
        notifier: Optional[Notifier] = None,
        copywriter: Optional[CopywriterEngine] = None,
        slot_allocator: Optional[SlotAllocator] = None,
    ) -> None:
        self.db = db or DatabaseManager()
        self.db.init_db()
        self.feed = feed or ChannelFeed()
        self.uploader = uploader or YouTubeUploader()
        self.instagram = instagram or InstagramUploader()
        self.notifier = notifier or Notifier()
        self.copywriter = copywriter or CopywriterEngine()
        self.slot_allocator = slot_allocator or SlotAllocator(
            db=self.db,
            daily_slots=daily_slots,
            timezone_offset_hours=timezone_offset_hours,
        )
        self.daily_slots = self.slot_allocator.daily_slots
        self.tz_offset = timezone_offset_hours

    # ------------------------------------------------------------------
    # Background Worker Lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def get_background_worker_info(cls) -> Dict[str, Any]:
        return dict(cls._worker_info)

    @classmethod
    def is_background_worker_running(cls) -> bool:
        return cls._worker_info.get("running", False)

    @classmethod
    def start_background_worker(cls, interval_hours: float = 2.0, db: Optional[DatabaseManager] = None) -> bool:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            if cls._worker_scheduler and cls._worker_scheduler.running:
                cls._worker_scheduler.shutdown(wait=False)

            cls._worker_scheduler = BackgroundScheduler(timezone="UTC")
            inst = cls(db=db)

            def job():
                cls._worker_info["last_run"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                inst.run_cycle()
                inst.publish_due_socials()

            def publish_tick():
                try:
                    inst.publish_due_socials()
                except Exception as e:
                    logger.debug("Publish tick error: {}", e)

            cls._worker_scheduler.add_job(
                job,
                "interval",
                hours=interval_hours,
                id="autopilot_cycle_job",
                replace_existing=True,
            )
            cls._worker_scheduler.add_job(
                publish_tick,
                "interval",
                minutes=1,
                id="autopilot_publish_tick",
                replace_existing=True,
            )
            cls._worker_scheduler.start()
            cls._worker_info = {
                "running": True,
                "interval_hours": interval_hours,
                "last_run": None,
                "next_run": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=interval_hours)).isoformat(),
            }
            logger.info("AutoPilot background worker started (interval: {}h).", interval_hours)
            return True
        except Exception as e:
            logger.error("Failed to start AutoPilot background worker: {}", e)
            cls._worker_info["running"] = False
            return False

    @classmethod
    def stop_background_worker(cls) -> bool:
        try:
            if cls._worker_scheduler and cls._worker_scheduler.running:
                cls._worker_scheduler.shutdown(wait=False)
            cls._worker_scheduler = None
            cls._worker_info = {
                "running": False,
                "interval_hours": 2.0,
                "last_run": None,
                "next_run": None,
            }
            logger.info("AutoPilot background worker stopped.")
            return True
        except Exception as e:
            logger.error("Failed to stop AutoPilot background worker: {}", e)
            return False

    # ------------------------------------------------------------------
    # Channel Management Delegates
    # ------------------------------------------------------------------

    def add_channel(
        self,
        url: str,
        name: str,
        min_score: int = 90,
        target_playlist: Optional[str] = None,
        auto_upload: bool = True,
    ) -> str:
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
        return self.db.get_tracked_channels(active_only=active_only)

    def remove_channel(self, channel_id_or_url: str) -> None:
        self.db.remove_tracked_channel(channel_id_or_url)

    # ------------------------------------------------------------------
    # Slot Allocator Delegates
    # ------------------------------------------------------------------

    def compute_next_available_slot(
        self,
        reference_time_utc: Optional[datetime.datetime] = None,
        latest_scheduled_iso: Optional[str] = None,
    ) -> Tuple[datetime.datetime, str]:
        return self.slot_allocator.compute_next_available_slot(reference_time_utc, latest_scheduled_iso)

    def remove_and_refill_gap(self, queue_id: str) -> Dict[str, Any]:
        return self.slot_allocator.remove_and_refill_gap(queue_id)

    def diversified_shuffle(self, selected_dates: List[str]) -> Dict[str, Any]:
        return self.slot_allocator.diversified_shuffle(selected_dates)

    def get_day_slots_grid(self, date_str: str) -> Dict[str, Optional[Dict[str, Any]]]:
        return self.slot_allocator.get_day_slots_grid(date_str)

    def assign_clip_to_date_slot(self, queue_id: str, date_str: str, slot_time: str) -> bool:
        parts = slot_time.strip().split(":")
        h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        target_local_date = datetime.date.fromisoformat(date_str)
        target_local_dt = datetime.datetime.combine(target_local_date, datetime.time(h, m))
        target_utc_dt = target_local_dt - datetime.timedelta(hours=self.tz_offset)
        target_iso = target_utc_dt.replace(tzinfo=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        day_items = self.db.get_day_slot_items(date_str, tz_offset_hours=self.tz_offset)
        occupant = next((item for item in day_items if item.get("slot_time") == slot_time and item["id"] != queue_id), None)

        if occupant:
            source_row = None
            with self.db._connect() as conn:
                source_row = conn.execute("SELECT scheduled_at FROM autopilot_queue WHERE id = ?;", (queue_id,)).fetchone()
            if source_row and source_row["scheduled_at"]:
                return self.db.swap_clip_slots(queue_id, occupant["id"])
            else:
                self.db.unassign_clip_to_pool(occupant["id"])
                return self.db.assign_clip_to_slot(queue_id, target_iso)
        else:
            return self.db.assign_clip_to_slot(queue_id, target_iso)

    def get_calendar_days_data(self, days_ahead: int = 14) -> List[Dict[str, Any]]:
        now_local = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=self.tz_offset)
        today = now_local.date()
        queue = self.db.get_all_active_scheduled_queue()

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
    # Backfill & Channel Operations
    # ------------------------------------------------------------------

    def backfill_processed_videos(self, progress_callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        cb = progress_callback or (lambda msg: None)
        channels = self.get_tracked_channels(active_only=False)
        summary = {"channels": len(channels), "recorded": 0, "errors": []}
        if not channels:
            cb("ℹ️ Takip listesinde kanal bulunamadı.")
            return summary

        for ch in channels:
            ch_url = ch["url"]
            ch_name = ch["name"]
            cb(f"🔄 '{ch_name}' için eski videolar taranıyor…")
            try:
                recent_videos = self.feed.get_channel_videos(ch_url, max_count=30)
                recorded_for_ch = 0
                for v in recent_videos:
                    vid = v["id"]
                    if not self.db.is_channel_video_processed(ch_url, vid):
                        self.db.record_processed_video(ch_url, vid, v.get("title", ""))
                        recorded_for_ch += 1
                summary["recorded"] += recorded_for_ch
                cb(f"   ✓ '{ch_name}': {recorded_for_ch} eski video anchor yapıldı.")
            except Exception as exc:
                logger.error("Backfill error: {}", exc)
                summary["errors"].append(f"{ch_name}: {exc}")

        return summary

    def run_cycle(self, api_key: Optional[str] = None, progress_callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
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
            cb(f"🔍 '{ch_name}' taranıyor…")
            try:
                recent_videos = self.feed.get_channel_videos(ch_url, max_count=30)
                if not recent_videos:
                    self.db.update_tracked_channel_checked(ch_url)
                    continue

                processed_ids = self.db.get_processed_video_ids(ch_url)
                candidate_new = [v for v in recent_videos if v["id"] not in processed_ids]
                new_videos = candidate_new[:5]

                if not new_videos:
                    self.db.update_tracked_channel_checked(ch_url)
                    continue

                summary["new_videos_found"] += len(new_videos)
                for vid in new_videos:
                    vid_url = vid["url"]
                    vid_title = vid.get("title", "Video")
                    if not self.db.video_exists(vid["id"]):
                        self.db.save_video({"id": vid["id"], "url": vid_url, "title": vid_title})
                        self.db.record_processed_video(ch_url, vid["id"], vid_title)
                        cb(f"   📥 [Kuyruğa Eklendi] {vid_title}")
                    else:
                        cb(f"   ⏩ [Zaten Var] {vid_title}")
            except Exception as e:
                logger.error("Channel scan error: {}", e)
                summary["errors"].append(str(e))

        return summary

    def process_pending_videos(
        self,
        api_key: Optional[str] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
        max_videos: int = 5,
        add_subtitles: bool = False,
    ) -> Dict[str, Any]:
        cb = progress_callback or (lambda msg: None)
        cb(f"⚙️ [İşleyici] 'Bekliyor' durumundaki videolar kontrol ediliyor (Limit: {max_videos})...")
        summary = {"processed": 0, "errors": []}

        with self.db._connect() as conn:
            pending_videos = conn.execute(
                "SELECT id, url, title FROM videos WHERE status='pending' LIMIT ?",
                (max_videos,)
            ).fetchall()

        if not pending_videos:
            cb("ℹ️ İşlenecek yeni video yok.")
            return summary

        for p_vid in pending_videos:
            v_id, v_url, v_title = p_vid
            cb(f"🎬 İşleniyor: {v_title}")
            try:
                with self.db._connect() as conn:
                    conn.execute("UPDATE videos SET status='processing' WHERE id=?", (v_id,))
                    conn.commit()

                pipeline = ClipperPipeline(db=self.db)
                results = pipeline.execute(
                    url=v_url,
                    target_clips=3,
                    render_mode="shorts_9x16_black",
                    add_subtitles=add_subtitles,
                    add_hook_card=True,
                    api_key=api_key,
                    progress_callback=cb,
                )

                for clip in results:
                    score = int(clip.get("viral_confidence") or clip.get("score") or 0)
                    if score < 90:
                        continue
                    render_path = clip.get("render_path", "")
                    if not render_path or not os.path.exists(render_path):
                        continue

                    # Copywriting & Metadata
                    meta = self.copywriter.generate_shorts_metadata(
                        clip=clip,
                        video_title=v_title,
                        channel_name="",
                    )
                    clip_title = meta.get("title", clip.get("title", "Highlight"))
                    desc = meta.get("description", f"{clip_title}\n\n🎬 Orijinal: {v_url}")

                    # Thumbnail
                    thumb_path = None
                    try:
                        thumbs = ThumbnailGenerator.batch_generate_thumbnails(
                            clips=[clip],
                            video_path_or_url=render_path,
                            output_dir="outputs/thumbnails",
                        )
                        if thumbs and os.path.exists(thumbs[0]):
                            thumb_path = thumbs[0]
                    except Exception:
                        pass

                    latest_sched = self.db.get_latest_scheduled_time()
                    _, sched_iso = self.compute_next_available_slot(latest_scheduled_iso=latest_sched)

                    self.db.add_to_autopilot_queue(
                        video_id=v_id,
                        clip_id=clip.get("clip_id"),
                        channel_url=v_url,
                        title=clip_title,
                        render_path=render_path,
                        thumbnail_path=thumb_path,
                        viral_score=score,
                        scheduled_at=sched_iso,
                        status="QUEUED",
                        youtube_url=None,
                        description=desc,
                    )

                with self.db._connect() as conn:
                    conn.execute("UPDATE videos SET status='processed' WHERE id=?", (v_id,))
                    conn.commit()
                summary["processed"] += 1
                cb(f"✅ Başarıyla İşlendi: {v_title}")

            except Exception as e:
                logger.error("Processing error for {}: {}", v_title, e)
                summary["errors"].append(str(e))
                with self.db._connect() as conn:
                    conn.execute("UPDATE videos SET status='error' WHERE id=?", (v_id,))
                    conn.commit()

        return summary

    def publish_due_socials(self) -> int:
        """Zamanı gelmiş videoları yayınlar."""
        from core.multi_publisher import MultiPublisher
        multi_pub = MultiPublisher(youtube_uploader=self.uploader, instagram_uploader=self.instagram, notifier=self.notifier)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db._connect() as conn:
            due_items = conn.execute("""
                SELECT id, video_id, clip_id, title, render_path, thumbnail_path, scheduled_at, description
                FROM autopilot_queue 
                WHERE scheduled_at <= ? AND status = 'QUEUED'
                ORDER BY scheduled_at ASC;
            """, (now_iso,)).fetchall()

        if not due_items:
            return 0

        published_count = 0
        for row in due_items:
            q_id, video_id, clip_id, title, render_path, thumb_path, sched_at, desc = row
            if render_path and os.path.exists(render_path):
                try:
                    res = multi_pub.publish_clip(
                        clip={"id": clip_id, "title": title, "score": 95},
                        render_path=render_path,
                        thumbnail_path=thumb_path,
                        platforms=["youtube", "instagram"],
                        video_title=title,
                    )
                    yt_url = res.get("youtube", {}).get("url") if res.get("youtube") else None
                    ig_url = res.get("instagram", {}).get("url") if res.get("instagram") else None
                    self.db.update_autopilot_queue_status(q_id, "PUBLISHED", youtube_url=yt_url)
                    if ig_url:
                        with self.db._connect() as conn:
                            conn.execute("UPDATE autopilot_queue SET instagram_url = ? WHERE id = ?;", (ig_url, q_id))
                            conn.commit()
                    published_count += 1
                except Exception as e:
                    logger.error("Publish error: {}", e)

        return published_count
