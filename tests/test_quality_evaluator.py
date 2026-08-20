import os
import json
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from core.quality_evaluator import QualityEvaluator, ClipQualityReport

@pytest.fixture
def mock_clip():
    return {
        "start_time": 10.0,
        "end_time": 40.0,
        "title": "Test Title",
        "category": "ACTION",
        "start_formatted": "00:10",
        "end_formatted": "00:40",
        "hook_caption": "Test hook",
        "reason": "Test reason",
        "text": "Test text"
    }

@pytest.fixture
def mock_arrays():
    times = np.array([5.0, 15.0, 25.0, 35.0, 45.0])
    rms = np.array([0.1, 0.8, 0.9, 0.7, 0.2])
    return times, rms

@pytest.fixture(autouse=True)
def isolate_gemini_tests():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "", "DEEPSEEK_API_KEY": ""}):
        yield


@patch("core.quality_evaluator.genai.Client")
def test_evaluate_clip_success_first_model(mock_client_class, mock_clip, mock_arrays):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "hook_score": 90,
        "entertainment_score": 95,
        "payoff_score": 92,
        "grade": "A+",
        "editor_feedback": "Great clip",
        "viral_tips": "Do this"
    })
    mock_client.models.generate_content.return_value = mock_response

    times, rms = mock_arrays
    
    result = QualityEvaluator.evaluate_clip(
        clip=mock_clip,
        video_title="Test Video",
        times=times,
        rms=rms,
        transcript=[],
        api_key="TEST_KEY"
    )

    assert result["composite_score"] > 0
    assert result["hook_score"] == 90
    assert result["context_score"] == 95
    assert result["payoff_score"] == 92
    assert result["grade"] in ["A+", "A", "B", "C", "D"]
    assert result["editor_feedback"] == "Great clip"
    assert result["viral_tips"] == "Do this"


@patch("core.quality_evaluator.genai.Client")
def test_evaluate_clip_fallback_model(mock_client_class, mock_clip, mock_arrays):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "hook_score": 80,
        "entertainment_score": 85,
        "payoff_score": 82,
        "grade": "A",
        "editor_feedback": "Good clip",
        "viral_tips": "Do that"
    })
    
    # Fail first, succeed second
    mock_client.models.generate_content.side_effect = [
        Exception("First model failed"),
        mock_response
    ]

    times, rms = mock_arrays
    
    result = QualityEvaluator.evaluate_clip(
        clip=mock_clip,
        video_title="Test Video",
        times=times,
        rms=rms,
        transcript=[],
        api_key="TEST_KEY"
    )

    assert result["hook_score"] == 80
    assert mock_client.models.generate_content.call_count == 2


@patch("core.quality_evaluator.genai.Client")
def test_evaluate_clip_all_models_fail(mock_client_class, mock_clip, mock_arrays):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_client.models.generate_content.side_effect = Exception("All models failed")

    times, rms = mock_arrays
    
    result = QualityEvaluator.evaluate_clip(
        clip=mock_clip,
        video_title="Test Video",
        times=times,
        rms=rms,
        transcript=[],
        api_key="TEST_KEY"
    )

    # Should use fallback LLM eval values
    assert result["hook_score"] == 88
    assert result["context_score"] == 90
    assert result["payoff_score"] == 86
    assert result["editor_feedback"] == "Yüksek aksiyon ve güçlü yayıncı tepkisi yakalandı."


def test_evaluate_clip_no_api_key(mock_clip, mock_arrays):
    # Test without providing api_key and no env var
    times, rms = mock_arrays
    with patch.dict(os.environ, clear=True):
        result = QualityEvaluator.evaluate_clip(
            clip=mock_clip,
            video_title="Test Video",
            times=times,
            rms=rms,
            transcript=[]
        )
        # Should fallback
        assert result["hook_score"] == 88


def test_evaluate_clip_durations(mock_clip, mock_arrays):
    # Test tech score branches
    times, rms = mock_arrays
    
    with patch("core.quality_evaluator.genai.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.models.generate_content.side_effect = Exception("Fallback")
        
        # duration = 30 (sweet spot 20-50, tech=95)
        clip1 = dict(mock_clip)
        clip1["start_time"] = 10.0
        clip1["end_time"] = 40.0
        res1 = QualityEvaluator.evaluate_clip(clip1, "Vid", times, rms, [], "KEY")
        assert res1["technical_score"] == 95

        # duration = 55 (15-60, tech=85)
        clip2 = dict(mock_clip)
        clip2["start_time"] = 5.0
        clip2["end_time"] = 60.0
        res2 = QualityEvaluator.evaluate_clip(clip2, "Vid", times, rms, [], "KEY")
        assert res2["technical_score"] == 85

        # duration = 65 (else, tech=70)
        clip3 = dict(mock_clip)
        clip3["start_time"] = 0.0
        clip3["end_time"] = 65.0
        res3 = QualityEvaluator.evaluate_clip(clip3, "Vid", times, rms, [], "KEY")
        assert res3["technical_score"] == 70

def test_evaluate_clip_action_density(mock_clip):
    # Test action density branches
    with patch("core.quality_evaluator.genai.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.models.generate_content.side_effect = Exception("Fallback")
        
        # Action density when clip mask is empty
        clip1 = dict(mock_clip)
        clip1["start_time"] = 100.0
        clip1["end_time"] = 120.0
        
        times = np.array([5.0, 10.0, 15.0])
        rms = np.array([0.1, 0.1, 0.1])
        
        res1 = QualityEvaluator.evaluate_clip(clip1, "Vid", times, rms, [], "KEY")
        assert res1["action_density"] == 80

def test_evaluate_clip_grades(mock_clip, mock_arrays):
    times, rms = mock_arrays
    
    with patch("core.quality_evaluator.genai.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Function to generate response with specific scores
        def generate_response(hook, ent, payoff):
            resp = MagicMock()
            resp.text = json.dumps({
                "hook_score": hook,
                "entertainment_score": ent,
                "payoff_score": payoff,
                "grade": "A+",
                "editor_feedback": "",
                "viral_tips": ""
            })
            return resp

        # Grade A+ (> 85) -> tech_score=95 (dur 30)
        # We need composite >= 85
        mock_client.models.generate_content.return_value = generate_response(100, 100, 100)
        res_aplus = QualityEvaluator.evaluate_clip(mock_clip, "Vid", times, rms, [], "KEY")
        assert res_aplus["grade"] == "A+"

        # Grade A (75-84)
        mock_client.models.generate_content.return_value = generate_response(75, 75, 75)
        res_a = QualityEvaluator.evaluate_clip(mock_clip, "Vid", times, rms, [], "KEY")
        assert res_a["grade"] == "A"

        # Grade B (65-74)
        mock_client.models.generate_content.return_value = generate_response(60, 60, 60)
        res_b = QualityEvaluator.evaluate_clip(mock_clip, "Vid", times, rms, [], "KEY")
        assert res_b["grade"] == "B"

        # Grade C (50-64)
        mock_client.models.generate_content.return_value = generate_response(50, 50, 50)
        res_c = QualityEvaluator.evaluate_clip(mock_clip, "Vid", times, rms, [], "KEY")
        assert res_c["grade"] == "C"

        # Grade D (<50) -> Need very low score. (0,0,0) will give 0+0+0+14.25 = 14
        mock_client.models.generate_content.return_value = generate_response(0, 0, 0)
        res_d = QualityEvaluator.evaluate_clip(mock_clip, "Vid", times, rms, [], "KEY")
        assert res_d["grade"] == "D"
