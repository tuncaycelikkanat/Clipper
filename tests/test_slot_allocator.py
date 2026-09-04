"""
tests/test_slot_allocator.py — Tests for SlotAllocator
"""

import datetime
import os
import tempfile

import pytest

from core.database import DatabaseManager
from core.slot_allocator import SlotAllocator


@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    db.init_db()
    yield db
    if os.path.exists(path):
        os.remove(path)


def test_slot_allocator_morning(test_db):
    allocator = SlotAllocator(db=test_db, daily_slots=["11:30", "15:30", "19:00", "22:30"])
    base_utc = datetime.datetime(2026, 8, 23, 6, 0, tzinfo=datetime.timezone.utc)
    cand_utc, iso_str = allocator.compute_next_available_slot(reference_time_utc=base_utc)
    # 11:30 TR = 08:30 UTC
    assert cand_utc == datetime.datetime(2026, 8, 23, 8, 30, tzinfo=datetime.timezone.utc)
    assert iso_str == "2026-08-23T08:30:00Z"


def test_slot_allocator_late_night(test_db):
    allocator = SlotAllocator(db=test_db, daily_slots=["11:30", "15:30", "19:00", "22:30"])
    base_utc = datetime.datetime(2026, 8, 23, 21, 0, tzinfo=datetime.timezone.utc)
    cand_utc, iso_str = allocator.compute_next_available_slot(reference_time_utc=base_utc)
    # Ertesi gün 11:30 TR = 08:30 UTC
    assert cand_utc == datetime.datetime(2026, 8, 24, 8, 30, tzinfo=datetime.timezone.utc)


def test_slot_allocator_gap_refill_and_shuffle(test_db):
    allocator = SlotAllocator(db=test_db)
    test_db.save_video({"id": "v1", "title": "Vid 1"})

    q1 = test_db.add_to_autopilot_queue(
        video_id="v1",
        clip_id="c1",
        channel_url="http://yt.com/1",
        title="Klip 1",
        render_path="",
        thumbnail_path="",
        viral_score=92,
        scheduled_at="2026-08-25T08:30:00Z",
        status="SCHEDULED",
    )
    q2 = test_db.add_to_autopilot_queue(
        video_id="v1",
        clip_id="c2",
        channel_url="http://yt.com/1",
        title="Klip 2",
        render_path="",
        thumbnail_path="",
        viral_score=94,
        scheduled_at="2026-08-25T12:30:00Z",
        status="SCHEDULED",
    )

    # q1 silinince q2 08:30'a kaymalı
    res = allocator.remove_and_refill_gap(q1)
    assert res["success"] is True
    assert res["shifted_count"] == 1

    items = test_db.get_all_active_scheduled_queue()
    assert len(items) == 1
    assert items[0]["id"] == q2
    assert items[0]["scheduled_at"] == "2026-08-25T08:30:00Z"
