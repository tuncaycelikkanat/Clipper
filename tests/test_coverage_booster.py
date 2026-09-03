"""
tests/test_coverage_booster.py — Final edge case coverage booster
"""

import sys
import json
from unittest.mock import MagicMock, patch
import pytest

from core.autopilot import AutoPilotManager
from core.database import DatabaseManager
from core.deepseek_engine import DeepSeekEngine
from core.multi_publisher import MultiPublisher
import core.smart_layout
from core.smart_layout import SmartLayoutEngine


def test_deepseek_batch_judge_candidates_and_quality():
    with patch("core.deepseek_engine.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps({
            "selected_clips": [{"candidate_id": 1, "verdict": "KEEP", "viral_confidence": 95}],
            "grade": "A+", "composite_score": 95, "hook_power": 90, "action_density": 85,
            "punchline_power": 90, "retention_prediction": "high", "summary": "Great clip"
        })
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        res1 = DeepSeekEngine.batch_judge_candidates(
            candidates_summary=[{"candidate_id": 1, "start_formatted": "00:00", "end_formatted": "00:10",
                                 "peak_formatted": "00:05", "start_time": 0, "end_time": 10,
                                 "signals": {}, "fusion_score": 90, "transcript_snippet": "hi"}],
            video_title="Game",
            total_duration=100,
            target_clips=1,
            api_key="sk-test"
        )
        assert "selected_clips" in res1

        res2 = DeepSeekEngine.evaluate_quality(
            clip={"title": "Clutch"},
            video_title="Game",
            dur=15.0,
            api_key="sk-test"
        )
        assert res2["grade"] == "A+"


def test_multi_publisher_original_tags_from_db(tmp_path):
    mock_db = MagicMock()
    mock_db.get_video.return_value = {"tags": '["valorant", "clutch"]'}

    mock_yt = MagicMock()
    mock_yt.is_authenticated.return_value = True
    mock_yt.upload_short.return_value = {"video_id": "yt99", "url": "https://yt.com/99"}

    fake_video = tmp_path / "clip_tag.mp4"
    fake_video.write_bytes(b"data")

    with patch("core.deepseek_engine.DeepSeekEngine.generate_shorts_copy") as mock_copy:
        mock_copy.return_value = {
            "title": "Title #Shorts",
            "description": "Desc",
            "tags": ["valorant", "clutch"]
        }
        pub = MultiPublisher(youtube_uploader=mock_yt, db=mock_db)
        res = pub.publish_clip(
            clip={"title": "Title", "video_id": "v_tag_1"},
            render_path=str(fake_video),
            video_title="Valorant Live",
            platforms=["youtube"]
        )
        assert res["youtube"]["status"] == "success"


def test_smart_layout_cv2_frame_capture():
    engine = SmartLayoutEngine()
    engine.client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"found": false, "corner": "none", "box_1000": {"ymin": 0, "xmin": 0, "ymax": 0, "xmax": 0}}'
    engine.client.models.generate_content.return_value = mock_resp

    mock_cv2 = MagicMock()
    cap_inst = MagicMock()
    cap_inst.read.return_value = (True, MagicMock())
    mock_cv2.VideoCapture.return_value = cap_inst
    mock_cv2.imencode.return_value = (True, MagicMock(tobytes=lambda: b"fake_bytes_1000"))

    with patch.object(core.smart_layout, "_CV2_AVAILABLE", True), \
         patch.object(core.smart_layout, "cv2", mock_cv2, create=True):
        res = engine.detect_facecam("/fake/video.mp4")
        assert res["found"] is False


def test_autopilot_diversified_shuffle_and_refill(tmp_path):
    db_file = tmp_path / "auto_boost.db"
    db = DatabaseManager(db_path=str(db_file))
    db.init_db()
    mgr = AutoPilotManager(db=db)

    db.save_video({"id": "vb1", "title": "B1"})
    qid1 = db.add_to_autopilot_queue("vb1", "cb1", "https://yt.com/@ch", "K1", "", "", 95, "2026-09-02T12:00:00Z")
    qid2 = db.add_to_autopilot_queue("vb1", "cb2", "https://yt.com/@ch", "K2", "", "", 95, "2026-09-02T15:00:00Z")

    res_shuffle = mgr.diversified_shuffle(selected_dates=["2026-09-02"])
    assert "shuffled_count" in res_shuffle

    res_refill = mgr.remove_and_refill_gap(qid1)
    assert res_refill["success"] is True


def test_autopilot_extra_edge_cases(tmp_path):
    db_file = tmp_path / "auto_edge.db"
    db = DatabaseManager(db_path=str(db_file))
    db.init_db()
    mgr = AutoPilotManager(db=db)

    # Empty channels
    res_empty_scan = mgr.run_cycle()
    assert res_empty_scan["channels_checked"] == 0

    res_empty_backfill = mgr.backfill_processed_videos()
    assert res_empty_backfill["channels"] == 0

    res_empty_proc = mgr.process_pending_videos()
    assert res_empty_proc["processed"] == 0


def test_multi_publisher_deepseek_fallback_and_link(tmp_path):
    mock_yt = MagicMock()
    mock_yt.is_authenticated.return_value = True
    mock_yt.upload_short.return_value = {"video_id": "yt_fb", "url": "https://yt.com/fb"}

    fake_video = tmp_path / "clip_fb.mp4"
    fake_video.write_bytes(b"data")

    with patch("core.deepseek_engine.DeepSeekEngine.generate_shorts_copy", side_effect=Exception("API down")):
        pub = MultiPublisher(youtube_uploader=mock_yt)
        res = pub.publish_clip(
            clip={"title": "Fallback Title", "video_id": "v_fb_1"},
            render_path=str(fake_video),
            video_title="Main Stream",
            source_video_id="v_fb_1",
            source_video_url="https://youtube.com/watch?v=v_fb_1",
            platforms=["youtube"]
        )
        assert res["youtube"]["status"] == "success"


def test_autopilot_cycle_with_new_videos(tmp_path):
    db_file = tmp_path / "auto_new.db"
    db = DatabaseManager(db_path=str(db_file))
    db.init_db()
    mgr = AutoPilotManager(db=db)

    mgr.add_channel("https://yt.com/@newgamer", "New Gamer")
    mgr.feed.get_channel_videos = MagicMock(return_value=[
        {"id": "nv1", "url": "https://yt.com/watch?v=nv1", "title": "New Vid 1"},
        {"id": "nv2", "url": "https://yt.com/watch?v=nv2", "title": "New Vid 2"}
    ])

    res = mgr.run_cycle()
    assert res["channels_checked"] == 1
    assert res["new_videos_found"] == 2
