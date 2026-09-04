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


@pytest.fixture(autouse=True)
def isolate_gemini_tests():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "", "DEEPSEEK_API_KEY": ""}):
        yield


def test_no_api_key(mock_candidates):
    with patch.dict(os.environ, {"GEMINI_API_KEY": "", "OPENROUTER_API_KEY": "", "DEEPSEEK_API_KEY": ""}, clear=True):
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
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
                "category": "FAIL_FUNNY",
                "title": "Title 2",
                "hook_caption": "Hook 2",
                "why_viral": "Why 2",
                "viral_confidence": 85,
                "suggested_start": 20.0,
                "suggested_end": 30.0
            }
        ]
    })
    
    mock_client.models.generate_content.side_effect = [
        Exception("First model failed"),
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

    with pytest.raises(RuntimeError, match="Batch Analiz hatası"):
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

def test_generate_shorts_metadata_no_api_key():
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=True):
        meta = GeminiHighlightEngine.generate_shorts_metadata(
            clip_title="Clutch Moment",
            hook_caption="Watch this!",
            category="CLUTCH",
            video_title="Main Video"
        )
        assert "Clutch Moment" in meta["title"]
        assert len(meta["tags"]) > 0

@patch("core.llm_engine.genai.Client")
def test_generate_shorts_metadata_success(mock_client_class):
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "", "DEEPSEEK_API_KEY": ""}):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "title": "EN İYİ AN! 🔥 #Shorts",
            "description": "Açıklama #Shorts",
            "tags": ["gaming", "shorts"]
        })
        mock_client.models.generate_content.return_value = mock_response
        
        meta = GeminiHighlightEngine.generate_shorts_metadata(
            clip_title="Clip",
            hook_caption="Hook",
            category="CLUTCH",
            api_key="fake_key"
        )
        assert meta["title"] == "EN İYİ AN! 🔥 #Shorts"
        assert "gaming" in meta["tags"]

@patch("core.deepseek_engine.DeepSeekEngine.generate_shorts_copy")
def test_generate_shorts_metadata_deepseek_delegation(mock_ds_call):
    mock_ds_call.return_value = {
        "title": "DEEPSEEK TITLE #Shorts",
        "description": "Desc",
        "tags": ["tag1"],
        "provider": "DeepSeek V3"
    }
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        meta = GeminiHighlightEngine.generate_shorts_metadata(
            clip_title="Clip",
            hook_caption="Hook",
            category="CLUTCH"
        )
        assert meta["title"] == "DEEPSEEK TITLE #Shorts"


# ---------------------------------------------------------------------------
# V2: Yeni özellikler
# ---------------------------------------------------------------------------

def test_score_to_band():
    """score_to_band() yardımcı fonksiyonu doğru bant etiketlerini döndürmeli."""
    from core.llm_engine import score_to_band
    import core.scoring_config as SC

    if not SC.BAND_LABELS_ENABLED:
        pytest.skip("Bant etiketleme kapalı (BAND_LABELS_ENABLED=False)")

    assert score_to_band(90) == "Yüksek"
    assert score_to_band(75) == "Yüksek"
    assert score_to_band(60) == "Orta-Yüksek"
    assert score_to_band(55) == "Orta-Yüksek"
    assert score_to_band(40) == "Orta"
    assert score_to_band(35) == "Orta"
    assert score_to_band(20) == "Düşük"
    assert score_to_band(0) == "Düşük"


@patch("core.llm_engine.genai.Client")
def test_mundane_category_drops_verdict(mock_client_class, mock_candidates):
    """MUNDANE kategorili adayların verdict DROP'a çevrilmeli ve skor ≤ MUNDANE_SCORE_CAP olmalı."""
    import core.scoring_config as SC

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "selected_clips": [
            {
                "candidate_id": 1,
                "verdict": "KEEP",
                "category": "MUNDANE",
                "title": "Sıradan Anı",
                "hook_caption": "Hook",
                "rationale": "Sıradan bir an, özel bir şey yok.",
                "why_viral": "Neden viral olsun?",
                "viral_confidence": 80,   # Yüksek skor ama MUNDANE
                "suggested_start": 0.0,
                "suggested_end": 15.0,
            },
            {
                "candidate_id": 2,
                "verdict": "KEEP",
                "category": "CLUTCH",
                "title": "Harika An",
                "hook_caption": "Bunu izle!",
                "rationale": "Ses spike'ı + silence burst birlikte.",
                "why_viral": "1v4 clutch",
                "viral_confidence": 75,
                "suggested_start": 20.0,
                "suggested_end": 30.0,
            },
        ]
    })
    mock_client.models.generate_content.return_value = mock_response

    result = GeminiHighlightEngine.batch_judge_gaming_candidates(
        candidates=mock_candidates,
        video_title="Test Video",
        total_duration=100,
        target_clips=2,
        api_key="TEST_KEY",
    )

    # MUNDANE olan candidate_id=1 DROP'a çevrilmeli, bu yüzden sonuç listesinde olmamalı
    # (veya varsa skoru kırpılmış olmalı)
    candidate_ids = [r["candidate_id"] for r in result]
    # CLUTCH olan cand 2 KEEP olarak kalmalı
    assert 2 in candidate_ids

    # Eğer MUNDANE aday sonuçta varsa, skoru MUNDANE_SCORE_CAP'ı aşmamalı
    for r in result:
        if r["candidate_id"] == 1:
            assert r["score"] <= SC.MUNDANE_SCORE_CAP, (
                f"MUNDANE aday skoru cap'ı ({SC.MUNDANE_SCORE_CAP}) aşmamalı, got {r['score']}"
            )


