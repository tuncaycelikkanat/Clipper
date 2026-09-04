"""
tests/test_comment_miner.py — Unit tests for CommentMiner
"""

import numpy as np
import pytest

from core.comment_miner import CommentMiner


@pytest.fixture
def miner():
    return CommentMiner(cluster_window_sec=10.0)


# ---------------------------------------------------------------------------
# Timestamp extraction tests
# ---------------------------------------------------------------------------


def test_extract_timestamps_empty_text(miner):
    assert miner.extract_timestamps_from_text("") == []
    assert miner.extract_timestamps_from_text(None) == []


def test_extract_timestamps_mm_ss(miner):
    text = "05:32 burası çok komikti ve 12:45 te bittim"
    timestamps = miner.extract_timestamps_from_text(text)
    assert timestamps == [332.0, 765.0]


def test_extract_timestamps_dot_format(miner):
    text = "5.13 koptum ya haha 05.13 de ne oldu öyle 1.05.32 efsane"
    timestamps = miner.extract_timestamps_from_text(text)
    assert 313.0 in timestamps
    assert 3932.0 in timestamps


def test_extract_timestamps_comma_and_space(miner):
    text = "5,13 de koptum ve 12 45 te adam öldü"
    timestamps = miner.extract_timestamps_from_text(text)
    assert 313.0 in timestamps
    assert 765.0 in timestamps


def test_extract_timestamps_turkish_ordinal_and_url(miner):
    text = "5. dakikada ne oldu öyle ve https://youtu.be/xyz?t=313 bakın"
    timestamps = miner.extract_timestamps_from_text(text)
    assert 300.0 in timestamps
    assert 313.0 in timestamps


def test_extract_timestamps_turkish_text(miner):
    text = "5 dk 13 sn burası efsane ve 10dk bakın"
    timestamps = miner.extract_timestamps_from_text(text)
    assert 313.0 in timestamps
    assert 600.0 in timestamps


def test_extract_timestamps_hh_mm_ss(miner):
    text = "1:02:15 efsane vuruş @02:30:00"
    timestamps = miner.extract_timestamps_from_text(text)
    assert timestamps == [3735.0, 9000.0]


def test_extract_timestamps_letter_format(miner):
    text = "5m32s bakın ya da 1h20m10s"
    timestamps = miner.extract_timestamps_from_text(text)
    assert 332.0 in timestamps
    assert 4810.0 in timestamps


def test_extract_timestamps_deduplication(miner):
    text = "05:32 ve yine 5:32"
    timestamps = miner.extract_timestamps_from_text(text)
    assert timestamps == [332.0]


# ---------------------------------------------------------------------------
# Sentiment / Reaction detection tests
# ---------------------------------------------------------------------------


def test_detect_comment_reaction_empty(miner):
    assert miner.detect_comment_reaction("") == "GENERAL"


def test_detect_comment_reaction_funny(miner):
    text = "05:32 koptum hahaha çok komik 😂"
    assert miner.detect_comment_reaction(text) == "FUNNY"


def test_detect_comment_reaction_epic(miner):
    text = "08:14 efsane clutch vuruş 🔥 goat"
    assert miner.detect_comment_reaction(text) == "EPIC"


def test_detect_comment_reaction_jumpscare(miner):
    text = "12:00 altıma yaptım çok korktum jumpscare 😱"
    assert miner.detect_comment_reaction(text) == "JUMPSCARE"


def test_detect_comment_reaction_rage(miner):
    text = "03:45 adam rage geçirdi çıldırdı 🤬"
    assert miner.detect_comment_reaction(text) == "RAGE"


def test_detect_comment_reaction_fail(miner):
    text = "15:20 büyük fail yazık oldu 💀"
    assert miner.detect_comment_reaction(text) == "FAIL"


def test_detect_comment_reaction_wtf(miner):
    text = "01:10 noldu lan ne alaka wtf 🤨"
    assert miner.detect_comment_reaction(text) == "WTF"


def test_detect_comment_reaction_default_highlight(miner):
    text = "04:20 burası çok güzel bir sahneydi"
    assert miner.detect_comment_reaction(text) == "HIGHLIGHT"


# ---------------------------------------------------------------------------
# process_comments tests
# ---------------------------------------------------------------------------


def test_process_comments_empty(miner):
    res = miner.process_comments([], total_duration=100.0)
    assert res["timestamp_clusters"] == []
    assert len(res["comment_signal"]) == 0
    assert res["total_timestamps_found"] == 0


def test_process_comments_no_timestamps(miner):
    comments = [
        {"text": "Harika video eline sağlık", "like_count": 10},
        {"text": "Devamı gelsin lütfen", "like_count": 5},
    ]
    res = miner.process_comments(comments, total_duration=200.0)
    assert res["timestamp_clusters"] == []
    assert res["total_timestamps_found"] == 0


def test_process_comments_clustering_and_density(miner):
    comments = [
        {"text": "01:30 hahaha koptum 😂", "like_count": 20},
        {"text": "@01:34 yarıldım burda", "like_count": 5},
        {"text": "10:00 efsane vuruş 🔥", "like_count": 50},
    ]
    timeline = np.linspace(0, 700, 700)
    res = miner.process_comments(comments, total_duration=700.0, timeline_times=timeline)

    assert res["total_timestamps_found"] == 3
    assert len(res["timestamp_clusters"]) == 2  # 01:30 and 01:34 merge into 1 cluster
    assert len(res["comment_signal"]) == 700
    assert 0.0 <= res["comment_signal"].max() <= 1.0

    # First cluster near 90-94 sec should have dominant reaction FUNNY
    c1 = next(c for c in res["timestamp_clusters"] if abs(c["time"] - 92) <= 5)
    assert c1["dominant_reaction"] == "FUNNY"
    assert c1["count"] == 2
