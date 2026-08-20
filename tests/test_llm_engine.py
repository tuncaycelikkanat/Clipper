import os
import json
import pytest
from unittest.mock import patch, MagicMock

from core.llm_engine import GeminiHighlightEngine, GeminiGamingBatchResult, GeminiBatchClipVerdict


@pytest.fixture
def mock_candidates():
    return [
        {
            "candidate_id": 1,
            "start_formatted": "00:00",
            "end_formatted": "00:15",
            "peak_formatted": "00:05",
            "start_time": 0.0,
            "end_time": 15.0,
            "signals": {"audio": True},
            "fusion_score": 90,
            "transcript_snippet": "Hello world"
        },
        {
            "candidate_id": 2,
            "start_formatted": "00:20",
            "end_formatted": "00:30",
            "peak_formatted": "00:25",
            "start_time": 20.0,
            "end_time": 30.0,
            "signals": {"audio": False},
            "fusion_score": 80,
            "transcript_snippet": "Test clip"
        },
        {
            "candidate_id": 3,
            "start_formatted": "00:40",
            "end_formatted": "00:50",
            "peak_formatted": "00:45",
            "start_time": 40.0,
            "end_time": 50.0,
            "signals": {"audio": True},
            "fusion_score": 75,
            "transcript_snippet": "Snippet 3"
        }
    ]


def test_no_api_key(mock_candidates):
    with patch.dict(os.environ, clear=True):
        with pytest.raises(ValueError, match="Gemini API Key bulunamadı."):
            GeminiHighlightEngine.batch_judge_gaming_candidates(
                candidates=mock_candidates,
                video_title="Test Video",
                total_duration=100
            )


@patch("core.llm_engine.genai.Client")
def test_success_first_model(mock_client_class, mock_candidates):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "selected_clips": [
            {
                "candidate_id": 1,
                "verdict": "KEEP",
                "category": "EPIC_MOMENT",
                "title": "Title 1",
                "hook_caption": "Hook 1",
                "why_viral": "Why 1",
                "viral_confidence": 95,
                "suggested_start": 0.0,
                "suggested_end": 15.0
            }
        ]
    })
    mock_client.models.generate_content.return_value = mock_response

    result = GeminiHighlightEngine.batch_judge_gaming_candidates(
        candidates=mock_candidates,
        video_title="Test Video",
        total_duration=100,
        api_key="TEST_KEY"
    )

    assert len(result) == 1
    assert result[0]["candidate_id"] == 1
    assert result[0]["text"] == "Hello world"
    assert result[0]["duration"] == 15.0
    mock_client.models.generate_content.assert_called_once()


@patch("core.llm_engine.genai.Client")
def test_fallback_models(mock_client_class, mock_candidates):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    # First call fails, second call succeeds
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "selected_clips": [
            {
                "candidate_id": 2,
                "verdict": "KEEP",
                "category": "FAIL/FUNNY",
                "title": "Title 2",
                "hook_caption": "Hook 2",
                "why_viral": "Why 2",
                "viral_confidence": 85,
                "suggested_start": 20.0,
                "suggested_end": 35.0
            }
        ]
    })
    
    mock_client.models.generate_content.side_effect = [
        Exception("Model 1 failed"),
        mock_response
    ]

    result = GeminiHighlightEngine.batch_judge_gaming_candidates(
        candidates=mock_candidates,
        video_title="Test Video",
        total_duration=100,
        api_key="TEST_KEY"
    )

    assert len(result) == 1
    assert result[0]["candidate_id"] == 2
    assert mock_client.models.generate_content.call_count == 2


@patch("core.llm_engine.genai.Client")
def test_all_models_fail(mock_client_class, mock_candidates):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.models.generate_content.side_effect = Exception("All models fail")

    with pytest.raises(RuntimeError, match="Gemini Batch API hatası"):
        GeminiHighlightEngine.batch_judge_gaming_candidates(
            candidates=mock_candidates,
            video_title="Test Video",
            total_duration=100,
            api_key="TEST_KEY"
        )


@patch("core.llm_engine.genai.Client")
def test_all_drop_fallback(mock_client_class, mock_candidates):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    # All clips marked DROP
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "selected_clips": [
            {
                "candidate_id": 1,
                "verdict": "DROP",
                "viral_confidence": 10,
                "suggested_start": 0.0,
                "suggested_end": 25.0
            },
            {
                "candidate_id": 2,
                "verdict": "DROP",
                "viral_confidence": 20,
                "suggested_start": 20.0,
                "suggested_end": 45.0
            }
        ]
    })
    mock_client.models.generate_content.return_value = mock_response

    result = GeminiHighlightEngine.batch_judge_gaming_candidates(
        candidates=mock_candidates,
        video_title="Test Video",
        total_duration=100,
        target_clips=1,
        api_key="TEST_KEY"
    )

    assert len(result) == 1
    # Should select the highest confidence among the drops (which is cand 2 with 20),
    # actually fallback logic just takes verdicts[:target_clips] then sorts by confidence.
    # verdicts[:1] is candidate 1. Then it sorts it (only 1 element). So it should return cand 1.
    assert result[0]["candidate_id"] == 1


@patch("core.llm_engine.genai.Client")
def test_invalid_duration_adjustment(mock_client_class, mock_candidates):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    # Duration < 10 or end < start
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "selected_clips": [
            {
                "candidate_id": 1,
                "verdict": "KEEP",
                "viral_confidence": 99,
                "suggested_start": 50.0,
                "suggested_end": 55.0  # Duration is 5 < 10
            },
            {
                "candidate_id": 3,
                "verdict": "KEEP",
                "viral_confidence": 98,
                "suggested_start": 60.0,
                "suggested_end": 50.0  # End < Start
            }
        ]
    })
    mock_client.models.generate_content.return_value = mock_response

    result = GeminiHighlightEngine.batch_judge_gaming_candidates(
        candidates=mock_candidates,
        video_title="Test Video",
        total_duration=100,
        target_clips=2,
        api_key="TEST_KEY"
    )

    assert len(result) == 2
    # First is candidate 1 (50.0 to 55.0 -> adjusted to 50.0 to min(100, 50+35) = 85.0)
    # wait, they are sorted by start_time at the end.
    # cand 1: start 50.0, end 85.0, duration 35.0
    # cand 3: start 60.0, end 95.0, duration 35.0
    assert result[0]["candidate_id"] == 1
    assert result[0]["start_time"] == 50.0
    assert result[0]["duration"] == 35.0
    
    assert result[1]["candidate_id"] == 3
    assert result[1]["start_time"] == 60.0
    assert result[1]["duration"] == 35.0

@patch("core.llm_engine.genai.Client")
def test_unmatched_candidate(mock_client_class, mock_candidates):
    # Test when candidate_id in LLM response does not match any candidate
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "selected_clips": [
            {
                "candidate_id": 999,
                "verdict": "KEEP",
                "viral_confidence": 99,
                "suggested_start": 10.0,
                "suggested_end": 30.0
            }
        ]
    })
    mock_client.models.generate_content.return_value = mock_response

    result = GeminiHighlightEngine.batch_judge_gaming_candidates(
        candidates=mock_candidates,
        video_title="Test Video",
        total_duration=100,
        api_key="TEST_KEY"
    )

    assert len(result) == 1
    assert result[0]["candidate_id"] == 999
    assert result[0]["text"] == "" # Snippet should be empty
