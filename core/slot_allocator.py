"""
core/slot_allocator.py — Bağımsız Yayın Slotu ve Takvim Zamanlayıcı Servis
"""

from __future__ import annotations

import datetime
import random
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger
from core.database import DatabaseManager


class SlotAllocator:
    """Türkiye Prime-Time Gaming slotlarını ve takvim yerleşimini yöneten bağımsız servis."""

    DEFAULT_DAILY_SLOTS = ["11:30", "15:30", "19:00", "22:30"]  # Türkiye Saati (UTC+3)

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        daily_slots: Optional[List[str]] = None,
        timezone_offset_hours: int = 3,
    ) -> None:
        self.db = db or DatabaseManager()
        self.daily_slots = sorted(daily_slots or list(self.DEFAULT_DAILY_SLOTS))
        self.tz_offset = timezone_offset_hours

    def compute_next_available_slot(
        self,
        reference_time_utc: Optional[datetime.datetime] = None,
        latest_scheduled_iso: Optional[str] = None,
    ) -> Tuple[datetime.datetime, str]:
        """Sıradaki en erken boş yayın zamanını hesaplar."""
        now_utc = reference_time_utc or datetime.datetime.now(datetime.timezone.utc)
        if now_utc.tzinfo is not None:
            now_utc = now_utc.astimezone(datetime.timezone.utc).replace(tzinfo=None)

        tz_delta = datetime.timedelta(hours=self.tz_offset)

        if latest_scheduled_iso:
            try:
                latest_utc = datetime.datetime.fromisoformat(
                    latest_scheduled_iso.replace("Z", "+00:00")
                ).astimezone(datetime.timezone.utc).replace(tzinfo=None)
                if latest_utc > now_utc:
                    now_utc = latest_utc + datetime.timedelta(minutes=15)
            except Exception as e:
                logger.warning("Could not parse latest_scheduled_iso '{}': {}", latest_scheduled_iso, e)

        local_now = now_utc + tz_delta
        today = local_now.date()

        parsed_slots = []
        for s in self.daily_slots:
            parts = s.strip().split(":")
            h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
            parsed_slots.append(datetime.time(h, m))

        candidate_local: Optional[datetime.datetime] = None
        for slot_time in parsed_slots:
            slot_dt = datetime.datetime.combine(today, slot_time)
            if slot_dt > (local_now + datetime.timedelta(minutes=15)):
                candidate_local = slot_dt
                break

        if not candidate_local:
            days_ahead = 1
            while not candidate_local:
                next_day = today + datetime.timedelta(days=days_ahead)
                for slot_time in parsed_slots:
                    candidate_local = datetime.datetime.combine(next_day, slot_time)
                    break
                days_ahead += 1

        candidate_utc_naive = candidate_local - tz_delta
        candidate_utc = candidate_utc_naive.replace(tzinfo=datetime.timezone.utc)
        iso_str = candidate_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        return candidate_utc, iso_str

    def remove_and_refill_gap(self, queue_id: str) -> Dict[str, Any]:
        """Kuyruktan bir videoyu siler ve arkasındakileri 1 slot öne kaydırır."""
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

        target_slot_time = deleted_item["scheduled_at"]
        shifted = []
        for i in range(target_idx + 1, len(active_items)):
            curr_item = active_items[i]
            curr_scheduled_time = curr_item["scheduled_at"]
            self.db.update_autopilot_queue_scheduled_time(curr_item["id"], target_slot_time)
            shifted.append({
                "id": curr_item["id"],
                "title": curr_item["title"],
                "new_time": target_slot_time
            })
            target_slot_time = curr_scheduled_time

        logger.info("Removed queue item '{}' and shifted {} items.", deleted_item["title"], len(shifted))
        return {
            "success": True,
            "deleted_title": deleted_item["title"],
            "shifted_count": len(shifted),
            "shifted_items": shifted,
        }

    def diversified_shuffle(self, selected_dates: List[str]) -> Dict[str, Any]:
        """Seçilen günlerdeki klipleri ardışık aynı kanal gelmeyecek şekilde dağıtır."""
        all_items = []
        all_slot_isos = []

        for d_str in sorted(selected_dates):
            grid = self.get_day_slots_grid(d_str)
            target_local_date = datetime.date.fromisoformat(d_str)
            for slot_time, item in grid.items():
                parts = slot_time.strip().split(":")
                h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
                target_local_dt = datetime.datetime.combine(target_local_date, datetime.time(h, m))
                target_utc_dt = target_local_dt - datetime.timedelta(hours=self.tz_offset)
                slot_iso = target_utc_dt.replace(tzinfo=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                if item and item.get("status") == "QUEUED":
                    all_items.append(item)
                    all_slot_isos.append(slot_iso)

        if not all_items:
            return {"shuffled_count": 0, "message": "Karıştırılacak yayınlanmamış klip bulunamadı."}

        channel_buckets = defaultdict(list)
        for item in all_items:
            ch_key = item.get("channel_url") or "Bilinmeyen"
            channel_buckets[ch_key].append(item)

        for ch in channel_buckets:
            random.shuffle(channel_buckets[ch])

        shuffled_items = []
        buckets_list = list(channel_buckets.values())
        random.shuffle(buckets_list)

        while any(buckets_list):
            for bucket in buckets_list:
                if bucket:
                    shuffled_items.append(bucket.pop(0))

        with self.db._connect() as conn:
            for item, target_iso in zip(shuffled_items, all_slot_isos):
                conn.execute(
                    "UPDATE autopilot_queue SET scheduled_at = ?, status = 'QUEUED' WHERE id = ?;",
                    (target_iso, item["id"]),
                )
            conn.commit()

        return {"shuffled_count": len(shuffled_items), "message": f"{len(shuffled_items)} klip akıllıca karıştırıldı!"}

    def get_day_slots_grid(self, date_str: str) -> Dict[str, Optional[Dict[str, Any]]]:
        """Günün slotlarındaki klipleri eşler."""
        day_items = self.db.get_day_slot_items(date_str, tz_offset_hours=self.tz_offset)
        grid = {slot: None for slot in self.daily_slots}
        for item in day_items:
            slot_time = item.get("slot_time")
            if slot_time in grid:
                grid[slot_time] = item
            else:
                for s in grid:
                    if grid[s] is None:
                        grid[s] = item
                        break
        return grid
