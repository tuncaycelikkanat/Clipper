"""
core/autopilot.py — Otonom Kanal Takip, Klip Stoklama & Planlı Otomatik Yayınlama Sistemi
"""

from __future__ import annotations

import datetime
import os
import threading
from collections.abc import Callable
from typing import Any

from loguru import logger

from core.copywriter import CopywriterEngine
from core.database import DatabaseManager
from core.feed import ChannelFeed
from core.instagram_uploader import InstagramUploader
from core.notifier import Notifier
from core.pipeline import ClipperPipeline
from core.slot_allocator import SlotAllocator
from core.thumbnail import ThumbnailGenerator
from core.uploader import YouTubeUploader


class AutoPilotManager:
    """Otonom kanal takip, klip stoklama ve akıllı zamanlanmış yayın yöneticisi."""

    _worker_scheduler: Any | None = None
    _lock = threading.Lock()
    _worker_info: dict[str, Any] = {
        "running": False,
        "interval_hours": 2.0,
        "last_run": None,
        "next_run": None,
    }

    def __init__(
        self,
        db: DatabaseManager | None = None,
        daily_slots: list[str] | None = None,
        timezone_offset_hours: int = 3,
        feed: ChannelFeed | None = None,
        uploader: YouTubeUploader | None = None,
        instagram: InstagramUploader | None = None,
        notifier: Notifier | None = None,
        copywriter: CopywriterEngine | None = None,
        slot_allocator: SlotAllocator | None = None,
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
    def get_background_worker_info(cls) -> dict[str, Any]:
        with cls._lock:
            return dict(cls._worker_info)

    get_status = get_background_worker_info

    @classmethod
    def _set_status(cls, **kwargs: Any) -> None:
        with cls._lock:
            cls._worker_info.update(kwargs)

    @classmethod
    def is_background_worker_running(cls) -> bool:
        with cls._lock:
            return bool(cls._worker_info.get("running", False))

    @classmethod
    def start_background_worker(cls, interval_hours: float = 2.0, db: DatabaseManager | None = None) -> bool:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            if cls._worker_scheduler and cls._worker_scheduler.running:
                cls._worker_scheduler.shutdown(wait=False)

            cls._worker_scheduler = BackgroundScheduler(timezone="UTC")
            inst = cls(db=db)

            def job():
                with cls._lock:
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
            with cls._lock:
                cls._worker_info = {
                    "running": True,
                    "interval_hours": interval_hours,
                    "last_run": None,
                    "next_run": (
                        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=interval_hours)
                    ).isoformat(),
                }
            logger.info("AutoPilot background worker started (interval: {}h).", interval_hours)
            return True
        except Exception as e:
            logger.error("Failed to start AutoPilot background worker: {}", e)
            with cls._lock:
                cls._worker_info["running"] = False
            return False

    @classmethod
    def stop_background_worker(cls) -> bool:
        try:
            if cls._worker_scheduler and cls._worker_scheduler.running:
                cls._worker_scheduler.shutdown(wait=False)
            cls._worker_scheduler = None
            with cls._lock:
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
        target_playlist: str | None = None,
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

    def get_tracked_channels(self, active_only: bool = True) -> list[dict[str, Any]]:
        return self.db.get_tracked_channels(active_only=active_only)

    def remove_channel(self, channel_id_or_url: str) -> None:
        self.db.remove_tracked_channel(channel_id_or_url)

    # ------------------------------------------------------------------
    # Slot Allocator Delegates
    # ------------------------------------------------------------------

    def compute_next_available_slot(
        self,
        reference_time_utc: datetime.datetime | None = None,
        latest_scheduled_iso: str | None = None,
    ) -> tuple[datetime.datetime, str]:
        return self.slot_allocator.compute_next_available_slot(reference_time_utc, latest_scheduled_iso)

    def remove_and_refill_gap(self, queue_id: str) -> dict[str, Any]:
        return self.slot_allocator.remove_and_refill_gap(queue_id)

    def diversified_shuffle(self, selected_dates: list[str]) -> dict[str, Any]:
        return self.slot_allocator.diversified_shuffle(selected_dates)

    def get_day_slots_grid(self, date_str: str) -> dict[str, dict[str, Any] | None]:
        return self.slot_allocator.get_day_slots_grid(date_str)

    def assign_clip_to_date_slot(self, queue_id: str, date_str: str, slot_time: str) -> bool:
        parts = slot_time.strip().split(":")
        h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        target_local_date = datetime.date.fromisoformat(date_str)
        target_local_dt = datetime.datetime.combine(target_local_date, datetime.time(h, m))
        target_utc_dt = target_local_dt - datetime.timedelta(hours=self.tz_offset)
        target_iso = target_utc_dt.replace(tzinfo=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        day_items = self.db.get_day_slot_items(date_str, tz_offset_hours=self.tz_offset)
        occupant = next(
            (item for item in day_items if item.get("slot_time") == slot_time and item["id"] != queue_id), None
        )

        if occupant:
            source_row = None
            with self.db._connect() as conn:
                source_row = conn.execute(
                    "SELECT scheduled_at FROM autopilot_queue WHERE id = ?;", (queue_id,)
                ).fetchone()
            if source_row and source_row["scheduled_at"]:
                return self.db.swap_clip_slots(queue_id, occupant["id"])
            else:
                self.db.unassign_clip_to_pool(occupant["id"])
                return self.db.assign_clip_to_slot(queue_id, target_iso)
        else:
            return self.db.assign_clip_to_slot(queue_id, target_iso)

    def get_calendar_days_data(self, days_ahead: int = 14) -> list[dict[str, Any]]:
        now_local = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=self.tz_offset)
        today = now_local.date()
        queue = self.db.get_all_active_scheduled_queue()

        items_by_date: dict[str, list[dict[str, Any]]] = {}
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

            days_data.append(
                {
                    "date": current_date,
                    "date_str": date_str,
                    "label": day_label,
                    "item_count": len(day_items),
                    "items": day_items,
                }
            )
        return days_data

    # ------------------------------------------------------------------
    # Backfill & Channel Operations
    # ------------------------------------------------------------------

    def backfill_processed_videos(self, progress_callback: Callable[[str], None] | None = None) -> dict[str, Any]:
        cb = progress_callback or (lambda msg: None)
        channels = self.get_tracked_channels(active_only=False)
        recorded_total = 0
        backfill_errors: list[str] = []
        if not channels:
            cb("ℹ️ Takip listesinde kanal bulunamadı.")
            return {"channels": 0, "recorded": 0, "errors": []}

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
                recorded_total += recorded_for_ch
                cb(f"   ✓ '{ch_name}': {recorded_for_ch} eski video anchor yapıldı.")
            except Exception as exc:
                logger.error("Backfill error: {}", exc)
                backfill_errors.append(f"{ch_name}: {exc}")

        return {"channels": len(channels), "recorded": recorded_total, "errors": backfill_errors}

    def run_cycle(
        self, api_key: str | None = None, progress_callback: Callable[[str], None] | None = None
    ) -> dict[str, Any]:
        cb = progress_callback or (lambda msg: None)
        channels = self.get_tracked_channels(active_only=True)
        cb(f"🤖 [AutoPilot] {len(channels)} aktif kanal taranıyor…")
        new_videos_found = 0
        cycle_errors: list[str] = []

        if not channels:
            cb("ℹ️ Takip listesinde aktif kanal bulunamadı.")
            return {
                "channels_checked": 0,
                "new_videos_found": 0,
                "clips_stockpiled": 0,
                "clips_scheduled": 0,
                "errors": [],
            }

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

                new_videos_found += len(new_videos)
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
                cycle_errors.append(str(e))

        return {
            "channels_checked": len(channels),
            "new_videos_found": new_videos_found,
            "clips_stockpiled": 0,
            "clips_scheduled": 0,
            "errors": cycle_errors,
        }

    def scan_and_queue_latest_channels(
        self,
        exclude_keywords: list[str] | None = None,
        max_videos_per_channel: int = 1,
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Takip edilen aktif kanalları tarar ve son videoları işleme sırasına ekler."""
        cb = progress_callback or (lambda msg: None)
        if exclude_keywords is None:
            exclude_keywords = []

        channels = self.get_tracked_channels(active_only=True)
        new_videos: list[dict[str, Any]] = []
        skipped_channels: list[str] = []
        scanned_count = 0

        if not channels:
            cb("ℹ️ Takip listesinde aktif kanal bulunamadı.")
            return {
                "scanned_channels": 0,
                "skipped_channels": [],
                "new_videos_found": 0,
                "videos": [],
                "message": "Takip edilen aktif kanal bulunamadı.",
            }

        for ch in channels:
            ch_name = ch.get("name", "")
            ch_url = ch.get("url", "")
            # Belirtilen anahtar kelimeleri hariç tut (varsa)
            if exclude_keywords and any(k.lower() in ch_name.lower() or k.lower() in ch_url.lower() for k in exclude_keywords):
                logger.info("Kanal '{}' ({}) filtre kuralı nedeniyle hariç tutuldu.", ch_name, ch_url)
                skipped_channels.append(ch_name)
                continue

            scanned_count += 1
            cb(f"🔍 '{ch_name}' taranıyor…")
            try:
                recent_videos = self.feed.get_channel_videos(ch_url, max_count=max(5, max_videos_per_channel * 2))
                if not recent_videos:
                    self.db.update_tracked_channel_checked(ch_url)
                    continue

                processed_ids = self.db.get_processed_video_ids(ch_url)
                candidate_new = [
                    v for v in recent_videos if v["id"] not in processed_ids and not self.db.video_exists(v["id"])
                ]
                to_queue = candidate_new[:max_videos_per_channel]

                # Eğer hepsi işlenmiş görünüyorsa ama DB'de yoksa ilk videoyu al
                if not to_queue and recent_videos:
                    latest_v = recent_videos[0]
                    if not self.db.video_exists(latest_v["id"]):
                        to_queue = [latest_v]

                for vid in to_queue:
                    vid_id = vid["id"]
                    vid_url = vid["url"]
                    vid_title = vid.get("title", "Video")
                    uploader = ch_name or vid.get("uploader", "")
                    upload_date = vid.get("upload_date", "")

                    v_data = {
                        "id": vid_id,
                        "url": vid_url,
                        "title": vid_title,
                        "uploader": uploader,
                        "upload_date": upload_date,
                        "duration": vid.get("duration", 0),
                        "view_count": vid.get("view_count", 0),
                        "status": "pending",
                    }
                    self.db.save_video(v_data)
                    self.db.record_processed_video(ch_url, vid_id, vid_title)
                    new_videos.append(v_data)
                    cb(f"   📥 [Sıraya Alındı] {vid_title}")

                self.db.update_tracked_channel_checked(ch_url)
            except Exception as exc:
                logger.error("Kanal tarama hatası ({}): {}", ch_name, exc)

        skipped_info = f" ({', '.join(skipped_channels)} hariç)" if skipped_channels else ""
        return {
            "scanned_channels": scanned_count,
            "skipped_channels": skipped_channels,
            "new_videos_found": len(new_videos),
            "videos": new_videos,
            "message": (
                f"{scanned_count} kanal tarandı{skipped_info}. "
                f"{len(new_videos)} yeni video sıraya eklendi."
            ),
        }

    def process_pending_videos(
        self,
        api_key: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
        max_videos: int = 5,
        add_subtitles: bool = False,
        add_hook_card: bool = False,
    ) -> dict[str, Any]:
        cb = progress_callback or (lambda msg: None)
        cb(f"⚙️ [İşleyici] 'Bekliyor' durumundaki videolar kontrol ediliyor (Limit: {max_videos})...")
        processed_count = 0
        proc_errors: list[str] = []

        with self.db._connect() as conn:
            pending_videos = conn.execute(
                "SELECT id, url, title FROM videos WHERE status='pending' LIMIT ?", (max_videos,)
            ).fetchall()

        if not pending_videos:
            cb("ℹ️ İşlenecek yeni video yok.")
            return {"processed": 0, "errors": []}

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
                    add_hook_card=add_hook_card,
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
                processed_count += 1
                cb(f"✅ Başarıyla İşlendi: {v_title}")

            except Exception as e:
                logger.error("Processing error for {}: {}", v_title, e)
                proc_errors.append(str(e))
                with self.db._connect() as conn:
                    conn.execute("UPDATE videos SET status='error' WHERE id=?", (v_id,))
                    conn.commit()

        return {"processed": processed_count, "errors": proc_errors}

    def _ensure_clip_rendered(self, clip_id: str, video_id: str, current_render_path: str | None) -> str | None:
        """Eğer render dosyası diskte yoksa veritabanındaki bilgilerle anında yeniden render eder."""
        if current_render_path and os.path.exists(current_render_path) and os.path.getsize(current_render_path) > 0:
            return current_render_path

        logger.warning(
            "Render dosyası diskte bulunamadı ({}). Klip {} için otomatik yeniden render başlatılıyor...",
            current_render_path,
            clip_id,
        )
        with self.db._connect() as conn:
            clip_row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
            video_row = conn.execute("SELECT url, title FROM videos WHERE id = ?", (video_id,)).fetchone()

        if not clip_row or not video_row:
            logger.error(
                "Yeniden render için klip veya video bilgisi bulunamadı: clip_id={}, video_id={}",
                clip_id,
                video_id,
            )
            return None

        clip_data = dict(clip_row)
        video_data = dict(video_row)

        from core.cutter import VideoCutter

        cutter = VideoCutter()
        try:
            rendered_file = cutter.cut_clip(
                url=video_data["url"],
                start_time=float(clip_data.get("start_time", 0.0)),
                end_time=float(clip_data.get("end_time", 30.0)),
                clip_id=clip_id,
                video_title=video_data.get("title", "clip"),
                hook_caption=clip_data.get("hook_caption", ""),
                render_mode=clip_data.get("render_mode", "shorts_9x16_blur"),
                add_subtitles=False,
                add_hook_card=False,
                enhance_colors=True,
                use_whisper=False,
            )
            if rendered_file and os.path.exists(rendered_file):
                with self.db._connect() as conn:
                    conn.execute("UPDATE clips SET render_path = ? WHERE id = ?", (rendered_file, clip_id))
                    conn.execute("UPDATE autopilot_queue SET render_path = ? WHERE clip_id = ?", (rendered_file, clip_id))
                    conn.commit()
                logger.success("Klip {} başarıyla yeniden render edildi: {}", clip_id, rendered_file)
                return rendered_file
        except Exception as e:
            logger.error("Otomatik yeniden render hatası (clip_id={}): {}", clip_id, e)

        return None

    def publish_due_socials(self) -> int:
        """Zamanı gelmiş videoları YouTube Shorts ve Instagram Reels platformlarında yayınlar."""
        from core.multi_publisher import MultiPublisher

        multi_pub = MultiPublisher(
            youtube_uploader=self.uploader, instagram_uploader=self.instagram, notifier=self.notifier, db=self.db
        )
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db._connect() as conn:
            due_items = conn.execute(
                """
                SELECT id, video_id, clip_id, title, render_path, thumbnail_path, scheduled_at, description, youtube_url, instagram_url
                FROM autopilot_queue
                WHERE scheduled_at <= ? AND status IN ('QUEUED', 'PARTIAL_FAILED')
                ORDER BY scheduled_at ASC;
            """,
                (now_iso,),
            ).fetchall()

        if not due_items:
            return 0

        published_count = 0
        for row in due_items:
            q_id = row["id"]
            video_id = row["video_id"]
            clip_id = row["clip_id"]
            title = row["title"]
            render_path = row["render_path"]
            thumb_path = row["thumbnail_path"]
            desc = row["description"]
            cur_yt_url = row["youtube_url"]
            cur_ig_url = row["instagram_url"]

            target_platforms: list[str] = []
            if not cur_yt_url:
                target_platforms.append("youtube")
            if not cur_ig_url:
                target_platforms.append("instagram")

            if not target_platforms:
                self.db.update_autopilot_queue_status(q_id, "PUBLISHED")
                continue

            valid_render_path = self._ensure_clip_rendered(clip_id, video_id, render_path)
            if not valid_render_path or not os.path.exists(valid_render_path):
                err_msg = f"Render dosyası diskte bulunamadı ve yeniden oluşturulamadı: {render_path}"
                logger.error("Queue item {} skipped: {}", q_id, err_msg)
                self.db.update_autopilot_queue_status(q_id, "PARTIAL_FAILED", error_msg=err_msg)
                continue

            try:
                logger.info("Publishing queue item {} ({}) to platforms: {}", q_id, title, target_platforms)
                res = multi_pub.publish_clip(
                    clip={"id": clip_id, "video_id": video_id, "title": title, "score": 95},
                    render_path=valid_render_path,
                    thumbnail_path=thumb_path,
                    platforms=target_platforms,
                    video_title=title,
                    description_override=desc,
                )

                new_yt_url = res.get("youtube", {}).get("url") if res.get("youtube", {}).get("status") == "success" else None
                new_ig_url = res.get("instagram", {}).get("url") if res.get("instagram", {}).get("status") == "success" else None

                effective_yt = new_yt_url or cur_yt_url
                effective_ig = new_ig_url or cur_ig_url

                errors: list[str] = []
                if "youtube" in target_platforms and not new_yt_url:
                    yt_err = res.get("youtube", {}).get("error", "YouTube upload failed")
                    errors.append(f"YouTube: {yt_err}")
                if "instagram" in target_platforms and not new_ig_url:
                    ig_err = res.get("instagram", {}).get("error", "Instagram upload failed")
                    errors.append(f"Instagram: {ig_err}")

                if not errors:
                    self.db.update_autopilot_queue_status(
                        q_id,
                        "PUBLISHED",
                        youtube_url=effective_yt,
                        instagram_url=effective_ig,
                        error_msg=None,
                    )
                    published_count += 1
                    logger.success("Queue item {} successfully published to all platforms!", q_id)
                elif effective_yt or effective_ig:
                    err_str = " | ".join(errors)
                    self.db.update_autopilot_queue_status(
                        q_id,
                        "PARTIAL_FAILED",
                        youtube_url=effective_yt,
                        instagram_url=effective_ig,
                        error_msg=err_str,
                    )
                    logger.warning("Queue item {} partially published: {}", q_id, err_str)
                else:
                    err_str = " | ".join(errors)
                    self.db.update_autopilot_queue_status(
                        q_id,
                        "PARTIAL_FAILED",
                        error_msg=err_str,
                    )
                    logger.error("Queue item {} failed on all platforms: {}", q_id, err_str)

            except Exception as e:
                logger.error("Publish execution error for {}: {}", q_id, e)
                self.db.update_autopilot_queue_status(q_id, "PARTIAL_FAILED", error_msg=str(e))

        return published_count
