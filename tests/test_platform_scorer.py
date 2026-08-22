"""
tests/test_platform_scorer.py — Unit tests for PlatformScorer
"""

import pytest

from core.platform_scorer import PlatformScorer


@pytest.fixture
def scorer():
    return PlatformScorer()


def test_score_clip_structure(scorer):
    clip = {
        "duration": 30.0,
        "category": "GAMING",
        "hook_caption": "Wait for the clutch moment!",
        "score": 85,
        "viral_confidence": 90,
    }
    result = scorer.score_clip(clip)

    assert "tiktok" in result
    assert "shorts" in result
    assert "reels" in result
    assert "twitter" in result
    assert "best_platform" in result
    assert "platform_badges" in result
    assert "recommendation" in result
    assert len(result["platform_badges"]) == 4


def test_score_clip_tiktok_favorable(scorer):
    clip = {
        "duration": 22.0,
        "category": "FUNNY",
        "hook_caption": "Gülmekten öldüm 😂",
        "score": 90,
        "signals": {"audio_spike": 0.9, "silence_burst": 0.8},
    }
    result = scorer.score_clip(clip)
    assert result["tiktok"] >= 80


def test_score_clip_shorts_over_60s_zero(scorer):
    clip = {
        "duration": 65.0,  # Shorts can only be max 60s
        "category": "GAMING",
        "hook_caption": "Long video clip",
        "score": 80,
    }
    result = scorer.score_clip(clip)
    assert result["shorts"] == 0


def test_score_clip_shorts_optimal(scorer):
    clip = {
        "duration": 35.0,
        "category": "CLUTCH",
        "hook_caption": "Son saniye 1v4 clutch!",
        "score": 95,
        "signals": {"heatmap_val": 0.85},
    }
    result = scorer.score_clip(clip)
    assert result["shorts"] >= 85
    assert result["best_platform"] == "YouTube Shorts"


def test_score_clip_twitter_favorable(scorer):
    clip = {
        "duration": 18.0,  # Very short & punchy
        "category": "RAGE",
        "hook_caption": "ÇILDIRDI!",
        "score": 85,
        "signals": {"audio_spike": 0.95},
    }
    result = scorer.score_clip(clip)
    assert result["twitter"] >= 75


def test_score_clip_reels_favorable(scorer):
    clip = {
        "duration": 25.0,
        "category": "EPIC",
        "hook_caption": "İnanılmaz sinematik vuruş",
        "score": 95,
    }
    result = scorer.score_clip(clip)
    assert result["reels"] >= 80


def test_platform_badges_sorting(scorer):
    clip = {
        "duration": 20.0,
        "category": "FAIL",
        "hook_caption": "Büyük fail",
        "score": 75,
    }
    result = scorer.score_clip(clip)
    badges = result["platform_badges"]
    # Check descending order of scores
    scores = [b["score"] for b in badges]
    assert scores == sorted(scores, reverse=True)
