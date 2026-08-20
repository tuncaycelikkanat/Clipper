import os
import json
import pytest
from unittest.mock import patch, MagicMock

from core.deepseek_engine import DeepSeekEngine


def test_deepseek_is_available():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-12345", "DEEPSEEK_API_KEY": ""}):
        assert DeepSeekEngine.is_available() is True

    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-12345", "OPENROUTER_API_KEY": ""}):
        assert DeepSeekEngine.is_available() is True

    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENROUTER_API_KEY": ""}, clear=True):
        assert DeepSeekEngine.is_available() is False


def test_deepseek_no_api_key():
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENROUTER_API_KEY": ""}, clear=True):
        with pytest.raises(ValueError, match="Neither OPENROUTER_API_KEY nor DEEPSEEK_API_KEY found."):
            DeepSeekEngine.generate_shorts_copy(
                clip_title="Clutch",
                hook_caption="Hook",
                category="CLUTCH",
                video_title="Game"
            )


@patch("core.deepseek_engine.OpenAI")
def test_deepseek_generate_shorts_copy_success(mock_openai_class):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "title": "BEAMNG EFSANE ÖN KALDIRMA! 🔥 #Shorts",
        "description": "Kaza anı #Shorts",
        "tags": ["beamng", "araba kazası"]
    })
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    result = DeepSeekEngine.generate_shorts_copy(
        clip_title="Clutch",
        hook_caption="Hook",
        category="CLUTCH",
        video_title="BeamNG",
        api_key="sk-test"
    )

    assert "BEAMNG" in result["title"]
    assert "beamng" in result["tags"]
    mock_client.chat.completions.create.assert_called_once()


@patch("core.deepseek_engine.OpenAI")
def test_deepseek_generate_shorts_copy_error(mock_openai_class):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("API connection error")

    with pytest.raises(Exception, match="API connection error"):
        DeepSeekEngine.generate_shorts_copy(
            clip_title="Clutch",
            hook_caption="Hook",
            category="CLUTCH",
            video_title="BeamNG",
            api_key="sk-test"
        )
