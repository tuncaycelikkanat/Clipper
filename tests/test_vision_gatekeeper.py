"""
tests/test_vision_gatekeeper.py — Tests for Multimodal Vision Gatekeeper and deterministic rubric.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.vision_gatekeeper import (
    CandidateVisualVerdict,
    VisionGatekeeper,
    compute_deterministic_score,
)


def test_candidate_visual_verdict_schema():
    verdict = CandidateVisualVerdict(
        candidate_id=1,
        hook_visual_punch=True,
        facecam_reaction="strong",
        gameplay_event_detected=True,
        story_complete=True,
        category="CLUTCH",
        visual_summary="1v3 clutch atılan ve oyuncunun çığlık attığı an",
        title_suggestion="1v3 clutch atınca gelen o çığlık",
        hook_caption_suggestion="BURADA NASIL SAĞ ÇIKTI?",
    )
    assert verdict.hook_visual_punch is True
    assert verdict.facecam_reaction == "strong"
    assert verdict.category == "CLUTCH"


def test_compute_deterministic_score_high_quality_passes():
    verdict = CandidateVisualVerdict(
        candidate_id=1,
        hook_visual_punch=True,
        facecam_reaction="strong",
        gameplay_event_detected=True,
        story_complete=True,
        category="FAIL/FUNNY",
        visual_summary="Araba takla atınca yayıncı kahkahalara boğuldu",
        title_suggestion="Araba takla atınca ben",
        hook_caption_suggestion="BÖYLE BİR BUG YOK!",
    )
    score, passed, rationale = compute_deterministic_score(verdict, fusion_score=85)

    assert passed is True
    assert score >= 85
    assert "Araba takla atınca" in rationale
    assert "[Vision:" in rationale


def test_compute_deterministic_score_non_facecam_gameplay_passes():
    # Facecam OLMAYAN oyun videosu (BeamNG, simülasyon vb.)
    verdict = CandidateVisualVerdict(
        candidate_id=1,
        has_facecam=False,
        hook_visual_punch=True,
        facecam_reaction="strong",  # Mikrofondan gelen çığlık/coşku
        gameplay_event_detected=True,  # 150 km/h kaza
        story_complete=True,
        category="FAIL/FUNNY",
        visual_summary="Xiaomi araç Tofaş'a 150 km/h hızla çarparak ikiye böldü",
        title_suggestion="Tofaş ikiye bölündü",
        hook_caption_suggestion="150 KM HIZLA ÇARPTI!",
    )
    score, passed, rationale = compute_deterministic_score(verdict, fusion_score=85)

    assert passed is True
    assert score >= 80
    assert "[Kamerasız Oyun]" in rationale
    assert "SesTepki=" in rationale



def test_compute_deterministic_score_mundane_dropped():
    verdict = CandidateVisualVerdict(
        candidate_id=2,
        hook_visual_punch=False,
        facecam_reaction="none",
        gameplay_event_detected=False,
        story_complete=False,
        category="MUNDANE",
        visual_summary="Yayıncı sessizce envanter düzenliyor",
        title_suggestion="Envanter",
        hook_caption_suggestion="İzle",
    )
    score, passed, rationale = compute_deterministic_score(verdict, fusion_score=90)

    assert passed is False
    assert score <= 30
    assert "ELENDİ" in rationale


def test_compute_deterministic_score_no_event_no_reaction_dropped():
    # Sırf ses patlaması yüzünden yüksek DSP skoru almış ama ekranda hiçbir şey olmayan an
    verdict = CandidateVisualVerdict(
        candidate_id=3,
        hook_visual_punch=False,
        facecam_reaction="none",
        gameplay_event_detected=False,
        story_complete=True,
        category="STORY",
        visual_summary="Yayıncı ekranda düz yürüyor",
        title_suggestion="Düz Yürüyüş",
        hook_caption_suggestion="Yürüyüş",
    )
    score, passed, rationale = compute_deterministic_score(verdict, fusion_score=95)

    assert passed is False
    assert score <= 35
    assert "Ne oyun içi olay ne de yayıncı tepkisi" in rationale


@patch("core.vision_gatekeeper.genai.Client")
def test_evaluate_candidate_multimodal(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.text = """{
        "candidate_id": 1,
        "hook_visual_punch": true,
        "facecam_reaction": "strong",
        "gameplay_event_detected": true,
        "story_complete": true,
        "category": "EPIC_MOMENT",
        "visual_summary": "Efsanevi vuruş",
        "title_suggestion": "Vuruş",
        "hook_caption_suggestion": "İnanılmaz"
    }"""
    mock_client.models.generate_content.return_value = mock_resp

    candidate = {
        "candidate_id": 1,
        "start_time": 10.0,
        "peak_time": 20.0,
        "end_time": 40.0,
        "transcript_snippet": "Vurdum!",
        "fusion_score": 80,
    }
    dummy_frames = [b"frame1", b"frame2", b"frame3"]

    verdict = VisionGatekeeper.evaluate_candidate(
        candidate=candidate,
        frames=dummy_frames,
        video_title="Game Stream",
        api_key="TEST_KEY",
    )

    assert verdict is not None
    assert verdict.candidate_id == 1
    assert verdict.hook_visual_punch is True
    assert verdict.category == "EPIC_MOMENT"


@patch.object(VisionGatekeeper, "extract_candidate_keyframes")
@patch.object(VisionGatekeeper, "evaluate_candidate")
def test_filter_and_evaluate_candidates_zero_clip_policy(mock_eval, mock_extract):
    # İki aday var: biri MUNDANE, diğeri düşük puanlı -> 0 klip çıkmalı
    mock_extract.return_value = [b"dummy_frame"]
    mock_eval.return_value = CandidateVisualVerdict(
        candidate_id=1,
        hook_visual_punch=False,
        facecam_reaction="none",
        gameplay_event_detected=False,
        story_complete=False,
        category="MUNDANE",
        visual_summary="Boş an",
        title_suggestion="",
        hook_caption_suggestion="",
    )

    candidates = [
        {"candidate_id": 1, "start_time": 0, "peak_time": 10, "end_time": 25, "fusion_score": 40}
    ]

    result = VisionGatekeeper.filter_and_evaluate_candidates(
        candidates=candidates,
        video_source="test.mp4",
        video_title="Boring Stream",
        total_duration=100,
        target_clips=3,
        api_key="TEST_KEY",
    )

    assert result == [], "Tüm adaylar elendiğinde tam olarak 0 klip dönmeli"


@patch.object(VisionGatekeeper, "extract_candidate_keyframes")
@patch.object(VisionGatekeeper, "evaluate_candidate")
def test_filter_and_evaluate_candidates_quota_fallback(mock_eval, mock_extract):
    # API kotası bittiğinde veya tüm çağrılar başarısız olduğunda RuntimeError fırlatmalı
    mock_extract.return_value = [b"dummy_frame"]
    mock_eval.return_value = None  # Quota exhausted simulation

    candidates = [
        {"candidate_id": 1, "start_time": 0, "peak_time": 10, "end_time": 25, "fusion_score": 80}
    ]

    with pytest.raises(RuntimeError, match="Gemini Vision API çağrıları yanıt vermedi"):
        VisionGatekeeper.filter_and_evaluate_candidates(
            candidates=candidates,
            video_source="test.mp4",
            video_title="Stream",
            total_duration=100,
            target_clips=3,
            api_key="TEST_KEY",
        )


@patch.object(VisionGatekeeper, "extract_candidate_keyframes")
@patch.object(VisionGatekeeper, "evaluate_candidate")
def test_filter_and_evaluate_candidates_include_rejected(mock_eval, mock_extract):
    # include_rejected=True olduğunda elenen klip de [ELENDİ] başlığıyla dönmeli
    mock_extract.return_value = [b"dummy_frame"]
    mock_eval.return_value = CandidateVisualVerdict(
        candidate_id=1,
        hook_visual_punch=False,
        facecam_reaction="none",
        gameplay_event_detected=False,
        story_complete=False,
        category="MUNDANE",
        visual_summary="Boş an",
        title_suggestion="Sıkıcı An",
        hook_caption_suggestion="",
    )

    candidates = [
        {"candidate_id": 1, "start_time": 0, "peak_time": 10, "end_time": 25, "fusion_score": 40}
    ]

    result = VisionGatekeeper.filter_and_evaluate_candidates(
        candidates=candidates,
        video_source="test.mp4",
        video_title="Boring Stream",
        total_duration=100,
        target_clips=3,
        api_key="TEST_KEY",
        include_rejected=True,
    )

    assert len(result) == 1
    assert result[0]["is_passed"] is False
    assert result[0]["gate_status"] == "REJECTED"
    assert result[0]["title"].startswith("[ELENDİ]")


