"""
tests/test_channel_dna.py — Unit tests for ChannelDNAManager
"""

import json
from unittest.mock import MagicMock

import pytest

from core.channel_dna import ChannelDNAManager


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_channel.return_value = None
    db.get_channel_clips.return_value = []
    return db


@pytest.fixture
def dna_manager(mock_db):
    return ChannelDNAManager(mock_db)


def test_compute_dna_empty_clips(dna_manager):
    dna = dna_manager.compute_dna_from_clips("TestChannel", [])
    assert dna["channel_name"] == "TestChannel"
    assert dna["dominant_category"] == "GAMING"
    assert dna["avg_clip_duration"] == 30.0
    assert dna["total_clips_analyzed"] == 0
    assert "dna_summary" in dna


def test_compute_dna_with_clips(dna_manager):
    clips = [
        {"category": "FUNNY", "duration": 22.0, "score": 95},
        {"category": "FUNNY", "duration": 26.0, "score": 90},
        {"category": "RAGE", "duration": 30.0, "score": 85},
        {"category": "CLUTCH", "duration": 35.0, "score": 60},
    ]
    dna = dna_manager.compute_dna_from_clips("StreamerX", clips)

    assert dna["channel_name"] == "StreamerX"
    assert dna["dominant_category"] == "FUNNY"
    assert dna["total_clips_analyzed"] == 4
    assert 25.0 <= dna["avg_clip_duration"] <= 30.0
    assert dna["shock_weight"] > 0.40
    assert "FUNNY" in dna["category_distribution"]
    assert "StreamerX" in dna["dna_summary"]


def test_compute_dna_high_shock_weights(dna_manager):
    clips = [
        {"category": "RAGE", "duration": 20.0, "score": 90},
        {"category": "JUMPSCARE", "duration": 15.0, "score": 95},
        {"category": "FUNNY", "duration": 25.0, "score": 88},
    ]
    dna = dna_manager.compute_dna_from_clips("RageKing", clips)
    assert dna["shock_weight"] > 0.60
    assert dna["optimal_fusion_weights"]["audio_spike"] == 0.45
    assert dna["optimal_fusion_weights"]["silence_burst"] == 0.35


def test_get_or_compute_dna_cached_in_db(mock_db):
    cached_dna = {
        "channel_name": "CachedChannel",
        "dominant_category": "EPIC",
        "avg_clip_duration": 40.0,
        "total_clips_analyzed": 10,
        "shock_weight": 0.50,
        "category_distribution": {"EPIC": 0.8},
        "optimal_fusion_weights": {"audio_spike": 0.4, "silence_burst": 0.3, "heatmap": 0.3},
        "dna_summary": "Epic player",
    }
    mock_db.get_channel.return_value = {"dna_json": json.dumps(cached_dna)}

    mgr = ChannelDNAManager(mock_db)
    dna = mgr.get_or_compute_dna("CachedChannel")

    assert dna["dominant_category"] == "EPIC"
    assert dna["avg_clip_duration"] == 40.0
    mock_db.get_channel_clips.assert_not_called()


def test_get_or_compute_dna_computes_and_saves(mock_db):
    mock_db.get_channel.return_value = None
    mock_db.get_channel_clips.return_value = [{"category": "CLUTCH", "duration": 28.0, "score": 92}]

    mgr = ChannelDNAManager(mock_db)
    dna = mgr.get_or_compute_dna("ClutchMaster")

    assert dna["dominant_category"] == "CLUTCH"
    assert dna["avg_clip_duration"] == 28.0
    mock_db.save_channel.assert_called_once()


def test_get_or_compute_dna_no_db():
    mgr = ChannelDNAManager(None)
    dna = mgr.get_or_compute_dna("NoDBChannel")
    assert dna["channel_name"] == "NoDBChannel"
    assert dna["dominant_category"] == "GAMING"


def test_format_prompt_context(dna_manager):
    dna = {
        "dna_summary": "Test summary",
        "dominant_category": "FUNNY",
        "avg_clip_duration": 25.0,
    }
    text = dna_manager.format_prompt_context(dna)
    assert "[KANAL PARMAK İZİ / CHANNEL DNA]" in text
    assert "FUNNY" in text
    assert "25.0" in text or "25" in text


def test_format_prompt_context_empty(dna_manager):
    assert dna_manager.format_prompt_context({}) == ""