@patch("core.llm_engine.genai.Client")
def test_rationale_field_in_output(mock_client_class, mock_candidates):
    """Çıktı kliplerinde rationale alanı mevcut olmalı."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "selected_clips": [
            {
                "candidate_id": 1,
                "verdict": "KEEP",
                "category": "EPIC_MOMENT",
                "title": "Epic",
                "hook_caption": "Hook",
                "rationale": "Ses spike'ı 0.85 ile doruk noktasında.",
                "why_viral": "Epic moment",
                "viral_confidence": 88,
                "suggested_start": 0.0,
                "suggested_end": 15.0,
            }
        ]
    })
    mock_client.models.generate_content.return_value = mock_response

    result = GeminiHighlightEngine.batch_judge_gaming_candidates(
        candidates=mock_candidates,
        video_title="Test Video",
        total_duration=100,
        api_key="TEST_KEY",
    )

    assert len(result) == 1
    assert "rationale" in result[0], "Çıktı klibinde 'rationale' alanı eksik"
    assert result[0]["rationale"] == "Ses spike'ı 0.85 ile doruk noktasında."
    assert "score_band" in result[0], "Çıktı klibinde 'score_band' alanı eksik"


@patch("core.llm_engine.genai.Client")
def test_ensemble_mode_median(mock_client_class, mock_candidates):
    """ensemble_runs=2 ile iki çalışmanın medyanı alınmalı."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # İlk çalışma: skor 80, ikinci çalışma: skor 60 → medyan 70
    def make_response(score: int):
        r = MagicMock()
        r.text = json.dumps({
            "selected_clips": [
                {
                    "candidate_id": 1,
                    "verdict": "KEEP",
                    "category": "CLUTCH",
                    "title": "Title",
                    "hook_caption": "Hook",
                    "rationale": "Gerekçe",
                    "why_viral": "Why",
                    "viral_confidence": score,
                    "suggested_start": 0.0,
                    "suggested_end": 15.0,
                }
            ]
        })
        return r

    mock_client.models.generate_content.side_effect = [
        make_response(80),
        make_response(60),
    ]

    result = GeminiHighlightEngine.batch_judge_gaming_candidates(
        candidates=mock_candidates,
        video_title="Test Video",
        total_duration=100,
        target_clips=1,
        api_key="TEST_KEY",
        ensemble_runs=2,
    )

    assert len(result) == 1
    # Medyan(80, 60) = 70
    assert result[0]["score"] == 70


@patch("core.llm_engine.genai.Client")
def test_score_consistency_test_returns_stats(mock_client_class, mock_candidates):
    """score_consistency_test() istatistik döndürmeli."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    def make_response(score: int):
        r = MagicMock()
        r.text = json.dumps({
            "selected_clips": [
                {
                    "candidate_id": 1,
                    "verdict": "KEEP",
                    "category": "CLUTCH",
                    "title": "T",
                    "hook_caption": "H",
                    "rationale": "R",
                    "why_viral": "W",
                    "viral_confidence": score,
                    "suggested_start": 0.0,
                    "suggested_end": 15.0,
                }
            ]
        })
        return r

    mock_client.models.generate_content.side_effect = [
        make_response(90),
        make_response(80),
        make_response(85),
    ]

    report = GeminiHighlightEngine.score_consistency_test(
        candidates=mock_candidates[:1],
        video_title="Test Video",
        total_duration=100,
        api_key="TEST_KEY",
        runs=3,
    )

    assert "per_candidate" in report
    assert "summary" in report
    assert 1 in report["per_candidate"]

    stats = report["per_candidate"][1]
    assert stats["range"] == 10  # 90 - 80
    assert stats["mean"] == 85.0
    assert stats["verdict"] == "STABLE"  # range=10 ≤ 15
    assert "recommendation" in report["summary"]
